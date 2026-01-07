"""Connection handling for remote and local development."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from vibe.config import (
    CODING_TOOL_CMD,
    REMOTE_WORKTREE_BASE,
    SSH_KEY_PATH,
    SSH_USER_HOST,
)
from vibe.utils import console

# Default timeout for SSH connection attempts (seconds)
SSH_TIMEOUT = 30


def validate_ssh_key(ssh_key: Path) -> bool:
    """Validate that SSH key exists and has correct permissions.

    Args:
        ssh_key: Path to SSH private key

    Returns:
        True if key is valid, False otherwise
    """
    if not ssh_key.exists():
        console.print(f"[red]Error:[/] SSH key not found: {ssh_key}")
        return False
    return True


def escape_shell_path(path: Path) -> str:
    """Escape a path for safe use in shell commands.

    Args:
        path: Path to escape

    Returns:
        Shell-escaped path string
    """
    return shlex.quote(str(path))


def build_ssh_command(
    ssh_key: Path = SSH_KEY_PATH,
    user_host: str = SSH_USER_HOST,
) -> list[str]:
    """Build the base SSH command with key authentication.

    Args:
        ssh_key: Path to SSH private key
        user_host: SSH user@host string

    Returns:
        List of command arguments for SSH
    """
    return ["ssh", "-i", str(ssh_key), user_host, "-t"]


def build_remote_setup_commands(
    worktree_path: Path,
    unlock_keychain: bool = True,
) -> str:
    """Build the shell commands to run on remote machine.

    Args:
        worktree_path: Remote path to the worktree
        unlock_keychain: Whether to unlock the macOS keychain

    Returns:
        Shell command string to execute remotely
    """
    # Use proper shell escaping for the path
    escaped_path = escape_shell_path(worktree_path)
    commands = [f"cd {escaped_path}"]

    if unlock_keychain:
        commands.append(
            "security -v unlock-keychain -p admin ~/Library/Keychains/login.keychain-db"
        )

    # Create temporary directory to avoid permission issues
    commands.append("export TMPDIR=$(mktemp -d)")

    return " && ".join(commands)


def connect_to_remote(
    repo_name: str,
    worktree_name: str,
    with_coding_tool: bool = True,
    ssh_key: Path = SSH_KEY_PATH,
    user_host: str = SSH_USER_HOST,
    remote_base: Path = REMOTE_WORKTREE_BASE,
    coding_tool: str = CODING_TOOL_CMD,
) -> int:
    """Connect to remote machine via SSH.

    Args:
        repo_name: Name of the repository
        worktree_name: Name of the worktree
        with_coding_tool: Whether to start the coding tool (cly) or just shell
        ssh_key: Path to SSH private key
        user_host: SSH user@host string
        remote_base: Remote base path for worktrees
        coding_tool: Command to run for coding tool

    Returns:
        Exit code from SSH command (255 typically indicates SSH failure)
    """
    # Validate SSH key exists
    if not validate_ssh_key(ssh_key):
        return 1

    remote_path = remote_base / repo_name / worktree_name

    if with_coding_tool:
        console.print(f"Connecting to {user_host} and starting {coding_tool}...")
    else:
        console.print(f"Connecting to {user_host} and navigating to worktree...")

    # Build the setup commands
    setup = build_remote_setup_commands(remote_path)

    # Build the full remote command - escape the coding tool name
    if with_coding_tool:
        escaped_tool = shlex.quote(coding_tool)
        remote_cmd = f'{setup} && zsh -l -i -c {escaped_tool}'
    else:
        remote_cmd = f"{setup} && zsh -l -i"

    # Build and execute SSH command
    ssh_cmd = build_ssh_command(ssh_key, user_host)
    ssh_cmd.append(remote_cmd)

    result = subprocess.run(ssh_cmd)

    # Provide helpful error messages for common SSH failures
    if result.returncode == 255:
        console.print()
        console.print("[red]SSH connection failed.[/] Common causes:")
        console.print(f"  - Host '{user_host}' is unreachable")
        console.print(f"  - SSH key '{ssh_key}' is not authorized")
        console.print("  - Network connectivity issues")

    return result.returncode


def connect_to_remote_home(
    ssh_key: Path = SSH_KEY_PATH,
    user_host: str = SSH_USER_HOST,
) -> int:
    """Connect to remote machine's home directory via SSH.

    Args:
        ssh_key: Path to SSH private key
        user_host: SSH user@host string

    Returns:
        Exit code from SSH command (255 typically indicates SSH failure)
    """
    # Validate SSH key exists
    if not validate_ssh_key(ssh_key):
        return 1

    console.print(f"Connecting to {user_host}...")

    # Build SSH command with just shell startup
    ssh_cmd = build_ssh_command(ssh_key, user_host)
    ssh_cmd.append("export TMPDIR=$(mktemp -d) && zsh -l -i")

    result = subprocess.run(ssh_cmd)

    # Provide helpful error messages for common SSH failures
    if result.returncode == 255:
        console.print()
        console.print("[red]SSH connection failed.[/] Common causes:")
        console.print(f"  - Host '{user_host}' is unreachable")
        console.print(f"  - SSH key '{ssh_key}' is not authorized")
        console.print("  - Network connectivity issues")

    return result.returncode


def connect_locally(
    worktree_path: Path,
    coding_tool: str = CODING_TOOL_CMD,
) -> int:
    """Run the coding tool locally in the worktree.

    Args:
        worktree_path: Path to the local worktree
        coding_tool: Command to run for coding tool

    Returns:
        Exit code from the coding tool
    """
    console.print(f"Switching to local worktree and starting {coding_tool}...")

    # Verify worktree exists
    if not worktree_path.is_dir():
        console.print(f"[red]Error:[/] Worktree path does not exist: {worktree_path}")
        return 1

    # Run the coding tool in the worktree directory
    result = subprocess.run([coding_tool], cwd=worktree_path)

    console.print("Returning to original directory...")
    return result.returncode


def connect_to_remote_path(
    remote_path: Path,
    with_coding_tool: bool = True,
    ssh_key: Path = SSH_KEY_PATH,
    user_host: str = SSH_USER_HOST,
    coding_tool: str = CODING_TOOL_CMD,
) -> int:
    """Connect to a specific remote path via SSH.

    This can be used to connect to either a main repository or a worktree.

    Args:
        remote_path: Remote path to connect to
        with_coding_tool: Whether to start the coding tool or just shell
        ssh_key: Path to SSH private key
        user_host: SSH user@host string
        coding_tool: Command to run for coding tool

    Returns:
        Exit code from SSH command (255 typically indicates SSH failure)
    """
    # Validate SSH key exists
    if not validate_ssh_key(ssh_key):
        return 1

    if with_coding_tool:
        console.print(f"Connecting to {user_host} and starting {coding_tool}...")
    else:
        console.print(f"Connecting to {user_host}...")

    # Build the setup commands
    setup = build_remote_setup_commands(remote_path)

    # Build the full remote command
    if with_coding_tool:
        escaped_tool = shlex.quote(coding_tool)
        remote_cmd = f'{setup} && zsh -l -i -c {escaped_tool}'
    else:
        remote_cmd = f"{setup} && zsh -l -i"

    # Build and execute SSH command
    ssh_cmd = build_ssh_command(ssh_key, user_host)
    ssh_cmd.append(remote_cmd)

    result = subprocess.run(ssh_cmd)

    # Provide helpful error messages for common SSH failures
    if result.returncode == 255:
        console.print()
        console.print("[red]SSH connection failed.[/] Common causes:")
        console.print(f"  - Host '{user_host}' is unreachable")
        console.print(f"  - SSH key '{ssh_key}' is not authorized")
        console.print("  - Network connectivity issues")

    return result.returncode
