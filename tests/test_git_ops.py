"""Tests for git operations module."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from vibe.git_ops import (
    RepoInfo,
    WorktreeStatus,
    branch_exists_local,
    branch_exists_remote,
    check_worktree_exists,
    create_worktree,
    get_local_branches,
    get_remote_branches,
    get_repo_info,
    has_uncommitted_changes,
    validate_git_repo,
)


class TestValidateGitRepo:
    """Tests for validate_git_repo function."""

    def test_valid_git_repo(self, temp_git_repo: Path) -> None:
        """Should return True when in a git repository."""
        assert validate_git_repo(cwd=temp_git_repo) is True

    def test_not_a_git_repo(self, tmp_path: Path) -> None:
        """Should return False when not in a git repository."""
        assert validate_git_repo(cwd=tmp_path) is False

    def test_subdirectory_of_git_repo(self, temp_git_repo: Path) -> None:
        """Should return True when in a subdirectory of a git repository."""
        subdir = temp_git_repo / "subdir"
        subdir.mkdir()
        assert validate_git_repo(cwd=subdir) is True


class TestGetRepoInfo:
    """Tests for get_repo_info function."""

    def test_returns_repo_info(self, temp_git_repo: Path) -> None:
        """Should return RepoInfo with correct root and name."""
        info = get_repo_info(cwd=temp_git_repo)
        assert isinstance(info, RepoInfo)
        assert info.root == temp_git_repo
        assert info.name == "test-repo"

    def test_from_subdirectory(self, temp_git_repo: Path) -> None:
        """Should return correct info from subdirectory."""
        subdir = temp_git_repo / "subdir"
        subdir.mkdir()
        info = get_repo_info(cwd=subdir)
        assert info.root == temp_git_repo
        assert info.name == "test-repo"

    def test_raises_when_not_in_repo(self, tmp_path: Path) -> None:
        """Should raise RuntimeError when not in a git repository."""
        with pytest.raises(RuntimeError, match="Not in a git repository"):
            get_repo_info(cwd=tmp_path)


class TestCheckWorktreeExists:
    """Tests for check_worktree_exists function."""

    def test_not_exists(
        self, temp_git_repo: Path, temp_worktree_base: Path
    ) -> None:
        """Should return NOT_EXISTS when worktree doesn't exist."""
        status = check_worktree_exists(
            worktree_name="nonexistent",
            repo_name="test-repo",
            worktree_base=temp_worktree_base,
            cwd=temp_git_repo,
        )
        assert status == WorktreeStatus.NOT_EXISTS

    def test_exists_valid(
        self, temp_git_repo: Path, temp_worktree_base: Path
    ) -> None:
        """Should return EXISTS_VALID when worktree exists and is valid."""
        # Create a worktree
        worktree_path = temp_worktree_base / "test-repo" / "feature"
        worktree_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "worktree", "add", "-b", "feature", str(worktree_path)],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )

        status = check_worktree_exists(
            worktree_name="feature",
            repo_name="test-repo",
            worktree_base=temp_worktree_base,
            cwd=temp_git_repo,
        )
        assert status == WorktreeStatus.EXISTS_VALID

    def test_exists_invalid(
        self, temp_git_repo: Path, temp_worktree_base: Path
    ) -> None:
        """Should return EXISTS_INVALID when directory exists but isn't a worktree."""
        # Create directory but not as worktree
        worktree_path = temp_worktree_base / "test-repo" / "fake"
        worktree_path.mkdir(parents=True)

        status = check_worktree_exists(
            worktree_name="fake",
            repo_name="test-repo",
            worktree_base=temp_worktree_base,
            cwd=temp_git_repo,
        )
        assert status == WorktreeStatus.EXISTS_INVALID


class TestBranchExists:
    """Tests for branch existence checks."""

    def test_local_branch_exists(self, temp_git_repo: Path) -> None:
        """Should detect existing local branch."""
        # Create a branch
        subprocess.run(
            ["git", "branch", "test-branch"],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )
        assert branch_exists_local("test-branch", cwd=temp_git_repo) is True

    def test_local_branch_not_exists(self, temp_git_repo: Path) -> None:
        """Should return False for non-existent branch."""
        assert branch_exists_local("nonexistent", cwd=temp_git_repo) is False

    def test_remote_branch_exists(
        self, temp_git_repo_with_remote: tuple[Path, Path]
    ) -> None:
        """Should detect existing remote branch."""
        repo, _ = temp_git_repo_with_remote
        # Check for origin/main or origin/master
        has_main = branch_exists_remote("origin/main", cwd=repo)
        has_master = branch_exists_remote("origin/master", cwd=repo)
        assert has_main or has_master

    def test_remote_branch_not_exists(
        self, temp_git_repo_with_remote: tuple[Path, Path]
    ) -> None:
        """Should return False for non-existent remote branch."""
        repo, _ = temp_git_repo_with_remote
        assert branch_exists_remote("origin/nonexistent", cwd=repo) is False


class TestGetBranches:
    """Tests for branch listing functions."""

    def test_get_local_branches(self, temp_git_repo: Path) -> None:
        """Should list local branches."""
        branches = get_local_branches(cwd=temp_git_repo)
        # Should have at least main or master
        assert len(branches) >= 1
        assert any(b in ["main", "master"] for b in branches)

    def test_get_local_branches_multiple(self, temp_git_repo: Path) -> None:
        """Should list multiple branches."""
        subprocess.run(
            ["git", "branch", "feature-1"],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "branch", "feature-2"],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )

        branches = get_local_branches(cwd=temp_git_repo)
        assert "feature-1" in branches
        assert "feature-2" in branches

    def test_get_remote_branches(
        self, temp_git_repo_with_remote: tuple[Path, Path]
    ) -> None:
        """Should list remote branches."""
        repo, _ = temp_git_repo_with_remote
        branches = get_remote_branches(cwd=repo)
        # Should have at least origin/main or origin/master
        assert any("origin/" in b for b in branches)


class TestHasUncommittedChanges:
    """Tests for has_uncommitted_changes function."""

    def test_clean_worktree(self, temp_git_repo: Path) -> None:
        """Should return False for clean worktree."""
        assert has_uncommitted_changes(temp_git_repo) is False

    def test_uncommitted_changes(self, temp_git_repo: Path) -> None:
        """Should return True when there are uncommitted changes."""
        # Create an uncommitted file
        (temp_git_repo / "new_file.txt").write_text("content")
        assert has_uncommitted_changes(temp_git_repo) is True

    def test_staged_changes(self, temp_git_repo: Path) -> None:
        """Should return True when there are staged but uncommitted changes."""
        new_file = temp_git_repo / "staged.txt"
        new_file.write_text("content")
        subprocess.run(
            ["git", "add", "staged.txt"],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )
        assert has_uncommitted_changes(temp_git_repo) is True

    def test_nonexistent_path(self, tmp_path: Path) -> None:
        """Should return False for non-existent path."""
        assert has_uncommitted_changes(tmp_path / "nonexistent") is False


class TestCreateWorktree:
    """Tests for create_worktree function."""

    def test_create_new_branch(
        self, temp_git_repo: Path, temp_worktree_base: Path
    ) -> None:
        """Should create worktree with new branch."""
        worktree_path = create_worktree(
            worktree_name="feature-new",
            repo_name="test-repo",
            worktree_base=temp_worktree_base,
            cwd=temp_git_repo,
        )

        assert worktree_path.exists()
        assert worktree_path == temp_worktree_base / "test-repo" / "feature-new"
        assert branch_exists_local("feature-new", cwd=temp_git_repo)

    def test_create_from_existing_branch(
        self, temp_git_repo: Path, temp_worktree_base: Path
    ) -> None:
        """Should create worktree from existing local branch."""
        # First create a branch
        subprocess.run(
            ["git", "branch", "existing-branch"],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )

        worktree_path = create_worktree(
            worktree_name="existing-branch",
            repo_name="test-repo",
            worktree_base=temp_worktree_base,
            cwd=temp_git_repo,
        )

        assert worktree_path.exists()

    def test_create_with_base_branch(
        self, temp_git_repo: Path, temp_worktree_base: Path
    ) -> None:
        """Should create new branch from base branch."""
        # Create a base branch with a commit
        subprocess.run(
            ["git", "branch", "base-branch"],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )

        worktree_path = create_worktree(
            worktree_name="derived-branch",
            repo_name="test-repo",
            base_branch="base-branch",
            worktree_base=temp_worktree_base,
            cwd=temp_git_repo,
        )

        assert worktree_path.exists()
        assert branch_exists_local("derived-branch", cwd=temp_git_repo)

    def test_create_from_remote_branch(
        self, temp_git_repo_with_remote: tuple[Path, Path], temp_worktree_base: Path
    ) -> None:
        """Should create worktree from remote branch reference."""
        repo, remote = temp_git_repo_with_remote

        # Create a new branch on remote
        subprocess.run(
            ["git", "branch", "remote-feature"],
            cwd=repo,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "push", "origin", "remote-feature"],
            cwd=repo,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "branch", "-D", "remote-feature"],
            cwd=repo,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "fetch", "origin"],
            cwd=repo,
            capture_output=True,
            check=True,
        )

        worktree_path = create_worktree(
            worktree_name="origin/remote-feature",
            repo_name="test-repo",
            worktree_base=temp_worktree_base,
            cwd=repo,
        )

        # The path should use the local branch name (without origin/)
        assert worktree_path == temp_worktree_base / "test-repo" / "remote-feature"
        assert worktree_path.exists()
        assert branch_exists_local("remote-feature", cwd=repo)

    def test_create_invalid_base_branch_raises(
        self, temp_git_repo: Path, temp_worktree_base: Path
    ) -> None:
        """Should raise error when base branch doesn't exist."""
        with pytest.raises(RuntimeError, match="does not exist"):
            create_worktree(
                worktree_name="new-feature",
                repo_name="test-repo",
                base_branch="nonexistent-base",
                worktree_base=temp_worktree_base,
                cwd=temp_git_repo,
            )

    def test_create_invalid_remote_branch_raises(
        self, temp_git_repo_with_remote: tuple[Path, Path], temp_worktree_base: Path
    ) -> None:
        """Should raise error when remote branch doesn't exist."""
        repo, _ = temp_git_repo_with_remote

        with pytest.raises(RuntimeError, match="does not exist"):
            create_worktree(
                worktree_name="origin/nonexistent",
                repo_name="test-repo",
                worktree_base=temp_worktree_base,
                cwd=repo,
            )

    def test_creates_repo_directory(
        self, temp_git_repo: Path, temp_worktree_base: Path
    ) -> None:
        """Should create repo subdirectory if it doesn't exist."""
        worktree_path = create_worktree(
            worktree_name="test-branch",
            repo_name="test-repo",
            worktree_base=temp_worktree_base,
            cwd=temp_git_repo,
        )

        assert (temp_worktree_base / "test-repo").exists()
        assert worktree_path.exists()
