"""Tests for connection module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from vibe.connection import (
    _build_remote_cmd_for_path,
    _wrap_for_powershell,
    _wrap_for_wsl,
    build_remote_setup_commands,
    build_ssh_command,
    connect_locally,
    connect_to_remote,
    connect_to_remote_home,
    connect_to_remote_path,
    escape_shell_path,
    validate_ssh_key,
)
from vibe.platform import Shell


class TestValidateSshKey:
    """Tests for validate_ssh_key function."""

    def test_returns_true_when_key_exists(self, tmp_path: Path) -> None:
        """Should return True when SSH key exists."""
        key_path = tmp_path / "id_test"
        key_path.write_text("fake key content")

        assert validate_ssh_key(key_path) is True

    def test_returns_false_when_key_missing(self, tmp_path: Path) -> None:
        """Should return False when SSH key doesn't exist."""
        key_path = tmp_path / "nonexistent_key"

        assert validate_ssh_key(key_path) is False


class TestEscapeShellPath:
    """Tests for escape_shell_path function."""

    def test_escapes_simple_path(self) -> None:
        """Should handle simple paths."""
        result = escape_shell_path(Path("/simple/path"))
        # shlex.quote only adds quotes if needed
        assert "/simple/path" in result

    def test_escapes_path_with_spaces(self) -> None:
        """Should properly escape paths with spaces."""
        result = escape_shell_path(Path("/path/with spaces/dir"))
        assert "with spaces" in result
        # Should be properly quoted
        assert result.startswith("'") or result.startswith('"')

    def test_escapes_path_with_quotes(self) -> None:
        """Should escape paths containing quotes."""
        result = escape_shell_path(Path("/path/with'quote"))
        # shlex.quote escapes single quotes properly
        assert "quote" in result


class TestBuildSshCommand:
    """Tests for build_ssh_command function."""

    def test_builds_correct_command(self) -> None:
        """Should build SSH command with correct arguments."""
        cmd = build_ssh_command(
            ssh_key=Path("/path/to/key"),
            user_host="user@host.local",
        )

        assert cmd == ["ssh", "-i", "/path/to/key", "user@host.local", "-t"]

    def test_uses_home_expansion_for_key(self, tmp_path: Path) -> None:
        """Should handle path objects correctly."""
        key_path = tmp_path / "test_key"
        cmd = build_ssh_command(ssh_key=key_path, user_host="test@test.com")

        assert str(key_path) in cmd


class TestBuildRemoteSetupCommands:
    """Tests for build_remote_setup_commands function."""

    def test_includes_cd_command(self) -> None:
        """Should include cd to worktree path."""
        cmd = build_remote_setup_commands(Path("/remote/path/worktree"))

        # Path is now properly shell-escaped
        assert "cd " in cmd
        assert "/remote/path/worktree" in cmd

    def test_includes_keychain_unlock_by_default(self) -> None:
        """Should include keychain unlock command by default."""
        cmd = build_remote_setup_commands(Path("/remote/path"))

        assert "security -v unlock-keychain" in cmd
        assert "login.keychain-db" in cmd

    def test_can_skip_keychain_unlock(self) -> None:
        """Should skip keychain unlock when disabled."""
        cmd = build_remote_setup_commands(
            Path("/remote/path"),
            unlock_keychain=False,
        )

        assert "security" not in cmd

    def test_skips_keychain_when_command_is_none(self) -> None:
        """Should skip keychain when keychain_command is None."""
        cmd = build_remote_setup_commands(
            Path("/remote/path"),
            unlock_keychain=True,
            keychain_command=None,
        )

        assert "security" not in cmd

    def test_includes_tmpdir_setup(self) -> None:
        """Should include TMPDIR setup."""
        cmd = build_remote_setup_commands(Path("/remote/path"))

        assert "export TMPDIR=$(mktemp -d)" in cmd

    def test_commands_are_chained(self) -> None:
        """Should chain commands with &&."""
        cmd = build_remote_setup_commands(Path("/remote/path"))

        assert " && " in cmd

    def test_uses_custom_keychain_command(self) -> None:
        """Should use custom keychain command when provided."""
        cmd = build_remote_setup_commands(
            Path("/remote/path"),
            unlock_keychain=True,
            keychain_command="custom-keychain-unlock",
        )

        assert "custom-keychain-unlock" in cmd
        assert "security" not in cmd


class TestWrapForWsl:
    """Tests for _wrap_for_wsl helper function."""

    def test_wraps_simple_command(self) -> None:
        """Should wrap command with wsl -e zsh using double quotes."""
        result = _wrap_for_wsl("cd /path && cly")
        assert result == 'wsl -e zsh -l -i -c "cd /path && cly"'

    def test_escapes_double_quotes(self) -> None:
        """Should escape double quotes in inner command."""
        result = _wrap_for_wsl('echo "hello"')
        assert 'wsl -e zsh -l -i -c "echo \\"hello\\""' == result

    def test_preserves_complex_commands(self) -> None:
        """Should preserve complex chained commands."""
        inner = "cd /mnt/repos/myrepo && export TMPDIR=$(mktemp -d) && cly"
        result = _wrap_for_wsl(inner)
        assert "wsl -e zsh -l -i -c" in result
        assert "cd /mnt/repos/myrepo" in result
        assert "TMPDIR" in result
        assert "cly" in result


class TestWrapForPowershell:
    """Tests for _wrap_for_powershell helper function."""

    def test_wraps_simple_command(self) -> None:
        """Should wrap command with powershell -Command."""
        result = _wrap_for_powershell("cd 'Z:\\repo'; claude")
        assert result == 'powershell -Command "cd \'Z:\\repo\'; claude"'

    def test_no_exit_flag(self) -> None:
        """Should include -NoExit when requested."""
        result = _wrap_for_powershell("cd 'Z:\\repo'", no_exit=True)
        assert result == 'powershell -NoExit -Command "cd \'Z:\\repo\'"'

    def test_escapes_double_quotes(self) -> None:
        """Should escape double quotes in inner command."""
        result = _wrap_for_powershell('echo "hello"')
        assert 'powershell -Command "echo \\"hello\\""' == result

    def test_no_exit_false_by_default(self) -> None:
        """Should not include -NoExit by default."""
        result = _wrap_for_powershell("test")
        assert "-NoExit" not in result


class TestBuildRemoteCmdForPath:
    """Tests for _build_remote_cmd_for_path helper function."""

    def test_macos_with_coding_tool(self) -> None:
        """Should build macOS command with coding tool."""
        result = _build_remote_cmd_for_path(
            Path("/remote/repo"), True, "cly", None
        )
        assert "/remote/repo" in result
        assert "cly" in result
        assert "zsh -l -i -c" in result

    def test_macos_without_coding_tool(self) -> None:
        """Should build macOS command with interactive shell."""
        result = _build_remote_cmd_for_path(
            Path("/remote/repo"), False, "cly", None
        )
        assert "zsh -l -i" in result
        assert "cly" not in result

    def test_wsl_with_coding_tool(self) -> None:
        """Should build WSL-wrapped command with coding tool."""
        result = _build_remote_cmd_for_path(
            Path("/mnt/z/repo"), True, "cly", Shell.WSL
        )
        assert result.startswith("wsl -e zsh -l -i -c")
        assert "/mnt/z/repo" in result
        assert "cly" in result

    def test_wsl_without_coding_tool(self) -> None:
        """Should build WSL-wrapped command with exec zsh."""
        result = _build_remote_cmd_for_path(
            Path("/mnt/z/repo"), False, "cly", Shell.WSL
        )
        assert result.startswith("wsl -e zsh -l -i -c")
        assert "exec zsh" in result

    def test_powershell_with_coding_tool(self) -> None:
        """Should build PowerShell command with coding tool."""
        result = _build_remote_cmd_for_path(
            Path("/mnt/z/repo"), True, "claude --dangerously-skip-permissions", Shell.POWERSHELL
        )
        assert "powershell" in result
        assert "Z:\\repo" in result
        assert "claude --dangerously-skip-permissions" in result
        assert "-NoExit" not in result

    def test_powershell_without_coding_tool(self) -> None:
        """Should build PowerShell command with -NoExit for shell."""
        result = _build_remote_cmd_for_path(
            Path("/mnt/z/repo"), False, "cly", Shell.POWERSHELL
        )
        assert "powershell -NoExit" in result
        assert "Z:\\repo" in result


class TestConnectToRemote:
    """Tests for connect_to_remote function."""

    @patch("vibe.connection.subprocess.run")
    @patch("vibe.connection.validate_ssh_key")
    def test_connects_with_coding_tool(
        self, mock_validate: MagicMock, mock_run: MagicMock
    ) -> None:
        """Should SSH and run coding tool when with_coding_tool=True."""
        mock_validate.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        result = connect_to_remote(
            repo_name="my-repo",
            worktree_name="feature-branch",
            with_coding_tool=True,
            ssh_key=Path("/key"),
            user_host="user@host",
            remote_base=Path("/remote"),
            coding_tool="cly",
        )

        assert result == 0
        mock_run.assert_called_once()

        # Check the SSH command
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "ssh"
        assert "-i" in call_args
        assert "user@host" in call_args

        # Check remote command includes coding tool
        remote_cmd = call_args[-1]
        assert "cly" in remote_cmd
        assert "/remote/my-repo/feature-branch" in remote_cmd

    @patch("vibe.connection.subprocess.run")
    @patch("vibe.connection.validate_ssh_key")
    def test_connects_without_coding_tool(
        self, mock_validate: MagicMock, mock_run: MagicMock
    ) -> None:
        """Should SSH to shell only when with_coding_tool=False."""
        mock_validate.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        connect_to_remote(
            repo_name="my-repo",
            worktree_name="feature-branch",
            with_coding_tool=False,
            ssh_key=Path("/key"),
            user_host="user@host",
            remote_base=Path("/remote"),
            coding_tool="cly",
        )

        # Check remote command does NOT include coding tool
        call_args = mock_run.call_args[0][0]
        remote_cmd = call_args[-1]
        assert "zsh -l -i" in remote_cmd
        # Should NOT have zsh -l -i -c 'cly'
        assert "-c" not in remote_cmd or "cly" not in remote_cmd.split("-c")[-1]

    @patch("vibe.connection.subprocess.run")
    @patch("vibe.connection.validate_ssh_key")
    def test_returns_exit_code(
        self, mock_validate: MagicMock, mock_run: MagicMock
    ) -> None:
        """Should return the exit code from SSH."""
        mock_validate.return_value = True
        mock_run.return_value = MagicMock(returncode=42)

        result = connect_to_remote(
            repo_name="repo",
            worktree_name="branch",
            ssh_key=Path("/key"),
            user_host="user@host",
            remote_base=Path("/remote"),
        )

        assert result == 42

    def test_returns_error_when_ssh_key_missing(self, tmp_path: Path) -> None:
        """Should return error code when SSH key doesn't exist."""
        missing_key = tmp_path / "nonexistent"

        result = connect_to_remote(
            repo_name="repo",
            worktree_name="branch",
            ssh_key=missing_key,
            user_host="user@host",
            remote_base=Path("/remote"),
        )

        assert result == 1

    @patch("vibe.connection.subprocess.run")
    @patch("vibe.connection.validate_ssh_key")
    def test_shows_error_on_ssh_failure(
        self, mock_validate: MagicMock, mock_run: MagicMock
    ) -> None:
        """Should show helpful error when SSH fails with 255."""
        mock_validate.return_value = True
        mock_run.return_value = MagicMock(returncode=255)

        result = connect_to_remote(
            repo_name="repo",
            worktree_name="branch",
            ssh_key=Path("/key"),
            user_host="user@host",
            remote_base=Path("/remote"),
        )

        assert result == 255

    @patch("vibe.connection.subprocess.run")
    @patch("vibe.connection.validate_ssh_key")
    def test_wsl_wrapper_with_coding_tool(
        self, mock_validate: MagicMock, mock_run: MagicMock
    ) -> None:
        """Should wrap command with wsl -e when wsl_wrapper=True."""
        mock_validate.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        connect_to_remote(
            repo_name="my-repo",
            worktree_name="feature",
            with_coding_tool=True,
            ssh_key=Path("/key"),
            user_host="admin@vibecoding",
            remote_base=Path("/mnt/repos/_vibecoding"),
            coding_tool="cly",
            remote_shell=Shell.WSL,
        )

        call_args = mock_run.call_args[0][0]
        remote_cmd = call_args[-1]
        assert remote_cmd.startswith("wsl -e zsh -l -i -c")
        assert "cd " in remote_cmd
        assert "/mnt/repos/_vibecoding/my-repo/feature" in remote_cmd
        assert "TMPDIR" in remote_cmd
        assert "cly" in remote_cmd

    @patch("vibe.connection.subprocess.run")
    @patch("vibe.connection.validate_ssh_key")
    def test_wsl_wrapper_without_coding_tool(
        self, mock_validate: MagicMock, mock_run: MagicMock
    ) -> None:
        """Should wrap shell-only command with wsl -e when remote_shell=WSL."""
        mock_validate.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        connect_to_remote(
            repo_name="my-repo",
            worktree_name="feature",
            with_coding_tool=False,
            ssh_key=Path("/key"),
            user_host="admin@vibecoding",
            remote_base=Path("/mnt/repos/_vibecoding"),
            remote_shell=Shell.WSL,
        )

        call_args = mock_run.call_args[0][0]
        remote_cmd = call_args[-1]
        assert remote_cmd.startswith("wsl -e zsh -l -i -c")
        assert "cd " in remote_cmd
        assert "/mnt/repos/_vibecoding/my-repo/feature" in remote_cmd
        # Should drop into interactive shell, not just exit
        assert "exec zsh" in remote_cmd
        # Should NOT include a coding tool command
        assert "cly" not in remote_cmd

    @patch("vibe.connection.subprocess.run")
    @patch("vibe.connection.validate_ssh_key")
    def test_wsl_wrapper_no_keychain(
        self, mock_validate: MagicMock, mock_run: MagicMock
    ) -> None:
        """WSL wrapper should not include keychain unlock."""
        mock_validate.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        connect_to_remote(
            repo_name="repo",
            worktree_name="branch",
            ssh_key=Path("/key"),
            user_host="admin@vibecoding",
            remote_base=Path("/mnt/repos/_vibecoding"),
            remote_shell=Shell.WSL,
        )

        call_args = mock_run.call_args[0][0]
        remote_cmd = call_args[-1]
        assert "security" not in remote_cmd
        assert "keychain" not in remote_cmd

    @patch("vibe.connection.subprocess.run")
    @patch("vibe.connection.validate_ssh_key")
    def test_powershell_with_coding_tool(
        self, mock_validate: MagicMock, mock_run: MagicMock
    ) -> None:
        """Should use PowerShell wrapping when remote_shell=POWERSHELL."""
        mock_validate.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        connect_to_remote(
            repo_name="my-repo",
            worktree_name="feature",
            with_coding_tool=True,
            ssh_key=Path("/key"),
            user_host="admin@vibecoding",
            remote_base=Path("/mnt/z/_vibecoding"),
            coding_tool="claude --dangerously-skip-permissions",
            remote_shell=Shell.POWERSHELL,
        )

        call_args = mock_run.call_args[0][0]
        remote_cmd = call_args[-1]
        assert "powershell" in remote_cmd
        assert "Z:\\_vibecoding\\my-repo\\feature" in remote_cmd
        assert "claude --dangerously-skip-permissions" in remote_cmd

    @patch("vibe.connection.subprocess.run")
    @patch("vibe.connection.validate_ssh_key")
    def test_powershell_without_coding_tool(
        self, mock_validate: MagicMock, mock_run: MagicMock
    ) -> None:
        """Should use PowerShell with -NoExit for shell-only."""
        mock_validate.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        connect_to_remote(
            repo_name="my-repo",
            worktree_name="feature",
            with_coding_tool=False,
            ssh_key=Path("/key"),
            user_host="admin@vibecoding",
            remote_base=Path("/mnt/z/_vibecoding"),
            remote_shell=Shell.POWERSHELL,
        )

        call_args = mock_run.call_args[0][0]
        remote_cmd = call_args[-1]
        assert "powershell -NoExit" in remote_cmd
        assert "Z:\\_vibecoding\\my-repo\\feature" in remote_cmd


class TestConnectToRemoteHome:
    """Tests for connect_to_remote_home function."""

    @patch("vibe.connection.subprocess.run")
    @patch("vibe.connection.validate_ssh_key")
    def test_connects_to_home(
        self, mock_validate: MagicMock, mock_run: MagicMock
    ) -> None:
        """Should SSH to home directory."""
        mock_validate.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        result = connect_to_remote_home(
            ssh_key=Path("/key"),
            user_host="user@host",
        )

        assert result == 0
        mock_run.assert_called_once()

        call_args = mock_run.call_args[0][0]
        assert "ssh" in call_args
        assert "user@host" in call_args

        # Should NOT cd to any worktree
        remote_cmd = call_args[-1]
        assert "cd '" not in remote_cmd
        assert "zsh -l -i" in remote_cmd

    @patch("vibe.connection.subprocess.run")
    @patch("vibe.connection.validate_ssh_key")
    def test_includes_tmpdir_setup(
        self, mock_validate: MagicMock, mock_run: MagicMock
    ) -> None:
        """Should set up TMPDIR even when going to home."""
        mock_validate.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        connect_to_remote_home(
            ssh_key=Path("/key"),
            user_host="user@host",
        )

        call_args = mock_run.call_args[0][0]
        remote_cmd = call_args[-1]
        assert "TMPDIR" in remote_cmd

    @patch("vibe.connection.subprocess.run")
    @patch("vibe.connection.validate_ssh_key")
    def test_includes_keychain_unlock(
        self, mock_validate: MagicMock, mock_run: MagicMock
    ) -> None:
        """Should unlock keychain when connecting to home."""
        mock_validate.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        connect_to_remote_home(
            ssh_key=Path("/key"),
            user_host="user@host",
        )

        call_args = mock_run.call_args[0][0]
        remote_cmd = call_args[-1]
        assert "security -v unlock-keychain" in remote_cmd
        assert "login.keychain-db" in remote_cmd

    @patch("vibe.connection.subprocess.run")
    @patch("vibe.connection.validate_ssh_key")
    def test_wsl_wrapper_enters_wsl(
        self, mock_validate: MagicMock, mock_run: MagicMock
    ) -> None:
        """Should enter WSL interactively when remote_shell=WSL."""
        mock_validate.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        connect_to_remote_home(
            ssh_key=Path("/key"),
            user_host="admin@vibecoding",
            remote_shell=Shell.WSL,
        )

        call_args = mock_run.call_args[0][0]
        remote_cmd = call_args[-1]
        assert remote_cmd == "wsl -e zsh -l -i"

    @patch("vibe.connection.subprocess.run")
    @patch("vibe.connection.validate_ssh_key")
    def test_wsl_wrapper_no_keychain(
        self, mock_validate: MagicMock, mock_run: MagicMock
    ) -> None:
        """WSL wrapper should not include keychain unlock."""
        mock_validate.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        connect_to_remote_home(
            ssh_key=Path("/key"),
            user_host="admin@vibecoding",
            unlock_keychain=False,
            keychain_command=None,
            remote_shell=Shell.WSL,
        )

        call_args = mock_run.call_args[0][0]
        remote_cmd = call_args[-1]
        assert "security" not in remote_cmd
        assert "keychain" not in remote_cmd

    @patch("vibe.connection.subprocess.run")
    @patch("vibe.connection.validate_ssh_key")
    def test_no_keychain_when_disabled(
        self, mock_validate: MagicMock, mock_run: MagicMock
    ) -> None:
        """Should skip keychain when unlock_keychain=False on macOS path."""
        mock_validate.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        connect_to_remote_home(
            ssh_key=Path("/key"),
            user_host="user@host",
            unlock_keychain=False,
            keychain_command=None,
            remote_shell=None,
        )

        call_args = mock_run.call_args[0][0]
        remote_cmd = call_args[-1]
        assert "security" not in remote_cmd
        assert "TMPDIR" in remote_cmd
        assert "zsh -l -i" in remote_cmd

    @patch("vibe.connection.subprocess.run")
    @patch("vibe.connection.validate_ssh_key")
    def test_powershell_enters_powershell(
        self, mock_validate: MagicMock, mock_run: MagicMock
    ) -> None:
        """Should enter PowerShell interactively when remote_shell=POWERSHELL."""
        mock_validate.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        connect_to_remote_home(
            ssh_key=Path("/key"),
            user_host="admin@vibecoding",
            remote_shell=Shell.POWERSHELL,
        )

        call_args = mock_run.call_args[0][0]
        remote_cmd = call_args[-1]
        assert remote_cmd == "powershell -NoExit"


class TestConnectLocally:
    """Tests for connect_locally function."""

    @patch("vibe.connection.subprocess.run")
    def test_runs_coding_tool_in_worktree(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        """Should run coding tool in worktree directory."""
        mock_run.return_value = MagicMock(returncode=0)
        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()

        result = connect_locally(
            worktree_path=worktree_path,
            coding_tool="cly",
        )

        assert result == 0
        mock_run.assert_called_once_with(["cly"], cwd=worktree_path)

    @patch("vibe.connection.subprocess.run")
    def test_returns_exit_code(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        """Should return the exit code from coding tool."""
        mock_run.return_value = MagicMock(returncode=1)
        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()

        result = connect_locally(
            worktree_path=worktree_path,
            coding_tool="cly",
        )

        assert result == 1

    @patch("vibe.connection.subprocess.run")
    def test_uses_custom_coding_tool(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        """Should use the specified coding tool."""
        mock_run.return_value = MagicMock(returncode=0)
        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()

        connect_locally(
            worktree_path=worktree_path,
            coding_tool="custom-tool",
        )

        mock_run.assert_called_once_with(["custom-tool"], cwd=worktree_path)

    def test_returns_error_when_worktree_missing(self, tmp_path: Path) -> None:
        """Should return error when worktree path doesn't exist."""
        missing_path = tmp_path / "nonexistent"

        result = connect_locally(
            worktree_path=missing_path,
            coding_tool="cly",
        )

        assert result == 1


class TestConnectToRemotePath:
    """Tests for connect_to_remote_path function."""

    @patch("vibe.connection.subprocess.run")
    @patch("vibe.connection.validate_ssh_key")
    def test_connects_with_coding_tool(
        self, mock_validate: MagicMock, mock_run: MagicMock
    ) -> None:
        """Should SSH to path and run coding tool."""
        mock_validate.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        result = connect_to_remote_path(
            remote_path=Path("/remote/my-repo"),
            with_coding_tool=True,
            ssh_key=Path("/key"),
            user_host="user@host",
            coding_tool="cly",
        )

        assert result == 0
        mock_run.assert_called_once()

        call_args = mock_run.call_args[0][0]
        remote_cmd = call_args[-1]
        assert "cly" in remote_cmd
        assert "/remote/my-repo" in remote_cmd

    @patch("vibe.connection.subprocess.run")
    @patch("vibe.connection.validate_ssh_key")
    def test_connects_without_coding_tool(
        self, mock_validate: MagicMock, mock_run: MagicMock
    ) -> None:
        """Should SSH to path without coding tool."""
        mock_validate.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        connect_to_remote_path(
            remote_path=Path("/remote/my-repo"),
            with_coding_tool=False,
            ssh_key=Path("/key"),
            user_host="user@host",
        )

        call_args = mock_run.call_args[0][0]
        remote_cmd = call_args[-1]
        assert "zsh -l -i" in remote_cmd
        assert "/remote/my-repo" in remote_cmd

    @patch("vibe.connection.subprocess.run")
    @patch("vibe.connection.validate_ssh_key")
    def test_returns_exit_code(
        self, mock_validate: MagicMock, mock_run: MagicMock
    ) -> None:
        """Should return the exit code from SSH."""
        mock_validate.return_value = True
        mock_run.return_value = MagicMock(returncode=42)

        result = connect_to_remote_path(
            remote_path=Path("/remote/path"),
            ssh_key=Path("/key"),
            user_host="user@host",
        )

        assert result == 42

    def test_returns_error_when_ssh_key_missing(self, tmp_path: Path) -> None:
        """Should return error code when SSH key doesn't exist."""
        missing_key = tmp_path / "nonexistent"

        result = connect_to_remote_path(
            remote_path=Path("/remote/path"),
            ssh_key=missing_key,
            user_host="user@host",
        )

        assert result == 1

    @patch("vibe.connection.subprocess.run")
    @patch("vibe.connection.validate_ssh_key")
    def test_wsl_wrapper_with_coding_tool(
        self, mock_validate: MagicMock, mock_run: MagicMock
    ) -> None:
        """Should wrap command with wsl -e when remote_shell=WSL."""
        mock_validate.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        connect_to_remote_path(
            remote_path=Path("/mnt/repos/my-repo"),
            with_coding_tool=True,
            ssh_key=Path("/key"),
            user_host="admin@vibecoding",
            coding_tool="cly",
            remote_shell=Shell.WSL,
        )

        call_args = mock_run.call_args[0][0]
        remote_cmd = call_args[-1]
        assert remote_cmd.startswith("wsl -e zsh -l -i -c")
        assert "/mnt/repos/my-repo" in remote_cmd
        assert "cly" in remote_cmd

    @patch("vibe.connection.subprocess.run")
    @patch("vibe.connection.validate_ssh_key")
    def test_wsl_wrapper_without_coding_tool(
        self, mock_validate: MagicMock, mock_run: MagicMock
    ) -> None:
        """Should wrap shell-only command with wsl -e when remote_shell=WSL."""
        mock_validate.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        connect_to_remote_path(
            remote_path=Path("/mnt/repos/my-repo"),
            with_coding_tool=False,
            ssh_key=Path("/key"),
            user_host="admin@vibecoding",
            remote_shell=Shell.WSL,
        )

        call_args = mock_run.call_args[0][0]
        remote_cmd = call_args[-1]
        assert remote_cmd.startswith("wsl -e zsh -l -i -c")
        assert "/mnt/repos/my-repo" in remote_cmd
        # Should drop into interactive shell, not just exit
        assert "exec zsh" in remote_cmd
        # Should NOT have coding tool
        assert "cly" not in remote_cmd

    @patch("vibe.connection.subprocess.run")
    @patch("vibe.connection.validate_ssh_key")
    def test_powershell_with_coding_tool(
        self, mock_validate: MagicMock, mock_run: MagicMock
    ) -> None:
        """Should use PowerShell wrapping when remote_shell=POWERSHELL."""
        mock_validate.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        connect_to_remote_path(
            remote_path=Path("/mnt/z/my-repo"),
            with_coding_tool=True,
            ssh_key=Path("/key"),
            user_host="admin@vibecoding",
            coding_tool="claude --dangerously-skip-permissions",
            remote_shell=Shell.POWERSHELL,
        )

        call_args = mock_run.call_args[0][0]
        remote_cmd = call_args[-1]
        assert "powershell" in remote_cmd
        assert "Z:\\my-repo" in remote_cmd
        assert "claude --dangerously-skip-permissions" in remote_cmd

    @patch("vibe.connection.subprocess.run")
    @patch("vibe.connection.validate_ssh_key")
    def test_powershell_without_coding_tool(
        self, mock_validate: MagicMock, mock_run: MagicMock
    ) -> None:
        """Should use PowerShell with -NoExit for shell-only."""
        mock_validate.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        connect_to_remote_path(
            remote_path=Path("/mnt/z/my-repo"),
            with_coding_tool=False,
            ssh_key=Path("/key"),
            user_host="admin@vibecoding",
            remote_shell=Shell.POWERSHELL,
        )

        call_args = mock_run.call_args[0][0]
        remote_cmd = call_args[-1]
        assert "powershell -NoExit" in remote_cmd
        assert "Z:\\my-repo" in remote_cmd
