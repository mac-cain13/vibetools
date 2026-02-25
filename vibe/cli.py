"""CLI interface for vibe using Typer."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console

from vibe.cleanup import clean_all_worktrees, clean_specific_worktree
from vibe.config import (
    CLAUDE_CODE_CMD,
    CLAUDE_CODE_DIRECT_CMD,
    CODEX_CMD,
    CODEX_DIRECT_CMD,
    DEFAULT_REMOTE_SHELL,
    LOCAL_WORKTREE_BASE,
    OPEN_CODE_CMD,
    OPEN_CODE_DIRECT_CMD,
    REMOTE_IS_WINDOWS,
)
from vibe.connection import (
    connect_locally,
    connect_to_remote,
    connect_to_remote_home,
    connect_to_remote_path,
)
from vibe.git_ops import (
    ContextType,
    CurrentContext,
    WorktreeStatus,
    check_worktree_exists,
    create_worktree,
    get_current_context,
    get_local_branches,
    get_remote_branches,
    get_repo_info,
    is_git_worktree,
    validate_git_repo,
)
from vibe.platform import Shell


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


def prompt_shell_choice() -> Shell:
    """Prompt user to select WSL or PowerShell on Windows targets.

    Returns:
        The selected Shell enum value.
    """
    from simple_term_menu import TerminalMenu

    options = ["WSL", "PowerShell"]
    shell_map = {
        0: Shell.WSL,
        1: Shell.POWERSHELL,
    }

    console.print("\n[bold]Select remote shell:[/bold]")
    menu = TerminalMenu(options, cursor_index=0)
    choice = menu.show()

    if choice is None:
        raise typer.Abort()

    return shell_map[choice]


def prompt_coding_tool_choice(powershell: bool = False) -> str:
    """Prompt user to select a coding tool interactively.

    Args:
        powershell: Whether to use direct commands (for PowerShell)

    Returns:
        The coding tool command to use.
    """
    from simple_term_menu import TerminalMenu

    options = ["Codex", "OpenCode", "Claude"]
    if powershell:
        tool_map = {
            0: CODEX_DIRECT_CMD,
            1: OPEN_CODE_DIRECT_CMD,
            2: CLAUDE_CODE_DIRECT_CMD,
        }
    else:
        tool_map = {
            0: CODEX_CMD,
            1: OPEN_CODE_CMD,
            2: CLAUDE_CODE_CMD,
        }

    console.print("\n[bold]Select coding tool:[/bold]")
    menu = TerminalMenu(options, cursor_index=0)
    choice = menu.show()

    if choice is None:
        # User cancelled (e.g., Ctrl+C)
        raise typer.Abort()

    return tool_map[choice]


def resolve_coding_tool(
    oc: bool,
    codex: bool,
    claude: bool,
    powershell: bool = False,
) -> Optional[str]:
    """Resolve which coding tool to use based on flags.

    Args:
        oc: Whether --oc flag was provided
        codex: Whether --codex flag was provided
        claude: Whether --claude flag was provided
        powershell: Whether to use direct commands (for PowerShell)

    Returns:
        The coding tool command to use, or None if no flag specified.

    Note:
        Assumes mutual exclusivity is validated before calling.
        Returns None if no flag is specified (caller should prompt).
    """
    if oc:
        return OPEN_CODE_DIRECT_CMD if powershell else OPEN_CODE_CMD
    if codex:
        return CODEX_DIRECT_CMD if powershell else CODEX_CMD
    if claude:
        return CLAUDE_CODE_DIRECT_CMD if powershell else CLAUDE_CODE_CMD
    return None  # No flag = interactive prompt


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


def _resolve_remote_shell() -> Shell | None:
    """Determine the remote shell to use.

    On Windows targets, prompts for WSL or PowerShell.
    On macOS targets, returns None (direct connection).

    Returns:
        Shell enum value or None for macOS
    """
    if REMOTE_IS_WINDOWS:
        return prompt_shell_choice()
    return DEFAULT_REMOTE_SHELL


def _resolve_tool_and_shell(
    oc: bool,
    codex: bool,
    claude: bool,
    remote_shell: Shell | None,
) -> str:
    """Resolve the coding tool command, prompting if needed.

    Args:
        oc: Whether --oc flag was provided
        codex: Whether --codex flag was provided
        claude: Whether --claude flag was provided
        remote_shell: The remote shell being used

    Returns:
        The coding tool command string
    """
    is_powershell = remote_shell == Shell.POWERSHELL
    coding_tool = resolve_coding_tool(oc, codex, claude, powershell=is_powershell)
    if coding_tool is None:
        coding_tool = prompt_coding_tool_choice(powershell=is_powershell)
    return coding_tool


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
    oc: bool = typer.Option(
        False,
        "--oc",
        help="Use OpenCode as the coding tool.",
    ),
    codex: bool = typer.Option(
        False,
        "--codex",
        help="Use Codex as the coding tool.",
    ),
    claude: bool = typer.Option(
        False,
        "--claude",
        help="Use Claude Code as the coding tool.",
    ),
) -> None:
    """Git worktree manager for remote development sessions.

    Creates and manages git worktrees, then connects to remote machine for coding.

    \b
    Examples:
        vibe                              # Interactive tool picker
        vibe feature-branch --codex       # Create worktree, use Codex
        vibe feature-branch --claude      # Create worktree, use Claude Code
        vibe feature-branch --oc          # Create worktree, use OpenCode
        vibe feature-branch --from main   # Create from main branch
        vibe --cli                        # SSH to home directory
        vibe --cli feature-branch         # Create worktree, SSH shell only
        vibe --local feature-branch       # Work locally (prompts for tool)
        vibe --clean                      # Clean all worktrees
        vibe --clean feature-branch       # Clean specific worktree

    \b
    Context-aware behavior:
        - In main repo: 'vibe' connects to that repo on remote
        - In worktree: 'vibe' connects to that worktree on remote
        - In worktree: 'vibe new-branch' branches from worktree's HEAD
    """
    # Validate that only one coding tool flag is provided
    flags_set = sum([oc, codex, claude])
    if flags_set > 1:
        console.print(
            "[red]Error:[/red] Cannot use multiple coding tool flags "
            "(--oc, --codex, --claude)"
        )
        raise typer.Exit(1)

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
            remote_shell = _resolve_remote_shell()
            exit_code = connect_to_remote_home(remote_shell=remote_shell)
            raise typer.Exit(exit_code)

        # SSH with worktree but no coding tool
        if not validate_git_repo():
            console.print("[red]Error:[/] Not in a git repository")
            raise typer.Exit(1)

        repo_info = get_repo_info()
        # Determine base branch for worktree-aware branching
        effective_from = from_branch
        if effective_from is None and is_git_worktree():
            # In a worktree without --from, we'll branch from current HEAD
            # (create_worktree handles this by not specifying a base)
            pass

        if not setup_worktree(branch, effective_from, repo_info.name, repo_info.root):
            raise typer.Exit(1)

        remote_shell = _resolve_remote_shell()
        exit_code = connect_to_remote(
            repo_name=repo_info.name,
            worktree_name=branch,
            with_coding_tool=False,
            remote_shell=remote_shell,
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

        coding_tool = resolve_coding_tool(oc, codex, claude)
        if coding_tool is None:
            coding_tool = prompt_coding_tool_choice()
        worktree_path = LOCAL_WORKTREE_BASE / repo_info.name / branch
        exit_code = connect_locally(worktree_path, coding_tool=coding_tool)
        raise typer.Exit(exit_code)

    # Handle no-argument case: connect to current context
    if branch is None:
        context = get_current_context()

        if context.context_type == ContextType.NONE:
            console.print("[red]Error:[/] Not in a git repository")
            raise typer.Exit(1)

        if context.remote_path is None:
            console.print(
                "[red]Error:[/] Repository is not in the expected location "
                f"({LOCAL_WORKTREE_BASE.parent})"
            )
            raise typer.Exit(1)

        # Connect to the current context (main repo or worktree)
        if context.context_type == ContextType.MAIN_REPO:
            console.print(f"Connecting to main repository '{context.repo_name}'...")
        else:
            console.print(
                f"Connecting to worktree '{context.worktree_name}' "
                f"in '{context.repo_name}'..."
            )

        remote_shell = _resolve_remote_shell()
        coding_tool = _resolve_tool_and_shell(oc, codex, claude, remote_shell)
        exit_code = connect_to_remote_path(
            remote_path=context.remote_path,
            with_coding_tool=True,
            coding_tool=coding_tool,
            remote_shell=remote_shell,
        )
        raise typer.Exit(exit_code)

    # Default: create worktree and connect with coding tool
    if not validate_git_repo():
        console.print("[red]Error:[/] Not in a git repository")
        raise typer.Exit(1)

    repo_info = get_repo_info()

    # Worktree-aware branching: if in a worktree and no --from specified,
    # the new branch will be created from the current HEAD (worktree's HEAD)
    # This is the default git behavior when no base is specified
    if not setup_worktree(branch, from_branch, repo_info.name, repo_info.root):
        raise typer.Exit(1)

    remote_shell = _resolve_remote_shell()
    coding_tool = _resolve_tool_and_shell(oc, codex, claude, remote_shell)
    exit_code = connect_to_remote(
        repo_name=repo_info.name,
        worktree_name=branch,
        with_coding_tool=True,
        coding_tool=coding_tool,
        remote_shell=remote_shell,
    )
    raise typer.Exit(exit_code)


if __name__ == "__main__":
    app()
