"""CLI interface for vibe using Typer."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, List, Optional

import typer
from rich.console import Console
from rich.markup import escape

from vibe.cleanup import (
    clean_all_worktrees,
    clean_specific_worktree,
    post_session_cleanup,
)
from vibe.config import (
    CLAUDE_CODE_CMD,
    CLAUDE_CODE_DIRECT_CMD,
    CODEX_CMD,
    CODEX_DIRECT_CMD,
    DEFAULT_REMOTE_SHELL,
    LOCAL_REPO_BASE,
    LOCAL_WORKTREE_BASE,
    OPEN_CODE_CMD,
    OPEN_CODE_DIRECT_CMD,
    REMOTE_IS_WINDOWS,
    REMOTE_REPO_BASE,
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
    branch_exists_local,
    branch_exists_remote,
    branch_to_worktree_dirname,
    check_worktree_exists,
    create_worktree,
    find_branch_checkout,
    get_current_context,
    get_default_branch,
    get_local_branches,
    get_remote_branches,
    get_repo_info,
    get_tip_commit_subject,
    has_uncommitted_changes,
    is_git_worktree,
    prune_worktrees,
    switch_checkout_to_branch,
    unwind_park_commit,
    validate_git_repo,
    worktree_dirname_to_branch,
    worktree_path_for_branch,
)
from vibe.platform import Shell
from vibe.nsproject import (
    ParkedWork,
    find_board,
    find_parked_work,
    is_safe_session_id,
    is_safe_ticket_id,
    list_resumable,
    mark_resumed,
)

# Fixed bootstrap prompt used to seed a fresh Claude session on resume
# (docs/nsproject-park.md §3): no apostrophes, no freeform text, safe through
# shell quoting. The ticket id is embedded only after it passes
# is_safe_ticket_id.
RESUME_BOOTSTRAP_PROMPT = (
    "Read NSProject ticket {ticket_id} via the nsproject skill "
    'and continue from its "Where I left off".'
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
    """Provide worktree branch name completions for --clean.

    Directory names on disk are encoded; completions offer the decoded
    branch names.

    Args:
        incomplete: The partial branch name typed so far

    Returns:
        List of matching branch names for worktrees in current repo
    """
    if not validate_git_repo():
        return []

    try:
        repo_info = get_repo_info()
        repo_worktrees = LOCAL_WORKTREE_BASE / repo_info.name
        if not repo_worktrees.exists():
            return []

        branches = [
            worktree_dirname_to_branch(d.name)
            for d in repo_worktrees.iterdir()
            if d.is_dir()
        ]
        return [b for b in branches if b.startswith(incomplete)]
    except Exception:
        return []


def complete_ticket_ids(incomplete: str) -> List[str]:
    """Provide ticket id completions for 'vibe resume <ticket>'.

    Args:
        incomplete: The partial ticket id typed so far

    Returns:
        List of matching resumable ticket ids from the NSProject board
    """
    try:
        return [
            ticket.id
            for ticket in list_resumable()
            if ticket.id.startswith(incomplete)
        ]
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

    options = ["PowerShell", "WSL"]
    shell_map = {
        0: Shell.POWERSHELL,
        1: Shell.WSL,
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

    options = ["Claude", "Codex", "OpenCode"]
    if powershell:
        tool_map = {
            0: CLAUDE_CODE_DIRECT_CMD,
            1: CODEX_DIRECT_CMD,
            2: OPEN_CODE_DIRECT_CMD,
        }
    else:
        tool_map = {
            0: CLAUDE_CODE_CMD,
            1: CODEX_CMD,
            2: OPEN_CODE_CMD,
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
        worktree_name: Branch name for the worktree (the on-disk directory
            name is the encoded form)
        from_branch: Optional base branch to create from
        repo_name: Name of the repository
        cwd: Current working directory

    Returns:
        True if worktree is ready to use, False on error
    """
    worktree_path = worktree_path_for_branch(
        repo_name, worktree_name, LOCAL_WORKTREE_BASE
    )
    status = check_worktree_exists(
        worktree_name=worktree_name,
        repo_name=repo_name,
        worktree_base=LOCAL_WORKTREE_BASE,
        cwd=cwd,
    )

    if status == WorktreeStatus.EXISTS_INVALID:
        console.print(
            f"[red]Error:[/] Directory exists at "
            f"{worktree_path} "
            f"but is not a git worktree"
        )
        console.print("Please remove the directory or choose a different name")
        return False

    if status == WorktreeStatus.EXISTS_VALID:
        console.print(
            f"Worktree directory already exists at: {worktree_path}"
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


def _run_post_session_cleanup(
    repo_name: str,
    branch: str,
    repo_root: Path,
) -> None:
    """Run post-session worktree cleanup for a worktree-backed session.

    Called after every worktree session exits: if the session was parked (its
    worktree tip is a 'wip: park' marker) and the tree is clean, the worktree is
    removed (it is reconstructed from the branch on resume).

    Args:
        repo_name: Name of the repository
        branch: Real branch name of the session's worktree
        repo_root: Path to the main repository root
    """
    post_session_cleanup(
        repo_name,
        branch,
        repo_root,
        worktree_base=LOCAL_WORKTREE_BASE,
    )


def _print_available_tickets() -> None:
    """Print the ids of resumable tickets on the NSProject board."""
    tickets = list_resumable()
    if not tickets:
        console.print(
            "[dim]No resumable tickets found on the NSProject board[/dim]"
        )
        return

    console.print("Resumable tickets:")
    for ticket in tickets:
        # Ids and titles come from hand-editable files: escape them so
        # bracketed text is never interpreted as Rich markup
        marker = "parked" if ticket.parked else "in progress"
        console.print(
            f"  {escape(ticket.id)}  [dim]({marker})[/dim] "
            f"{escape(ticket.title)}"
        )


def _resolve_resume_tool(
    oc: bool,
    codex: bool,
    claude: bool,
    ticket_tool: Optional[str],
    powershell: bool,
) -> tuple[Optional[str], str]:
    """Resolve the coding tool for a resume launch.

    CLI flags take precedence over the ticket's recorded tool; when neither
    is available the user is prompted interactively.

    Args:
        oc: Whether --oc flag was provided
        codex: Whether --codex flag was provided
        claude: Whether --claude flag was provided
        ticket_tool: The ticket's recorded tool (claude|codex|opencode|None)
        powershell: Whether to use direct commands (for PowerShell)

    Returns:
        Tuple of (tool name or None when unknown, base command string)
    """
    tool_commands = {
        "claude": CLAUDE_CODE_DIRECT_CMD if powershell else CLAUDE_CODE_CMD,
        "codex": CODEX_DIRECT_CMD if powershell else CODEX_CMD,
        "opencode": OPEN_CODE_DIRECT_CMD if powershell else OPEN_CODE_CMD,
    }

    if claude:
        return "claude", tool_commands["claude"]
    if codex:
        return "codex", tool_commands["codex"]
    if oc:
        return "opencode", tool_commands["opencode"]
    if ticket_tool in tool_commands:
        return ticket_tool, tool_commands[ticket_tool]

    command = prompt_coding_tool_choice(powershell=powershell)
    for name, tool_command in tool_commands.items():
        if tool_command == command:
            return name, command
    return None, command


def _build_resume_command(
    base_cmd: str,
    tool_name: Optional[str],
    work: ParkedWork,
    powershell: bool,
    use_session: bool = True,
) -> tuple[str, bool]:
    """Build the coding tool command string for a resume launch.

    Claude resumes its recorded session via --resume when the work entry
    carries a safe session id; otherwise a fresh Claude session is seeded
    with the fixed bootstrap prompt. Non-Claude tools always launch fresh
    with no arguments (no session restore, no bootstrap prompt —
    docs/nsproject-park.md §7).

    Args:
        base_cmd: Base coding tool command
        tool_name: Resolved tool name (claude|codex|opencode|None)
        work: The parked work being resumed
        powershell: Whether the remote shell is PowerShell
        use_session: Whether to attempt resuming the recorded session

    Returns:
        Tuple of (command string, True when the command resumes a session)
    """
    if powershell:
        # Windows quoting / PowerShell arg-threading is explicitly out of
        # scope for v1: launch the direct command with no appended
        # arguments.
        return base_cmd, False

    if tool_name != "claude":
        return base_cmd, False

    session_id = work.session_id
    if use_session and session_id is not None and is_safe_session_id(session_id):
        return f"{base_cmd} --resume {session_id}", True

    if is_safe_ticket_id(work.id):
        prompt = RESUME_BOOTSTRAP_PROMPT.format(ticket_id=work.id)
        return f"{base_cmd} {shlex.quote(prompt)}", False

    return base_cmd, False


def _launch_resume(
    work: ParkedWork,
    tool_name: Optional[str],
    base_cmd: str,
    powershell: bool,
    launch: Callable[[str], int],
    seed_fresh: bool = False,
) -> int:
    """Launch the coding tool for a resume, degrading on stale sessions.

    When a Claude session resume exits non-zero, the recorded session id
    may be stale; the user is offered a single fresh relaunch seeded with
    the bootstrap prompt (docs/nsproject-park.md §7). When ``seed_fresh`` is
    set (cross-dev / branch unavailable locally) the session is never
    attempted — the launch goes straight to the bootstrap prompt.

    Args:
        work: The parked work being resumed
        tool_name: Resolved tool name (claude|codex|opencode|None)
        base_cmd: Base coding tool command
        powershell: Whether the remote shell is PowerShell
        launch: Callable that runs a tool command and returns its exit code
        seed_fresh: Skip session restore and seed the bootstrap prompt

    Returns:
        Exit code of the (re)launched session
    """
    command, used_resume = _build_resume_command(
        base_cmd, tool_name, work, powershell, use_session=not seed_fresh
    )
    exit_code = launch(command)

    if used_resume and exit_code != 0:
        console.print(
            f"[yellow]Warning:[/] Resuming session '{work.session_id}' "
            f"exited with code {exit_code}; the recorded session id may "
            "be stale."
        )
        if typer.confirm("Relaunch with a fresh session?", default=True):
            command, _ = _build_resume_command(
                base_cmd, tool_name, work, powershell, use_session=False
            )
            exit_code = launch(command)

    return exit_code


def _unwind_if_park_marker(worktree_path: Path, ticket_id: str) -> None:
    """Unwind a park commit when — and only when — the tip is the marker.

    The tip commit subject must equal exactly 'wip: park <ticket_id>'
    (whitespace-trimmed) for this ticket; any other tip (including another
    ticket's park marker) is never unwound. The unwind is a mixed
    'git reset HEAD~1' restoring park-time working-tree state.

    Args:
        worktree_path: Path to the worktree to inspect
        ticket_id: Id of the ticket being resumed
    """
    subject = get_tip_commit_subject(worktree_path)
    if subject is None or subject.strip() != f"wip: park {ticket_id}":
        return

    console.print(f"Unwinding park commit 'wip: park {ticket_id}'...")
    if not unwind_park_commit(worktree_path):
        console.print(
            "[yellow]Warning:[/] Failed to unwind the park commit; "
            "continuing with the worktree as-is"
        )


@dataclass
class ResumeTarget:
    """Where a resumed session should run.

    Attributes:
        path: Directory to unwind in and launch the tool from.
        is_worktree: True when ``path`` is a managed worktree (run
            post-session cleanup after); False when resuming in place on the
            repo's main checkout.
        fresh: True when there is no local code state to restore (the branch
            is unavailable on this machine — typically cross-dev). The launch
            skips the unwind and seeds a fresh session from the handoff note.
    """

    path: Path
    is_worktree: bool
    fresh: bool = False


class StrandedBranchChoice(Enum):
    """User's choice when a ticket's branch is stranded on the main checkout."""

    SWITCH = "switch"  # move the main checkout off the branch, create a worktree
    IN_PLACE = "in_place"  # resume in the main checkout as it stands
    ABORT = "abort"  # do nothing


def prompt_stranded_branch_choice(
    branch: str,
    target_branch: str,
    main_dirty: bool,
) -> StrandedBranchChoice:
    """Prompt for how to recover a branch stranded on the main checkout.

    When the main checkout is clean the default (and recommended) action is
    to switch it back to ``target_branch`` and create a fresh worktree. When
    it has uncommitted changes the switch is unsafe and is not offered.

    Args:
        branch: The stranded branch name
        target_branch: Branch the main checkout would be switched back to
        main_dirty: Whether the main checkout has uncommitted changes

    Returns:
        The selected StrandedBranchChoice (ABORT if cancelled)
    """
    from simple_term_menu import TerminalMenu

    if main_dirty:
        options = [
            "Resume in the main checkout as-is (keeps its uncommitted changes)",
            "Abort",
        ]
        choices = [StrandedBranchChoice.IN_PLACE, StrandedBranchChoice.ABORT]
    else:
        options = [
            f"Switch the main checkout back to '{target_branch}' and "
            f"create a worktree for '{branch}' (recommended)",
            "Resume in the main checkout as-is (no worktree)",
            "Abort",
        ]
        choices = [
            StrandedBranchChoice.SWITCH,
            StrandedBranchChoice.IN_PLACE,
            StrandedBranchChoice.ABORT,
        ]

    console.print("\n[bold]How would you like to resume?[/bold]")
    menu = TerminalMenu(options, cursor_index=0)
    index = menu.show()
    if index is None:
        return StrandedBranchChoice.ABORT
    return choices[index]


def _resolve_switchback_branch(work: ParkedWork, repo_root: Path) -> str | None:
    """Pick a branch to move a stranded main checkout back to.

    Prefers the work entry's recorded ``base_branch`` when it exists locally,
    then the repository's detected default branch, then a plain 'main' or
    'master' if either exists.

    Args:
        work: The parked work being resumed
        repo_root: Path to the main repository root

    Returns:
        A local branch name to switch to, or None if none could be resolved
    """
    base = work.base_branch
    if base and branch_exists_local(base, cwd=repo_root):
        return base

    default = get_default_branch(cwd=repo_root)
    if default and branch_exists_local(default, cwd=repo_root):
        return default

    for candidate in ("main", "master"):
        if branch_exists_local(candidate, cwd=repo_root):
            return candidate
    return None


def _recover_stranded_branch(
    work: ParkedWork,
    repo_root: Path,
    branch: str,
    worktree_path: Path,
) -> ResumeTarget | None:
    """Recover a branch checked out on the main checkout (interrupted park).

    Notifies, then prompts for one of: switch the main checkout back and
    create a worktree, resume in place on the main checkout, or abort.

    Args:
        work: The parked work being resumed
        repo_root: Path to the main repository root
        branch: The stranded branch name
        worktree_path: Where the managed worktree would live

    Returns:
        A ResumeTarget, or None when the user aborts.

    Raises:
        typer.Exit: When the chosen recovery cannot be completed
    """
    repo = work.repo_name
    main_dirty = has_uncommitted_changes(repo_root)
    target_branch = _resolve_switchback_branch(work, repo_root)

    console.print(
        f"[yellow]Heads up:[/] branch '{branch}' is still checked out on the "
        f"main checkout at {repo_root}."
    )
    console.print(
        "An earlier park didn't finish switching it back (e.g. an "
        "interrupted session), so a worktree can't be created for it yet."
    )
    if main_dirty:
        console.print(
            "The main checkout also has uncommitted changes, so it can't be "
            "switched automatically."
        )

    choice = prompt_stranded_branch_choice(branch, target_branch or "?", main_dirty)

    if choice == StrandedBranchChoice.ABORT:
        console.print("Aborted — nothing changed.")
        return None

    if choice == StrandedBranchChoice.IN_PLACE:
        console.print(f"Resuming in the main checkout at {repo_root}...")
        return ResumeTarget(path=repo_root, is_worktree=False)

    # SWITCH: move the main checkout off the branch, then create the worktree.
    if target_branch is None:
        console.print(
            "[red]Error:[/] Could not determine a branch to switch the main "
            "checkout back to. Switch it manually, then retry the resume."
        )
        raise typer.Exit(1)

    console.print(f"Switching the main checkout back to '{target_branch}'...")
    if not switch_checkout_to_branch(repo_root, target_branch):
        console.print(
            f"[red]Error:[/] Failed to switch the main checkout to "
            f"'{target_branch}'. Resolve it manually, then retry the resume."
        )
        raise typer.Exit(1)

    try:
        console.print(f"Recreating worktree for branch '{branch}'...")
        create_worktree(
            worktree_name=branch,
            repo_name=repo,
            worktree_base=LOCAL_WORKTREE_BASE,
            cwd=repo_root,
        )
    except RuntimeError as e:
        console.print(f"[red]Error:[/] {e}")
        raise typer.Exit(1)

    return ResumeTarget(path=worktree_path, is_worktree=True)


def _ensure_resume_worktree(
    work: ParkedWork,
    repo_root: Path,
    branch: str,
) -> ResumeTarget | None:
    """Resolve where a branch-backed ticket should resume.

    Reuses a valid existing worktree; recreates a missing one from the
    local branch, or from origin/<branch> when only the remote branch
    exists. Recovers a branch stranded on the main checkout after an
    interrupted park (prompting the user), and prunes stale worktree
    registrations. When the branch exists neither locally nor on origin
    (typically cross-dev — the parker never pushed it), falls back to a
    fresh session in the main checkout rather than erroring. Errors loudly
    only when the directory is not a worktree or the branch is held by
    another live worktree.

    Args:
        work: The parked work being resumed
        repo_root: Path to the main repository root
        branch: Real branch name (may contain '/')

    Returns:
        The resolved ResumeTarget, or None when the user aborts recovery.

    Raises:
        typer.Exit: When the worktree or branch cannot be resolved
    """
    repo = work.repo_name
    worktree_path = worktree_path_for_branch(repo, branch, LOCAL_WORKTREE_BASE)
    status = check_worktree_exists(
        worktree_name=branch,
        repo_name=repo,
        worktree_base=LOCAL_WORKTREE_BASE,
        cwd=repo_root,
    )

    if status == WorktreeStatus.EXISTS_INVALID:
        console.print(
            f"[red]Error:[/] Directory exists at {worktree_path} "
            "but is not a git worktree"
        )
        console.print("Please remove the directory, then retry the resume")
        raise typer.Exit(1)

    if status == WorktreeStatus.EXISTS_VALID:
        return ResumeTarget(path=worktree_path, is_worktree=True)

    # NOT_EXISTS: recreate from the local or remote branch.
    try:
        if branch_exists_local(branch, cwd=repo_root):
            # The branch may be stranded — checked out somewhere git knows
            # about but not usable as our worktree (interrupted park, or a
            # stale registration after a deleted worktree dir).
            checkout = find_branch_checkout(branch, cwd=repo_root)
            if checkout is not None:
                resolved = checkout.resolve()
                if not resolved.exists():
                    # Registered to a directory that no longer exists (our
                    # worktree path or any other) — prune frees the branch.
                    console.print(
                        "Pruning a stale worktree registration for "
                        f"branch '{branch}'..."
                    )
                    prune_worktrees(cwd=repo_root)
                elif resolved == repo_root.resolve():
                    return _recover_stranded_branch(
                        work, repo_root, branch, worktree_path
                    )
                elif resolved != worktree_path.resolve():
                    console.print(
                        f"[red]Error:[/] Branch '{branch}' is already checked "
                        f"out at {resolved}."
                    )
                    console.print(
                        "Free that worktree (or remove it), then retry the "
                        "resume."
                    )
                    raise typer.Exit(1)

            console.print(f"Recreating worktree for branch '{branch}'...")
            create_worktree(
                worktree_name=branch,
                repo_name=repo,
                worktree_base=LOCAL_WORKTREE_BASE,
                cwd=repo_root,
            )
        elif branch_exists_remote(branch, cwd=repo_root):
            console.print(
                f"Branch '{branch}' only exists on origin, "
                "creating a tracking worktree..."
            )
            create_worktree(
                worktree_name=f"origin/{branch}",
                repo_name=repo,
                worktree_base=LOCAL_WORKTREE_BASE,
                cwd=repo_root,
            )
        else:
            # The branch is on neither this machine nor origin. Most often
            # the parker never pushed it (cross-dev resume): there is no code
            # state to restore here, so launch a fresh session in the main
            # checkout seeded from the ticket's "Where I left off" rather than
            # erroring (docs/nsproject-park.md §7).
            console.print(
                f"[yellow]Heads up:[/] branch '{branch}' for ticket "
                f"'{work.id}' isn't on this machine or on origin "
                "(the parked branch may not have been pushed)."
            )
            console.print(
                "Starting a fresh session in the main checkout — read the "
                'ticket\'s "Where I left off" to continue.'
            )
            return ResumeTarget(path=repo_root, is_worktree=False, fresh=True)
    except RuntimeError as e:
        console.print(f"[red]Error:[/] {e}")
        raise typer.Exit(1)

    return ResumeTarget(path=worktree_path, is_worktree=True)


def _handle_resume(
    ticket_id: Optional[str],
    oc: bool,
    codex: bool,
    claude: bool,
    local: bool,
) -> None:
    """Handle 'vibe resume <ticket>': pick a piece of work back up.

    Reads the parked-work snapshot from the NSProject board, reconstructs or
    reuses the work branch's worktree, unwinds the park commit only when the
    tip is this ticket's marker, launches the tool, and clears the board's
    `parked_at` marker. When the branch isn't available locally (cross-dev),
    launches a fresh session in the main checkout seeded from the handoff.

    Args:
        ticket_id: NSProject ticket id from the command line (None when omitted)
        oc: Whether --oc flag was provided
        codex: Whether --codex flag was provided
        claude: Whether --claude flag was provided
        local: Whether --local flag was provided

    Raises:
        typer.Exit: Always — with the session's exit code, or 1 on errors
    """
    if ticket_id is None:
        console.print("[red]Error:[/] 'vibe resume' requires a ticket id")
        console.print("Usage: vibe resume <ticket-id>")
        _print_available_tickets()
        raise typer.Exit(1)

    board = find_board()
    if board is None:
        console.print("[red]Error:[/] Could not find the NSProject board.")
        console.print(
            "Set NSPROJECT_BOARD to the board root (the directory holding "
            "CLAUDE.md and data/)."
        )
        raise typer.Exit(1)

    work = find_parked_work(ticket_id, board=board)
    if work is None:
        console.print(
            f"[red]Error:[/] No resumable work found for ticket '{ticket_id}'"
        )
        _print_available_tickets()
        raise typer.Exit(1)

    repo_root = work.repo_path
    if not repo_root.is_dir():
        console.print(
            f"[red]Error:[/] Local checkout for ticket '{work.id}' not found "
            f"at {repo_root}"
        )
        raise typer.Exit(1)
    if not validate_git_repo(repo_root):
        console.print(
            f"[red]Error:[/] {repo_root} exists but is not a git repository"
        )
        raise typer.Exit(1)

    remote_shell = None if local else _resolve_remote_shell()
    is_powershell = remote_shell == Shell.POWERSHELL
    tool_name, base_cmd = _resolve_resume_tool(
        oc, codex, claude, work.tool, is_powershell
    )

    branch = work.branch
    if branch is None:
        # A parked work entry always records its branch; one without is
        # malformed and cannot be resumed.
        console.print(
            f"[red]Error:[/] Ticket '{work.id}' has no recorded branch and "
            "cannot be resumed (a parked work entry always records a branch)."
        )
        raise typer.Exit(1)

    # Reuse or recreate the worktree (or fall back to a fresh main-checkout
    # session cross-dev); unwind only if the tip is this ticket's park marker.
    target = _ensure_resume_worktree(work, repo_root, branch)
    if target is None:
        raise typer.Exit(1)  # user aborted recovery
    if not target.fresh:
        _unwind_if_park_marker(target.path, work.id)

    # The work is active again: clear the board's parked marker. Best-effort —
    # a board write/push failure warns but never blocks the resume.
    mark_resumed(work)

    console.print(f"Resuming ticket '{work.id}' on branch '{branch}'...")
    repo = work.repo_name
    if target.is_worktree:
        if local:
            def launch(command: str) -> int:
                return connect_locally(target.path, coding_tool=command)
        else:
            def launch(command: str) -> int:
                return connect_to_remote(
                    repo_name=repo,
                    worktree_name=branch_to_worktree_dirname(branch),
                    with_coding_tool=True,
                    coding_tool=command,
                    remote_shell=remote_shell,
                )
    else:
        # Resuming on the main checkout (stranded-branch in-place, or a
        # cross-dev fresh start): no managed worktree, so no post-session
        # cleanup.
        remote_main = REMOTE_REPO_BASE / repo

        if local:
            def launch(command: str) -> int:
                return connect_locally(repo_root, coding_tool=command)
        else:
            def launch(command: str) -> int:
                return connect_to_remote_path(
                    remote_path=remote_main,
                    with_coding_tool=True,
                    coding_tool=command,
                    remote_shell=remote_shell,
                )

    exit_code = _launch_resume(
        work, tool_name, base_cmd, is_powershell, launch, seed_fresh=target.fresh
    )
    if target.is_worktree:
        _run_post_session_cleanup(repo, branch, repo_root)
    raise typer.Exit(exit_code)


@app.command(
    context_settings={"help_option_names": ["-h", "--help"]},
)
def main(
    ctx: typer.Context,
    branch: Optional[str] = typer.Argument(
        None,
        help="Branch name for the worktree. Creates worktree and connects to it. "
        "Use the literal 'resume' to resume an NSProject ticket.",
        autocompletion=complete_branches,
    ),
    ticket: Optional[str] = typer.Argument(
        None,
        help="Ticket id for 'vibe resume <ticket>'. Only valid after 'resume'.",
        autocompletion=complete_ticket_ids,
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
        vibe resume BZL_q7m2x             # Resume parked work from the NSProject board
        vibe resume BZL_q7m2x --local     # Resume parked work locally
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

    # Handle 'vibe resume <ticket>' — the literal 'resume' as first
    # positional routes to the NSProject resume flow
    if branch == "resume":
        _handle_resume(ticket, oc=oc, codex=codex, claude=claude, local=local)
        return  # pragma: no cover — _handle_resume always raises typer.Exit

    # A second positional is only valid as 'vibe resume <ticket-id>'
    if ticket is not None:
        console.print(f"[red]Error:[/red] Unexpected argument '{ticket}'")
        console.print(
            "A second argument is only valid as: vibe resume <ticket-id>"
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
            repo_root=repo_info.main_root,
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
            worktree_name=branch_to_worktree_dirname(branch),
            with_coding_tool=False,
            remote_shell=remote_shell,
        )
        _run_post_session_cleanup(repo_info.name, branch, repo_info.main_root)
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
        worktree_path = worktree_path_for_branch(
            repo_info.name, branch, LOCAL_WORKTREE_BASE
        )
        exit_code = connect_locally(worktree_path, coding_tool=coding_tool)
        _run_post_session_cleanup(repo_info.name, branch, repo_info.main_root)
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
        if (
            context.context_type == ContextType.WORKTREE
            and context.repo_name is not None
            and context.branch is not None
        ):
            _run_post_session_cleanup(
                context.repo_name,
                context.branch,
                LOCAL_REPO_BASE / context.repo_name,
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
        worktree_name=branch_to_worktree_dirname(branch),
        with_coding_tool=True,
        coding_tool=coding_tool,
        remote_shell=remote_shell,
    )
    _run_post_session_cleanup(repo_info.name, branch, repo_info.main_root)
    raise typer.Exit(exit_code)


if __name__ == "__main__":
    app()
