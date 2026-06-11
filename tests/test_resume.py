"""Tests for 'vibe resume <ticket>' — the resume state x worktree matrix."""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from vibe.cli import (
    RESUME_BOOTSTRAP_PROMPT,
    StrandedBranchChoice,
    _build_resume_command,
    _resolve_resume_tool,
    _resolve_switchback_branch,
    app,
    complete_ticket_ids,
)
from vibe.git_ops import (
    branch_to_worktree_dirname,
    find_branch_checkout,
    get_local_branches,
    get_tip_commit_subject,
)
from vibe.tickets import Ticket, read_ticket

runner = CliRunner()


def write_ticket(store: Path, ticket_id: str, **fields: str) -> Path:
    """Write a minimal ticket file into a store directory.

    Args:
        store: Ticket store directory
        ticket_id: Ticket id (also the filename stem)
        **fields: Additional frontmatter fields

    Returns:
        Path to the written ticket file
    """
    store.mkdir(parents=True, exist_ok=True)
    lines = ["---", f"id: {ticket_id}"]
    for key, value in fields.items():
        lines.append(f"{key}: {value}")
    lines.extend(["---", "", "Body."])
    path = store / f"{ticket_id}.md"
    path.write_text("\n".join(lines) + "\n")
    return path


def create_branch_with_commit(
    repo: Path,
    branch: str,
    message: str,
    filename: str = "work.txt",
) -> None:
    """Create a branch carrying one commit, leaving it not checked out.

    Args:
        repo: Path to the git repository
        branch: Branch name to create
        message: Commit message for the branch's commit
        filename: File created in the commit
    """
    subprocess.run(
        ["git", "checkout", "-b", branch],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    (repo / filename).write_text("work\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "checkout", "-"], cwd=repo, capture_output=True, check=True
    )


def add_worktree(repo: Path, worktree_base: Path, branch: str) -> Path:
    """Create a git worktree for a new branch at its encoded path.

    Args:
        repo: Path to the git repository
        worktree_base: Base directory for worktrees
        branch: Branch name (may contain '/')

    Returns:
        Path to the created worktree
    """
    path = worktree_base / "test-repo" / branch_to_worktree_dirname(branch)
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "worktree", "add", "-b", branch, str(path)],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    return path


def commit_in_worktree(
    worktree: Path,
    message: str,
    filename: str = "parked.txt",
) -> None:
    """Create a commit in a worktree (staging everything, like park does).

    Args:
        worktree: Path to the worktree
        message: Commit message
        filename: File created before committing
    """
    (worktree / filename).write_text("parked\n")
    subprocess.run(
        ["git", "add", "-A"], cwd=worktree, capture_output=True, check=True
    )
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=worktree,
        capture_output=True,
        check=True,
    )


def git_porcelain(worktree: Path) -> set[str]:
    """Get the non-empty 'git status --porcelain' lines of a worktree.

    Args:
        worktree: Path to the worktree

    Returns:
        Set of porcelain status lines
    """
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        cwd=worktree,
        check=True,
    )
    return {line for line in result.stdout.splitlines() if line.strip()}


@dataclass
class ResumeEnv:
    """A patched resume environment rooted in a temp directory."""

    repo: Path
    repo_base: Path
    worktree_base: Path
    store: Path


def _setup_resume_env(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> ResumeEnv:
    """Patch the cli module constants to point at a temp environment.

    Args:
        repo: Path to the git repository (must live under tmp_path)
        tmp_path: Temp directory acting as the repo base
        monkeypatch: Pytest monkeypatch fixture

    Returns:
        ResumeEnv describing the patched environment
    """
    worktree_base = tmp_path / "worktrees"
    worktree_base.mkdir(exist_ok=True)
    store = tmp_path / "_vibeboard"
    store.mkdir(exist_ok=True)
    monkeypatch.setattr("vibe.cli.LOCAL_REPO_BASE", tmp_path)
    monkeypatch.setattr("vibe.cli.LOCAL_WORKTREE_BASE", worktree_base)
    monkeypatch.setattr("vibe.cli.VIBEBOARD_DIR", store)
    monkeypatch.setattr("vibe.cli.REMOTE_REPO_BASE", Path("/remote-repos"))
    return ResumeEnv(
        repo=repo, repo_base=tmp_path, worktree_base=worktree_base, store=store
    )


@pytest.fixture
def resume_env(
    temp_git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> ResumeEnv:
    """Set up a patched resume environment around a real git repo."""
    return _setup_resume_env(temp_git_repo, tmp_path, monkeypatch)


@pytest.fixture
def resume_env_with_remote(
    temp_git_repo_with_remote: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> ResumeEnv:
    """Set up a patched resume environment around a repo with an origin."""
    repo, _ = temp_git_repo_with_remote
    return _setup_resume_env(repo, tmp_path, monkeypatch)


class TestResumeCliShape:
    """Tests for the 'vibe resume <ticket>' command-line shape."""

    def test_help_shows_resume_example(self) -> None:
        """Should mention resume in the command help."""
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "resume" in result.stdout

    def test_resume_without_ticket_id_errors(
        self, resume_env: ResumeEnv
    ) -> None:
        """Should error with usage and available ids when ticket omitted."""
        write_ticket(resume_env.store, "test-repo-1", state="todo")

        result = runner.invoke(app, ["resume"])

        assert result.exit_code == 1
        assert "requires a ticket id" in result.stdout
        assert "vibe resume <ticket-id>" in result.stdout
        assert "test-repo-1" in result.stdout

    def test_resume_without_ticket_id_empty_store(
        self, resume_env: ResumeEnv
    ) -> None:
        """Should mention the empty store when no tickets exist."""
        result = runner.invoke(app, ["resume"])

        assert result.exit_code == 1
        assert "No tickets found" in result.stdout

    def test_second_positional_without_resume_errors(self) -> None:
        """Should reject a second positional unless the first is 'resume'."""
        result = runner.invoke(app, ["feature-branch", "extra-arg"])

        assert result.exit_code == 1
        assert "Unexpected argument" in result.stdout
        assert "vibe resume <ticket-id>" in result.stdout

    def test_unknown_ticket_errors_listing_available(
        self, resume_env: ResumeEnv
    ) -> None:
        """Should error and list available ids for an unknown ticket."""
        write_ticket(resume_env.store, "test-repo-7", state="todo")

        result = runner.invoke(app, ["resume", "nope-1"])

        assert result.exit_code == 1
        assert "No ticket found" in result.stdout
        assert "test-repo-7" in result.stdout

    def test_listing_tolerates_markup_like_titles(
        self, resume_env: ResumeEnv
    ) -> None:
        """Should print bracketed hand-edited titles literally, not crash."""
        write_ticket(
            resume_env.store, "test-repo-8", state="todo", title="[v1.2] release"
        )
        write_ticket(
            resume_env.store,
            "test-repo-9",
            state="todo",
            title='"broken [/] title"',
        )

        result = runner.invoke(app, ["resume", "nope-1"])

        assert result.exit_code == 1
        assert "[v1.2] release" in result.stdout
        assert "broken [/] title" in result.stdout

    def test_missing_repo_errors(self, resume_env: ResumeEnv) -> None:
        """Should error loudly when the ticket's repo doesn't exist."""
        write_ticket(resume_env.store, "ghost-1", repo="ghost", state="todo")

        result = runner.invoke(app, ["resume", "ghost-1"])

        assert result.exit_code == 1
        assert "not found" in result.stdout

    def test_repo_not_a_git_repository_errors(
        self, resume_env: ResumeEnv
    ) -> None:
        """Should error loudly when the repo directory isn't a git repo."""
        (resume_env.repo_base / "plain").mkdir()
        write_ticket(resume_env.store, "plain-1", repo="plain", state="todo")

        result = runner.invoke(app, ["resume", "plain-1"])

        assert result.exit_code == 1
        assert "not a git" in result.stdout

    def test_complete_ticket_ids(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should offer ticket ids from the store as completions."""
        store = tmp_path / "_vibeboard"
        write_ticket(store, "vibe-1", state="todo")
        write_ticket(store, "vibe-2", state="doing")
        write_ticket(store, "bezel-3", state="on_hold")
        monkeypatch.setattr("vibe.cli.VIBEBOARD_DIR", store)

        assert sorted(complete_ticket_ids("")) == ["bezel-3", "vibe-1", "vibe-2"]
        assert sorted(complete_ticket_ids("vibe-")) == ["vibe-1", "vibe-2"]
        assert complete_ticket_ids("zzz") == []


class TestResumeMatrix:
    """Tests for the resume state x worktree matrix."""

    def test_on_hold_without_worktree_recreates_and_unwinds(
        self, resume_env: ResumeEnv
    ) -> None:
        """Should recreate the worktree and unwind the park marker."""
        create_branch_with_commit(
            resume_env.repo, "feature-x", "wip: park test-repo-2", "parked.txt"
        )
        ticket_path = write_ticket(
            resume_env.store,
            "test-repo-2",
            repo="test-repo",
            branch="feature-x",
            state="on_hold",
            tool="claude",
        )
        worktree_path = resume_env.worktree_base / "test-repo" / "feature-x"

        with patch(
            "vibe.cli.connect_to_remote", return_value=0
        ) as mock_connect:
            result = runner.invoke(app, ["resume", "test-repo-2"])

        assert result.exit_code == 0
        assert worktree_path.is_dir()
        # Park commit unwound: tip is back to the initial commit and the
        # parked file is restored as an untracked working-tree change
        assert get_tip_commit_subject(worktree_path) == "Initial commit"
        assert (worktree_path / "parked.txt").is_file()
        assert "?? parked.txt" in git_porcelain(worktree_path)

        mock_connect.assert_called_once()
        kwargs = mock_connect.call_args.kwargs
        assert kwargs["repo_name"] == "test-repo"
        assert kwargs["worktree_name"] == "feature-x"

        # Resume consumes the ticket — the work is no longer parked
        assert not ticket_path.exists()

    def test_on_hold_with_worktree_reuses_and_unwinds(
        self, resume_env: ResumeEnv
    ) -> None:
        """Should reuse the existing worktree and unwind the park marker."""
        worktree_path = add_worktree(
            resume_env.repo, resume_env.worktree_base, "feature-y"
        )
        commit_in_worktree(worktree_path, "wip: park test-repo-3")
        ticket_path = write_ticket(
            resume_env.store,
            "test-repo-3",
            repo="test-repo",
            branch="feature-y",
            state="on_hold",
            tool="claude",
        )

        with patch(
            "vibe.cli.connect_to_remote", return_value=0
        ) as mock_connect:
            result = runner.invoke(app, ["resume", "test-repo-3"])

        assert result.exit_code == 0
        assert get_tip_commit_subject(worktree_path) == "Initial commit"
        assert "?? parked.txt" in git_porcelain(worktree_path)
        mock_connect.assert_called_once()
        assert not ticket_path.exists()

    def test_existing_worktree_non_marker_tip_not_unwound(
        self, resume_env: ResumeEnv
    ) -> None:
        """Should reconnect and never unwind a non-marker tip."""
        worktree_path = add_worktree(
            resume_env.repo, resume_env.worktree_base, "feature-w"
        )
        commit_in_worktree(worktree_path, "normal work commit")
        ticket_path = write_ticket(
            resume_env.store,
            "test-repo-4",
            repo="test-repo",
            branch="feature-w",
            state="on_hold",
            tool="claude",
        )

        with patch(
            "vibe.cli.connect_to_remote", return_value=0
        ) as mock_connect:
            result = runner.invoke(app, ["resume", "test-repo-4"])

        assert result.exit_code == 0
        assert get_tip_commit_subject(worktree_path) == "normal work commit"
        assert git_porcelain(worktree_path) == set()
        mock_connect.assert_called_once()
        assert not ticket_path.exists()

    def test_missing_worktree_non_marker_tip_recreates(
        self, resume_env: ResumeEnv
    ) -> None:
        """Should recreate the worktree post-reboot without unwinding."""
        create_branch_with_commit(
            resume_env.repo, "feature-z", "normal work commit"
        )
        write_ticket(
            resume_env.store,
            "test-repo-5",
            repo="test-repo",
            branch="feature-z",
            state="on_hold",
            tool="claude",
        )
        worktree_path = resume_env.worktree_base / "test-repo" / "feature-z"

        with patch(
            "vibe.cli.connect_to_remote", return_value=0
        ) as mock_connect:
            result = runner.invoke(app, ["resume", "test-repo-5"])

        assert result.exit_code == 0
        assert worktree_path.is_dir()
        assert get_tip_commit_subject(worktree_path) == "normal work commit"
        mock_connect.assert_called_once()

    def test_slashed_branch_uses_encoded_worktree(
        self, resume_env: ResumeEnv
    ) -> None:
        """Should place the worktree at the encoded dirname for '/' branches."""
        branch = "feature/retry-upload"
        create_branch_with_commit(
            resume_env.repo, branch, "wip: park test-repo-6", "parked.txt"
        )
        ticket_path = write_ticket(
            resume_env.store,
            "test-repo-6",
            repo="test-repo",
            branch=branch,
            state="on_hold",
            tool="claude",
        )
        worktree_path = (
            resume_env.worktree_base / "test-repo" / "feature%2Fretry-upload"
        )

        with patch(
            "vibe.cli.connect_to_remote", return_value=0
        ) as mock_connect:
            result = runner.invoke(app, ["resume", "test-repo-6"])

        assert result.exit_code == 0
        assert worktree_path.is_dir()
        assert get_tip_commit_subject(worktree_path) == "Initial commit"
        assert (
            mock_connect.call_args.kwargs["worktree_name"]
            == "feature%2Fretry-upload"
        )
        assert not ticket_path.exists()

    def test_branch_only_on_origin_creates_tracking_worktree(
        self, resume_env_with_remote: ResumeEnv
    ) -> None:
        """Should create the worktree from origin/<branch> when local is gone."""
        env = resume_env_with_remote
        create_branch_with_commit(env.repo, "feature-r", "remote-only work")
        subprocess.run(
            ["git", "push", "-u", "origin", "feature-r"],
            cwd=env.repo,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "branch", "-D", "feature-r"],
            cwd=env.repo,
            capture_output=True,
            check=True,
        )
        write_ticket(
            env.store,
            "test-repo-8",
            repo="test-repo",
            branch="feature-r",
            state="on_hold",
            tool="claude",
        )
        worktree_path = env.worktree_base / "test-repo" / "feature-r"

        with patch(
            "vibe.cli.connect_to_remote", return_value=0
        ) as mock_connect:
            result = runner.invoke(app, ["resume", "test-repo-8"])

        assert result.exit_code == 0
        assert worktree_path.is_dir()
        assert get_tip_commit_subject(worktree_path) == "remote-only work"
        mock_connect.assert_called_once()

    def test_branch_missing_everywhere_errors(
        self, resume_env: ResumeEnv
    ) -> None:
        """Should error loudly and never guess when the branch is gone."""
        ticket_path = write_ticket(
            resume_env.store,
            "test-repo-9",
            repo="test-repo",
            branch="ghost-branch",
            state="on_hold",
            tool="claude",
        )

        with patch("vibe.cli.connect_to_remote") as mock_connect:
            result = runner.invoke(app, ["resume", "test-repo-9"])

        assert result.exit_code == 1
        assert "merged and deleted" in result.stdout
        mock_connect.assert_not_called()
        # Ticket untouched on the error path
        assert read_ticket(ticket_path).state == "on_hold"

    def test_invalid_worktree_directory_errors(
        self, resume_env: ResumeEnv
    ) -> None:
        """Should error loudly when the directory isn't a git worktree."""
        create_branch_with_commit(resume_env.repo, "feature-bad", "some work")
        bad_dir = resume_env.worktree_base / "test-repo" / "feature-bad"
        bad_dir.mkdir(parents=True)
        (bad_dir / "junk.txt").write_text("junk\n")
        write_ticket(
            resume_env.store,
            "test-repo-10",
            repo="test-repo",
            branch="feature-bad",
            state="on_hold",
            tool="claude",
        )

        with patch("vibe.cli.connect_to_remote") as mock_connect:
            result = runner.invoke(app, ["resume", "test-repo-10"])

        assert result.exit_code == 1
        assert "not a git worktree" in result.stdout
        mock_connect.assert_not_called()


class TestResumeUnwindGuard:
    """Tests for the unwind-only-if-marker rule (never unwind otherwise)."""

    def test_never_unwinds_another_tickets_marker(
        self, resume_env: ResumeEnv
    ) -> None:
        """Should leave another ticket's park marker untouched."""
        worktree_path = add_worktree(
            resume_env.repo, resume_env.worktree_base, "feature-other"
        )
        commit_in_worktree(worktree_path, "wip: park other-99")
        write_ticket(
            resume_env.store,
            "test-repo-11",
            repo="test-repo",
            branch="feature-other",
            state="on_hold",
            tool="claude",
        )

        with patch("vibe.cli.connect_to_remote", return_value=0):
            result = runner.invoke(app, ["resume", "test-repo-11"])

        assert result.exit_code == 0
        assert get_tip_commit_subject(worktree_path) == "wip: park other-99"
        assert git_porcelain(worktree_path) == set()

    def test_never_unwinds_near_miss_marker(
        self, resume_env: ResumeEnv
    ) -> None:
        """Should require an exact marker match, not a prefix match."""
        worktree_path = add_worktree(
            resume_env.repo, resume_env.worktree_base, "feature-near"
        )
        commit_in_worktree(worktree_path, "wip: park test-repo-12 and more")
        write_ticket(
            resume_env.store,
            "test-repo-12",
            repo="test-repo",
            branch="feature-near",
            state="on_hold",
            tool="claude",
        )

        with patch("vibe.cli.connect_to_remote", return_value=0):
            result = runner.invoke(app, ["resume", "test-repo-12"])

        assert result.exit_code == 0
        assert (
            get_tip_commit_subject(worktree_path)
            == "wip: park test-repo-12 and more"
        )

    def test_unwind_is_a_mixed_reset(self, resume_env: ResumeEnv) -> None:
        """Should restore tracked changes unstaged and untracked files."""
        worktree_path = add_worktree(
            resume_env.repo, resume_env.worktree_base, "feature-mixed"
        )
        # Park commit carries a tracked-file modification and a new file
        (worktree_path / "README.md").write_text("# Test Repo\nmodified\n")
        commit_in_worktree(worktree_path, "wip: park test-repo-13", "new.txt")
        write_ticket(
            resume_env.store,
            "test-repo-13",
            repo="test-repo",
            branch="feature-mixed",
            state="on_hold",
            tool="claude",
        )

        with patch("vibe.cli.connect_to_remote", return_value=0):
            result = runner.invoke(app, ["resume", "test-repo-13"])

        assert result.exit_code == 0
        assert get_tip_commit_subject(worktree_path) == "Initial commit"
        # Mixed reset: tracked change back unstaged, new file untracked
        assert git_porcelain(worktree_path) == {" M README.md", "?? new.txt"}
        assert (
            worktree_path / "README.md"
        ).read_text() == "# Test Repo\nmodified\n"
        assert (worktree_path / "new.txt").is_file()


def setup_branch_ticket(
    env: ResumeEnv,
    ticket_id: str,
    branch: str,
    *,
    marker: bool = False,
    **fields: str,
) -> tuple[Path, Path]:
    """Create a resumable on_hold ticket backed by a real (uncheckedout) branch.

    Args:
        env: The patched resume environment
        ticket_id: Ticket id / filename stem
        branch: Branch to create with one commit
        marker: When True the branch tip is this ticket's park marker
        **fields: Extra frontmatter fields (e.g. tool, session_id)

    Returns:
        Tuple of (ticket_path, expected worktree path)
    """
    message = f"wip: park {ticket_id}" if marker else "work commit"
    create_branch_with_commit(env.repo, branch, message)
    path = write_ticket(
        env.store,
        ticket_id,
        repo="test-repo",
        branch=branch,
        state="on_hold",
        **fields,
    )
    worktree_path = (
        env.worktree_base / "test-repo" / branch_to_worktree_dirname(branch)
    )
    return path, worktree_path


class TestResumeLaunchPlumbing:
    """Tests for the resume launch command construction (worktree path)."""

    def test_claude_with_session_id_resumes_session(
        self, resume_env: ResumeEnv
    ) -> None:
        """Should append --resume <session-id> for Claude with a safe id."""
        setup_branch_ticket(
            resume_env, "test-repo-20", "feature-20",
            tool="claude", session_id="abc-123",
        )

        with patch(
            "vibe.cli.connect_to_remote", return_value=0
        ) as mock_connect:
            result = runner.invoke(app, ["resume", "test-repo-20"])

        assert result.exit_code == 0
        assert (
            mock_connect.call_args.kwargs["coding_tool"]
            == "cly --resume abc-123"
        )

    def test_claude_with_unsafe_session_id_uses_bootstrap(
        self, resume_env: ResumeEnv
    ) -> None:
        """Should fall back to the bootstrap prompt for unsafe session ids."""
        setup_branch_ticket(
            resume_env, "test-repo-21", "feature-21",
            tool="claude", session_id="abc;rm -rf /",
        )

        with patch(
            "vibe.cli.connect_to_remote", return_value=0
        ) as mock_connect:
            result = runner.invoke(app, ["resume", "test-repo-21"])

        assert result.exit_code == 0
        coding_tool = mock_connect.call_args.kwargs["coding_tool"]
        assert "--resume" not in coding_tool
        expected_prompt = RESUME_BOOTSTRAP_PROMPT.format(
            ticket_id="test-repo-21"
        )
        assert coding_tool == f"cly {shlex.quote(expected_prompt)}"

    def test_codex_launches_bare_even_with_session_id(
        self, resume_env: ResumeEnv
    ) -> None:
        """Should launch codex fresh with no arguments."""
        setup_branch_ticket(
            resume_env, "test-repo-22", "feature-22",
            tool="codex", session_id="abc-123",
        )

        with patch(
            "vibe.cli.connect_to_remote", return_value=0
        ) as mock_connect:
            result = runner.invoke(app, ["resume", "test-repo-22"])

        assert result.exit_code == 0
        assert mock_connect.call_args.kwargs["coding_tool"] == "cdx"

    def test_oc_flag_overrides_ticket_tool(
        self, resume_env: ResumeEnv
    ) -> None:
        """Should let --oc override the ticket's recorded claude tool."""
        setup_branch_ticket(
            resume_env, "test-repo-23", "feature-23",
            tool="claude", session_id="abc-123",
        )

        with patch(
            "vibe.cli.connect_to_remote", return_value=0
        ) as mock_connect:
            result = runner.invoke(app, ["resume", "test-repo-23", "--oc"])

        assert result.exit_code == 0
        assert mock_connect.call_args.kwargs["coding_tool"] == "opencode"

    def test_claude_flag_overrides_ticket_tool(
        self, resume_env: ResumeEnv
    ) -> None:
        """Should let --claude override the ticket's recorded codex tool."""
        setup_branch_ticket(
            resume_env, "test-repo-24", "feature-24",
            tool="codex", session_id="abc-123",
        )

        with patch(
            "vibe.cli.connect_to_remote", return_value=0
        ) as mock_connect:
            result = runner.invoke(app, ["resume", "test-repo-24", "--claude"])

        assert result.exit_code == 0
        assert (
            mock_connect.call_args.kwargs["coding_tool"]
            == "cly --resume abc-123"
        )

    def test_local_resume_launches_locally(
        self, resume_env: ResumeEnv
    ) -> None:
        """Should launch locally in the worktree with --local."""
        _, worktree_path = setup_branch_ticket(
            resume_env, "test-repo-25", "feature-25", tool="claude",
        )

        with patch(
            "vibe.cli.connect_locally", return_value=0
        ) as mock_connect:
            result = runner.invoke(
                app, ["resume", "test-repo-25", "--local"]
            )

        assert result.exit_code == 0
        mock_connect.assert_called_once()
        assert mock_connect.call_args.args[0] == worktree_path

    def test_stale_session_relaunches_fresh_after_confirm(
        self, resume_env: ResumeEnv
    ) -> None:
        """Should offer one fresh relaunch when a session resume fails."""
        setup_branch_ticket(
            resume_env, "test-repo-26", "feature-26",
            tool="claude", session_id="stale-1",
        )

        with patch(
            "vibe.cli.connect_to_remote", side_effect=[3, 0]
        ) as mock_connect:
            result = runner.invoke(
                app, ["resume", "test-repo-26"], input="y\n"
            )

        assert result.exit_code == 0
        assert "stale" in result.stdout
        assert mock_connect.call_count == 2
        first_cmd = mock_connect.call_args_list[0].kwargs["coding_tool"]
        second_cmd = mock_connect.call_args_list[1].kwargs["coding_tool"]
        assert first_cmd == "cly --resume stale-1"
        assert "--resume" not in second_cmd
        expected_prompt = RESUME_BOOTSTRAP_PROMPT.format(
            ticket_id="test-repo-26"
        )
        assert second_cmd == f"cly {shlex.quote(expected_prompt)}"

    def test_stale_session_retry_declined(
        self, resume_env: ResumeEnv
    ) -> None:
        """Should keep the failing exit code when the relaunch is declined."""
        setup_branch_ticket(
            resume_env, "test-repo-27", "feature-27",
            tool="claude", session_id="stale-2",
        )

        with patch(
            "vibe.cli.connect_to_remote", return_value=3
        ) as mock_connect:
            result = runner.invoke(
                app, ["resume", "test-repo-27"], input="n\n"
            )

        assert result.exit_code == 3
        assert mock_connect.call_count == 1

    def test_resume_branch_path_runs_post_session_cleanup(
        self, resume_env: ResumeEnv
    ) -> None:
        """Should run post-session cleanup after a worktree session exits."""
        worktree_path = add_worktree(
            resume_env.repo, resume_env.worktree_base, "feature-psc"
        )
        commit_in_worktree(worktree_path, "normal work commit")
        write_ticket(
            resume_env.store,
            "test-repo-28",
            repo="test-repo",
            branch="feature-psc",
            state="on_hold",
            tool="claude",
        )

        with patch("vibe.cli.connect_to_remote", return_value=0), patch(
            "vibe.cli.post_session_cleanup"
        ) as mock_cleanup:
            result = runner.invoke(app, ["resume", "test-repo-28"])

        assert result.exit_code == 0
        mock_cleanup.assert_called_once()
        assert mock_cleanup.call_args.args[:3] == (
            "test-repo",
            "feature-psc",
            resume_env.repo,
        )


class TestBuildResumeCommand:
    """Unit tests for _build_resume_command."""

    def _ticket(self, **fields: str) -> Ticket:
        """Build an in-memory ticket for command construction tests."""
        return Ticket(path=Path("/store/vibe-1.md"), fields=fields, body="")

    def test_powershell_never_appends_args(self) -> None:
        """Should send the bare direct command on PowerShell remotes."""
        ticket = self._ticket(id="vibe-1", session_id="abc-123")

        command, used_resume = _build_resume_command(
            "claude --dangerously-skip-permissions",
            "claude",
            ticket,
            powershell=True,
        )

        assert command == "claude --dangerously-skip-permissions"
        assert used_resume is False

    def test_unknown_tool_launches_bare(self) -> None:
        """Should launch an unrecognized tool fresh with no arguments."""
        ticket = self._ticket(id="vibe-1", session_id="abc-123")

        command, used_resume = _build_resume_command(
            "custom-tool", None, ticket, powershell=False
        )

        assert command == "custom-tool"
        assert used_resume is False

    def test_unsafe_ticket_id_launches_without_prompt(self) -> None:
        """Should omit the bootstrap prompt for unsafe ticket ids."""
        ticket = Ticket(
            path=Path("/store/bad id.md"), fields={"id": "bad id"}, body=""
        )

        command, used_resume = _build_resume_command(
            "cly", "claude", ticket, powershell=False
        )

        assert command == "cly"
        assert used_resume is False

    def test_use_session_false_forces_bootstrap(self) -> None:
        """Should ignore a valid session id when use_session is False."""
        ticket = self._ticket(id="vibe-1", session_id="abc-123")

        command, used_resume = _build_resume_command(
            "cly", "claude", ticket, powershell=False, use_session=False
        )

        expected_prompt = RESUME_BOOTSTRAP_PROMPT.format(ticket_id="vibe-1")
        assert command == f"cly {shlex.quote(expected_prompt)}"
        assert used_resume is False


class TestResolveResumeTool:
    """Unit tests for _resolve_resume_tool."""

    def test_flags_take_precedence_over_ticket_tool(self) -> None:
        """Should prefer CLI flags over the ticket's recorded tool."""
        assert _resolve_resume_tool(False, True, False, "claude", False) == (
            "codex",
            "cdx",
        )

    def test_ticket_tool_used_without_flags(self) -> None:
        """Should fall back to the ticket's recorded tool."""
        assert _resolve_resume_tool(False, False, False, "opencode", False) == (
            "opencode",
            "opencode",
        )

    def test_powershell_uses_direct_commands(self) -> None:
        """Should resolve direct commands for PowerShell remotes."""
        assert _resolve_resume_tool(False, False, True, None, True) == (
            "claude",
            "claude --dangerously-skip-permissions",
        )

    @patch("vibe.cli.prompt_coding_tool_choice")
    def test_prompts_when_no_flag_and_no_ticket_tool(
        self, mock_prompt: MagicMock
    ) -> None:
        """Should prompt interactively and map the choice back to a tool."""
        mock_prompt.return_value = "cly"

        assert _resolve_resume_tool(False, False, False, None, False) == (
            "claude",
            "cly",
        )
        mock_prompt.assert_called_once()

    @patch("vibe.cli.prompt_coding_tool_choice")
    def test_unmapped_prompt_choice_returns_unknown_tool(
        self, mock_prompt: MagicMock
    ) -> None:
        """Should return None for a tool name it cannot map."""
        mock_prompt.return_value = "something-else"

        assert _resolve_resume_tool(False, False, False, None, False) == (
            None,
            "something-else",
        )


def strand_branch_on_main(
    repo: Path,
    branch: str,
    message: str,
    filename: str = "parked.txt",
) -> str:
    """Leave a branch checked out on the main checkout (interrupted park).

    Mimics a park that created the branch and wrote the park commit on the
    main checkout but never switched back (e.g. a crash). The main checkout
    is left ON the branch with a clean tree.

    Args:
        repo: Path to the git repository
        branch: Branch to create and strand
        message: Park commit message
        filename: File folded into the park commit

    Returns:
        The branch the main checkout was on before stranding
    """
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    original = result.stdout.strip()
    subprocess.run(
        ["git", "checkout", "-b", branch], cwd=repo, capture_output=True, check=True
    )
    (repo / filename).write_text("parked\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", message], cwd=repo, capture_output=True, check=True
    )
    return original


def current_branch(repo: Path) -> str:
    """Return the branch currently checked out in a repo.

    Args:
        repo: Path to the git repository

    Returns:
        The checked-out branch name
    """
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


class TestResumeStrandedBranch:
    """Resume recovery when a ticket's branch is stranded on the main checkout."""

    def _write_stranded_ticket(self, env: ResumeEnv, ticket_id: str) -> Path:
        """Write an on_hold ticket whose branch is stranded on main."""
        return write_ticket(
            env.store,
            ticket_id,
            repo="test-repo",
            branch="screenshot-actions",
            base_branch="main",
            state="on_hold",
            tool="claude",
        )

    @patch("vibe.cli.prompt_stranded_branch_choice")
    def test_switch_moves_main_back_and_creates_worktree(
        self, mock_prompt: MagicMock, resume_env: ResumeEnv
    ) -> None:
        """SWITCH frees the branch, builds the worktree, and unwinds the park."""
        mock_prompt.return_value = StrandedBranchChoice.SWITCH
        strand_branch_on_main(
            resume_env.repo, "screenshot-actions", "wip: park test-repo-1"
        )
        ticket_path = self._write_stranded_ticket(resume_env, "test-repo-1")
        worktree_path = (
            resume_env.worktree_base / "test-repo" / "screenshot-actions"
        )

        with patch("vibe.cli.connect_to_remote", return_value=0) as mock_connect:
            result = runner.invoke(app, ["resume", "test-repo-1"])

        assert result.exit_code == 0
        # Main checkout was switched off the branch back to main
        assert current_branch(resume_env.repo) == "main"
        # A worktree now holds the branch, with the park commit unwound
        assert worktree_path.is_dir()
        assert get_tip_commit_subject(worktree_path) == "Initial commit"
        assert (worktree_path / "parked.txt").is_file()
        assert "?? parked.txt" in git_porcelain(worktree_path)

        kwargs = mock_connect.call_args.kwargs
        assert kwargs["repo_name"] == "test-repo"
        assert kwargs["worktree_name"] == "screenshot-actions"

        # Resume consumes the ticket
        assert not ticket_path.exists()

    @patch("vibe.cli.prompt_stranded_branch_choice")
    def test_in_place_resumes_on_main_checkout(
        self, mock_prompt: MagicMock, resume_env: ResumeEnv
    ) -> None:
        """IN_PLACE unwinds and launches in the main checkout, no worktree."""
        mock_prompt.return_value = StrandedBranchChoice.IN_PLACE
        strand_branch_on_main(
            resume_env.repo, "screenshot-actions", "wip: park test-repo-1"
        )
        ticket_path = self._write_stranded_ticket(resume_env, "test-repo-1")
        worktree_path = (
            resume_env.worktree_base / "test-repo" / "screenshot-actions"
        )

        with patch(
            "vibe.cli.connect_to_remote_path", return_value=0
        ) as mock_connect, patch("vibe.cli.post_session_cleanup") as mock_cleanup:
            result = runner.invoke(app, ["resume", "test-repo-1"])

        assert result.exit_code == 0
        # No worktree was created; the branch stays on the main checkout
        assert not worktree_path.exists()
        assert current_branch(resume_env.repo) == "screenshot-actions"
        # Park commit unwound in place: parked file restored as a change
        assert get_tip_commit_subject(resume_env.repo) == "Initial commit"
        assert "?? parked.txt" in git_porcelain(resume_env.repo)

        kwargs = mock_connect.call_args.kwargs
        assert kwargs["remote_path"] == Path("/remote-repos/test-repo")

        # Resume consumes the ticket; in-place runs no worktree cleanup
        assert not ticket_path.exists()
        mock_cleanup.assert_not_called()

    @patch("vibe.cli.prompt_stranded_branch_choice")
    def test_abort_changes_nothing(
        self, mock_prompt: MagicMock, resume_env: ResumeEnv
    ) -> None:
        """ABORT exits non-zero and leaves the repo and ticket untouched."""
        mock_prompt.return_value = StrandedBranchChoice.ABORT
        strand_branch_on_main(
            resume_env.repo, "screenshot-actions", "wip: park test-repo-1"
        )
        ticket_path = self._write_stranded_ticket(resume_env, "test-repo-1")

        with patch("vibe.cli.connect_to_remote", return_value=0) as mock_connect:
            result = runner.invoke(app, ["resume", "test-repo-1"])

        assert result.exit_code == 1
        mock_connect.assert_not_called()
        # Nothing changed: branch still on main, park commit still the tip
        assert current_branch(resume_env.repo) == "screenshot-actions"
        assert get_tip_commit_subject(resume_env.repo) == "wip: park test-repo-1"
        ticket = read_ticket(ticket_path)
        assert ticket.state == "on_hold"

    @patch("vibe.cli.prompt_stranded_branch_choice")
    def test_dirty_main_checkout_offers_no_switch(
        self, mock_prompt: MagicMock, resume_env: ResumeEnv
    ) -> None:
        """A dirty main checkout is reported as dirty and never switched."""
        mock_prompt.return_value = StrandedBranchChoice.IN_PLACE
        strand_branch_on_main(
            resume_env.repo, "screenshot-actions", "wip: park test-repo-1"
        )
        # Dirty the main checkout after the park
        (resume_env.repo / "uncommitted.txt").write_text("wip\n")
        self._write_stranded_ticket(resume_env, "test-repo-1")

        with patch("vibe.cli.connect_to_remote_path", return_value=0):
            result = runner.invoke(app, ["resume", "test-repo-1"])

        assert result.exit_code == 0
        # The prompt was told the checkout is dirty
        assert mock_prompt.call_args.args[2] is True
        # Still on the branch (never switched)
        assert current_branch(resume_env.repo) == "screenshot-actions"

    def test_stale_registration_is_pruned_and_recreated(
        self, resume_env: ResumeEnv
    ) -> None:
        """A deleted-but-registered worktree is pruned, then recreated."""
        worktree_path = add_worktree(
            resume_env.repo, resume_env.worktree_base, "feature-stale"
        )
        commit_in_worktree(worktree_path, "wip: park test-repo-1")
        # Delete the directory but leave git's registration behind
        import shutil

        shutil.rmtree(worktree_path)
        assert find_branch_checkout("feature-stale", cwd=resume_env.repo) is not None

        write_ticket(
            resume_env.store,
            "test-repo-1",
            repo="test-repo",
            branch="feature-stale",
            state="on_hold",
            tool="claude",
        )

        with patch("vibe.cli.connect_to_remote", return_value=0):
            result = runner.invoke(app, ["resume", "test-repo-1"])

        assert result.exit_code == 0
        assert worktree_path.is_dir()
        # Park commit unwound in the recreated worktree
        assert get_tip_commit_subject(worktree_path) == "Initial commit"

    def test_resolve_switchback_prefers_base_branch(
        self, resume_env: ResumeEnv
    ) -> None:
        """base_branch is used when it exists locally."""
        ticket_path = write_ticket(
            resume_env.store,
            "test-repo-1",
            repo="test-repo",
            branch="screenshot-actions",
            base_branch="main",
        )
        ticket = read_ticket(ticket_path)

        assert _resolve_switchback_branch(ticket, resume_env.repo) == "main"

    def test_resolve_switchback_falls_back_when_base_missing(
        self, resume_env: ResumeEnv
    ) -> None:
        """A null/absent base_branch falls back to the default branch."""
        ticket_path = write_ticket(
            resume_env.store,
            "test-repo-1",
            repo="test-repo",
            branch="screenshot-actions",
            base_branch="null",
        )
        ticket = read_ticket(ticket_path)

        # No origin in this repo, so it falls through to a literal 'main'
        assert _resolve_switchback_branch(ticket, resume_env.repo) == "main"


class TestResumeSoftDelete:
    """Resume soft-deletes (archives) the ticket and can recover it."""

    def test_resume_archives_ticket_instead_of_deleting(
        self, resume_env: ResumeEnv
    ) -> None:
        """Resume should move the ticket into the .resumed/ archive."""
        create_branch_with_commit(
            resume_env.repo, "feature-arch", "wip: park test-repo-30", "parked.txt"
        )
        ticket_path = write_ticket(
            resume_env.store, "test-repo-30", repo="test-repo",
            branch="feature-arch", state="on_hold", tool="claude",
        )

        with patch("vibe.cli.connect_to_remote", return_value=0):
            result = runner.invoke(app, ["resume", "test-repo-30"])

        assert result.exit_code == 0
        # The live ticket is gone from the board…
        assert not ticket_path.exists()
        # …but preserved in the hidden archive.
        archived = resume_env.store / ".resumed" / "test-repo-30.md"
        assert archived.is_file()

    def test_re_resume_recovers_from_archive(
        self, resume_env: ResumeEnv
    ) -> None:
        """A second resume of an already-resumed ticket recovers it by id."""
        create_branch_with_commit(
            resume_env.repo, "feature-recover", "wip: park test-repo-31", "parked.txt"
        )
        write_ticket(
            resume_env.store, "test-repo-31", repo="test-repo",
            branch="feature-recover", state="on_hold", tool="claude",
        )
        worktree_path = resume_env.worktree_base / "test-repo" / "feature-recover"

        with patch("vibe.cli.connect_to_remote", return_value=0):
            first = runner.invoke(app, ["resume", "test-repo-31"])
        assert first.exit_code == 0
        archived = resume_env.store / ".resumed" / "test-repo-31.md"
        assert archived.is_file()
        assert worktree_path.is_dir()

        # Simulate "closed immediately, resume again": the ticket is no longer
        # a live ticket, but resume recovers it from the archive and reconnects.
        with patch("vibe.cli.connect_to_remote", return_value=0) as mock_connect:
            second = runner.invoke(app, ["resume", "test-repo-31"])

        assert second.exit_code == 0
        assert "archive" in second.stdout.lower()
        mock_connect.assert_called_once()
        # Still archived afterwards (recoverable yet again), never duplicated.
        assert archived.is_file()

    def test_unknown_ticket_with_no_archive_still_errors(
        self, resume_env: ResumeEnv
    ) -> None:
        """A truly unknown id (no live ticket, no archive) still errors."""
        result = runner.invoke(app, ["resume", "test-repo-999"])
        assert result.exit_code == 1
        assert "No ticket found" in result.stdout
