"""Tests for 'vibe resume <ticket>' against the NSProject board backend."""

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
    get_tip_commit_subject,
)
from vibe.nsproject import ParkedWork, parse_ticket

runner = CliRunner()

# The work entry's canonical repo URL — its basename ("test-repo") resolves to
# the temp product repo under the patched repo base.
REPO_URL = "https://github.com/nonstrict-hq/test-repo.git"


def make_board(tmp_path: Path) -> Path:
    """Create a minimal valid NSProject board under tmp_path.

    Args:
        tmp_path: Temp directory.

    Returns:
        The board root.
    """
    board = tmp_path / "board"
    (board / "data" / "maybe").mkdir(parents=True)
    (board / "data" / "this-week").mkdir(parents=True)
    (board / "CLAUDE.md").write_text("# board\n")
    return board


def write_board_ticket(
    board: Path,
    ticket_id: str,
    branch: str,
    *,
    repo_url: str = REPO_URL,
    by: str = "mathijs",
    parked_at: str = "2026-06-10T00:00:00Z",
    title: str = "Parked work",
    **work_extra: str,
) -> Path:
    """Write a board ticket carrying one parked work[] entry.

    Args:
        board: Board root.
        ticket_id: Ticket id (also the frontmatter id).
        branch: The work branch.
        repo_url: Canonical repo URL for the work entry.
        by: Person handle.
        parked_at: Park marker timestamp (empty string omits it).
        title: Ticket title.
        **work_extra: Extra work[] child keys (e.g. tool, session, base_branch).

    Returns:
        Path to the written ticket file.
    """
    folder = board / "data" / "this-week"
    lines = [
        "---",
        f"id: {ticket_id}",
        f"title: {title}",
        "components: [test]",
        "work:",
        f"  - repo: {repo_url}",
        f"    branch: {branch}",
        f"    by: {by}",
    ]
    if parked_at:
        lines.append(f"    parked_at: {parked_at}")
    for key, value in work_extra.items():
        lines.append(f"    {key}: {value}")
    lines += ["---", "", "## Where I left off", "Continue here.", ""]
    path = folder / f"010-{ticket_id}-x.md"
    path.write_text("\n".join(lines))
    return path


def create_branch_with_commit(
    repo: Path, branch: str, message: str, filename: str = "work.txt"
) -> None:
    """Create a branch carrying one commit, leaving it not checked out."""
    subprocess.run(
        ["git", "checkout", "-b", branch], cwd=repo, capture_output=True, check=True
    )
    (repo / filename).write_text("work\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", message], cwd=repo, capture_output=True, check=True
    )
    subprocess.run(["git", "checkout", "-"], cwd=repo, capture_output=True, check=True)


def add_worktree(repo: Path, worktree_base: Path, branch: str) -> Path:
    """Create a git worktree for a new branch at its encoded path."""
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
    worktree: Path, message: str, filename: str = "parked.txt"
) -> None:
    """Create a commit in a worktree (staging everything, like park does)."""
    (worktree / filename).write_text("parked\n")
    subprocess.run(["git", "add", "-A"], cwd=worktree, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", message], cwd=worktree, capture_output=True, check=True
    )


def git_porcelain(worktree: Path) -> set[str]:
    """Get the non-empty 'git status --porcelain' lines of a worktree."""
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
    board: Path


def _setup_resume_env(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> ResumeEnv:
    """Patch cli/nsproject so resume runs against a temp board + repo base."""
    worktree_base = tmp_path / "worktrees"
    worktree_base.mkdir(exist_ok=True)
    board = make_board(tmp_path)
    # The board is found via the env var; repo URLs resolve under tmp_path.
    monkeypatch.setenv("NSPROJECT_BOARD", str(board))
    monkeypatch.setattr("vibe.nsproject.LOCAL_REPO_BASE", tmp_path)
    monkeypatch.setattr("vibe.cli.LOCAL_WORKTREE_BASE", worktree_base)
    monkeypatch.setattr("vibe.cli.REMOTE_REPO_BASE", Path("/remote-repos"))
    return ResumeEnv(
        repo=repo, repo_base=tmp_path, worktree_base=worktree_base, board=board
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


def parked_at_of(ticket_path: Path) -> str | None:
    """Read the parked_at value of a board ticket's first work entry."""
    parsed_ticket = parse_ticket(ticket_path)
    if parsed_ticket is None or not parsed_ticket.work:
        return None
    return parsed_ticket.work[0].get("parked_at")


class TestResumeCliShape:
    """Tests for the 'vibe resume <ticket>' command-line shape."""

    def test_help_shows_resume_example(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "resume" in result.stdout

    def test_resume_without_ticket_id_errors(self, resume_env: ResumeEnv) -> None:
        write_board_ticket(resume_env.board, "TST_aaaaa", "feature-x")
        result = runner.invoke(app, ["resume"])
        assert result.exit_code == 1
        assert "requires a ticket id" in result.stdout
        assert "vibe resume <ticket-id>" in result.stdout
        assert "TST_aaaaa" in result.stdout

    def test_resume_without_ticket_id_empty_board(self, resume_env: ResumeEnv) -> None:
        result = runner.invoke(app, ["resume"])
        assert result.exit_code == 1
        assert "No resumable tickets" in result.stdout

    def test_second_positional_without_resume_errors(self) -> None:
        result = runner.invoke(app, ["feature-branch", "extra-arg"])
        assert result.exit_code == 1
        assert "Unexpected argument" in result.stdout
        assert "vibe resume <ticket-id>" in result.stdout

    def test_unknown_ticket_errors_listing_available(
        self, resume_env: ResumeEnv
    ) -> None:
        write_board_ticket(resume_env.board, "TST_known", "feature-x")
        result = runner.invoke(app, ["resume", "TST_nope"])
        assert result.exit_code == 1
        assert "No resumable work" in result.stdout
        assert "TST_known" in result.stdout

    def test_listing_tolerates_markup_like_titles(self, resume_env: ResumeEnv) -> None:
        write_board_ticket(
            resume_env.board, "TST_v12", "feature-x", title="[v1.2] release"
        )
        result = runner.invoke(app, ["resume", "TST_nope"])
        assert result.exit_code == 1
        assert "[v1.2] release" in result.stdout

    def test_missing_repo_errors(self, resume_env: ResumeEnv) -> None:
        # A repo URL whose basename does not resolve under the repo base.
        write_board_ticket(
            resume_env.board,
            "TST_ghost",
            "feature-x",
            repo_url="https://github.com/x/ghost-repo.git",
        )
        result = runner.invoke(app, ["resume", "TST_ghost"])
        assert result.exit_code == 1
        assert "No resumable work" in result.stdout

    def test_board_not_found_errors(
        self, temp_git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("NSPROJECT_BOARD", raising=False)
        empty = tmp_path / "empty"
        empty.mkdir()
        monkeypatch.setattr("vibe.nsproject.LOCAL_REPO_BASE", empty)
        result = runner.invoke(app, ["resume", "TST_aaaaa"])
        assert result.exit_code == 1
        assert "Could not find the NSProject board" in result.stdout

    def test_complete_ticket_ids(self, resume_env: ResumeEnv) -> None:
        write_board_ticket(resume_env.board, "TST_alpha", "feature-a")
        write_board_ticket(resume_env.board, "TST_beta", "feature-b")
        assert sorted(complete_ticket_ids("")) == ["TST_alpha", "TST_beta"]
        assert complete_ticket_ids("TST_a") == ["TST_alpha"]
        assert complete_ticket_ids("zzz") == []


class TestResumeMatrix:
    """Tests for the resume worktree matrix."""

    def test_parked_without_worktree_recreates_and_unwinds(
        self, resume_env: ResumeEnv
    ) -> None:
        create_branch_with_commit(
            resume_env.repo, "feature-x", "wip: park TST_2", "parked.txt"
        )
        ticket_path = write_board_ticket(
            resume_env.board, "TST_2", "feature-x", tool="claude"
        )
        worktree_path = resume_env.worktree_base / "test-repo" / "feature-x"

        with patch("vibe.cli.connect_to_remote", return_value=0) as mock_connect:
            result = runner.invoke(app, ["resume", "TST_2"])

        assert result.exit_code == 0
        assert worktree_path.is_dir()
        assert get_tip_commit_subject(worktree_path) == "Initial commit"
        assert (worktree_path / "parked.txt").is_file()
        assert "?? parked.txt" in git_porcelain(worktree_path)
        kwargs = mock_connect.call_args.kwargs
        assert kwargs["repo_name"] == "test-repo"
        assert kwargs["worktree_name"] == "feature-x"
        # Resume clears the board's parked marker.
        assert parked_at_of(ticket_path) is None

    def test_parked_with_worktree_reuses_and_unwinds(
        self, resume_env: ResumeEnv
    ) -> None:
        worktree_path = add_worktree(
            resume_env.repo, resume_env.worktree_base, "feature-y"
        )
        commit_in_worktree(worktree_path, "wip: park TST_3")
        write_board_ticket(resume_env.board, "TST_3", "feature-y", tool="claude")

        with patch("vibe.cli.connect_to_remote", return_value=0) as mock_connect:
            result = runner.invoke(app, ["resume", "TST_3"])

        assert result.exit_code == 0
        assert get_tip_commit_subject(worktree_path) == "Initial commit"
        assert "?? parked.txt" in git_porcelain(worktree_path)
        mock_connect.assert_called_once()

    def test_resume_vm_flag_threads_target(self, resume_env: ResumeEnv) -> None:
        """`resume --vm` should resolve via tart and thread host + opts."""
        from vibe.connection import EPHEMERAL_HOSTKEY_OPTS
        from vibe.target import DEFAULT_USER

        worktree_path = add_worktree(
            resume_env.repo, resume_env.worktree_base, "feature-vm"
        )
        commit_in_worktree(worktree_path, "wip: park TST_VM")
        write_board_ticket(resume_env.board, "TST_VM", "feature-vm", tool="claude")

        with patch(
            "vibe.target.tart_ip", return_value="10.0.0.7"
        ) as mock_ip, patch(
            "vibe.cli.connect_to_remote", return_value=0
        ) as mock_connect:
            result = runner.invoke(app, ["resume", "TST_VM", "--vm", "beta"])

        assert result.exit_code == 0
        mock_ip.assert_called_once_with("beta")
        kwargs = mock_connect.call_args.kwargs
        assert kwargs["user_host"] == f"{DEFAULT_USER}@10.0.0.7"
        assert kwargs["ssh_opts"] == EPHEMERAL_HOSTKEY_OPTS

    def test_existing_worktree_non_marker_tip_not_unwound(
        self, resume_env: ResumeEnv
    ) -> None:
        worktree_path = add_worktree(
            resume_env.repo, resume_env.worktree_base, "feature-w"
        )
        commit_in_worktree(worktree_path, "normal work commit")
        write_board_ticket(resume_env.board, "TST_4", "feature-w", tool="claude")

        with patch("vibe.cli.connect_to_remote", return_value=0) as mock_connect:
            result = runner.invoke(app, ["resume", "TST_4"])

        assert result.exit_code == 0
        assert get_tip_commit_subject(worktree_path) == "normal work commit"
        assert git_porcelain(worktree_path) == set()
        mock_connect.assert_called_once()

    def test_slashed_branch_uses_encoded_worktree(
        self, resume_env: ResumeEnv
    ) -> None:
        branch = "feature/retry-upload"
        create_branch_with_commit(
            resume_env.repo, branch, "wip: park TST_6", "parked.txt"
        )
        write_board_ticket(resume_env.board, "TST_6", branch, tool="claude")
        worktree_path = (
            resume_env.worktree_base / "test-repo" / "feature%2Fretry-upload"
        )

        with patch("vibe.cli.connect_to_remote", return_value=0) as mock_connect:
            result = runner.invoke(app, ["resume", "TST_6"])

        assert result.exit_code == 0
        assert worktree_path.is_dir()
        assert get_tip_commit_subject(worktree_path) == "Initial commit"
        assert (
            mock_connect.call_args.kwargs["worktree_name"] == "feature%2Fretry-upload"
        )

    def test_branch_only_on_origin_creates_tracking_worktree(
        self, resume_env_with_remote: ResumeEnv
    ) -> None:
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
        write_board_ticket(env.board, "TST_8", "feature-r", tool="claude")
        worktree_path = env.worktree_base / "test-repo" / "feature-r"

        with patch("vibe.cli.connect_to_remote", return_value=0) as mock_connect:
            result = runner.invoke(app, ["resume", "TST_8"])

        assert result.exit_code == 0
        assert worktree_path.is_dir()
        assert get_tip_commit_subject(worktree_path) == "remote-only work"
        mock_connect.assert_called_once()

    def test_branch_missing_everywhere_starts_fresh_in_main_checkout(
        self, resume_env: ResumeEnv
    ) -> None:
        """Cross-dev: branch not local or on origin -> fresh session in main checkout."""
        write_board_ticket(
            resume_env.board, "TST_9", "ghost-branch", tool="claude",
            session="abc-123",
        )

        with patch(
            "vibe.cli.connect_to_remote"
        ) as mock_remote, patch(
            "vibe.cli.connect_to_remote_path", return_value=0
        ) as mock_path:
            result = runner.invoke(app, ["resume", "TST_9"])

        assert result.exit_code == 0
        mock_remote.assert_not_called()  # no worktree
        # Launched fresh in the main checkout, seeded (no --resume despite a session).
        kwargs = mock_path.call_args.kwargs
        assert kwargs["remote_path"] == Path("/remote-repos/test-repo")
        assert "--resume" not in kwargs["coding_tool"]
        expected = RESUME_BOOTSTRAP_PROMPT.format(ticket_id="TST_9")
        assert kwargs["coding_tool"] == f"cly {shlex.quote(expected)}"

    def test_invalid_worktree_directory_errors(self, resume_env: ResumeEnv) -> None:
        create_branch_with_commit(resume_env.repo, "feature-bad", "some work")
        bad_dir = resume_env.worktree_base / "test-repo" / "feature-bad"
        bad_dir.mkdir(parents=True)
        (bad_dir / "junk.txt").write_text("junk\n")
        write_board_ticket(resume_env.board, "TST_10", "feature-bad", tool="claude")

        with patch("vibe.cli.connect_to_remote") as mock_connect:
            result = runner.invoke(app, ["resume", "TST_10"])

        assert result.exit_code == 1
        assert "not a git worktree" in result.stdout
        mock_connect.assert_not_called()


class TestResumeUnwindGuard:
    """Tests for the unwind-only-if-marker rule (never unwind otherwise)."""

    def test_never_unwinds_another_tickets_marker(
        self, resume_env: ResumeEnv
    ) -> None:
        worktree_path = add_worktree(
            resume_env.repo, resume_env.worktree_base, "feature-other"
        )
        commit_in_worktree(worktree_path, "wip: park OTHER_99")
        write_board_ticket(resume_env.board, "TST_11", "feature-other", tool="claude")

        # Patch out post-session cleanup so the worktree survives for the tip
        # assertion (the tip stays a park marker, so cleanup would remove it).
        with patch("vibe.cli.connect_to_remote", return_value=0), patch(
            "vibe.cli.post_session_cleanup"
        ):
            result = runner.invoke(app, ["resume", "TST_11"])

        assert result.exit_code == 0
        assert get_tip_commit_subject(worktree_path) == "wip: park OTHER_99"
        assert git_porcelain(worktree_path) == set()

    def test_never_unwinds_near_miss_marker(self, resume_env: ResumeEnv) -> None:
        worktree_path = add_worktree(
            resume_env.repo, resume_env.worktree_base, "feature-near"
        )
        commit_in_worktree(worktree_path, "wip: park TST_12 and more")
        write_board_ticket(resume_env.board, "TST_12", "feature-near", tool="claude")

        with patch("vibe.cli.connect_to_remote", return_value=0), patch(
            "vibe.cli.post_session_cleanup"
        ):
            result = runner.invoke(app, ["resume", "TST_12"])

        assert result.exit_code == 0
        assert (
            get_tip_commit_subject(worktree_path) == "wip: park TST_12 and more"
        )

    def test_unwind_is_a_mixed_reset(self, resume_env: ResumeEnv) -> None:
        worktree_path = add_worktree(
            resume_env.repo, resume_env.worktree_base, "feature-mixed"
        )
        (worktree_path / "README.md").write_text("# Test Repo\nmodified\n")
        commit_in_worktree(worktree_path, "wip: park TST_13", "new.txt")
        write_board_ticket(resume_env.board, "TST_13", "feature-mixed", tool="claude")

        with patch("vibe.cli.connect_to_remote", return_value=0):
            result = runner.invoke(app, ["resume", "TST_13"])

        assert result.exit_code == 0
        assert get_tip_commit_subject(worktree_path) == "Initial commit"
        assert git_porcelain(worktree_path) == {" M README.md", "?? new.txt"}
        assert (worktree_path / "README.md").read_text() == "# Test Repo\nmodified\n"
        assert (worktree_path / "new.txt").is_file()


def setup_branch_ticket(
    env: ResumeEnv, ticket_id: str, branch: str, **work_extra: str
) -> tuple[Path, Path]:
    """Create a resumable ticket backed by a real (uncheckedout) branch."""
    create_branch_with_commit(env.repo, branch, "work commit")
    path = write_board_ticket(env.board, ticket_id, branch, **work_extra)
    worktree_path = (
        env.worktree_base / "test-repo" / branch_to_worktree_dirname(branch)
    )
    return path, worktree_path


class TestResumeLaunchPlumbing:
    """Tests for the resume launch command construction (worktree path)."""

    def test_claude_with_session_id_resumes_session(
        self, resume_env: ResumeEnv
    ) -> None:
        setup_branch_ticket(
            resume_env, "TST_20", "feature-20", tool="claude", session="abc-123"
        )
        with patch("vibe.cli.connect_to_remote", return_value=0) as mock_connect:
            result = runner.invoke(app, ["resume", "TST_20"])
        assert result.exit_code == 0
        assert mock_connect.call_args.kwargs["coding_tool"] == "cly --resume abc-123"

    def test_claude_with_unsafe_session_id_uses_bootstrap(
        self, resume_env: ResumeEnv
    ) -> None:
        setup_branch_ticket(
            resume_env, "TST_21", "feature-21", tool="claude",
            session='"abc;rm"',
        )
        with patch("vibe.cli.connect_to_remote", return_value=0) as mock_connect:
            result = runner.invoke(app, ["resume", "TST_21"])
        assert result.exit_code == 0
        coding_tool = mock_connect.call_args.kwargs["coding_tool"]
        assert "--resume" not in coding_tool
        expected = RESUME_BOOTSTRAP_PROMPT.format(ticket_id="TST_21")
        assert coding_tool == f"cly {shlex.quote(expected)}"

    def test_codex_launches_bare_even_with_session_id(
        self, resume_env: ResumeEnv
    ) -> None:
        setup_branch_ticket(
            resume_env, "TST_22", "feature-22", tool="codex", session="abc-123"
        )
        with patch("vibe.cli.connect_to_remote", return_value=0) as mock_connect:
            result = runner.invoke(app, ["resume", "TST_22"])
        assert result.exit_code == 0
        assert mock_connect.call_args.kwargs["coding_tool"] == "cdx"

    def test_oc_flag_overrides_ticket_tool(self, resume_env: ResumeEnv) -> None:
        setup_branch_ticket(
            resume_env, "TST_23", "feature-23", tool="claude", session="abc-123"
        )
        with patch("vibe.cli.connect_to_remote", return_value=0) as mock_connect:
            result = runner.invoke(app, ["resume", "TST_23", "--oc"])
        assert result.exit_code == 0
        assert mock_connect.call_args.kwargs["coding_tool"] == "opencode"

    def test_claude_flag_overrides_ticket_tool(self, resume_env: ResumeEnv) -> None:
        setup_branch_ticket(
            resume_env, "TST_24", "feature-24", tool="codex", session="abc-123"
        )
        with patch("vibe.cli.connect_to_remote", return_value=0) as mock_connect:
            result = runner.invoke(app, ["resume", "TST_24", "--claude"])
        assert result.exit_code == 0
        assert mock_connect.call_args.kwargs["coding_tool"] == "cly --resume abc-123"

    def test_local_resume_launches_locally(self, resume_env: ResumeEnv) -> None:
        _, worktree_path = setup_branch_ticket(
            resume_env, "TST_25", "feature-25", tool="claude"
        )
        with patch("vibe.cli.connect_locally", return_value=0) as mock_connect:
            result = runner.invoke(app, ["resume", "TST_25", "--local"])
        assert result.exit_code == 0
        mock_connect.assert_called_once()
        assert mock_connect.call_args.args[0] == worktree_path

    def test_stale_session_relaunches_fresh_after_confirm(
        self, resume_env: ResumeEnv
    ) -> None:
        setup_branch_ticket(
            resume_env, "TST_26", "feature-26", tool="claude", session="stale-1"
        )
        with patch(
            "vibe.cli.connect_to_remote", side_effect=[3, 0]
        ) as mock_connect:
            result = runner.invoke(app, ["resume", "TST_26"], input="y\n")
        assert result.exit_code == 0
        assert "stale" in result.stdout
        assert mock_connect.call_count == 2
        first = mock_connect.call_args_list[0].kwargs["coding_tool"]
        second = mock_connect.call_args_list[1].kwargs["coding_tool"]
        assert first == "cly --resume stale-1"
        assert "--resume" not in second

    def test_stale_session_retry_declined(self, resume_env: ResumeEnv) -> None:
        setup_branch_ticket(
            resume_env, "TST_27", "feature-27", tool="claude", session="stale-2"
        )
        with patch("vibe.cli.connect_to_remote", return_value=3) as mock_connect:
            result = runner.invoke(app, ["resume", "TST_27"], input="n\n")
        assert result.exit_code == 3
        assert mock_connect.call_count == 1

    def test_resume_branch_path_runs_post_session_cleanup(
        self, resume_env: ResumeEnv
    ) -> None:
        worktree_path = add_worktree(
            resume_env.repo, resume_env.worktree_base, "feature-psc"
        )
        commit_in_worktree(worktree_path, "normal work commit")
        write_board_ticket(resume_env.board, "TST_28", "feature-psc", tool="claude")

        with patch("vibe.cli.connect_to_remote", return_value=0), patch(
            "vibe.cli.post_session_cleanup"
        ) as mock_cleanup:
            result = runner.invoke(app, ["resume", "TST_28"])

        assert result.exit_code == 0
        mock_cleanup.assert_called_once()
        assert mock_cleanup.call_args.args[:3] == (
            "test-repo",
            "feature-psc",
            resume_env.repo,
        )


def _pw(**over: object) -> ParkedWork:
    """Build a ParkedWork for command-construction unit tests."""
    defaults: dict[str, object] = dict(
        id="TST_aaaaa", title="t", board=Path("/b"), ticket_path=Path("/b/t.md"),
        repo_path=Path("/r"), repo_name="r", branch="br", base_branch="main",
        tool="claude", session_id=None, by="mathijs", parked_at=None,
    )
    defaults.update(over)
    return ParkedWork(**defaults)  # type: ignore[arg-type]


class TestBuildResumeCommand:
    """Unit tests for _build_resume_command."""

    def test_powershell_never_appends_args(self) -> None:
        command, used = _build_resume_command(
            "claude --dangerously-skip-permissions", "claude",
            _pw(session_id="abc-123"), powershell=True,
        )
        assert command == "claude --dangerously-skip-permissions"
        assert used is False

    def test_unknown_tool_launches_bare(self) -> None:
        command, used = _build_resume_command(
            "custom-tool", None, _pw(session_id="abc-123"), powershell=False
        )
        assert command == "custom-tool"
        assert used is False

    def test_unsafe_ticket_id_launches_without_prompt(self) -> None:
        command, used = _build_resume_command(
            "cly", "claude", _pw(id="bad id"), powershell=False
        )
        assert command == "cly"
        assert used is False

    def test_use_session_false_forces_bootstrap(self) -> None:
        command, used = _build_resume_command(
            "cly", "claude", _pw(session_id="abc-123"), powershell=False,
            use_session=False,
        )
        expected = RESUME_BOOTSTRAP_PROMPT.format(ticket_id="TST_aaaaa")
        assert command == f"cly {shlex.quote(expected)}"
        assert used is False


class TestResolveResumeTool:
    """Unit tests for _resolve_resume_tool."""

    def test_flags_take_precedence_over_ticket_tool(self) -> None:
        assert _resolve_resume_tool(False, True, False, "claude", False) == (
            "codex", "cdx",
        )

    def test_ticket_tool_used_without_flags(self) -> None:
        assert _resolve_resume_tool(False, False, False, "opencode", False) == (
            "opencode", "opencode",
        )

    def test_powershell_uses_direct_commands(self) -> None:
        assert _resolve_resume_tool(False, False, True, None, True) == (
            "claude", "claude --dangerously-skip-permissions",
        )

    @patch("vibe.cli.prompt_coding_tool_choice")
    def test_prompts_when_no_flag_and_no_ticket_tool(
        self, mock_prompt: MagicMock
    ) -> None:
        mock_prompt.return_value = "cly"
        assert _resolve_resume_tool(False, False, False, None, False) == (
            "claude", "cly",
        )
        mock_prompt.assert_called_once()

    @patch("vibe.cli.prompt_coding_tool_choice")
    def test_unmapped_prompt_choice_returns_unknown_tool(
        self, mock_prompt: MagicMock
    ) -> None:
        mock_prompt.return_value = "something-else"
        assert _resolve_resume_tool(False, False, False, None, False) == (
            None, "something-else",
        )


def strand_branch_on_main(
    repo: Path, branch: str, message: str, filename: str = "parked.txt"
) -> str:
    """Leave a branch checked out on the main checkout (interrupted park)."""
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
    """Return the branch currently checked out in a repo."""
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
        return write_board_ticket(
            env.board, ticket_id, "screenshot-actions",
            base_branch="main", tool="claude",
        )

    @patch("vibe.cli.prompt_stranded_branch_choice")
    def test_switch_moves_main_back_and_creates_worktree(
        self, mock_prompt: MagicMock, resume_env: ResumeEnv
    ) -> None:
        mock_prompt.return_value = StrandedBranchChoice.SWITCH
        strand_branch_on_main(
            resume_env.repo, "screenshot-actions", "wip: park TST_1"
        )
        self._write_stranded_ticket(resume_env, "TST_1")
        worktree_path = (
            resume_env.worktree_base / "test-repo" / "screenshot-actions"
        )

        with patch("vibe.cli.connect_to_remote", return_value=0) as mock_connect:
            result = runner.invoke(app, ["resume", "TST_1"])

        assert result.exit_code == 0
        assert current_branch(resume_env.repo) == "main"
        assert worktree_path.is_dir()
        assert get_tip_commit_subject(worktree_path) == "Initial commit"
        assert "?? parked.txt" in git_porcelain(worktree_path)
        kwargs = mock_connect.call_args.kwargs
        assert kwargs["repo_name"] == "test-repo"
        assert kwargs["worktree_name"] == "screenshot-actions"

    @patch("vibe.cli.prompt_stranded_branch_choice")
    def test_in_place_resumes_on_main_checkout(
        self, mock_prompt: MagicMock, resume_env: ResumeEnv
    ) -> None:
        mock_prompt.return_value = StrandedBranchChoice.IN_PLACE
        strand_branch_on_main(
            resume_env.repo, "screenshot-actions", "wip: park TST_1"
        )
        self._write_stranded_ticket(resume_env, "TST_1")
        worktree_path = (
            resume_env.worktree_base / "test-repo" / "screenshot-actions"
        )

        with patch(
            "vibe.cli.connect_to_remote_path", return_value=0
        ) as mock_connect, patch("vibe.cli.post_session_cleanup") as mock_cleanup:
            result = runner.invoke(app, ["resume", "TST_1"])

        assert result.exit_code == 0
        assert not worktree_path.exists()
        assert current_branch(resume_env.repo) == "screenshot-actions"
        assert get_tip_commit_subject(resume_env.repo) == "Initial commit"
        assert "?? parked.txt" in git_porcelain(resume_env.repo)
        assert mock_connect.call_args.kwargs["remote_path"] == Path(
            "/remote-repos/test-repo"
        )
        mock_cleanup.assert_not_called()

    @patch("vibe.cli.prompt_stranded_branch_choice")
    def test_abort_changes_nothing(
        self, mock_prompt: MagicMock, resume_env: ResumeEnv
    ) -> None:
        mock_prompt.return_value = StrandedBranchChoice.ABORT
        strand_branch_on_main(
            resume_env.repo, "screenshot-actions", "wip: park TST_1"
        )
        self._write_stranded_ticket(resume_env, "TST_1")

        with patch("vibe.cli.connect_to_remote", return_value=0) as mock_connect:
            result = runner.invoke(app, ["resume", "TST_1"])

        assert result.exit_code == 1
        mock_connect.assert_not_called()
        assert current_branch(resume_env.repo) == "screenshot-actions"
        assert get_tip_commit_subject(resume_env.repo) == "wip: park TST_1"

    @patch("vibe.cli.prompt_stranded_branch_choice")
    def test_dirty_main_checkout_offers_no_switch(
        self, mock_prompt: MagicMock, resume_env: ResumeEnv
    ) -> None:
        mock_prompt.return_value = StrandedBranchChoice.IN_PLACE
        strand_branch_on_main(
            resume_env.repo, "screenshot-actions", "wip: park TST_1"
        )
        (resume_env.repo / "uncommitted.txt").write_text("wip\n")
        self._write_stranded_ticket(resume_env, "TST_1")

        with patch("vibe.cli.connect_to_remote_path", return_value=0):
            result = runner.invoke(app, ["resume", "TST_1"])

        assert result.exit_code == 0
        assert mock_prompt.call_args.args[2] is True
        assert current_branch(resume_env.repo) == "screenshot-actions"

    def test_stale_registration_is_pruned_and_recreated(
        self, resume_env: ResumeEnv
    ) -> None:
        worktree_path = add_worktree(
            resume_env.repo, resume_env.worktree_base, "feature-stale"
        )
        commit_in_worktree(worktree_path, "wip: park TST_1")
        import shutil

        shutil.rmtree(worktree_path)
        assert find_branch_checkout("feature-stale", cwd=resume_env.repo) is not None
        write_board_ticket(resume_env.board, "TST_1", "feature-stale", tool="claude")

        with patch("vibe.cli.connect_to_remote", return_value=0):
            result = runner.invoke(app, ["resume", "TST_1"])

        assert result.exit_code == 0
        assert worktree_path.is_dir()
        assert get_tip_commit_subject(worktree_path) == "Initial commit"

    def test_resolve_switchback_prefers_base_branch(
        self, resume_env: ResumeEnv
    ) -> None:
        work = _pw(base_branch="main")
        assert _resolve_switchback_branch(work, resume_env.repo) == "main"

    def test_resolve_switchback_falls_back_when_base_missing(
        self, resume_env: ResumeEnv
    ) -> None:
        work = _pw(base_branch=None)
        assert _resolve_switchback_branch(work, resume_env.repo) == "main"
