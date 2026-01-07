"""CLI interface for vibe using Typer."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console

from vibe.cleanup import clean_all_worktrees, clean_specific_worktree
from vibe.config import LOCAL_WORKTREE_BASE
from vibe.connection import (
    connect_locally,
    connect_to_remote,
    connect_to_remote_home,
)
from vibe.git_ops import (
    WorktreeStatus,
    check_worktree_exists,
    create_worktree,
    get_local_branches,
    get_remote_branches,
    get_repo_info,
    validate_git_repo,
)


def complete_branches(incomplete: str) -> List[str]:
    """Provide branch name completions.

    Args:
        incomplete: The partial branch name typed so far

    Returns:
        List of matching branch names
    """
    if not validate_git_repo():
        return []

    branches = get_local_branches() + get_remote_branches()
    return [b for b in branches if b.startswith(incomplete)]


def complete_worktrees(incomplete: str) -> List[str]:
    """Provide worktree name completions for --clean.

    Args:
        incomplete: The partial worktree name typed so far

    Returns:
        List of matching worktree names in current repo
    """
    if not validate_git_repo():
        return []

    try:
        repo_info = get_repo_info()
        repo_worktrees = LOCAL_WORKTREE_BASE / repo_info.name
        if not repo_worktrees.exists():
            return []

        worktrees = [d.name for d in repo_worktrees.iterdir() if d.is_dir()]
        return [w for w in worktrees if w.startswith(incomplete)]
    except Exception:
        return []

app = typer.Typer(
    name="vibe",
    help="Git worktree manager for remote development sessions.",
    add_completion=True,
)

console = Console()


def setup_worktree(
    worktree_name: str,
    from_branch: Optional[str],
    repo_name: str,
    cwd: Path,
) -> bool:
    """Set up a worktree, handling existence checks and creation.

    Args:
        worktree_name: Name of the worktree/branch
        from_branch: Optional base branch to create from
        repo_name: Name of the repository
        cwd: Current working directory

    Returns:
        True if worktree is ready to use, False on error
    """
    status = check_worktree_exists(
        worktree_name=worktree_name,
        repo_name=repo_name,
        worktree_base=LOCAL_WORKTREE_BASE,
        cwd=cwd,
    )

    if status == WorktreeStatus.EXISTS_INVALID:
        console.print(
            f"[red]Error:[/] Directory exists at "
            f"{LOCAL_WORKTREE_BASE / repo_name / worktree_name} "
            f"but is not a git worktree"
        )
        console.print("Please remove the directory or choose a different name")
        return False

    if status == WorktreeStatus.EXISTS_VALID:
        console.print(
            f"Worktree directory already exists at: "
            f"{LOCAL_WORKTREE_BASE / repo_name / worktree_name}"
        )
        console.print("Directory is already a valid worktree")

        if from_branch:
            console.print()
            console.print(
                f"[yellow]Warning:[/] Branch '{worktree_name}' already exists. "
                f"The --from flag will be ignored."
            )
            console.print()
            if not typer.confirm("Continue anyway?", default=True):
                raise typer.Abort()

        return True

    # Worktree doesn't exist, create it
    console.print(f"Creating worktree '{worktree_name}'...")
    try:
        create_worktree(
            worktree_name=worktree_name,
            repo_name=repo_name,
            base_branch=from_branch,
            worktree_base=LOCAL_WORKTREE_BASE,
            cwd=cwd,
        )
        return True
    except RuntimeError as e:
        console.print(f"[red]Error:[/] {e}")
        return False


@app.command(
    context_settings={"help_option_names": ["-h", "--help"]},
)
def main(
    ctx: typer.Context,
    branch: Optional[str] = typer.Argument(
        None,
        help="Branch name for the worktree. Creates worktree and connects to it.",
        autocompletion=complete_branches,
    ),
    cli: bool = typer.Option(
        False,
        "--cli",
        help="Connect to remote CLI (shell only, without coding tool). "
        "If no branch specified, connects to home directory.",
    ),
    local: bool = typer.Option(
        False,
        "--local",
        help="Work locally instead of SSH to remote. Requires branch name.",
    ),
    clean: bool = typer.Option(
        False,
        "--clean",
        help="Clean worktrees. Without branch, cleans all. With branch, cleans specific worktree.",
    ),
    from_branch: Optional[str] = typer.Option(
        None,
        "--from",
        help="Base branch to create new branch from.",
        autocompletion=complete_branches,
    ),
) -> None:
    """Git worktree manager for remote development sessions.

    Creates and manages git worktrees, then connects to remote machine for coding.

    \b
    Examples:
        vibe feature-branch              # Create worktree, SSH with coding tool
        vibe feature-branch --from main  # Create from main branch
        vibe --cli                        # SSH to home directory
        vibe --cli feature-branch        # Create worktree, SSH shell only
        vibe --local feature-branch      # Work locally in worktree
        vibe --clean                      # Clean all worktrees
        vibe --clean feature-branch      # Clean specific worktree
    """
    # Show help if no arguments provided (mimics no_args_is_help behavior)
    if branch is None and not cli and not local and not clean:
        console.print(ctx.get_help())
        raise typer.Exit(0)

    # Handle --clean option
    if clean:
        if branch is None:
            # Clean all worktrees
            clean_all_worktrees()
            return

        # Clean specific worktree - requires git repo
        if not validate_git_repo():
            console.print("[red]Error:[/] Not in a git repository")
            raise typer.Exit(1)

        repo_info = get_repo_info()
        success = clean_specific_worktree(
            worktree_name=branch,
            repo_name=repo_info.name,
            repo_root=repo_info.root,
        )
        if not success:
            raise typer.Exit(1)
        return

    # Handle --cli option
    if cli:
        if branch is None:
            # Just SSH to home directory
            exit_code = connect_to_remote_home()
            raise typer.Exit(exit_code)

        # SSH with worktree but no coding tool
        if not validate_git_repo():
            console.print("[red]Error:[/] Not in a git repository")
            raise typer.Exit(1)

        repo_info = get_repo_info()
        if not setup_worktree(branch, from_branch, repo_info.name, repo_info.root):
            raise typer.Exit(1)

        exit_code = connect_to_remote(
            repo_name=repo_info.name,
            worktree_name=branch,
            with_coding_tool=False,
        )
        raise typer.Exit(exit_code)

    # Handle --local option
    if local:
        if branch is None:
            console.print("[red]Error:[/] --local requires a branch name")
            console.print("Usage: vibe --local <worktree_name> [--from base_branch]")
            raise typer.Exit(1)

        if not validate_git_repo():
            console.print("[red]Error:[/] Not in a git repository")
            raise typer.Exit(1)

        repo_info = get_repo_info()
        if not setup_worktree(branch, from_branch, repo_info.name, repo_info.root):
            raise typer.Exit(1)

        worktree_path = LOCAL_WORKTREE_BASE / repo_info.name / branch
        exit_code = connect_locally(worktree_path)
        raise typer.Exit(exit_code)

    # Default: create worktree and connect with coding tool
    if not validate_git_repo():
        console.print("[red]Error:[/] Not in a git repository")
        raise typer.Exit(1)

    repo_info = get_repo_info()
    if not setup_worktree(branch, from_branch, repo_info.name, repo_info.root):
        raise typer.Exit(1)

    exit_code = connect_to_remote(
        repo_name=repo_info.name,
        worktree_name=branch,
        with_coding_tool=True,
    )
    raise typer.Exit(exit_code)


if __name__ == "__main__":
    app()
