"""Tests for cleanup module."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from vibe.cleanup import (
    CleanupStats,
    RemoveResult,
    clean_all_worktrees,
    clean_specific_worktree,
    cleanup_lingering_directory,
    remove_worktree,
)
from vibe.utils import is_directory_empty, is_junk_file


class TestIsJunkFile:
    """Tests for is_junk_file utility function."""

    def test_ds_store_is_junk(self) -> None:
        """Should recognize .DS_Store as junk on macOS."""
        assert is_junk_file(".DS_Store") is True

    def test_regular_file_is_not_junk(self) -> None:
        """Should not treat regular files as junk."""
        assert is_junk_file("file.txt") is False
        assert is_junk_file("README.md") is False

    @patch("vibe.utils.JUNK_FILES", ["Thumbs.db", "desktop.ini"])
    def test_windows_junk_files(self) -> None:
        """Should recognize Windows junk files when configured."""
        assert is_junk_file("Thumbs.db") is True
        assert is_junk_file("desktop.ini") is True
        assert is_junk_file(".DS_Store") is False


class TestIsDirectoryEmpty:
    """Tests for is_directory_empty utility function."""

    def test_empty_directory(self, tmp_path: Path) -> None:
        """Should return True for empty directory."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        assert is_directory_empty(empty_dir) is True

    def test_directory_with_only_ds_store(self, tmp_path: Path) -> None:
        """Should return True for directory with only .DS_Store."""
        dir_path = tmp_path / "ds_store_only"
        dir_path.mkdir()
        (dir_path / ".DS_Store").write_text("")
        assert is_directory_empty(dir_path) is True

    def test_directory_with_files(self, tmp_path: Path) -> None:
        """Should return False for directory with files."""
        dir_path = tmp_path / "has_files"
        dir_path.mkdir()
        (dir_path / "file.txt").write_text("content")
        assert is_directory_empty(dir_path) is False

    def test_directory_with_subdirs(self, tmp_path: Path) -> None:
        """Should return False for directory with subdirectories."""
        dir_path = tmp_path / "has_subdirs"
        dir_path.mkdir()
        (dir_path / "subdir").mkdir()
        assert is_directory_empty(dir_path) is False

    def test_nonexistent_directory(self, tmp_path: Path) -> None:
        """Should return False for non-existent directory."""
        assert is_directory_empty(tmp_path / "nonexistent") is False

    @patch("vibe.utils.JUNK_FILES", ["Thumbs.db", "desktop.ini"])
    def test_directory_with_only_windows_junk(self, tmp_path: Path) -> None:
        """Should return True for directory with only Windows junk files."""
        dir_path = tmp_path / "win_junk"
        dir_path.mkdir()
        (dir_path / "Thumbs.db").write_text("")
        (dir_path / "desktop.ini").write_text("")
        assert is_directory_empty(dir_path) is True

    @patch("vibe.utils.JUNK_FILES", ["Thumbs.db", "desktop.ini"])
    def test_directory_with_windows_junk_and_real_files(self, tmp_path: Path) -> None:
        """Should return False when real files exist alongside Windows junk."""
        dir_path = tmp_path / "win_mixed"
        dir_path.mkdir()
        (dir_path / "Thumbs.db").write_text("")
        (dir_path / "code.py").write_text("print('hello')")
        assert is_directory_empty(dir_path) is False


class TestRemoveWorktree:
    """Tests for remove_worktree function."""

    def test_remove_clean_worktree(
        self, temp_git_repo: Path, temp_worktree_base: Path
    ) -> None:
        """Should remove a clean worktree successfully."""
        # Create a worktree
        worktree_path = temp_worktree_base / "test-repo" / "feature"
        worktree_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "worktree", "add", "-b", "feature", str(worktree_path)],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )

        result = remove_worktree(worktree_path, temp_git_repo)

        assert result in (RemoveResult.REMOVED, RemoveResult.REMOVED_WITH_PARENT)
        assert not worktree_path.exists()

    def test_remove_nonexistent_repo_root(
        self, temp_worktree_base: Path, tmp_path: Path
    ) -> None:
        """Should return FAILED when repo root doesn't exist."""
        worktree_path = temp_worktree_base / "test-repo" / "feature"
        nonexistent_repo = tmp_path / "nonexistent"

        result = remove_worktree(worktree_path, nonexistent_repo)

        assert result == RemoveResult.FAILED

    def test_cleans_empty_parent_directory(
        self, temp_git_repo: Path, temp_worktree_base: Path
    ) -> None:
        """Should clean empty parent directory after removing worktree."""
        # Create a worktree (the only one in repo dir)
        worktree_path = temp_worktree_base / "test-repo" / "only-worktree"
        worktree_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "worktree", "add", "-b", "only-worktree", str(worktree_path)],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )

        result = remove_worktree(worktree_path, temp_git_repo)

        assert result == RemoveResult.REMOVED_WITH_PARENT
        assert not worktree_path.parent.exists()


class TestCleanupLingeringDirectory:
    """Tests for cleanup_lingering_directory function."""

    def test_cleanup_empty_directory(self, tmp_path: Path) -> None:
        """Should clean empty lingering directory."""
        lingering = tmp_path / "lingering"
        lingering.mkdir()

        result = cleanup_lingering_directory(lingering)

        assert result is True
        assert not lingering.exists()

    def test_cleanup_directory_with_files(self, tmp_path: Path) -> None:
        """Should clean lingering directory with files."""
        lingering = tmp_path / "lingering"
        lingering.mkdir()
        (lingering / "file.txt").write_text("content")
        (lingering / "subdir").mkdir()
        (lingering / "subdir" / "nested.txt").write_text("nested")

        result = cleanup_lingering_directory(lingering)

        assert result is True
        assert not lingering.exists()


class TestCleanSpecificWorktree:
    """Tests for clean_specific_worktree function."""

    def test_clean_valid_worktree(
        self, temp_git_repo: Path, temp_worktree_base: Path
    ) -> None:
        """Should clean a valid worktree without changes."""
        # Create a worktree
        worktree_path = temp_worktree_base / "test-repo" / "feature-clean"
        worktree_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "worktree", "add", "-b", "feature-clean", str(worktree_path)],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )

        result = clean_specific_worktree(
            worktree_name="feature-clean",
            repo_name="test-repo",
            repo_root=temp_git_repo,
            worktree_base=temp_worktree_base,
        )

        assert result is True
        assert not worktree_path.exists()

    def test_clean_worktree_with_uncommitted_changes(
        self, temp_git_repo: Path, temp_worktree_base: Path
    ) -> None:
        """Should refuse to clean worktree with uncommitted changes."""
        # Create a worktree
        worktree_path = temp_worktree_base / "test-repo" / "feature-dirty"
        worktree_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "worktree", "add", "-b", "feature-dirty", str(worktree_path)],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )

        # Add uncommitted changes
        (worktree_path / "uncommitted.txt").write_text("uncommitted")

        result = clean_specific_worktree(
            worktree_name="feature-dirty",
            repo_name="test-repo",
            repo_root=temp_git_repo,
            worktree_base=temp_worktree_base,
        )

        assert result is False
        assert worktree_path.exists()

    def test_clean_nonexistent_worktree(
        self, temp_git_repo: Path, temp_worktree_base: Path
    ) -> None:
        """Should return False for non-existent worktree."""
        result = clean_specific_worktree(
            worktree_name="nonexistent",
            repo_name="test-repo",
            repo_root=temp_git_repo,
            worktree_base=temp_worktree_base,
        )

        assert result is False

    def test_clean_invalid_worktree_directory(
        self, temp_git_repo: Path, temp_worktree_base: Path
    ) -> None:
        """Should return False for directory that isn't a valid worktree."""
        # Create directory but not as worktree
        fake_worktree = temp_worktree_base / "test-repo" / "fake-worktree"
        fake_worktree.mkdir(parents=True)
        (fake_worktree / "file.txt").write_text("content")

        result = clean_specific_worktree(
            worktree_name="fake-worktree",
            repo_name="test-repo",
            repo_root=temp_git_repo,
            worktree_base=temp_worktree_base,
        )

        assert result is False


class TestCleanAllWorktrees:
    """Tests for clean_all_worktrees function."""

    def test_clean_empty_base(self, tmp_path: Path) -> None:
        """Should handle empty worktree base gracefully."""
        empty_base = tmp_path / "empty_base"
        empty_base.mkdir()

        stats = clean_all_worktrees(worktree_base=empty_base)

        assert isinstance(stats, CleanupStats)
        assert stats.cleaned == 0
        assert stats.skipped == 0

    def test_clean_nonexistent_base(self, tmp_path: Path) -> None:
        """Should handle non-existent worktree base gracefully."""
        stats = clean_all_worktrees(worktree_base=tmp_path / "nonexistent")

        assert isinstance(stats, CleanupStats)
        assert stats.cleaned == 0

    def test_cleans_multiple_worktrees(
        self, temp_git_repo: Path, temp_worktree_base: Path
    ) -> None:
        """Should clean multiple worktrees."""
        # Create multiple worktrees
        repo_dir = temp_worktree_base / "test-repo"
        repo_dir.mkdir(parents=True, exist_ok=True)

        for i in range(3):
            worktree_path = repo_dir / f"feature-{i}"
            subprocess.run(
                ["git", "worktree", "add", "-b", f"feature-{i}", str(worktree_path)],
                cwd=temp_git_repo,
                capture_output=True,
                check=True,
            )

        stats = clean_all_worktrees(worktree_base=temp_worktree_base)

        assert stats.cleaned == 3
        assert stats.skipped == 0
        assert not repo_dir.exists()  # Should be cleaned as empty

    def test_skips_worktrees_with_changes(
        self, temp_git_repo: Path, temp_worktree_base: Path
    ) -> None:
        """Should skip worktrees with uncommitted changes."""
        repo_dir = temp_worktree_base / "test-repo"
        repo_dir.mkdir(parents=True, exist_ok=True)

        # Create a worktree
        worktree_path = repo_dir / "dirty-feature"
        subprocess.run(
            ["git", "worktree", "add", "-b", "dirty-feature", str(worktree_path)],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )

        # Add uncommitted changes
        (worktree_path / "uncommitted.txt").write_text("uncommitted")

        stats = clean_all_worktrees(worktree_base=temp_worktree_base)

        assert stats.skipped == 1
        assert stats.cleaned == 0
        assert worktree_path.exists()

    def test_cleans_lingering_directories(
        self, temp_git_repo: Path, temp_worktree_base: Path
    ) -> None:
        """Should clean lingering directories that aren't valid worktrees."""
        repo_dir = temp_worktree_base / "test-repo"
        repo_dir.mkdir(parents=True, exist_ok=True)

        # Create a valid worktree first (so we have a reference to the repo)
        valid_worktree = repo_dir / "valid-feature"
        subprocess.run(
            ["git", "worktree", "add", "-b", "valid-feature", str(valid_worktree)],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )

        # Create a lingering directory (not a worktree)
        lingering = repo_dir / "lingering-dir"
        lingering.mkdir()
        (lingering / "file.txt").write_text("orphaned content")

        stats = clean_all_worktrees(worktree_base=temp_worktree_base)

        assert stats.lingering == 1
        assert not lingering.exists()
