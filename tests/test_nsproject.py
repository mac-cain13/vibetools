"""Tests for the NSProject board store (vibe/nsproject.py)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from vibe import nsproject
from vibe.nsproject import (
    ParkedWork,
    find_board,
    find_parked_work,
    is_safe_session_id,
    is_safe_ticket_id,
    list_resumable,
    local_person,
    mark_resumed,
    parse_ticket,
    resolve_local_repo,
)

# A representative parked ticket as written by the park skill.
TICKET = """\
---
id: PW_2cmmx
title: Local Network permission improvements
components: [pw_mac]
created: 2026-06-10
updated: 2026-06-10
work:
  - repo: https://github.com/nonstrict-hq/PersonaWebcam.git
    branch: local-network-permission-improvements
    by: mathijs
    session: bbacac76-a2b4-4b0a-86df-bd0fe78c88d5
    base_branch: main
    tool: claude
    parked_at: 2026-06-10T21:50:41Z
    note: keep-me
---

## What
Body content.

## Where I left off
Pick up at on-device testing.
"""


def make_board(tmp_path: Path, ticket_text: str = TICKET,
               state: str = "this-week",
               filename: str = "010-2cmmx-x.md") -> tuple[Path, Path]:
    """Create a minimal valid board with one ticket.

    Args:
        tmp_path: Temp directory.
        ticket_text: Ticket file contents.
        state: State folder to place the ticket in.
        filename: Ticket file name.

    Returns:
        (board_root, ticket_path)
    """
    board = tmp_path / "board"
    data = board / "data"
    (data / "maybe").mkdir(parents=True)  # board marker dir
    (board / "CLAUDE.md").write_text("# board\n")
    folder = data / state
    folder.mkdir(parents=True, exist_ok=True)
    ticket = folder / filename
    ticket.write_text(ticket_text)
    return board, ticket


def make_repo(repo_base: Path, name: str, origin: str | None = None) -> Path:
    """Create a local repo directory (optionally with an origin URL).

    Args:
        repo_base: Base directory.
        name: Repo directory name.
        origin: Origin URL to set, or None.

    Returns:
        The repo path.
    """
    repo = repo_base / name
    repo.mkdir(parents=True)
    if origin is not None:
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(
            ["git", "remote", "add", "origin", origin], cwd=repo, check=True
        )
    return repo


class TestSafeValidators:
    def test_safe_ticket_id(self) -> None:
        assert is_safe_ticket_id("PW_2cmmx")
        assert is_safe_ticket_id("BZL_q7m2x")
        assert not is_safe_ticket_id("bad id")
        assert not is_safe_ticket_id("a;rm -rf /")

    def test_safe_session_id(self) -> None:
        assert is_safe_session_id("bbacac76-a2b4-4b0a-86df-bd0fe78c88d5")
        assert not is_safe_session_id("abc;rm -rf /")


class TestLocalPerson:
    def test_env_var_wins(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("VIBE_PERSON", "Mathijs")
        assert local_person(tmp_path) == "mathijs"

    def test_falls_back_to_git_user_name(
        self, temp_git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("VIBE_PERSON", raising=False)
        # conftest configures user.name "Test User" -> first token, lowercased.
        assert local_person(temp_git_repo) == "test"

    def test_now_and_today_formats(self) -> None:
        assert nsproject.now_iso().endswith("Z")
        assert len(nsproject.today_iso()) == 10  # YYYY-MM-DD


class TestNormalizeRemote:
    def test_https_and_scp_normalize_equal(self) -> None:
        a = nsproject._normalize_remote("https://github.com/acme/Foo.git")
        b = nsproject._normalize_remote("git@github.com:acme/Foo.git")
        assert a == b == "github.com/acme/foo"

    def test_basename_preserves_case(self) -> None:
        assert nsproject._repo_basename(
            "https://github.com/acme/PersonaWebcam.git"
        ) == "PersonaWebcam"
        assert nsproject._repo_basename(
            "git@github.com:acme/PersonaWebcam.git"
        ) == "PersonaWebcam"


class TestFindBoard:
    def test_env_var_wins(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        board, _ = make_board(tmp_path)
        monkeypatch.setenv("NSPROJECT_BOARD", str(board))
        assert find_board(tmp_path / "elsewhere") == board

    def test_sibling_scan(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NSPROJECT_BOARD", raising=False)
        board, _ = make_board(tmp_path)
        # The board is a child of tmp_path; scanning tmp_path finds it.
        assert find_board(tmp_path) == board

    def test_none_when_absent(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NSPROJECT_BOARD", raising=False)
        empty = tmp_path / "empty"
        empty.mkdir()
        assert find_board(empty) is None


class TestParseTicket:
    def test_parses_top_level_and_work(self, tmp_path: Path) -> None:
        _, ticket = make_board(tmp_path)
        parsed = parse_ticket(ticket)
        assert parsed is not None
        assert parsed.id == "PW_2cmmx"
        assert parsed.title == "Local Network permission improvements"
        assert len(parsed.work) == 1
        entry = parsed.work[0]
        assert entry.get("branch") == "local-network-permission-improvements"
        assert entry.get("tool") == "claude"
        assert entry.get("base_branch") == "main"
        assert entry.get("parked_at") == "2026-06-10T21:50:41Z"
        assert entry.get("note") == "keep-me"  # unknown key preserved on read

    def test_multiple_work_entries(self, tmp_path: Path) -> None:
        text = (
            "---\nid: X_aaaaa\ntitle: T\nwork:\n"
            "  - repo: https://x/a.git\n    branch: a\n    by: me\n"
            "  - repo: https://x/b.git\n    branch: b\n    by: tom\n"
            "---\n\nbody\n"
        )
        _, ticket = make_board(tmp_path, text)
        parsed = parse_ticket(ticket)
        assert parsed is not None
        assert [e.get("branch") for e in parsed.work] == ["a", "b"]
        assert [e.get("by") for e in parsed.work] == ["me", "tom"]

    def test_top_level_after_work_block(self, tmp_path: Path) -> None:
        text = (
            "---\nid: X_aaaaa\nwork:\n  - repo: https://x/a.git\n    branch: a\n"
            "updated: 2026-06-10\n---\n\nbody\n"
        )
        _, ticket = make_board(tmp_path, text)
        parsed = parse_ticket(ticket)
        assert parsed is not None
        assert "updated" in parsed.top
        assert len(parsed.work) == 1

    def test_no_frontmatter_returns_none(self, tmp_path: Path) -> None:
        _, ticket = make_board(tmp_path, "no frontmatter here\n")
        assert parse_ticket(ticket) is None


class TestResolveLocalRepo:
    def test_basename_resolution(self, tmp_path: Path) -> None:
        make_repo(tmp_path, "Foo")
        resolved = resolve_local_repo("https://github.com/acme/Foo.git", tmp_path)
        assert resolved == tmp_path / "Foo"

    def test_origin_scan_resolution(self, tmp_path: Path) -> None:
        # Local dir name differs from the URL basename; match by origin.
        make_repo(tmp_path, "checkout-dir", origin="https://github.com/acme/Foo.git")
        resolved = resolve_local_repo("git@github.com:acme/Foo.git", tmp_path)
        assert resolved == tmp_path / "checkout-dir"

    def test_unresolvable_returns_none(self, tmp_path: Path) -> None:
        assert resolve_local_repo("https://github.com/acme/Ghost.git", tmp_path) is None


class TestSelectWorkEntry:
    def test_prefers_local_handle(self, tmp_path: Path) -> None:
        text = (
            "---\nid: X_aaaaa\nwork:\n"
            "  - repo: https://x/a.git\n    branch: a\n    by: tom\n    parked_at: 2026-06-10T00:00:00Z\n"
            "  - repo: https://x/b.git\n    branch: b\n    by: mathijs\n"
            "---\n\nbody\n"
        )
        _, ticket = make_board(tmp_path, text)
        parsed = parse_ticket(ticket)
        entry = nsproject._select_work_entry(parsed, "mathijs")
        assert entry.get("branch") == "b"

    def test_falls_back_to_most_recent_parked(self, tmp_path: Path) -> None:
        text = (
            "---\nid: X_aaaaa\nwork:\n"
            "  - repo: https://x/a.git\n    branch: a\n    by: tom\n    parked_at: 2026-06-01T00:00:00Z\n"
            "  - repo: https://x/b.git\n    branch: b\n    by: jan\n    parked_at: 2026-06-10T00:00:00Z\n"
            "---\n\nbody\n"
        )
        _, ticket = make_board(tmp_path, text)
        parsed = parse_ticket(ticket)
        entry = nsproject._select_work_entry(parsed, "nobody")
        assert entry.get("branch") == "b"


class TestFindParkedWork:
    def test_resolves_full_parked_work(self, tmp_path: Path) -> None:
        board, _ = make_board(tmp_path)
        repo_base = tmp_path / "repos"
        make_repo(repo_base, "PersonaWebcam")
        work = find_parked_work("PW_2cmmx", board=board, repo_base=repo_base)
        assert work is not None
        assert work.id == "PW_2cmmx"
        assert work.repo_name == "PersonaWebcam"
        assert work.branch == "local-network-permission-improvements"
        assert work.base_branch == "main"
        assert work.tool == "claude"
        assert work.session_id == "bbacac76-a2b4-4b0a-86df-bd0fe78c88d5"
        assert work.parked_at == "2026-06-10T21:50:41Z"

    def test_none_when_repo_unresolvable(self, tmp_path: Path) -> None:
        board, _ = make_board(tmp_path)
        repo_base = tmp_path / "repos"
        repo_base.mkdir()
        assert find_parked_work("PW_2cmmx", board=board, repo_base=repo_base) is None

    def test_none_for_unknown_id(self, tmp_path: Path) -> None:
        board, _ = make_board(tmp_path)
        assert find_parked_work("NOPE_xxxxx", board=board, repo_base=tmp_path) is None

    def test_unknown_tool_falls_back_to_none(self, tmp_path: Path) -> None:
        text = TICKET.replace("tool: claude", "tool: emacs")
        board, _ = make_board(tmp_path, text)
        repo_base = tmp_path / "repos"
        make_repo(repo_base, "PersonaWebcam")
        work = find_parked_work("PW_2cmmx", board=board, repo_base=repo_base)
        assert work is not None
        assert work.tool is None


class TestListResumable:
    def test_lists_tickets_with_work(self, tmp_path: Path) -> None:
        board, _ = make_board(tmp_path)
        # A ticket with no work entry is not resumable.
        (board / "data" / "up-next").mkdir()
        (board / "data" / "up-next" / "010-zzzzz-no-work.md").write_text(
            "---\nid: X_zzzzz\ntitle: No work\n---\n\nbody\n"
        )
        resumable = list_resumable(board=board, repo_base=tmp_path)
        ids = {t.id: t for t in resumable}
        assert "PW_2cmmx" in ids
        assert ids["PW_2cmmx"].parked is True
        assert "X_zzzzz" not in ids

    def test_work_without_parked_at_is_unparked(self, tmp_path: Path) -> None:
        text = (
            "---\nid: X_aaaaa\ntitle: T\nwork:\n"
            "  - repo: https://x/a.git\n    branch: a\n    by: me\n---\n\nbody\n"
        )
        board, _ = make_board(tmp_path, text)
        resumable = list_resumable(board=board, repo_base=tmp_path)
        assert resumable[0].parked is False


class TestMarkResumed:
    def _work(self, board: Path, ticket: Path) -> ParkedWork:
        return ParkedWork(
            id="PW_2cmmx", title="t", board=board, ticket_path=ticket,
            repo_path=board, repo_name="PersonaWebcam",
            branch="local-network-permission-improvements", base_branch="main",
            tool="claude", session_id="s", by="mathijs",
            parked_at="2026-06-10T21:50:41Z",
        )

    def test_clears_parked_at_and_preserves_everything_else(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(nsproject, "today_iso", lambda: "2026-06-16")
        board, ticket = make_board(tmp_path)

        assert mark_resumed(self._work(board, ticket), push=False) is True

        text = ticket.read_text()
        assert "parked_at:" not in text          # the marker line is gone
        assert "note: keep-me" in text            # unknown key preserved
        assert "tool: claude" in text             # sibling keys preserved
        assert "updated: 2026-06-16" in text      # stamped to today
        assert "## Where I left off" in text      # body preserved
        assert "Pick up at on-device testing." in text

    def test_idempotent_when_already_clear(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(nsproject, "today_iso", lambda: "2026-06-16")
        board, ticket = make_board(tmp_path)
        work = self._work(board, ticket)
        assert mark_resumed(work, push=False) is True
        # Re-running re-parses (parked_at gone) and only re-stamps updated.
        assert mark_resumed(work, push=False) is True
        assert "parked_at:" not in ticket.read_text()

    def test_commits_to_board_and_push_failure_is_nonfatal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """push=True commits in data/; a push failure (no remote) only warns."""
        monkeypatch.setattr(nsproject, "today_iso", lambda: "2026-06-16")
        board, ticket = make_board(tmp_path)
        # Make the board a git repo so the commit path runs (no remote => push
        # fails gracefully).
        subprocess.run(["git", "init", "-q"], cwd=board, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.co"], cwd=board, check=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=board, check=True)
        subprocess.run(["git", "add", "-A"], cwd=board, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "init"], cwd=board, capture_output=True,
            check=True,
        )

        assert mark_resumed(self._work(board, ticket), push=True) is True

        assert "parked_at:" not in ticket.read_text()
        # The resume edit was committed in the board repo…
        subject = subprocess.run(
            ["git", "log", "-1", "--pretty=%s"], cwd=board, capture_output=True,
            text=True, check=True,
        ).stdout.strip()
        assert subject == "Update PW_2cmmx: resume"
        # …and the missing remote only produced a warning.
        assert "could not push the board" in capsys.readouterr().out
