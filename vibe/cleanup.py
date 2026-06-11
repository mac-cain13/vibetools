"""Worktree cleanup operations."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from vibe.config import LOCAL_WORKTREE_BASE, VIBEBOARD_DIR
from vibe.git_ops import (
    get_git_common_dir,
    get_repo_info,
    get_worktree_list,
    has_uncommitted_changes,
    validate_git_repo,
    worktree_dirname_to_branch,
    worktree_path_for_branch,
)
from rich.markup import escape

from vibe.config import JUNK_FILES
from vibe.tickets import (
    find_ticket_by_repo_branch,
    list_resumed_tickets,
    update_ticket_fields,
)
from vibe.utils import console, is_directory_empty, is_junk_file


def prune_resumed_archive(
    store_dir: Path = VIBEBOARD_DIR,
    worktree_base: Path = LOCAL_WORKTREE_BASE,
) -> int:
    """Remove `.resumed/` archive entries whose worktree no longer exists.

    A soft-deleted (resumed) ticket is recoverable only while its work is
    still around; once the worktree is gone (the work was finished and the
    worktree cleaned up), the archived ticket is stale and is pruned.

    Args:
        store_dir: Ticket store directory
        worktree_base: Base directory for worktrees

    Returns:
        The number of archived tickets pruned.
    """
    pruned = 0
    for ticket in list_resumed_tickets(store_dir):
        branch = ticket.branch
        if branch is None:
            continue
        worktree_path = worktree_path_for_branch(ticket.repo, branch, worktree_base)
        if not worktree_path.exists():
            try:
                ticket.path.unlink(missing_ok=True)
                pruned += 1
            except OSError:
                pass
    return pruned


@dataclass
class CleanupStats:
    """Statistics from a cleanup operation."""

    cleaned: int = 0
    skipped: int = 0
    lingering: int = 0
    failed: int = 0


class RemoveResult:
    """Result of removing a worktree."""

    REMOVED = 0  # Successfully removed
    FAILED = 1  # Failed to remove
    REMOVED_WITH_PARENT = 2  # Removed and also cleaned empty parent


def remove_worktree(
    worktree_path: Path,
    repo_root: Path,
) -> int:
    """Remove a worktree and optionally clean empty parent directories.

    Args:
        worktree_path: Path to the worktree to remove
        repo_root: Path to the main repository root

    Returns:
        RemoveResult constant indicating outcome
    """
    if not repo_root.is_dir():
        return RemoveResult.FAILED

    # Remove the worktree using git
    result = subprocess.run(
        ["git", "worktree", "remove", str(worktree_path)],
        capture_output=True,
        cwd=repo_root,
    )

    if result.returncode != 0:
        return RemoveResult.FAILED

    # Check if parent directory is now empty
    parent_dir = worktree_path.parent
    if is_directory_empty(parent_dir):
        # Remove any junk files before rmdir
        for junk in JUNK_FILES:
            junk_path = parent_dir / junk
            if junk_path.exists():
                junk_path.unlink()

        # Try to remove the empty directory
        try:
            parent_dir.rmdir()
            return RemoveResult.REMOVED_WITH_PARENT
        except OSError:
            pass

    return RemoveResult.REMOVED


def cleanup_lingering_directory(directory: Path) -> bool:
    """Clean up a lingering directory that isn't a valid worktree.

    Args:
        directory: Path to the directory to clean

    Returns:
        True if successfully cleaned, False otherwise
    """
    dir_name = directory.name

    if is_directory_empty(directory):
        # Remove any junk files before rmdir
        for junk in JUNK_FILES:
            junk_path = directory / junk
            if junk_path.exists():
                junk_path.unlink()

        try:
            directory.rmdir()
            console.print(f"  [green]●[/] {dir_name} — cleaned (empty)")
            return True
        except OSError:
            return False
    else:
        # Directory has files but isn't a valid worktree - remove it
        try:
            import shutil

            shutil.rmtree(directory)
            console.print(f"  [green]●[/] {dir_name} — cleaned (lingering)")
            return True
        except OSError:
            console.print(f"  [red]✗[/] {dir_name} — failed (lingering)")
            return False


def post_session_cleanup(
    repo_name: str,
    branch: str,
    repo_root: Path,
    worktree_base: Path = LOCAL_WORKTREE_BASE,
    store_dir: Path = VIBEBOARD_DIR,
) -> None:
    """Remove a session's worktree after exit when its ticket was parked.

    Re-reads the ticket fresh (matched by repo + branch) and removes the
    worktree only when the ticket's state is 'on_hold' and the worktree is
    clean. Never uses --force: a dirty worktree is skipped loudly. A
    successful removal clears the ticket's worktree field. Silent no-op
    when no ticket matches the repo + branch pair.

    Args:
        repo_name: Name of the repository
        branch: Real branch name of the session's worktree
        repo_root: Path to the main repository root
        worktree_base: Base directory for worktrees
        store_dir: Vibe Board ticket store directory
    """
    ticket = find_ticket_by_repo_branch(repo_name, branch, store_dir)
    if ticket is None or ticket.state != "on_hold":
        return

    worktree_path = worktree_path_for_branch(repo_name, branch, worktree_base)
    if not worktree_path.is_dir():
        return

    if has_uncommitted_changes(worktree_path):
        console.print(
            f"[yellow]Warning:[/] Ticket '{escape(ticket.id)}' is on hold "
            f"but worktree '{branch}' has uncommitted changes — leaving it "
            "in place. Park again or clean it up manually."
        )
        return

    remove_status = remove_worktree(worktree_path, repo_root)
    if remove_status in (RemoveResult.REMOVED, RemoveResult.REMOVED_WITH_PARENT):
        console.print(
            f"Removed parked worktree for ticket '{escape(ticket.id)}' "
            f"({branch})"
        )
        update_ticket_fields(ticket.path, {"worktree": None})
    else:
        console.print(
            f"[yellow]Warning:[/] Failed to remove worktree '{branch}' "
            f"for on-hold ticket '{escape(ticket.id)}'"
        )


def clean_all_worktrees(
    worktree_base: Path = LOCAL_WORKTREE_BASE,
    store_dir: Path = VIBEBOARD_DIR,
) -> CleanupStats:
    """Clean all worktrees across all repositories.

    Worktrees with uncommitted changes are skipped (never `--force`); when a
    removed worktree has a matching parked ticket, that ticket's worktree
    field is cleared.

    Args:
        worktree_base: Base directory containing worktrees
        store_dir: Vibe Board ticket store directory

    Returns:
        CleanupStats with counts of cleaned, skipped, etc.
    """
    console.print(f"Cleaning worktrees in {worktree_base}")
    console.print()

    if not worktree_base.is_dir():
        console.print("No worktree base directory found")
        return CleanupStats()

    stats = CleanupStats()

    # Iterate through all repository directories
    for repo_dir in sorted(worktree_base.iterdir()):
        if not repo_dir.is_dir():
            continue

        repo_name = repo_dir.name
        repo_has_output = False

        # Track which directories are valid worktrees
        valid_worktree_paths: set[Path] = set()
        original_repo: Path | None = None

        # Look for any worktree in this repo directory to find the original repo
        for worktree_dir in repo_dir.iterdir():
            if not worktree_dir.is_dir():
                continue

            # Check if it's a git worktree (has .git file or directory)
            git_marker = worktree_dir / ".git"
            if git_marker.exists():
                common_dir = get_git_common_dir(worktree_dir)
                if common_dir:
                    # The common dir points to the main repo's .git directory
                    original_repo = common_dir.parent
                    break

        # If we found an original repo, process valid worktrees first
        if original_repo:
            worktree_list = get_worktree_list(cwd=original_repo)

            for worktree_path in worktree_list:
                # Check if this worktree is in our managed directory
                try:
                    worktree_path.relative_to(worktree_base / repo_name)
                except ValueError:
                    continue  # Not in our managed directory

                valid_worktree_paths.add(worktree_path)
                # Display the decoded branch name, not the encoded dirname
                worktree_name = worktree_dirname_to_branch(worktree_path.name)
                ticket = find_ticket_by_repo_branch(
                    repo_name, worktree_name, store_dir
                )

                # Print repo header only when we find the first item
                if not repo_has_output:
                    console.print(f"[bold]{repo_name}[/]")
                    repo_has_output = True

                if has_uncommitted_changes(worktree_path):
                    console.print(f"  [yellow]○[/] {worktree_name} — skipped (uncommitted changes)")
                    stats.skipped += 1
                else:
                    remove_status = remove_worktree(worktree_path, original_repo)
                    if remove_status == RemoveResult.REMOVED:
                        console.print(f"  [green]●[/] {worktree_name} — cleaned")
                        stats.cleaned += 1
                    elif remove_status == RemoveResult.REMOVED_WITH_PARENT:
                        console.print(f"  [green]●[/] {worktree_name} — cleaned + parent")
                        stats.cleaned += 1
                    else:
                        console.print(f"  [red]✗[/] {worktree_name} — failed")
                        stats.failed += 1
                    if (
                        remove_status != RemoveResult.FAILED
                        and ticket is not None
                    ):
                        update_ticket_fields(ticket.path, {"worktree": None})

        # Now clean up any lingering directories that aren't valid worktrees
        # Check if repo_dir still exists (might have been removed with last worktree)
        if not repo_dir.exists():
            continue

        for subdir in sorted(repo_dir.iterdir()):
            if not subdir.is_dir():
                continue

            # Skip if this was a valid worktree (already processed above)
            if subdir in valid_worktree_paths:
                continue

            # This is a lingering directory - print header if needed
            if not repo_has_output:
                console.print(f"[bold]{repo_name}[/]")
                repo_has_output = True

            if cleanup_lingering_directory(subdir):
                stats.lingering += 1

        # After processing all subdirectories, check if repo_dir itself is now empty
        if is_directory_empty(repo_dir):
            for junk in JUNK_FILES:
                junk_path = repo_dir / junk
                if junk_path.exists():
                    junk_path.unlink()
            try:
                repo_dir.rmdir()
                if repo_has_output:
                    console.print("  [dim](removed empty directory)[/]")
            except OSError:
                pass

    # Drop archived (resumed) tickets whose worktree is now gone.
    prune_resumed_archive(store_dir=store_dir, worktree_base=worktree_base)

    console.print()
    summary_parts = []
    if stats.cleaned > 0:
        summary_parts.append(f"[green]{stats.cleaned} cleaned[/]")
    if stats.skipped > 0:
        summary_parts.append(f"[yellow]{stats.skipped} skipped[/]")
    if stats.failed > 0:
        summary_parts.append(f"[red]{stats.failed} failed[/]")
    if stats.lingering > 0:
        summary_parts.append(f"{stats.lingering} lingering")

    if summary_parts:
        console.print("Summary: " + " · ".join(summary_parts))
    else:
        console.print("[dim]Nothing to clean[/]")

    return stats


def clean_specific_worktree(
    worktree_name: str,
    repo_name: str,
    repo_root: Path,
    worktree_base: Path = LOCAL_WORKTREE_BASE,
    store_dir: Path = VIBEBOARD_DIR,
) -> bool:
    """Clean a specific worktree.

    Worktrees with uncommitted changes are skipped (never `--force`). On
    success, a matching parked ticket's worktree field is cleared.

    Args:
        worktree_name: Branch name of the worktree to clean (the on-disk
            directory name is the encoded form)
        repo_name: Name of the repository
        repo_root: Path to the repository root
        worktree_base: Base directory for worktrees
        store_dir: Vibe Board ticket store directory

    Returns:
        True if successfully cleaned, False otherwise
    """
    worktree_path = worktree_path_for_branch(repo_name, worktree_name, worktree_base)

    console.print(f"Cleaning worktree: [bold]{worktree_name}[/]")
    console.print()

    # Check if worktree exists
    if not worktree_path.is_dir():
        console.print(f"[red]✗[/] Worktree '{worktree_name}' does not exist")
        return False

    # Check if it's a valid worktree
    worktree_list = get_worktree_list(cwd=repo_root)
    if worktree_path not in worktree_list:
        console.print(f"[red]✗[/] '{worktree_name}' is not a valid git worktree")
        return False

    # Check for uncommitted changes
    if has_uncommitted_changes(worktree_path):
        console.print(f"[yellow]○[/] {worktree_name} — skipped (uncommitted changes)")
        console.print("  Please commit or stash changes first")
        return False

    # Look up the matching parked ticket so its worktree field can be cleared.
    ticket = find_ticket_by_repo_branch(repo_name, worktree_name, store_dir)

    # Remove the worktree
    remove_status = remove_worktree(worktree_path, repo_root)

    if remove_status == RemoveResult.FAILED:
        console.print(f"[red]✗[/] {worktree_name} — failed")
        return False

    if remove_status == RemoveResult.REMOVED_WITH_PARENT:
        console.print(f"[green]●[/] {worktree_name} — cleaned + parent")
    else:
        console.print(f"[green]●[/] {worktree_name} — cleaned")

    if ticket is not None:
        update_ticket_fields(ticket.path, {"worktree": None})
    return True
