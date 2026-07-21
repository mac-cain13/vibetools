"""Tests for git operations module."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from vibe.git_ops import (
    ContextType,
    CurrentContext,
    RepoInfo,
    WorktreeStatus,
    branch_exists_local,
    branch_exists_remote,
    branch_to_worktree_dirname,
    check_worktree_exists,
    create_worktree,
    get_current_context,
    get_local_branches,
    get_remote_branches,
    get_repo_info,
    has_uncommitted_changes,
    is_git_worktree,
    is_inside_worktree_base,
    validate_git_repo,
    worktree_dirname_to_branch,
    worktree_path_for_branch,
)

# Branch <-> dirname mapping cases: (branch, expected encoded dirname)
BRANCH_DIRNAME_CASES = [
    ("main", "main"),
    ("feature/retry-upload", "feature%2Fretry-upload"),
    ("a/b/c", "a%2Fb%2Fc"),
    ("a%b", "a%25b"),
    ("a%2Fb", "a%252Fb"),  # A branch literally containing the text %2F
    ("fix/50%-faster", "fix%2F50%25-faster"),
]


class TestBranchDirnameMapping:
    """Tests for branch <-> worktree directory name mapping."""

    @pytest.mark.parametrize("branch,dirname", BRANCH_DIRNAME_CASES)
    def test_encode(self, branch: str, dirname: str) -> None:
        """Should encode branch names to the expected directory names."""
        assert branch_to_worktree_dirname(branch) == dirname

    @pytest.mark.parametrize("branch,dirname", BRANCH_DIRNAME_CASES)
    def test_decode(self, branch: str, dirname: str) -> None:
        """Should decode directory names back to the expected branch names."""
        assert worktree_dirname_to_branch(dirname) == branch

    @pytest.mark.parametrize("branch,dirname", BRANCH_DIRNAME_CASES)
    def test_round_trip(self, branch: str, dirname: str) -> None:
        """decode(encode(x)) should equal x for all cases."""
        assert worktree_dirname_to_branch(branch_to_worktree_dirname(branch)) == branch

    @pytest.mark.parametrize("branch,dirname", BRANCH_DIRNAME_CASES)
    def test_encoded_dirname_is_single_path_component(
        self, branch: str, dirname: str
    ) -> None:
        """Encoded directory names must never contain '/'."""
        assert "/" not in branch_to_worktree_dirname(branch)


class TestWorktreePathForBranch:
    """Tests for worktree_path_for_branch function."""

    def test_plain_branch(self, tmp_path: Path) -> None:
        """Should build base/repo/branch for a branch without slashes."""
        path = worktree_path_for_branch("test-repo", "main", worktree_base=tmp_path)
        assert path == tmp_path / "test-repo" / "main"

    def test_slashed_branch_is_encoded(self, tmp_path: Path) -> None:
        """Should encode slashed branch names into a single path component."""
        path = worktree_path_for_branch(
            "test-repo", "feature/retry-upload", worktree_base=tmp_path
        )
        assert path == tmp_path / "test-repo" / "feature%2Fretry-upload"
        assert path.parent == tmp_path / "test-repo"


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
        assert info.main_root == temp_git_repo

    def test_from_subdirectory(self, temp_git_repo: Path) -> None:
        """Should return correct info from subdirectory."""
        subdir = temp_git_repo / "subdir"
        subdir.mkdir()
        info = get_repo_info(cwd=subdir)
        assert info.root == temp_git_repo
        assert info.name == "test-repo"
        assert info.main_root == temp_git_repo

    def test_from_worktree_uses_main_repo_name(
        self, temp_git_repo: Path, tmp_path: Path
    ) -> None:
        """Inside a linked worktree, name/main_root come from the main repo.

        Regression: running 'vibe <branch>' from a worktree used the
        worktree's directory name as the repo name, placing the new worktree
        under _vibecoding/<worktree-name>/ instead of _vibecoding/<repo>/.
        """
        worktree_path = tmp_path / "_vibecoding" / "test-repo" / "os27"
        subprocess.run(
            ["git", "worktree", "add", "-b", "os27", str(worktree_path)],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )

        info = get_repo_info(cwd=worktree_path)

        assert info.root == worktree_path
        assert info.name == "test-repo"
        assert info.main_root == temp_git_repo

    def test_from_worktree_subdirectory(
        self, temp_git_repo: Path, tmp_path: Path
    ) -> None:
        """Should also resolve the main repo name from a worktree subdir."""
        worktree_path = tmp_path / "_vibecoding" / "test-repo" / "os27"
        subprocess.run(
            ["git", "worktree", "add", "-b", "os27", str(worktree_path)],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )
        subdir = worktree_path / "subdir"
        subdir.mkdir()

        info = get_repo_info(cwd=subdir)

        assert info.root == worktree_path
        assert info.name == "test-repo"
        assert info.main_root == temp_git_repo

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

    def test_slashed_branch_not_exists(
        self, temp_git_repo: Path, temp_worktree_base: Path
    ) -> None:
        """Should return NOT_EXISTS for a slashed branch without a worktree."""
        status = check_worktree_exists(
            worktree_name="feature/retry-upload",
            repo_name="test-repo",
            worktree_base=temp_worktree_base,
            cwd=temp_git_repo,
        )
        assert status == WorktreeStatus.NOT_EXISTS

    def test_slashed_branch_exists_valid(
        self, temp_git_repo: Path, temp_worktree_base: Path
    ) -> None:
        """Should find a worktree for a slashed branch via the encoded path."""
        # Create a worktree at the encoded directory for the slashed branch
        worktree_path = temp_worktree_base / "test-repo" / "feature%2Fretry-upload"
        worktree_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "git",
                "worktree",
                "add",
                "-b",
                "feature/retry-upload",
                str(worktree_path),
            ],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )

        status = check_worktree_exists(
            worktree_name="feature/retry-upload",
            repo_name="test-repo",
            worktree_base=temp_worktree_base,
            cwd=temp_git_repo,
        )
        assert status == WorktreeStatus.EXISTS_VALID


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

    def test_create_with_base_branch_checked_out_in_worktree(
        self, temp_git_repo: Path, temp_worktree_base: Path
    ) -> None:
        """Should branch from a base that is checked out in another worktree.

        Covers 'vibe <new> --from <branch>' run from the main checkout while
        <branch> lives in its own worktree: the new branch must start at the
        base branch's tip, not the main checkout's HEAD.
        """
        # Give the base branch a commit that main doesn't have, and check it
        # out in a worktree of its own.
        base_worktree = temp_worktree_base / "test-repo" / "os27"
        subprocess.run(
            ["git", "worktree", "add", "-b", "os27", str(base_worktree)],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )
        (base_worktree / "os27.txt").write_text("os27\n")
        subprocess.run(
            ["git", "add", "."], cwd=base_worktree, capture_output=True, check=True
        )
        subprocess.run(
            ["git", "commit", "-m", "os27 work"],
            cwd=base_worktree,
            capture_output=True,
            check=True,
        )

        worktree_path = create_worktree(
            worktree_name="appintents",
            repo_name="test-repo",
            base_branch="os27",
            worktree_base=temp_worktree_base,
            cwd=temp_git_repo,
        )

        assert worktree_path == temp_worktree_base / "test-repo" / "appintents"
        assert worktree_path.exists()
        tips = subprocess.run(
            ["git", "rev-parse", "appintents", "os27"],
            cwd=temp_git_repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
        assert tips[0] == tips[1]

    def test_existing_branch_warns_when_base_branch_given(
        self,
        temp_git_repo: Path,
        temp_worktree_base: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Should warn that --from is ignored when the branch already exists."""
        subprocess.run(
            ["git", "branch", "existing-branch"],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "branch", "some-base"],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )

        worktree_path = create_worktree(
            worktree_name="existing-branch",
            repo_name="test-repo",
            base_branch="some-base",
            worktree_base=temp_worktree_base,
            cwd=temp_git_repo,
        )

        assert worktree_path.exists()
        # Normalize rich's line wrapping before matching the message.
        output = " ".join(capsys.readouterr().out.split())
        assert "Branch 'existing-branch' already exists" in output
        assert "--from flag will be ignored" in output

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

    def test_create_with_slashed_branch(
        self, temp_git_repo: Path, temp_worktree_base: Path
    ) -> None:
        """Should encode slashed branch names into a flat directory name."""
        worktree_path = create_worktree(
            worktree_name="feature/retry-upload",
            repo_name="test-repo",
            worktree_base=temp_worktree_base,
            cwd=temp_git_repo,
        )

        # Directory is the encoded name, directly under the repo dir
        assert worktree_path == (
            temp_worktree_base / "test-repo" / "feature%2Fretry-upload"
        )
        assert worktree_path.exists()
        # No nested 'feature/' directory was created
        assert not (temp_worktree_base / "test-repo" / "feature").exists()

        # The branch inside the worktree is the real slashed branch name
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            cwd=worktree_path,
            check=True,
        )
        assert result.stdout.strip() == "feature/retry-upload"
        assert branch_exists_local("feature/retry-upload", cwd=temp_git_repo)

    def test_create_from_remote_slashed_branch(
        self, temp_git_repo_with_remote: tuple[Path, Path], temp_worktree_base: Path
    ) -> None:
        """Should encode the local tracking branch dirname for origin/ refs."""
        repo, _ = temp_git_repo_with_remote

        # Create a slashed branch on the remote, then remove it locally
        subprocess.run(
            ["git", "branch", "feature/remote-slashed"],
            cwd=repo,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "push", "origin", "feature/remote-slashed"],
            cwd=repo,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "branch", "-D", "feature/remote-slashed"],
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
            worktree_name="origin/feature/remote-slashed",
            repo_name="test-repo",
            worktree_base=temp_worktree_base,
            cwd=repo,
        )

        assert worktree_path == (
            temp_worktree_base / "test-repo" / "feature%2Fremote-slashed"
        )
        assert worktree_path.exists()
        assert branch_exists_local("feature/remote-slashed", cwd=repo)

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


class TestIsInsideWorktreeBase:
    """Tests for is_inside_worktree_base function."""

    def test_inside_worktree_base(self, tmp_path: Path) -> None:
        """Should return True when inside worktree base."""
        worktree_base = tmp_path / "worktrees"
        worktree_base.mkdir()
        subdir = worktree_base / "repo" / "branch"
        subdir.mkdir(parents=True)

        assert is_inside_worktree_base(cwd=subdir, worktree_base=worktree_base) is True

    def test_outside_worktree_base(self, tmp_path: Path) -> None:
        """Should return False when outside worktree base."""
        worktree_base = tmp_path / "worktrees"
        worktree_base.mkdir()
        other_dir = tmp_path / "other"
        other_dir.mkdir()

        assert is_inside_worktree_base(cwd=other_dir, worktree_base=worktree_base) is False


class TestIsGitWorktree:
    """Tests for is_git_worktree function."""

    def test_main_repo_not_worktree(self, temp_git_repo: Path) -> None:
        """Should return False for main repository."""
        assert is_git_worktree(cwd=temp_git_repo) is False

    def test_worktree_is_worktree(
        self, temp_git_repo: Path, temp_worktree_base: Path
    ) -> None:
        """Should return True for a worktree."""
        # Create a worktree
        worktree_path = temp_worktree_base / "test-repo" / "feature"
        worktree_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "worktree", "add", "-b", "feature", str(worktree_path)],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )

        assert is_git_worktree(cwd=worktree_path) is True

    def test_not_git_repo(self, tmp_path: Path) -> None:
        """Should return False when not in git repo."""
        assert is_git_worktree(cwd=tmp_path) is False


class TestGetCurrentContext:
    """Tests for get_current_context function."""

    def test_not_in_git_repo(self, tmp_path: Path) -> None:
        """Should return NONE context when not in git repo."""
        context = get_current_context(cwd=tmp_path)

        assert context.context_type == ContextType.NONE
        assert context.local_path is None
        assert context.remote_path is None

    def test_in_main_repo(self, temp_git_repo: Path, tmp_path: Path) -> None:
        """Should return MAIN_REPO context in main repository."""
        # Use repo_base and worktree_base that contain temp_git_repo
        repo_base = temp_git_repo.parent

        context = get_current_context(
            cwd=temp_git_repo,
            repo_base=repo_base,
            worktree_base=repo_base / "_vibecoding",
            remote_base=repo_base,
        )

        assert context.context_type == ContextType.MAIN_REPO
        assert context.local_path == temp_git_repo
        assert context.repo_name == "test-repo"
        assert context.remote_path == repo_base / "test-repo"

    def test_in_worktree(
        self, temp_git_repo: Path, temp_worktree_base: Path
    ) -> None:
        """Should return WORKTREE context in a worktree."""
        # Create a worktree in expected structure: worktree_base/repo_name/branch_name
        repo_name = "test-repo"
        worktree_name = "feature"
        worktree_path = temp_worktree_base / repo_name / worktree_name
        worktree_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "worktree", "add", "-b", worktree_name, str(worktree_path)],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )

        remote_base = temp_worktree_base.parent

        context = get_current_context(
            cwd=worktree_path,
            repo_base=temp_worktree_base.parent,
            worktree_base=temp_worktree_base,
            remote_base=remote_base,
        )

        assert context.context_type == ContextType.WORKTREE
        assert context.local_path == worktree_path
        assert context.repo_name == repo_name
        assert context.worktree_name == worktree_name
        assert context.branch == worktree_name  # No slashes: decoded == dirname

    def test_in_worktree_with_slashed_branch(
        self, temp_git_repo: Path, temp_worktree_base: Path
    ) -> None:
        """Should report the encoded dirname and the decoded branch name."""
        branch = "feature/retry-upload"
        worktree_path = create_worktree(
            worktree_name=branch,
            repo_name="test-repo",
            worktree_base=temp_worktree_base,
            cwd=temp_git_repo,
        )

        remote_base = temp_worktree_base.parent

        context = get_current_context(
            cwd=worktree_path,
            repo_base=temp_worktree_base.parent,
            worktree_base=temp_worktree_base,
            remote_base=remote_base,
        )

        assert context.context_type == ContextType.WORKTREE
        assert context.local_path == worktree_path
        assert context.repo_name == "test-repo"
        # worktree_name is the on-disk (encoded) directory name
        assert context.worktree_name == "feature%2Fretry-upload"
        # branch is the decoded branch name
        assert context.branch == branch
        # remote_path uses the encoded directory name
        assert context.remote_path == (
            remote_base / "_vibecoding" / "test-repo" / "feature%2Fretry-upload"
        )

    def test_branch_is_none_outside_worktree(self, temp_git_repo: Path) -> None:
        """Should leave branch as None outside worktree context."""
        repo_base = temp_git_repo.parent

        context = get_current_context(
            cwd=temp_git_repo,
            repo_base=repo_base,
            worktree_base=repo_base / "_vibecoding",
            remote_base=repo_base,
        )

        assert context.context_type == ContextType.MAIN_REPO
        assert context.branch is None

    def test_repo_not_in_expected_location(self, temp_git_repo: Path, tmp_path: Path) -> None:
        """Should return MAIN_REPO but with no remote_path when not in expected location."""
        # Use a different repo_base that doesn't contain temp_git_repo
        different_base = tmp_path / "different_base"
        different_base.mkdir()

        context = get_current_context(
            cwd=temp_git_repo,
            repo_base=different_base,
            worktree_base=different_base / "_vibecoding",
            remote_base=different_base,
        )

        assert context.context_type == ContextType.MAIN_REPO
        assert context.local_path == temp_git_repo
        assert context.remote_path is None  # Not in expected location


class TestBranchCheckoutHelpers:
    """Tests for stranded-branch detection and recovery helpers."""

    def test_find_branch_checkout_main(self, temp_git_repo: Path) -> None:
        """Should find a branch checked out in the main checkout."""
        from vibe.git_ops import find_branch_checkout

        subprocess.run(
            ["git", "checkout", "-b", "feature-x"],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )

        found = find_branch_checkout("feature-x", cwd=temp_git_repo)
        assert found is not None
        assert found.resolve() == temp_git_repo.resolve()

    def test_find_branch_checkout_in_worktree(
        self, temp_git_repo: Path, tmp_path: Path
    ) -> None:
        """Should find a branch checked out in a linked worktree."""
        from vibe.git_ops import find_branch_checkout

        wt = tmp_path / "wt"
        subprocess.run(
            ["git", "worktree", "add", "-b", "feature-y", str(wt)],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )

        found = find_branch_checkout("feature-y", cwd=temp_git_repo)
        assert found is not None
        assert found.resolve() == wt.resolve()

    def test_find_branch_checkout_not_checked_out(
        self, temp_git_repo: Path
    ) -> None:
        """Should return None for a branch checked out nowhere."""
        from vibe.git_ops import find_branch_checkout

        subprocess.run(
            ["git", "branch", "idle-branch"],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )

        assert find_branch_checkout("idle-branch", cwd=temp_git_repo) is None
        assert find_branch_checkout("nope", cwd=temp_git_repo) is None

    def test_switch_checkout_to_branch(self, temp_git_repo: Path) -> None:
        """Should switch the checkout to another existing branch."""
        from vibe.git_ops import switch_checkout_to_branch

        subprocess.run(
            ["git", "checkout", "-b", "feature-z"],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )

        assert switch_checkout_to_branch(temp_git_repo, "main") is True
        current = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=temp_git_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert current.stdout.strip() == "main"

    def test_switch_checkout_to_missing_branch_fails(
        self, temp_git_repo: Path
    ) -> None:
        """Should return False when the target branch does not exist."""
        from vibe.git_ops import switch_checkout_to_branch

        assert switch_checkout_to_branch(temp_git_repo, "no-such-branch") is False

    def test_prune_worktrees_frees_stale_branch(
        self, temp_git_repo: Path, tmp_path: Path
    ) -> None:
        """Should drop a registration whose directory was removed."""
        import shutil

        from vibe.git_ops import find_branch_checkout, prune_worktrees

        wt = tmp_path / "stale-wt"
        subprocess.run(
            ["git", "worktree", "add", "-b", "stale", str(wt)],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )
        shutil.rmtree(wt)
        assert find_branch_checkout("stale", cwd=temp_git_repo) is not None

        prune_worktrees(cwd=temp_git_repo)
        assert find_branch_checkout("stale", cwd=temp_git_repo) is None

    def test_get_default_branch_from_origin(
        self, temp_git_repo_with_remote: tuple[Path, Path]
    ) -> None:
        """Should resolve the default branch from origin/HEAD."""
        from vibe.git_ops import get_default_branch

        repo, _ = temp_git_repo_with_remote
        subprocess.run(
            ["git", "remote", "set-head", "origin", "--auto"],
            cwd=repo,
            capture_output=True,
        )

        assert get_default_branch(cwd=repo) in {"main", "master"}

    def test_get_default_branch_no_origin(self, temp_git_repo: Path) -> None:
        """Should return None when there is no origin HEAD."""
        from vibe.git_ops import get_default_branch

        assert get_default_branch(cwd=temp_git_repo) is None
