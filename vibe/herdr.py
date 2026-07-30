"""herdr integration — agent hinting and pane hygiene.

[herdr](https://herdr.dev) classifies a pane's agent by scanning the foreground
process group, picking an *eligible* process and matching that agent's screen
manifest against the terminal. Shells, `sleep` and — crucially — `ssh` are not
eligible, so a pane where vibe has SSH'd into a VM looks like nothing at all.

`HERDR_AGENT` names the manifest to use, but only when set on the eligible
process. vibe itself (python) is the eligible process in that group, so the hint
has to be on *vibe*, not on the ssh child it spawns. macOS reads another
process's environment from its exec-time image, which means assigning to
`os.environ` at runtime is invisible to herdr — vibe has to be re-exec'd with
the variable already set.

Requires herdr 0.7.5+ on macOS (0.7.1+ on Linux); older builds ignore the hint.
"""

from __future__ import annotations

import os
import shlex
import shutil
import sys
from pathlib import Path

from vibe.config import (
    CLAUDE_CODE_CMD,
    CLAUDE_CODE_DIRECT_CMD,
    CODEX_CMD,
    CODEX_DIRECT_CMD,
    OPEN_CODE_CMD,
    OPEN_CODE_DIRECT_CMD,
)
from vibe.utils import console

# Names the manifest herdr should match this pane against. Never export it from
# a shell profile, or every inherited foreground process is treated as that
# agent; setting it for a single invocation is supported and wins over vibe's
# own mapping.
HERDR_AGENT_ENV = "HERDR_AGENT"

# Markers herdr exports into every pane; any of them means vibe is inside herdr.
HERDR_ENV_MARKERS = ("HERDR_ENV", "HERDR_SOCKET_PATH", "HERDR_SESSION")

# Carries the resolved coding tool across the re-exec that sets HERDR_AGENT, so
# the interactive tool picker does not run a second time.
VIBE_CODING_TOOL_ENV = "VIBE_CODING_TOOL"

# Cursor home, erase display, erase scrollback. herdr's detection buffer is
# purged by the erase-display (`2J`) part — erase-scrollback (`3J`) alone leaves
# it intact — but the full sequence is what a real terminal expects, so all
# three are sent.
CLEAR_SEQUENCE = "\033[H\033[2J\033[3J"


def _cmd_head(command: str) -> str:
    """Return the executable name of a coding tool command.

    Args:
        command: Full tool command, possibly with arguments
            (e.g. 'cly --resume abc123')

    Returns:
        The leading executable token (e.g. 'cly'), or the input unchanged when
        it cannot be split.
    """
    parts = shlex.split(command)
    return parts[0] if parts else command


# Maps a coding tool executable to the herdr agent manifest it should be
# detected as. Keyed by executable so tool commands carrying arguments (the
# --resume forms, the PowerShell direct commands) resolve too. Check the names
# your herdr build ships with `herdr server agent-manifests` if a pane stays
# unrecognised.
HERDR_AGENT_NAMES: dict[str, str] = {
    _cmd_head(CLAUDE_CODE_CMD): "claude",
    _cmd_head(CLAUDE_CODE_DIRECT_CMD): "claude",
    _cmd_head(CODEX_CMD): "codex",
    _cmd_head(CODEX_DIRECT_CMD): "codex",
    _cmd_head(OPEN_CODE_CMD): "opencode",
    _cmd_head(OPEN_CODE_DIRECT_CMD): "opencode",
}


def in_herdr(env: dict[str, str] | None = None) -> bool:
    """Report whether vibe is running inside a herdr pane.

    Args:
        env: Environment to inspect. Defaults to os.environ.

    Returns:
        True when herdr's pane environment is present.
    """
    source = os.environ if env is None else env
    return any(source.get(marker) for marker in HERDR_ENV_MARKERS)


def resolve_agent(coding_tool: str) -> str | None:
    """Resolve the herdr agent manifest name for a coding tool.

    Args:
        coding_tool: Command vibe launches (may carry arguments, e.g.
            'cly --resume abc123')

    Returns:
        The herdr agent name to hint (e.g. 'claude'), or None for a tool with
        no known manifest.
    """
    return HERDR_AGENT_NAMES.get(_cmd_head(coding_tool))


def clear_pane() -> None:
    """Clear the pane so nothing of ours sits above the agent.

    herdr's screen rules match against the pane's recent buffer, so whatever was
    on screen before the agent started is still evaluated. That is not cosmetic:
    Codex's `weak_blocker` rule looks for a prompt phrase anywhere in that buffer
    alongside a `yes` or a `❯`, and a shell prompt left above the agent supplies
    the `❯` — pinning the session at `blocked` for as long as it runs.

    Only clears inside herdr; elsewhere vibe's output is left alone.
    """
    if not in_herdr():
        return

    sys.stdout.write(CLEAR_SEQUENCE)
    sys.stdout.flush()


def _reexec_argv() -> list[str]:
    """Build the argv that re-runs this vibe invocation.

    Returns:
        Command list suitable for os.execv, covering the installed console
        script, `python -m vibe`, and a directly-run .py entry point.
    """
    argv0 = sys.argv[0]
    name = Path(argv0).name

    # `python -m vibe`: re-enter the same way, since running __main__.py as a
    # plain file would not put the package on sys.path.
    if name == "__main__.py":
        return [sys.executable, "-m", "vibe", *sys.argv[1:]]

    # A plain script path is not necessarily executable and may have no
    # shebang, so hand it to the interpreter rather than exec'ing it directly.
    if name.endswith(".py"):
        return [sys.executable, argv0, *sys.argv[1:]]

    return [shutil.which(argv0) or argv0, *sys.argv[1:]]


def ensure_agent_hint(coding_tool: str) -> None:
    """Re-exec vibe with HERDR_AGENT set so herdr can classify this pane.

    Does nothing outside herdr, for a tool with no known manifest, or when
    HERDR_AGENT is already set — which both stops the re-exec looping and lets
    `HERDR_AGENT=<name> vibe ...` override vibe's mapping without one. The
    resolved tool is carried across so the picker does not run twice.

    Args:
        coding_tool: Command vibe is about to launch
    """
    if os.environ.get(HERDR_AGENT_ENV) or not in_herdr():
        return

    agent = resolve_agent(coding_tool)
    if agent is None:
        return

    os.environ[HERDR_AGENT_ENV] = agent
    os.environ[VIBE_CODING_TOOL_ENV] = coding_tool

    argv = _reexec_argv()
    try:
        os.execv(argv[0], argv)
    except OSError as error:
        # The hint is a nicety; losing it must never stop the session from
        # starting. Carry on unhinted in this process.
        console.print(
            f"[yellow]Warning:[/] could not set the herdr agent hint: "
            f"{(error.strerror or error)}"
        )
        os.environ.pop(VIBE_CODING_TOOL_ENV, None)
