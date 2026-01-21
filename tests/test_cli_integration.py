"""Integration tests for CLI interface."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from vibe.cli import app

runner = CliRunner()


def make_repo_info(name: str = "test-repo", root: Path = Path("/repo")):
    """Create a properly configured mock RepoInfo."""
    from vibe.git_ops import RepoInfo
    return RepoInfo(name=name, root=root)


class TestCliHelp:
    """Tests for CLI help and basic usage."""

    def test_shows_help_with_help_flag(self) -> None:
        """Should show help with --help flag."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Git worktree manager" in result.stdout
        assert "--cli" in result.stdout
        assert "--local" in result.stdout
        assert "--clean" in result.stdout
        assert "--from" in result.stdout


class TestCleanCommand:
    """Tests for --clean option."""

    @patch("vibe.cli.clean_all_worktrees")
    def test_clean_all_worktrees(self, mock_clean: MagicMock) -> None:
        """Should call clean_all_worktrees when --clean without branch."""
        result = runner.invoke(app, ["--clean"])

        assert result.exit_code == 0
        mock_clean.assert_called_once()

    @patch("vibe.cli.validate_git_repo")
    def test_clean_specific_requires_git_repo(
        self, mock_validate: MagicMock
    ) -> None:
        """Should require git repo when cleaning specific worktree."""
        mock_validate.return_value = False

        result = runner.invoke(app, ["--clean", "some-branch"])

        assert result.exit_code == 1
        assert "Not in a git repository" in result.stdout

    @patch("vibe.cli.clean_specific_worktree")
    @patch("vibe.cli.get_repo_info")
    @patch("vibe.cli.validate_git_repo")
    def test_clean_specific_worktree(
        self,
        mock_validate: MagicMock,
        mock_repo_info: MagicMock,
        mock_clean: MagicMock,
    ) -> None:
        """Should clean specific worktree when branch provided."""
        mock_validate.return_value = True
        mock_repo_info.return_value = make_repo_info()
        mock_clean.return_value = True

        result = runner.invoke(app, ["--clean", "feature-branch"])

        assert result.exit_code == 0
        mock_clean.assert_called_once_with(
            worktree_name="feature-branch",
            repo_name="test-repo",
            repo_root=Path("/repo"),
        )


class TestCliCommand:
    """Tests for --cli option."""

    @patch("vibe.cli.connect_to_remote_home")
    def test_cli_without_branch_goes_to_home(
        self, mock_connect: MagicMock
    ) -> None:
        """Should SSH to home when --cli without branch."""
        mock_connect.return_value = 0

        result = runner.invoke(app, ["--cli"])

        assert result.exit_code == 0
        mock_connect.assert_called_once()

    @patch("vibe.cli.validate_git_repo")
    def test_cli_with_branch_requires_git_repo(
        self, mock_validate: MagicMock
    ) -> None:
        """Should require git repo when --cli with branch."""
        mock_validate.return_value = False

        result = runner.invoke(app, ["--cli", "some-branch"])

        assert result.exit_code == 1
        assert "Not in a git repository" in result.stdout

    @patch("vibe.cli.connect_to_remote")
    @patch("vibe.cli.setup_worktree")
    @patch("vibe.cli.get_repo_info")
    @patch("vibe.cli.validate_git_repo")
    def test_cli_with_branch_no_coding_tool(
        self,
        mock_validate: MagicMock,
        mock_repo_info: MagicMock,
        mock_setup: MagicMock,
        mock_connect: MagicMock,
    ) -> None:
        """Should SSH without coding tool when --cli with branch."""
        mock_validate.return_value = True
        mock_repo_info.return_value = make_repo_info()
        mock_setup.return_value = True
        mock_connect.return_value = 0

        result = runner.invoke(app, ["--cli", "feature-branch"])

        assert result.exit_code == 0
        mock_connect.assert_called_once_with(
            repo_name="test-repo",
            worktree_name="feature-branch",
            with_coding_tool=False,
        )


class TestLocalCommand:
    """Tests for --local option."""

    def test_local_requires_branch(self) -> None:
        """Should require branch name with --local."""
        result = runner.invoke(app, ["--local"])

        assert result.exit_code == 1
        assert "--local requires a branch name" in result.stdout

    @patch("vibe.cli.validate_git_repo")
    def test_local_requires_git_repo(self, mock_validate: MagicMock) -> None:
        """Should require git repo with --local."""
        mock_validate.return_value = False

        result = runner.invoke(app, ["--local", "some-branch"])

        assert result.exit_code == 1
        assert "Not in a git repository" in result.stdout

    @patch("vibe.cli.connect_locally")
    @patch("vibe.cli.setup_worktree")
    @patch("vibe.cli.get_repo_info")
    @patch("vibe.cli.validate_git_repo")
    @patch("vibe.cli.LOCAL_WORKTREE_BASE", Path("/worktrees"))
    def test_local_runs_locally(
        self,
        mock_validate: MagicMock,
        mock_repo_info: MagicMock,
        mock_setup: MagicMock,
        mock_connect: MagicMock,
    ) -> None:
        """Should run coding tool locally."""
        mock_validate.return_value = True
        mock_repo_info.return_value = make_repo_info()
        mock_setup.return_value = True
        mock_connect.return_value = 0

        result = runner.invoke(app, ["--local", "feature-branch", "--cc"])

        assert result.exit_code == 0
        mock_connect.assert_called_once_with(
            Path("/worktrees/test-repo/feature-branch"), coding_tool="cly"
        )


class TestDefaultCommand:
    """Tests for default (no flags) command."""

    @patch("vibe.cli.validate_git_repo")
    def test_requires_git_repo(self, mock_validate: MagicMock) -> None:
        """Should require git repo for default command."""
        mock_validate.return_value = False

        result = runner.invoke(app, ["feature-branch"])

        assert result.exit_code == 1
        assert "Not in a git repository" in result.stdout

    @patch("vibe.cli.connect_to_remote")
    @patch("vibe.cli.setup_worktree")
    @patch("vibe.cli.get_repo_info")
    @patch("vibe.cli.validate_git_repo")
    def test_creates_worktree_and_connects(
        self,
        mock_validate: MagicMock,
        mock_repo_info: MagicMock,
        mock_setup: MagicMock,
        mock_connect: MagicMock,
    ) -> None:
        """Should create worktree and connect with coding tool."""
        mock_validate.return_value = True
        mock_repo_info.return_value = make_repo_info()
        mock_setup.return_value = True
        mock_connect.return_value = 0

        result = runner.invoke(app, ["feature-branch", "--cc"])

        assert result.exit_code == 0
        mock_setup.assert_called_once_with(
            "feature-branch", None, "test-repo", Path("/repo")
        )
        mock_connect.assert_called_once_with(
            repo_name="test-repo",
            worktree_name="feature-branch",
            with_coding_tool=True,
            coding_tool="cly",
        )

    @patch("vibe.cli.connect_to_remote")
    @patch("vibe.cli.setup_worktree")
    @patch("vibe.cli.get_repo_info")
    @patch("vibe.cli.validate_git_repo")
    def test_passes_from_branch(
        self,
        mock_validate: MagicMock,
        mock_repo_info: MagicMock,
        mock_setup: MagicMock,
        mock_connect: MagicMock,
    ) -> None:
        """Should pass --from branch to setup_worktree."""
        mock_validate.return_value = True
        mock_repo_info.return_value = make_repo_info()
        mock_setup.return_value = True
        mock_connect.return_value = 0

        result = runner.invoke(app, ["feature-branch", "--from", "main", "--cc"])

        assert result.exit_code == 0
        mock_setup.assert_called_once_with(
            "feature-branch", "main", "test-repo", Path("/repo")
        )


class TestSetupWorktree:
    """Tests for setup_worktree helper function."""

    @patch("vibe.cli.check_worktree_exists")
    @patch("vibe.cli.console")
    def test_handles_invalid_existing_directory(
        self,
        mock_console: MagicMock,
        mock_check: MagicMock,
    ) -> None:
        """Should return False when directory exists but isn't worktree."""
        from vibe.cli import setup_worktree
        from vibe.git_ops import WorktreeStatus

        mock_check.return_value = WorktreeStatus.EXISTS_INVALID

        result = setup_worktree(
            worktree_name="feature",
            from_branch=None,
            repo_name="repo",
            cwd=Path("/repo"),
        )

        assert result is False

    @patch("vibe.cli.check_worktree_exists")
    @patch("vibe.cli.console")
    def test_reuses_existing_valid_worktree(
        self,
        mock_console: MagicMock,
        mock_check: MagicMock,
    ) -> None:
        """Should return True when valid worktree exists."""
        from vibe.cli import setup_worktree
        from vibe.git_ops import WorktreeStatus

        mock_check.return_value = WorktreeStatus.EXISTS_VALID

        result = setup_worktree(
            worktree_name="feature",
            from_branch=None,
            repo_name="repo",
            cwd=Path("/repo"),
        )

        assert result is True

    @patch("vibe.cli.create_worktree")
    @patch("vibe.cli.check_worktree_exists")
    @patch("vibe.cli.console")
    def test_creates_new_worktree(
        self,
        mock_console: MagicMock,
        mock_check: MagicMock,
        mock_create: MagicMock,
    ) -> None:
        """Should create worktree when it doesn't exist."""
        from vibe.cli import setup_worktree
        from vibe.git_ops import WorktreeStatus

        mock_check.return_value = WorktreeStatus.NOT_EXISTS
        mock_create.return_value = Path("/worktrees/repo/feature")

        result = setup_worktree(
            worktree_name="feature",
            from_branch="main",
            repo_name="repo",
            cwd=Path("/repo"),
        )

        assert result is True
        mock_create.assert_called_once()


class TestExitCodes:
    """Tests for proper exit code propagation."""

    @patch("vibe.cli.connect_to_remote_home")
    def test_propagates_ssh_exit_code(self, mock_connect: MagicMock) -> None:
        """Should propagate exit code from SSH."""
        mock_connect.return_value = 42

        result = runner.invoke(app, ["--cli"])

        assert result.exit_code == 42

    @patch("vibe.cli.connect_to_remote")
    @patch("vibe.cli.setup_worktree")
    @patch("vibe.cli.get_repo_info")
    @patch("vibe.cli.validate_git_repo")
    def test_propagates_connect_exit_code(
        self,
        mock_validate: MagicMock,
        mock_repo_info: MagicMock,
        mock_setup: MagicMock,
        mock_connect: MagicMock,
    ) -> None:
        """Should propagate exit code from connect."""
        mock_validate.return_value = True
        mock_repo_info.return_value = make_repo_info()
        mock_setup.return_value = True
        mock_connect.return_value = 5

        result = runner.invoke(app, ["feature-branch", "--cc"])

        assert result.exit_code == 5


class TestCodingToolOptions:
    """Tests for --oc and --cc coding tool options."""

    def test_help_shows_oc_and_cc_options(self) -> None:
        """Should show --oc and --cc in help output."""
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "--oc" in result.stdout
        assert "--cc" in result.stdout
        assert "open code" in result.stdout.lower()
        assert "cloud code" in result.stdout.lower()

    def test_oc_and_cc_together_errors(self) -> None:
        """Should error when both --oc and --cc are provided."""
        result = runner.invoke(app, ["feature-branch", "--oc", "--cc"])

        assert result.exit_code == 1
        assert "Cannot use both --oc and --cc" in result.stdout

    @patch("vibe.cli.connect_to_remote")
    @patch("vibe.cli.setup_worktree")
    @patch("vibe.cli.get_repo_info")
    @patch("vibe.cli.validate_git_repo")
    def test_oc_flag_uses_opencode(
        self,
        mock_validate: MagicMock,
        mock_repo_info: MagicMock,
        mock_setup: MagicMock,
        mock_connect: MagicMock,
    ) -> None:
        """Should use opencode when --oc flag is provided."""
        mock_validate.return_value = True
        mock_repo_info.return_value = make_repo_info()
        mock_setup.return_value = True
        mock_connect.return_value = 0

        result = runner.invoke(app, ["feature-branch", "--oc"])

        assert result.exit_code == 0
        mock_connect.assert_called_once_with(
            repo_name="test-repo",
            worktree_name="feature-branch",
            with_coding_tool=True,
            coding_tool="opencode",
        )

    @patch("vibe.cli.connect_to_remote")
    @patch("vibe.cli.setup_worktree")
    @patch("vibe.cli.get_repo_info")
    @patch("vibe.cli.validate_git_repo")
    def test_cc_flag_uses_cly(
        self,
        mock_validate: MagicMock,
        mock_repo_info: MagicMock,
        mock_setup: MagicMock,
        mock_connect: MagicMock,
    ) -> None:
        """Should use cly when --cc flag is provided."""
        mock_validate.return_value = True
        mock_repo_info.return_value = make_repo_info()
        mock_setup.return_value = True
        mock_connect.return_value = 0

        result = runner.invoke(app, ["feature-branch", "--cc"])

        assert result.exit_code == 0
        mock_connect.assert_called_once_with(
            repo_name="test-repo",
            worktree_name="feature-branch",
            with_coding_tool=True,
            coding_tool="cly",
        )

    @patch("vibe.cli.connect_locally")
    @patch("vibe.cli.setup_worktree")
    @patch("vibe.cli.get_repo_info")
    @patch("vibe.cli.validate_git_repo")
    @patch("vibe.cli.LOCAL_WORKTREE_BASE", Path("/worktrees"))
    def test_local_with_oc_flag(
        self,
        mock_validate: MagicMock,
        mock_repo_info: MagicMock,
        mock_setup: MagicMock,
        mock_connect: MagicMock,
    ) -> None:
        """Should use opencode locally when --oc flag is provided."""
        mock_validate.return_value = True
        mock_repo_info.return_value = make_repo_info()
        mock_setup.return_value = True
        mock_connect.return_value = 0

        result = runner.invoke(app, ["--local", "feature-branch", "--oc"])

        assert result.exit_code == 0
        mock_connect.assert_called_once_with(
            Path("/worktrees/test-repo/feature-branch"), coding_tool="opencode"
        )

    @patch("vibe.cli.connect_locally")
    @patch("vibe.cli.setup_worktree")
    @patch("vibe.cli.get_repo_info")
    @patch("vibe.cli.validate_git_repo")
    @patch("vibe.cli.LOCAL_WORKTREE_BASE", Path("/worktrees"))
    def test_local_with_cc_flag(
        self,
        mock_validate: MagicMock,
        mock_repo_info: MagicMock,
        mock_setup: MagicMock,
        mock_connect: MagicMock,
    ) -> None:
        """Should use cly locally when --cc flag is provided."""
        mock_validate.return_value = True
        mock_repo_info.return_value = make_repo_info()
        mock_setup.return_value = True
        mock_connect.return_value = 0

        result = runner.invoke(app, ["--local", "feature-branch", "--cc"])

        assert result.exit_code == 0
        mock_connect.assert_called_once_with(
            Path("/worktrees/test-repo/feature-branch"), coding_tool="cly"
        )

    @patch("vibe.cli.connect_to_remote")
    @patch("vibe.cli.setup_worktree")
    @patch("vibe.cli.get_repo_info")
    @patch("vibe.cli.validate_git_repo")
    def test_defaults_to_cloud_code_when_no_flag(
        self,
        mock_validate: MagicMock,
        mock_repo_info: MagicMock,
        mock_setup: MagicMock,
        mock_connect: MagicMock,
    ) -> None:
        """Should default to cloud code when neither flag is provided."""
        mock_validate.return_value = True
        mock_repo_info.return_value = make_repo_info()
        mock_setup.return_value = True
        mock_connect.return_value = 0

        result = runner.invoke(app, ["feature-branch"])

        assert result.exit_code == 0
        mock_connect.assert_called_once_with(
            repo_name="test-repo",
            worktree_name="feature-branch",
            with_coding_tool=True,
            coding_tool="cly",
        )

    @patch("vibe.cli.connect_locally")
    @patch("vibe.cli.setup_worktree")
    @patch("vibe.cli.get_repo_info")
    @patch("vibe.cli.validate_git_repo")
    @patch("vibe.cli.LOCAL_WORKTREE_BASE", Path("/worktrees"))
    def test_local_defaults_to_cloud_code_when_no_flag(
        self,
        mock_validate: MagicMock,
        mock_repo_info: MagicMock,
        mock_setup: MagicMock,
        mock_connect: MagicMock,
    ) -> None:
        """Should default to cloud code locally when neither flag is provided."""
        mock_validate.return_value = True
        mock_repo_info.return_value = make_repo_info()
        mock_setup.return_value = True
        mock_connect.return_value = 0

        result = runner.invoke(app, ["--local", "feature-branch"])

        assert result.exit_code == 0
        mock_connect.assert_called_once_with(
            Path("/worktrees/test-repo/feature-branch"), coding_tool="cly"
        )


class TestNoArgBehavior:
    """Tests for no-argument context-aware behavior."""

    @patch("vibe.cli.get_current_context")
    def test_no_args_not_in_git_repo(self, mock_context: MagicMock) -> None:
        """Should error when not in a git repo with no arguments."""
        from vibe.git_ops import ContextType, CurrentContext

        mock_context.return_value = CurrentContext(context_type=ContextType.NONE)

        result = runner.invoke(app, [])

        assert result.exit_code == 1
        assert "Not in a git repository" in result.stdout

    @patch("vibe.cli.connect_to_remote_path")
    @patch("vibe.cli.get_current_context")
    def test_no_args_in_main_repo(
        self, mock_context: MagicMock, mock_connect: MagicMock
    ) -> None:
        """Should connect to main repo when no args from main repo."""
        from vibe.git_ops import ContextType, CurrentContext

        mock_context.return_value = CurrentContext(
            context_type=ContextType.MAIN_REPO,
            local_path=Path("/Volumes/External/Repositories/my-repo"),
            remote_path=Path("/Volumes/External/Repositories/my-repo"),
            repo_name="my-repo",
        )
        mock_connect.return_value = 0

        result = runner.invoke(app, ["--cc"])

        assert result.exit_code == 0
        assert "main repository" in result.stdout
        mock_connect.assert_called_once_with(
            remote_path=Path("/Volumes/External/Repositories/my-repo"),
            with_coding_tool=True,
            coding_tool="cly",
        )

    @patch("vibe.cli.connect_to_remote_path")
    @patch("vibe.cli.get_current_context")
    def test_no_args_in_worktree(
        self, mock_context: MagicMock, mock_connect: MagicMock
    ) -> None:
        """Should connect to worktree when no args from worktree."""
        from vibe.git_ops import ContextType, CurrentContext

        mock_context.return_value = CurrentContext(
            context_type=ContextType.WORKTREE,
            local_path=Path("/Volumes/External/Repositories/_vibecoding/my-repo/feature"),
            remote_path=Path("/Volumes/External/Repositories/_vibecoding/my-repo/feature"),
            repo_name="my-repo",
            worktree_name="feature",
        )
        mock_connect.return_value = 0

        result = runner.invoke(app, ["--cc"])

        assert result.exit_code == 0
        assert "worktree" in result.stdout
        mock_connect.assert_called_once_with(
            remote_path=Path("/Volumes/External/Repositories/_vibecoding/my-repo/feature"),
            with_coding_tool=True,
            coding_tool="cly",
        )

    @patch("vibe.cli.get_current_context")
    def test_no_args_repo_not_in_expected_location(
        self, mock_context: MagicMock
    ) -> None:
        """Should error when repo is not in expected location."""
        from vibe.git_ops import ContextType, CurrentContext

        mock_context.return_value = CurrentContext(
            context_type=ContextType.MAIN_REPO,
            local_path=Path("/some/other/path"),
            remote_path=None,  # No remote path means not in expected location
            repo_name="my-repo",
        )

        result = runner.invoke(app, [])

        assert result.exit_code == 1
        assert "not in the expected location" in result.stdout
