"""Pytest fixtures for vibe tests."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Path:
    """Create a temporary git repository for testing.

    Returns:
        Path to the git repository root
    """
    repo_path = tmp_path / "test-repo"
    repo_path.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )

    # Create initial commit
    readme = repo_path / "README.md"
    readme.write_text("# Test Repo\n")
    subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )

    return repo_path


@pytest.fixture
def temp_git_repo_with_remote(temp_git_repo: Path, tmp_path: Path) -> tuple[Path, Path]:
    """Create a git repo with a bare remote for testing remote branch scenarios.

    Returns:
        Tuple of (repo_path, remote_path)
    """
    # Create a bare remote
    remote_path = tmp_path / "remote.git"
    subprocess.run(
        ["git", "clone", "--bare", str(temp_git_repo), str(remote_path)],
        capture_output=True,
        check=True,
    )

    # Add remote to the repo
    subprocess.run(
        ["git", "remote", "add", "origin", str(remote_path)],
        cwd=temp_git_repo,
        capture_output=True,
        check=True,
    )

    # Push main branch
    subprocess.run(
        ["git", "push", "-u", "origin", "main"],
        cwd=temp_git_repo,
        capture_output=True,
    )
    # Try master if main failed
    subprocess.run(
        ["git", "push", "-u", "origin", "master"],
        cwd=temp_git_repo,
        capture_output=True,
    )

    # Fetch to update remote refs
    subprocess.run(
        ["git", "fetch", "origin"],
        cwd=temp_git_repo,
        capture_output=True,
        check=True,
    )

    return temp_git_repo, remote_path


@pytest.fixture
def temp_worktree_base(tmp_path: Path) -> Path:
    """Create a temporary worktree base directory.

    Returns:
        Path to the worktree base directory
    """
    worktree_base = tmp_path / "worktrees"
    worktree_base.mkdir()
    return worktree_base


@pytest.fixture
def in_temp_git_repo(temp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Change to a temporary git repository for testing.

    Returns:
        Path to the git repository root
    """
    monkeypatch.chdir(temp_git_repo)
    return temp_git_repo
