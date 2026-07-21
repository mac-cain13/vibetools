"""Git operations for worktree management."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from vibe.config import LOCAL_REPO_BASE, LOCAL_WORKTREE_BASE, REMOTE_REPO_BASE
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
    """Information about a git repository checkout.

    Attributes:
        root: Toplevel of the current checkout; inside a linked worktree this
            is the worktree's own root
        name: Repository name, always derived from the main checkout
        main_root: Root of the main repository checkout (equals root when not
            inside a linked worktree)
    """

    root: Path
    name: str
    main_root: Path


def branch_to_worktree_dirname(branch: str) -> str:
    """Encode a branch name into a flat worktree directory name.

    Branch names may contain '/', but worktree directories must be a single
    path component. The mapping is deterministic and reversible: '%' is
    replaced with '%25' first, then '/' with '%2F'.

    Args:
        branch: Real branch name (may contain '/')

    Returns:
        Encoded directory name containing no '/'
    """
    return branch.replace("%", "%25").replace("/", "%2F")


def worktree_dirname_to_branch(dirname: str) -> str:
    """Decode a worktree directory name back into the real branch name.

    Reverses branch_to_worktree_dirname: '%2F' is replaced with '/' first,
    then '%25' with '%'.

    Args:
        dirname: Encoded worktree directory name

    Returns:
        The real branch name (may contain '/')
    """
    return dirname.replace("%2F", "/").replace("%25", "%")


def worktree_path_for_branch(
    repo_name: str,
    branch: str,
    worktree_base: Path = LOCAL_WORKTREE_BASE,
) -> Path:
    """Build the on-disk worktree path for a branch.

    The directory name is the encoded branch name so that branches
    containing '/' map to a single path component.

    Args:
        repo_name: Name of the repository
        branch: Real branch name (may contain '/')
        worktree_base: Base directory for worktrees

    Returns:
        Path of the form worktree_base / repo_name / encoded-dirname
    """
    return worktree_base / repo_name / branch_to_worktree_dirname(branch)


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

    Inside a linked worktree, `name` and `main_root` come from the main
    checkout (the parent of the shared .git directory) rather than the
    worktree directory itself, so worktrees are always grouped under the
    real repository name. `root` still points at the current checkout's
    toplevel.

    Args:
        cwd: Working directory (defaults to current directory)

    Returns:
        RepoInfo with root path, repository name, and main checkout root

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

    main_root = root
    common_result = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if common_result.returncode == 0:
        common_dir = Path(common_result.stdout.strip())
        if not common_dir.is_absolute():
            common_dir = ((cwd or Path.cwd()) / common_dir).resolve()
        if common_dir.name == ".git":
            main_root = common_dir.parent

    return RepoInfo(root=root, name=main_root.name, main_root=main_root)


def check_worktree_exists(
    worktree_name: str,
    repo_name: str,
    worktree_base: Path = LOCAL_WORKTREE_BASE,
    cwd: Path | None = None,
) -> WorktreeStatus:
    """Check if a worktree exists and whether it's valid.

    Args:
        worktree_name: Branch name for the worktree (encoded for the path)
        repo_name: Name of the repository
        worktree_base: Base directory for worktrees
        cwd: Working directory for git commands

    Returns:
        WorktreeStatus indicating the state of the worktree
    """
    worktree_path = worktree_path_for_branch(repo_name, worktree_name, worktree_base)

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


def get_tip_commit_subject(worktree_path: Path) -> str | None:
    """Get the subject line of a worktree's tip commit.

    Decoding is lossy ('errors=replace'): the only consumer compares the
    subject against the ASCII park marker, so a non-UTF-8 commit subject
    simply fails that comparison instead of crashing the resume.

    Args:
        worktree_path: Path to the worktree

    Returns:
        The tip commit's subject line (stripped), or None when it cannot
        be read (missing directory, no commits, not a git worktree)
    """
    if not worktree_path.is_dir():
        return None

    result = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"],
        capture_output=True,
        text=True,
        errors="replace",
        cwd=worktree_path,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def unwind_park_commit(worktree_path: Path) -> bool:
    """Unwind a worktree's tip commit with a mixed reset.

    A mixed 'git reset HEAD~1' restores the commit's contents as
    working-directory changes: tracked changes return unstaged and
    previously-untracked files reappear (docs/nsproject-park.md §4).
    Callers must verify the tip commit is the park marker before calling.

    Args:
        worktree_path: Path to the worktree

    Returns:
        True if the reset succeeded
    """
    result = subprocess.run(
        ["git", "reset", "HEAD~1"],
        capture_output=True,
        cwd=worktree_path,
    )
    return result.returncode == 0


def find_branch_checkout(branch: str, cwd: Path | None = None) -> Path | None:
    """Find which worktree (if any) currently has a branch checked out.

    Git refuses to check a branch out in two worktrees at once, so a branch
    can be checked out in at most one place. This parses 'git worktree list'
    to find it — used by resume to detect a branch stranded on the main
    checkout after an interrupted park.

    Args:
        branch: Real branch name (may contain '/')
        cwd: Working directory for git commands

    Returns:
        Path to the worktree holding the branch, or None if the branch is
        not checked out anywhere (or git could not be queried)
    """
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if result.returncode != 0:
        return None

    current: Path | None = None
    target_ref = f"refs/heads/{branch}"
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            current = Path(line[len("worktree "):])
        elif line.startswith("branch ") and line[len("branch "):] == target_ref:
            return current
    return None


def prune_worktrees(cwd: Path | None = None) -> None:
    """Prune stale worktree administrative entries.

    Removes registrations whose working-tree directory no longer exists,
    freeing a branch that git still believes is checked out. Safe to call
    unconditionally — it only touches entries with missing directories.

    Args:
        cwd: Working directory for git commands
    """
    subprocess.run(
        ["git", "worktree", "prune"],
        capture_output=True,
        cwd=cwd,
    )


def switch_checkout_to_branch(repo_root: Path, target_branch: str) -> bool:
    """Switch a checkout to another branch (e.g. to free a stranded branch).

    Used by resume to complete an interrupted park's switch-back: moving the
    main checkout off a ticket's branch so it can be checked out in a
    worktree. The caller must ensure the working tree is clean first.

    Args:
        repo_root: Path to the checkout to switch
        target_branch: Branch to switch to

    Returns:
        True if the switch succeeded
    """
    result = subprocess.run(
        ["git", "switch", target_branch],
        capture_output=True,
        cwd=repo_root,
    )
    return result.returncode == 0


def get_default_branch(cwd: Path | None = None) -> str | None:
    """Get the repository's default branch name.

    Resolves origin's HEAD symbolic ref (e.g. 'origin/main' -> 'main'). Used
    as a fall-back target when switching a stranded main checkout away from a
    ticket's branch and the ticket records no usable base branch.

    Args:
        cwd: Working directory for git commands

    Returns:
        The default branch name, or None if it cannot be determined
    """
    result = subprocess.run(
        ["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if result.returncode != 0:
        return None
    ref = result.stdout.strip()
    if ref.startswith("origin/"):
        return ref[len("origin/"):]
    return ref or None


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
        worktree_name: Branch name for the worktree (the on-disk directory
            name is the encoded form; git commands use the real branch name)
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
        worktree_path = repo_worktree_dir / branch_to_worktree_dirname(
            local_branch_name
        )

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

    # Standard worktree path (directory name is the encoded branch name)
    worktree_path = repo_worktree_dir / branch_to_worktree_dirname(worktree_name)

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


class ContextType(Enum):
    """Type of git context the user is in."""

    MAIN_REPO = "main_repo"  # In a main repository checkout
    WORKTREE = "worktree"  # In a worktree
    NONE = "none"  # Not in a git context


@dataclass
class CurrentContext:
    """Information about the current git context."""

    context_type: ContextType
    local_path: Path | None = None
    remote_path: Path | None = None
    repo_name: str | None = None
    worktree_name: str | None = None  # Encoded on-disk directory name
    branch: str | None = None  # Decoded branch name (None outside worktree context)


def is_inside_worktree_base(
    cwd: Path | None = None,
    worktree_base: Path = LOCAL_WORKTREE_BASE,
) -> bool:
    """Check if current directory is inside the worktree base directory.

    Args:
        cwd: Working directory to check (defaults to current directory)
        worktree_base: Base directory for worktrees

    Returns:
        True if inside worktree base, False otherwise
    """
    if cwd is None:
        cwd = Path.cwd()

    try:
        cwd.resolve().relative_to(worktree_base.resolve())
        return True
    except ValueError:
        return False


def is_git_worktree(cwd: Path | None = None) -> bool:
    """Check if current directory is a git worktree (not the main repo).

    Args:
        cwd: Working directory to check (defaults to current directory)

    Returns:
        True if in a worktree, False if in main repo or not in git
    """
    if cwd is None:
        cwd = Path.cwd()

    # Get git dir and common dir
    git_dir_result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if git_dir_result.returncode != 0:
        return False

    common_dir_result = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if common_dir_result.returncode != 0:
        return False

    git_dir = Path(git_dir_result.stdout.strip())
    common_dir = Path(common_dir_result.stdout.strip())

    # If git-dir != git-common-dir, we're in a worktree
    # Resolve relative paths based on cwd
    if not git_dir.is_absolute():
        git_dir = (cwd / git_dir).resolve()
    if not common_dir.is_absolute():
        common_dir = (cwd / common_dir).resolve()

    return git_dir != common_dir


def get_current_context(
    cwd: Path | None = None,
    repo_base: Path = LOCAL_REPO_BASE,
    worktree_base: Path = LOCAL_WORKTREE_BASE,
    remote_base: Path = REMOTE_REPO_BASE,
) -> CurrentContext:
    """Detect if we're in a main repo, worktree, or neither.

    Args:
        cwd: Working directory to check (defaults to current directory)
        repo_base: Base directory for repositories
        worktree_base: Base directory for worktrees
        remote_base: Remote base directory for path mapping

    Returns:
        CurrentContext with type and path information
    """
    if cwd is None:
        cwd = Path.cwd()

    # Check if we're in a git repository at all
    if not validate_git_repo(cwd):
        return CurrentContext(context_type=ContextType.NONE)

    repo_info = get_repo_info(cwd)

    # Check if we're in a worktree
    if is_git_worktree(cwd):
        # We're in a worktree - extract worktree name from path
        # Worktree path: {worktree_base}/{repo_name}/{worktree_name}
        # where {worktree_name} is the encoded branch directory name
        try:
            rel_path = repo_info.root.relative_to(worktree_base)
            parts = rel_path.parts
            if len(parts) >= 2:
                repo_name = parts[0]
                worktree_name = parts[1]
                remote_path = remote_base / "_vibecoding" / repo_name / worktree_name
                return CurrentContext(
                    context_type=ContextType.WORKTREE,
                    local_path=repo_info.root,
                    remote_path=remote_path,
                    repo_name=repo_name,
                    worktree_name=worktree_name,
                    branch=worktree_dirname_to_branch(worktree_name),
                )
        except ValueError:
            pass

        # Fallback: worktree not in expected location
        return CurrentContext(
            context_type=ContextType.WORKTREE,
            local_path=repo_info.root,
            repo_name=repo_info.name,
        )

    # We're in a main repo
    # Check if it's in the expected repo base
    try:
        repo_info.root.relative_to(repo_base)
        remote_path = remote_base / repo_info.name
        return CurrentContext(
            context_type=ContextType.MAIN_REPO,
            local_path=repo_info.root,
            remote_path=remote_path,
            repo_name=repo_info.name,
        )
    except ValueError:
        # Repo not in expected location
        return CurrentContext(
            context_type=ContextType.MAIN_REPO,
            local_path=repo_info.root,
            repo_name=repo_info.name,
        )
