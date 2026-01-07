"""Git operations for worktree management."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from vibe.config import LOCAL_WORKTREE_BASE
from vibe.utils import console

# Default timeout for git operations (seconds)
GIT_TIMEOUT = 60


class WorktreeStatus(Enum):
    """Status of a worktree check."""

    EXISTS_VALID = "exists_valid"  # Directory exists and is a valid git worktree
    EXISTS_INVALID = "exists_invalid"  # Directory exists but is NOT a git worktree
    NOT_EXISTS = "not_exists"  # Directory does not exist


@dataclass
class RepoInfo:
    """Information about a git repository."""

    root: Path
    name: str


def validate_git_repo(cwd: Path | None = None) -> bool:
    """Check if the current directory is inside a git repository.

    Args:
        cwd: Working directory to check (defaults to current directory)

    Returns:
        True if in a git repository, False otherwise
    """
    result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        capture_output=True,
        cwd=cwd,
    )
    return result.returncode == 0


def get_repo_info(cwd: Path | None = None) -> RepoInfo:
    """Get repository root path and name.

    Args:
        cwd: Working directory (defaults to current directory)

    Returns:
        RepoInfo with root path and repository name

    Raises:
        RuntimeError: If not in a git repository
    """
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if result.returncode != 0:
        raise RuntimeError("Not in a git repository")

    root = Path(result.stdout.strip())
    return RepoInfo(root=root, name=root.name)


def check_worktree_exists(
    worktree_name: str,
    repo_name: str,
    worktree_base: Path = LOCAL_WORKTREE_BASE,
    cwd: Path | None = None,
) -> WorktreeStatus:
    """Check if a worktree exists and whether it's valid.

    Args:
        worktree_name: Name of the worktree/branch
        repo_name: Name of the repository
        worktree_base: Base directory for worktrees
        cwd: Working directory for git commands

    Returns:
        WorktreeStatus indicating the state of the worktree
    """
    worktree_path = worktree_base / repo_name / worktree_name

    if not worktree_path.exists():
        return WorktreeStatus.NOT_EXISTS

    # Check if it's a valid git worktree
    result = subprocess.run(
        ["git", "worktree", "list"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )

    if str(worktree_path) in result.stdout:
        return WorktreeStatus.EXISTS_VALID
    else:
        return WorktreeStatus.EXISTS_INVALID


def branch_exists_local(branch: str, cwd: Path | None = None) -> bool:
    """Check if a local branch exists.

    Args:
        branch: Branch name to check
        cwd: Working directory for git commands

    Returns:
        True if the local branch exists
    """
    result = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
        capture_output=True,
        cwd=cwd,
    )
    return result.returncode == 0


def branch_exists_remote(branch: str, cwd: Path | None = None) -> bool:
    """Check if a remote branch exists.

    Args:
        branch: Branch name (can include origin/ prefix or not)
        cwd: Working directory for git commands

    Returns:
        True if the remote branch exists
    """
    # Normalize the branch name
    if not branch.startswith("origin/"):
        ref = f"refs/remotes/origin/{branch}"
    else:
        ref = f"refs/remotes/{branch}"

    result = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", ref],
        capture_output=True,
        cwd=cwd,
    )
    return result.returncode == 0


def get_local_branches(cwd: Path | None = None) -> list[str]:
    """Get list of local branch names.

    Args:
        cwd: Working directory for git commands

    Returns:
        List of local branch names
    """
    result = subprocess.run(
        ["git", "branch", "--format=%(refname:short)"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if result.returncode != 0:
        return []
    return [b.strip() for b in result.stdout.strip().split("\n") if b.strip()]


def get_remote_branches(cwd: Path | None = None) -> list[str]:
    """Get list of remote branch names.

    Args:
        cwd: Working directory for git commands

    Returns:
        List of remote branch names (including origin/ prefix)
    """
    result = subprocess.run(
        ["git", "branch", "-r", "--format=%(refname:short)"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if result.returncode != 0:
        return []
    return [b.strip() for b in result.stdout.strip().split("\n") if b.strip()]


def has_uncommitted_changes(worktree_path: Path) -> bool:
    """Check if a worktree has uncommitted changes.

    Args:
        worktree_path: Path to the worktree

    Returns:
        True if there are uncommitted changes
    """
    if not worktree_path.is_dir():
        return False

    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        cwd=worktree_path,
    )
    return bool(result.stdout.strip())


def create_worktree(
    worktree_name: str,
    repo_name: str,
    base_branch: str | None = None,
    worktree_base: Path = LOCAL_WORKTREE_BASE,
    cwd: Path | None = None,
) -> Path:
    """Create a new worktree.

    Handles three scenarios:
    1. Remote branch (origin/branch) - creates local tracking branch
    2. Existing local branch - creates worktree from it
    3. New branch - creates new branch and worktree (optionally from base)

    Args:
        worktree_name: Name for the worktree (usually branch name)
        repo_name: Name of the repository
        base_branch: Optional base branch to create new branch from
        worktree_base: Base directory for worktrees
        cwd: Working directory for git commands

    Returns:
        Path to the created worktree

    Raises:
        RuntimeError: If worktree creation fails
    """
    # Ensure repository subdirectory exists
    repo_worktree_dir = worktree_base / repo_name
    repo_worktree_dir.mkdir(parents=True, exist_ok=True)

    # Handle origin/ prefix (remote branch reference)
    if worktree_name.startswith("origin/"):
        local_branch_name = worktree_name[7:]  # Remove "origin/" prefix
        worktree_path = repo_worktree_dir / local_branch_name

        # Check if remote branch exists
        if not branch_exists_remote(worktree_name, cwd):
            remote_branches = get_remote_branches(cwd)
            raise RuntimeError(
                f"Remote branch '{worktree_name}' does not exist.\n"
                f"Available remote branches: {', '.join(remote_branches)}"
            )

        console.print(
            f"Found remote branch '{worktree_name}', "
            f"creating local tracking branch '{local_branch_name}'..."
        )

        result = subprocess.run(
            [
                "git",
                "worktree",
                "add",
                "-b",
                local_branch_name,
                str(worktree_path),
                worktree_name,
            ],
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else "Unknown error"
            raise RuntimeError(
                f"Failed to create worktree '{local_branch_name}' from "
                f"remote branch '{worktree_name}'.\n"
                f"Path: {worktree_path}\n"
                f"Git error: {error_msg}"
            )

        return worktree_path

    # Standard worktree path
    worktree_path = repo_worktree_dir / worktree_name

    # Check if local branch already exists
    if branch_exists_local(worktree_name, cwd):
        # Branch exists, create worktree from existing branch
        result = subprocess.run(
            ["git", "worktree", "add", str(worktree_path), worktree_name],
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else "Unknown error"
            raise RuntimeError(
                f"Failed to create worktree for existing branch '{worktree_name}'.\n"
                f"Path: {worktree_path}\n"
                f"Git error: {error_msg}"
            )

        return worktree_path

    # Branch doesn't exist, create new branch and worktree
    if base_branch:
        # Validate base branch exists (local or remote)
        if not branch_exists_local(base_branch, cwd) and not branch_exists_remote(
            base_branch, cwd
        ):
            local_branches = get_local_branches(cwd)
            remote_branches = get_remote_branches(cwd)
            raise RuntimeError(
                f"Base branch '{base_branch}' does not exist.\n"
                f"Available local branches: {', '.join(local_branches)}\n"
                f"Available remote branches: {', '.join(remote_branches)}"
            )

        console.print(f"Creating branch '{worktree_name}' from '{base_branch}'...")

        result = subprocess.run(
            [
                "git",
                "worktree",
                "add",
                "-b",
                worktree_name,
                str(worktree_path),
                base_branch,
            ],
            capture_output=True,
            text=True,
            cwd=cwd,
        )
    else:
        # Create new branch from HEAD
        result = subprocess.run(
            ["git", "worktree", "add", "-b", worktree_name, str(worktree_path)],
            capture_output=True,
            text=True,
            cwd=cwd,
        )

    if result.returncode != 0:
        error_msg = result.stderr.strip() if result.stderr else "Unknown error"
        base_info = f" from '{base_branch}'" if base_branch else ""
        raise RuntimeError(
            f"Failed to create worktree '{worktree_name}'{base_info}.\n"
            f"Path: {worktree_path}\n"
            f"Git error: {error_msg}"
        )

    console.print(f"Worktree created successfully at: {worktree_path}")
    return worktree_path


def get_worktree_list(cwd: Path | None = None) -> list[Path]:
    """Get list of all worktree paths for the repository.

    Args:
        cwd: Working directory for git commands

    Returns:
        List of worktree paths
    """
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if result.returncode != 0:
        return []

    worktrees = []
    for line in result.stdout.split("\n"):
        if line.startswith("worktree "):
            worktrees.append(Path(line[9:]))  # Remove "worktree " prefix

    return worktrees


def get_git_common_dir(worktree_path: Path) -> Path | None:
    """Get the common git directory for a worktree.

    This points to the main repository's .git directory.

    Args:
        worktree_path: Path to the worktree

    Returns:
        Path to the common git directory, or None if not a worktree
    """
    result = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        capture_output=True,
        text=True,
        cwd=worktree_path,
    )
    if result.returncode != 0:
        return None

    common_dir = result.stdout.strip()
    if common_dir:
        return Path(common_dir).resolve()
    return None
