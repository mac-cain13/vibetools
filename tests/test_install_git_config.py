"""Tests for the installer's cross-machine worktree configuration."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


INSTALLER = Path(__file__).parents[1] / "install.sh"
SETTING = "worktree.useRelativePaths"


def run_configure(global_config: Path) -> subprocess.CompletedProcess[str]:
    """Run the installer's git step against an isolated global config file."""
    environment = os.environ.copy()
    environment["GIT_CONFIG_GLOBAL"] = str(global_config)
    return subprocess.run(
        [
            "/bin/bash",
            "-c",
            'source "$1"; configure_relative_worktrees',
            "test-install-git-config",
            str(INSTALLER),
        ],
        capture_output=True,
        check=False,
        env=environment,
        text=True,
    )


def read_setting(global_config: Path) -> str:
    """Read the recorded worktree path setting from a git config file."""
    result = subprocess.run(
        ["git", "config", "--file", str(global_config), "--get", SETTING],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def test_enables_relative_worktree_paths(tmp_path: Path) -> None:
    """A fresh install should make git record worktrees relatively."""
    config = tmp_path / "gitconfig"

    result = run_configure(config)

    assert result.returncode == 0, result.stderr
    assert read_setting(config) == "true"


def test_reruns_leave_the_setting_alone(tmp_path: Path) -> None:
    """Re-running the installer should recognise the setting is in place."""
    config = tmp_path / "gitconfig"
    run_configure(config)

    result = run_configure(config)

    assert result.returncode == 0, result.stderr
    assert "already" in result.stdout
    assert read_setting(config) == "true"
