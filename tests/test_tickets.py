"""Tests for the vibeboard ticket store module."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from unittest.mock import patch

import pytest

from vibe.tickets import (
    Ticket,
    find_ticket,
    find_ticket_by_repo_branch,
    is_safe_session_id,
    is_safe_ticket_id,
    list_tickets,
    now_iso,
    read_ticket,
    update_ticket_fields,
)

FROZEN_NOW = "2026-06-10T12:00:00Z"


@pytest.fixture
def store(tmp_path: Path) -> Path:
    """Create a temporary ticket store directory.

    Returns:
        Path to the store directory
    """
    store_dir = tmp_path / "_vibeboard"
    store_dir.mkdir()
    return store_dir


def write_ticket_file(store_dir: Path, name: str, content: str) -> Path:
    """Write a ticket file into the store.

    Args:
        store_dir: Store directory
        name: Filename (including .md)
        content: File content

    Returns:
        Path to the written file
    """
    path = store_dir / name
    path.write_bytes(content.encode("utf-8"))
    return path


class TestNowIso:
    """Tests for now_iso."""

    def test_format(self) -> None:
        """Should match YYYY-MM-DDTHH:MM:SSZ exactly."""
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", now_iso())

    def test_is_utc(self) -> None:
        """Should be the current UTC time, second precision."""
        before = datetime.now(timezone.utc).replace(microsecond=0)
        parsed = datetime.strptime(now_iso(), "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
        after = datetime.now(timezone.utc)
        assert before <= parsed <= after


class TestSafeIdValidation:
    """Tests for is_safe_ticket_id and is_safe_session_id."""

    def test_safe_ticket_ids(self) -> None:
        """Should accept ids in the conservative charset."""
        assert is_safe_ticket_id("vibe-12") is True
        assert is_safe_ticket_id("my.repo_2-3") is True
        assert is_safe_ticket_id("ABC-9") is True

    def test_unsafe_ticket_ids(self) -> None:
        """Should reject empty ids and shell-dangerous characters."""
        assert is_safe_ticket_id("") is False
        assert is_safe_ticket_id("has space-1") is False
        assert is_safe_ticket_id("a/b-1") is False
        assert is_safe_ticket_id("x;rm -rf-1") is False
        assert is_safe_ticket_id("tick$et-1") is False

    def test_safe_session_ids(self) -> None:
        """Should accept UUID-shaped session ids."""
        assert is_safe_session_id("0c4f9a2e-1b3d-4c5e-8f6a-7b8c9d0e1f2a") is True
        assert is_safe_session_id("abc123") is True

    def test_unsafe_session_ids(self) -> None:
        """Should reject empty values and anything outside [A-Za-z0-9-]."""
        assert is_safe_session_id("") is False
        assert is_safe_session_id("a_b") is False
        assert is_safe_session_id("a.b") is False
        assert is_safe_session_id("a b") is False
        assert is_safe_session_id("a;b") is False


class TestReadTicketLenient:
    """Tests for read_ticket lenient parsing."""

    def test_well_formed_ticket(self, store: Path) -> None:
        """Should parse frontmatter fields and body."""
        path = write_ticket_file(
            store,
            "vibe-12.md",
            "---\n"
            "id: vibe-12\n"
            "title: Retry logic\n"
            "state: on_hold\n"
            "---\n"
            "\n"
            "Body text.\n",
        )
        ticket = read_ticket(path)
        assert ticket.fields["id"] == "vibe-12"
        assert ticket.fields["title"] == "Retry logic"
        assert ticket.fields["state"] == "on_hold"
        assert ticket.body == "\nBody text.\n"

    def test_no_frontmatter_whole_file_is_body(self, store: Path) -> None:
        """Should treat a file without frontmatter as all body."""
        path = write_ticket_file(store, "vibe-1.md", "Just some notes.\n")
        ticket = read_ticket(path)
        assert ticket.fields == {}
        assert ticket.body == "Just some notes.\n"
        assert ticket.id == "vibe-1"

    def test_unclosed_frontmatter_is_body(self, store: Path) -> None:
        """Should treat an opening '---' without a closing one as all body."""
        content = "---\nid: vibe-2\nno closing delimiter\n"
        path = write_ticket_file(store, "vibe-2.md", content)
        ticket = read_ticket(path)
        assert ticket.fields == {}
        assert ticket.body == content

    def test_crlf_line_endings(self, store: Path) -> None:
        """Should parse CRLF files; values carry no trailing CR."""
        path = write_ticket_file(
            store,
            "vibe-3.md",
            "---\r\nid: vibe-3\r\nstate: doing\r\n---\r\nbody\r\n",
        )
        ticket = read_ticket(path)
        assert ticket.fields["id"] == "vibe-3"
        assert ticket.state == "doing"

    def test_comment_lines_skipped(self, store: Path) -> None:
        """Should skip '#' comment lines inside frontmatter."""
        path = write_ticket_file(
            store,
            "vibe-4.md",
            "---\n# a comment\nid: vibe-4\n  # indented comment\n---\n",
        )
        ticket = read_ticket(path)
        assert ticket.fields == {"id": "vibe-4"}

    def test_quoted_values_one_layer_stripped(self, store: Path) -> None:
        """Should strip exactly one layer of matching quotes."""
        path = write_ticket_file(
            store,
            "vibe-5.md",
            "---\n"
            'title: "Quoted: title"\n'
            "branch: 'feature/x'\n"
            "repo: \"'nested'\"\n"
            'session_id: "unbalanced\n'
            "---\n",
        )
        ticket = read_ticket(path)
        assert ticket.fields["title"] == "Quoted: title"
        assert ticket.fields["branch"] == "feature/x"
        assert ticket.fields["repo"] == "'nested'"
        assert ticket.fields["session_id"] == '"unbalanced'

    def test_quote_escapes_resolved(self, store: Path) -> None:
        """Should resolve quote escapes the same way as the other readers."""
        path = write_ticket_file(
            store,
            "vibe-14.md",
            "---\n"
            'title: "escaped \\"quote\\" inside"\n'
            'description: "back\\\\slash"\n'
            "branch: 'it''s quoted'\n"
            "---\n",
        )
        ticket = read_ticket(path)
        assert ticket.fields["title"] == 'escaped "quote" inside'
        assert ticket.fields["description"] == "back\\slash"
        assert ticket.fields["branch"] == "it's quoted"

    def test_indented_dashes_do_not_close_frontmatter(self, store: Path) -> None:
        """Should keep an indented '---' in a block from closing frontmatter."""
        path = write_ticket_file(
            store,
            "vibe-15.md",
            "---\n"
            "id: vibe-15\n"
            "description: |\n"
            "  before rule\n"
            "  ---\n"
            "  after rule\n"
            "state: on_hold\n"
            "branch: feature/x\n"
            "---\n"
            "body\n",
        )
        ticket = read_ticket(path)
        assert ticket.state == "on_hold"
        assert ticket.branch == "feature/x"
        assert ticket.fields["description"] == "before rule\n---\nafter rule"
        assert ticket.body == "body\n"

    def test_block_scalar_consumed(self, store: Path) -> None:
        """Should consume block scalar continuation lines without crashing."""
        path = write_ticket_file(
            store,
            "vibe-6.md",
            "---\n"
            "description: |\n"
            "  line one\n"
            "  line two\n"
            "state: ready\n"
            "---\n"
            "body\n",
        )
        ticket = read_ticket(path)
        assert ticket.fields["description"] == "line one\nline two"
        assert ticket.state == "ready"

    def test_block_scalar_with_blank_line_inside(self, store: Path) -> None:
        """Should keep a blank line inside a block from breaking the parse."""
        path = write_ticket_file(
            store,
            "vibe-7.md",
            "---\n"
            "description: |-\n"
            "  first\n"
            "\n"
            "  second\n"
            "priority: high\n"
            "---\n",
        )
        ticket = read_ticket(path)
        assert "first" in ticket.fields["description"]
        assert "second" in ticket.fields["description"]
        # priority is retired but still tolerated and kept as a raw field.
        assert ticket.fields["priority"] == "high"

    def test_block_scalar_at_end_of_frontmatter(self, store: Path) -> None:
        """Should handle a block scalar running up to the closing '---'."""
        path = write_ticket_file(
            store,
            "vibe-8.md",
            "---\nid: vibe-8\ndescription: |\n  only line\n---\nbody\n",
        )
        ticket = read_ticket(path)
        assert ticket.fields["id"] == "vibe-8"
        assert ticket.fields["description"] == "only line"
        assert ticket.body == "body\n"

    def test_empty_value_treated_as_absent(self, store: Path) -> None:
        """Should treat empty values as absent/null."""
        path = write_ticket_file(store, "vibe-9.md", "---\nbranch:\nworktree: \n---\n")
        ticket = read_ticket(path)
        assert ticket.branch is None
        assert ticket.worktree is None

    def test_duplicate_keys_last_wins(self, store: Path) -> None:
        """Should let the last occurrence of a duplicate key win."""
        path = write_ticket_file(
            store, "vibe-10.md", "---\nstate: todo\nstate: doing\n---\n"
        )
        ticket = read_ticket(path)
        assert ticket.state == "doing"

    def test_junk_line_without_colon_skipped(self, store: Path) -> None:
        """Should skip frontmatter lines without a ':' separator."""
        path = write_ticket_file(
            store, "vibe-11.md", "---\njust some junk\nid: vibe-11\n---\n"
        )
        ticket = read_ticket(path)
        assert ticket.fields == {"id": "vibe-11"}

    def test_invalid_utf8_does_not_crash(self, store: Path) -> None:
        """Should never crash on undecodable bytes."""
        path = store / "vibe-12.md"
        path.write_bytes(b"---\nid: vibe-12\n---\nbody \xff\xfe bytes\n")
        ticket = read_ticket(path)
        assert ticket.fields["id"] == "vibe-12"

    def test_empty_file(self, store: Path) -> None:
        """Should parse an empty file as an empty-bodied ticket."""
        path = write_ticket_file(store, "vibe-13.md", "")
        ticket = read_ticket(path)
        assert ticket.fields == {}
        assert ticket.body == ""
        assert ticket.id == "vibe-13"


class TestTicketProperties:
    """Tests for Ticket property defaults and fallbacks."""

    def make(self, fields: dict[str, str], stem: str = "vibe-12") -> Ticket:
        """Build a Ticket with the given raw fields.

        Args:
            fields: Raw frontmatter fields
            stem: Filename stem for the synthetic path

        Returns:
            Ticket instance
        """
        return Ticket(path=Path(f"/store/{stem}.md"), fields=fields, body="")

    def test_id_from_field(self) -> None:
        """Should prefer the id field over the filename."""
        assert self.make({"id": "other-7"}).id == "other-7"

    def test_id_fallback_to_filename_stem(self) -> None:
        """Should fall back to the filename stem when id is missing."""
        assert self.make({}).id == "vibe-12"
        assert self.make({"id": ""}).id == "vibe-12"
        assert self.make({"id": "null"}).id == "vibe-12"

    def test_repo_from_field(self) -> None:
        """Should prefer the repo field."""
        assert self.make({"repo": "bezel"}).repo == "bezel"

    def test_repo_fallback_strips_trailing_number(self) -> None:
        """Should derive repo by stripping the id's trailing -<digits>."""
        assert self.make({}).repo == "vibe"
        assert self.make({"id": "my-repo-3"}).repo == "my-repo"

    def test_repo_fallback_without_trailing_number(self) -> None:
        """Should leave an id without a numeric suffix unchanged."""
        assert self.make({}, stem="weird").repo == "weird"

    def test_title_fallback_to_id(self) -> None:
        """Should fall back to the id when title is missing."""
        assert self.make({}).title == "vibe-12"
        assert self.make({"title": "Real title"}).title == "Real title"

    def test_branch_null_handling(self) -> None:
        """Should return None for missing/empty/null branch."""
        assert self.make({}).branch is None
        assert self.make({"branch": ""}).branch is None
        assert self.make({"branch": "null"}).branch is None
        assert self.make({"branch": "feature/x"}).branch == "feature/x"

    def test_worktree_null_handling(self) -> None:
        """Should return None for missing/empty/null worktree."""
        assert self.make({}).worktree is None
        assert self.make({"worktree": "null"}).worktree is None
        assert self.make({"worktree": "/tmp/wt"}).worktree == "/tmp/wt"

    def test_tool_validation(self) -> None:
        """Should return only known tools, None otherwise."""
        assert self.make({"tool": "claude"}).tool == "claude"
        assert self.make({"tool": "codex"}).tool == "codex"
        assert self.make({"tool": "opencode"}).tool == "opencode"
        assert self.make({"tool": "Claude"}).tool == "claude"
        assert self.make({"tool": "vim"}).tool is None
        assert self.make({}).tool is None

    def test_session_id_null_handling(self) -> None:
        """Should return None for missing/empty/null session_id."""
        assert self.make({}).session_id is None
        assert self.make({"session_id": "null"}).session_id is None
        assert self.make({"session_id": "abc-123"}).session_id == "abc-123"

    def test_state_default_and_unknown(self) -> None:
        """Should default to 'todo' for missing or unrecognized state."""
        assert self.make({}).state == "todo"
        assert self.make({"state": "bogus"}).state == "todo"
        assert self.make({"state": "DOING"}).state == "doing"
        for state in ("todo", "doing", "on_hold", "ready", "archived"):
            assert self.make({"state": state}).state == state

    def test_retired_priority_field_is_kept_as_raw(self) -> None:
        """Retired 'priority' has no accessor but survives in raw fields."""
        ticket = self.make({"priority": "high"})
        assert ticket.fields["priority"] == "high"
        assert not hasattr(ticket, "priority")


class TestListTickets:
    """Tests for list_tickets."""

    def test_lists_tickets_sorted_by_filename(self, store: Path) -> None:
        """Should return tickets sorted by filename."""
        write_ticket_file(store, "vibe-2.md", "---\nid: vibe-2\n---\n")
        write_ticket_file(store, "bezel-1.md", "---\nid: bezel-1\n---\n")
        tickets = list_tickets(store)
        assert [t.id for t in tickets] == ["bezel-1", "vibe-2"]

    def test_skips_junk(self, store: Path) -> None:
        """Should skip hidden files, directories, and non-.md files."""
        write_ticket_file(store, "vibe-1.md", "---\nid: vibe-1\n---\n")
        (store / ".DS_Store").write_bytes(b"\x00junk")
        (store / ".hidden.md").write_text("---\nid: hidden-1\n---\n")
        (store / "notes.txt").write_text("not a ticket")
        (store / "subdir-1.md").mkdir()
        (store / "plain-dir").mkdir()
        tickets = list_tickets(store)
        assert [t.id for t in tickets] == ["vibe-1"]

    def test_skips_md_files_not_matching_naming_rule(self, store: Path) -> None:
        """Should ignore .md files whose stem is not '<repo>-<digits>'."""
        write_ticket_file(store, "vibe-1.md", "---\nid: vibe-1\n---\n")
        (store / "README.md").write_text("# About this store\n")
        (store / "notes.md").write_text("scratch notes")
        (store / "no-number-.md").write_text("---\nid: x\n---\n")
        (store / "-1.md").write_text("---\nid: y\n---\n")
        (store / "trailing-1x.md").write_text("---\nid: z\n---\n")
        tickets = list_tickets(store)
        assert [t.id for t in tickets] == ["vibe-1"]

    def test_never_raises_on_garbage_content(self, store: Path) -> None:
        """Should include but not choke on garbage .md content."""
        (store / "garbage-1.md").write_bytes(b"\x00\xff\xfe\x01 not yaml at all")
        write_ticket_file(store, "vibe-1.md", "---\nid: vibe-1\n---\n")
        tickets = list_tickets(store)
        assert "vibe-1" in [t.id for t in tickets]

    def test_never_raises_on_read_error(self, store: Path) -> None:
        """Should skip files whose read raises instead of propagating."""
        write_ticket_file(store, "vibe-1.md", "---\nid: vibe-1\n---\n")
        with patch("vibe.tickets.read_ticket", side_effect=OSError("boom")):
            assert list_tickets(store) == []

    def test_missing_store_dir(self, tmp_path: Path) -> None:
        """Should return an empty list when the store doesn't exist."""
        assert list_tickets(tmp_path / "nope") == []


class TestFindTicket:
    """Tests for find_ticket."""

    def test_primary_lookup_by_filename(self, store: Path) -> None:
        """Should find a ticket at the conventional <id>.md path."""
        write_ticket_file(store, "vibe-12.md", "---\nid: vibe-12\nstate: doing\n---\n")
        ticket = find_ticket("vibe-12", store)
        assert ticket is not None
        assert ticket.state == "doing"

    def test_primary_lookup_wins_over_id_field(self, store: Path) -> None:
        """Should return the conventionally-named file even with a stray id."""
        write_ticket_file(store, "vibe-12.md", "---\nid: other-9\n---\n")
        ticket = find_ticket("vibe-12", store)
        assert ticket is not None
        assert ticket.path.name == "vibe-12.md"

    def test_fallback_scan_by_id_field(self, store: Path) -> None:
        """Should fall back to scanning the id field of every ticket."""
        write_ticket_file(store, "renamed-2.md", "---\nid: vibe-7\n---\n")
        ticket = find_ticket("vibe-7", store)
        assert ticket is not None
        assert ticket.path.name == "renamed-2.md"

    def test_not_found(self, store: Path) -> None:
        """Should return None when no ticket matches."""
        assert find_ticket("missing-1", store) is None

    def test_non_ticket_filename_never_resolves(self, store: Path) -> None:
        """Should not resolve a stray .md file that isn't a ticket."""
        (store / "README.md").write_text("# About this store\n")
        assert find_ticket("README", store) is None

    def test_unsafe_id_does_not_crash(self, store: Path) -> None:
        """Should handle path-dangerous ids without touching the filesystem."""
        assert find_ticket("../escape", store) is None
        assert find_ticket("a/b", store) is None


class TestFindTicketByRepoBranch:
    """Tests for find_ticket_by_repo_branch."""

    def test_basic_match(self, store: Path) -> None:
        """Should match on explicit repo and branch fields."""
        write_ticket_file(
            store, "vibe-1.md", "---\nrepo: vibe\nbranch: feature/x\n---\n"
        )
        ticket = find_ticket_by_repo_branch("vibe", "feature/x", store)
        assert ticket is not None
        assert ticket.id == "vibe-1"

    def test_match_uses_resolved_repo_fallback(self, store: Path) -> None:
        """Should match using the repo derived from the id."""
        write_ticket_file(store, "vibe-3.md", "---\nbranch: fix/y\n---\n")
        ticket = find_ticket_by_repo_branch("vibe", "fix/y", store)
        assert ticket is not None
        assert ticket.id == "vibe-3"

    def test_branch_must_match(self, store: Path) -> None:
        """Should not match a ticket with a different or null branch."""
        write_ticket_file(store, "vibe-1.md", "---\nrepo: vibe\nbranch: null\n---\n")
        write_ticket_file(store, "vibe-2.md", "---\nrepo: vibe\nbranch: other\n---\n")
        assert find_ticket_by_repo_branch("vibe", "feature/x", store) is None

    def test_prefers_non_archived(self, store: Path) -> None:
        """Should prefer a non-archived ticket over an archived one."""
        write_ticket_file(
            store,
            "vibe-1.md",
            "---\nrepo: vibe\nbranch: b\nstate: archived\n"
            "updated: 2026-06-09T10:00:00Z\n---\n",
        )
        write_ticket_file(
            store,
            "vibe-2.md",
            "---\nrepo: vibe\nbranch: b\nstate: on_hold\n"
            "updated: 2026-06-01T10:00:00Z\n---\n",
        )
        ticket = find_ticket_by_repo_branch("vibe", "b", store)
        assert ticket is not None
        assert ticket.id == "vibe-2"

    def test_prefers_most_recently_updated(self, store: Path) -> None:
        """Should prefer the most recently updated among non-archived."""
        write_ticket_file(
            store,
            "vibe-1.md",
            "---\nrepo: vibe\nbranch: b\nupdated: 2026-06-01T10:00:00Z\n---\n",
        )
        write_ticket_file(
            store,
            "vibe-2.md",
            "---\nrepo: vibe\nbranch: b\nupdated: 2026-06-09T10:00:00Z\n---\n",
        )
        ticket = find_ticket_by_repo_branch("vibe", "b", store)
        assert ticket is not None
        assert ticket.id == "vibe-2"

    def test_no_match(self, store: Path) -> None:
        """Should return None when nothing matches."""
        assert find_ticket_by_repo_branch("vibe", "b", store) is None


@pytest.fixture
def frozen_now() -> Iterator[None]:
    """Freeze now_iso for deterministic update assertions."""
    with patch("vibe.tickets.now_iso", return_value=FROZEN_NOW):
        yield


@pytest.mark.usefixtures("frozen_now")
class TestUpdateTicketFields:
    """Tests for update_ticket_fields."""

    def test_preserves_everything_byte_identical(self, store: Path) -> None:
        """Should round-trip unknown keys, comments, ordering, and body."""
        original = (
            "---\n"
            "id: vibe-12\n"
            "# keep this comment\n"
            "custom_key: custom value\n"
            "title: Retry logic\n"
            "state: doing\n"
            "junk line without separator\n"
            "updated: 2026-01-01T00:00:00Z\n"
            "---\n"
            "\n"
            "Body text.\n"
            "\n"
            "## Next step\n"
            "\n"
            "Do the thing.\n"
        )
        path = write_ticket_file(store, "vibe-12.md", original)
        assert update_ticket_fields(path, {"state": "on_hold"}) is True
        expected = original.replace("state: doing", "state: on_hold").replace(
            "updated: 2026-01-01T00:00:00Z", f"updated: {FROZEN_NOW}"
        )
        assert path.read_bytes().decode("utf-8") == expected

    def test_replaces_block_scalar_value(self, store: Path) -> None:
        """Should remove a replaced block scalar's continuation lines."""
        path = write_ticket_file(
            store,
            "vibe-1.md",
            "---\n"
            "description: |\n"
            "  line one\n"
            "  line two\n"
            "state: todo\n"
            "---\n"
            "body\n",
        )
        assert update_ticket_fields(path, {"description": "short now"}) is True
        assert path.read_bytes().decode("utf-8") == (
            "---\n"
            "description: short now\n"
            "state: todo\n"
            f"updated: {FROZEN_NOW}\n"
            "---\n"
            "body\n"
        )

    def test_inserts_missing_keys_before_closing_delimiter(self, store: Path) -> None:
        """Should insert keys the file lacks before the closing '---'."""
        path = write_ticket_file(store, "vibe-1.md", "---\nid: vibe-1\n---\nbody\n")
        updates = {"worktree": "/tmp/wt", "branch": "feature/x"}
        assert update_ticket_fields(path, updates) is True
        assert path.read_bytes().decode("utf-8") == (
            "---\n"
            "id: vibe-1\n"
            "worktree: /tmp/wt\n"
            "branch: feature/x\n"
            f"updated: {FROZEN_NOW}\n"
            "---\n"
            "body\n"
        )

    def test_none_writes_literal_null(self, store: Path) -> None:
        """Should write None values as the literal 'null'."""
        path = write_ticket_file(
            store, "vibe-1.md", "---\nworktree: /tmp/wt\n---\n"
        )
        assert update_ticket_fields(path, {"worktree": None}) is True
        content = path.read_bytes().decode("utf-8")
        assert "worktree: null\n" in content
        assert read_ticket(path).worktree is None

    def test_refreshes_updated_in_place(self, store: Path) -> None:
        """Should refresh an existing 'updated' line at its position."""
        path = write_ticket_file(
            store,
            "vibe-1.md",
            "---\nupdated: 2020-01-01T00:00:00Z\nid: vibe-1\n---\n",
        )
        assert update_ticket_fields(path, {"state": "doing"}) is True
        assert path.read_bytes().decode("utf-8") == (
            "---\n"
            f"updated: {FROZEN_NOW}\n"
            "id: vibe-1\n"
            "state: doing\n"
            "---\n"
        )

    def test_no_temp_residue_after_update(self, store: Path) -> None:
        """Should leave only ticket files in the store after updating."""
        path = write_ticket_file(store, "vibe-1.md", "---\nid: vibe-1\n---\n")
        assert update_ticket_fields(path, {"state": "doing"}) is True
        assert sorted(p.name for p in store.iterdir()) == ["vibe-1.md"]

    def test_no_temp_residue_when_replace_fails(self, store: Path) -> None:
        """Should clean up the temp file and return False on rename failure."""
        original = "---\nid: vibe-1\n---\n"
        path = write_ticket_file(store, "vibe-1.md", original)
        with patch("vibe.tickets.os.replace", side_effect=OSError("boom")):
            assert update_ticket_fields(path, {"state": "doing"}) is False
        assert sorted(p.name for p in store.iterdir()) == ["vibe-1.md"]
        assert path.read_bytes().decode("utf-8") == original

    def test_file_without_frontmatter_gets_block_prepended(self, store: Path) -> None:
        """Should prepend a new frontmatter block, leaving the body intact."""
        path = write_ticket_file(store, "vibe-1.md", "Just a body.\n")
        assert update_ticket_fields(path, {"state": "doing"}) is True
        assert path.read_bytes().decode("utf-8") == (
            "---\n"
            "state: doing\n"
            f"updated: {FROZEN_NOW}\n"
            "---\n"
            "Just a body.\n"
        )

    def test_returns_false_and_warns_on_read_error(self, store: Path) -> None:
        """Should return False and warn instead of raising on IO errors."""
        missing = store / "nope" / "vibe-1.md"
        with patch("vibe.tickets.console") as mock_console:
            assert update_ticket_fields(missing, {"state": "doing"}) is False
        mock_console.print.assert_called_once()

    def test_preserves_crlf_line_endings(self, store: Path) -> None:
        """Should keep CRLF endings on all lines, including new ones."""
        path = write_ticket_file(
            store, "vibe-1.md", "---\r\nid: vibe-1\r\nstate: todo\r\n---\r\nbody\r\n"
        )
        assert update_ticket_fields(path, {"state": "doing"}) is True
        assert path.read_bytes().decode("utf-8") == (
            "---\r\n"
            "id: vibe-1\r\n"
            "state: doing\r\n"
            f"updated: {FROZEN_NOW}\r\n"
            "---\r\n"
            "body\r\n"
        )

    def test_preserves_undecodable_body_bytes(self, store: Path) -> None:
        """Should round-trip bytes that are not valid UTF-8."""
        path = store / "vibe-1.md"
        path.write_bytes(b"---\nstate: todo\n---\nbody \xff\xfe bytes\n")
        assert update_ticket_fields(path, {"state": "doing"}) is True
        assert path.read_bytes() == (
            b"---\nstate: doing\nupdated: " + FROZEN_NOW.encode()
            + b"\n---\nbody \xff\xfe bytes\n"
        )

    def test_duplicate_keys_all_replaced(self, store: Path) -> None:
        """Should rewrite every occurrence of an updated duplicate key."""
        path = write_ticket_file(
            store, "vibe-1.md", "---\nstate: todo\nstate: doing\n---\n"
        )
        assert update_ticket_fields(path, {"state": "ready"}) is True
        content = path.read_bytes().decode("utf-8")
        assert content.count("state: ready\n") == 2
        assert "todo" not in content
        assert "doing" not in content

    def test_quotes_values_that_need_it(self, store: Path) -> None:
        """Should double-quote values containing ': ' and read them back."""
        path = write_ticket_file(store, "vibe-1.md", "---\nid: vibe-1\n---\n")
        assert update_ticket_fields(path, {"title": "has: colon"}) is True
        content = path.read_bytes().decode("utf-8")
        assert 'title: "has: colon"\n' in content
        assert read_ticket(path).title == "has: colon"

    def test_embedded_quotes_round_trip(self, store: Path) -> None:
        """Should escape embedded double quotes on write and read them back."""
        path = write_ticket_file(store, "vibe-1.md", "---\nid: vibe-1\n---\n")
        assert update_ticket_fields(path, {"title": '"Bug" in parser'}) is True
        content = path.read_bytes().decode("utf-8")
        assert 'title: "\\"Bug\\" in parser"\n' in content
        assert read_ticket(path).title == '"Bug" in parser'

    def test_embedded_backslashes_round_trip(self, store: Path) -> None:
        """Should escape embedded backslashes on write and read them back."""
        path = write_ticket_file(store, "vibe-1.md", "---\nid: vibe-1\n---\n")
        value = "C:\\path: yes"
        assert update_ticket_fields(path, {"title": value}) is True
        content = path.read_bytes().decode("utf-8")
        assert 'title: "C:\\\\path: yes"\n' in content
        assert read_ticket(path).title == value

    def test_update_preserves_block_with_indented_dashes(
        self, store: Path
    ) -> None:
        """Should never splice fields into a block containing '  ---'."""
        path = write_ticket_file(
            store,
            "vibe-1.md",
            "---\n"
            "description: |\n"
            "  intro\n"
            "  ---\n"
            "  outro\n"
            "state: on_hold\n"
            "---\n"
            "body\n",
        )
        assert update_ticket_fields(path, {"state": "doing"}) is True
        assert path.read_bytes().decode("utf-8") == (
            "---\n"
            "description: |\n"
            "  intro\n"
            "  ---\n"
            "  outro\n"
            "state: doing\n"
            f"updated: {FROZEN_NOW}\n"
            "---\n"
            "body\n"
        )

    def test_body_without_trailing_newline_preserved(self, store: Path) -> None:
        """Should not add a trailing newline to the body."""
        path = write_ticket_file(store, "vibe-1.md", "---\nid: vibe-1\n---\nno newline")
        assert update_ticket_fields(path, {"state": "doing"}) is True
        assert path.read_bytes().decode("utf-8").endswith("no newline")
