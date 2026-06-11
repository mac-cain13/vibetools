"""Vibe Board ticket store — lenient reads and field-preserving writes.

Python `vibe` is one of three independent implementers of the ticket format
defined in docs/vibeboard-format.md (alongside the park skill and the
native Mac app). There is no shared library, so this module follows the two
hard requirements of the spec: lenient parsing (every field is optional on
read; malformed content never crashes a reader) and field-preserving
read-modify-write (unknown keys, comments, ordering, and the body round-trip
byte-identical).

vibe never creates tickets — it only reads and updates them.
"""

from __future__ import annotations

import contextlib
import os
import re
import tempfile
import textwrap
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from vibe.config import VIBEBOARD_DIR
from vibe.utils import console

# Known enum values (vibeboard-format.md §4); unrecognized values fall back
# to the §6 defaults instead of failing.
VALID_STATES = frozenset({"todo", "doing", "on_hold", "ready", "archived"})
VALID_TOOLS = frozenset({"claude", "codex", "opencode"})

# Resume soft-deletes a ticket by moving it into this hidden subdirectory of the
# store, so it leaves the board (which scans the root, ignoring dotfiles) but
# `vibe resume <id>` can still recover it after an accidental close.
RESUMED_SUBDIR = ".resumed"

# Conservative charsets for ticket values that end up in shell commands or
# prompts (vibeboard-format.md §6) — tickets are hand-editable files.
_SAFE_TICKET_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_SAFE_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9-]+$")

# Trailing -<digits> suffix of a ticket id (stripped to recover the repo name)
_ID_NUMBER_SUFFIX_RE = re.compile(r"-\d+$")

# Filename stem of a ticket file: <repo>-<number> (vibeboard-format.md §2)
_TICKET_FILENAME_STEM_RE = re.compile(r".+-\d+")

# Leading characters that force double-quoting when writing a scalar value
_YAML_SPECIAL_LEAD = set("!&*?{}[]#|>@`\"'%,:")


def now_iso() -> str:
    """Get the current UTC time in the ticket timestamp format.

    Returns:
        Timestamp string like '2026-06-10T14:30:00Z' (second precision, UTC)
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_safe_ticket_id(value: str) -> bool:
    """Check whether a ticket id is safe to embed in shell commands/prompts.

    Args:
        value: Candidate ticket id

    Returns:
        True if the value matches the conservative ^[A-Za-z0-9._-]+$ charset
    """
    return bool(_SAFE_TICKET_ID_RE.match(value))


def is_safe_session_id(value: str) -> bool:
    """Check whether a session id is safe to embed in shell commands.

    Args:
        value: Candidate session id

    Returns:
        True if the value matches the conservative ^[A-Za-z0-9-]+$ charset
    """
    return bool(_SAFE_SESSION_ID_RE.match(value))


def _is_ticket_filename(name: str) -> bool:
    """Check a filename against the ticket naming rule '<repo>-<n>.md'.

    Readers must ignore anything that is not a ticket file
    (vibeboard-format.md §1): hidden files, non-.md files, and .md files
    whose stem is not '<repo>-<digits>' (e.g. a README.md) never parse.

    Args:
        name: A directory entry name

    Returns:
        True when the name matches the ticket naming rule
    """
    if name.startswith(".") or not name.endswith(".md"):
        return False
    return bool(_TICKET_FILENAME_STEM_RE.fullmatch(name[: -len(".md")]))


def _strip_line_ending(line: str) -> str:
    """Remove a trailing line terminator from a line.

    Args:
        line: Line that may end with '\\n', '\\r\\n', or '\\r'

    Returns:
        Line content without its terminator
    """
    return line.rstrip("\r\n")


def _line_ending(line: str) -> str:
    """Extract a line's terminator, defaulting to '\\n'.

    Args:
        line: Line that may end with a terminator

    Returns:
        The terminator ('\\n', '\\r\\n', ...) or '\\n' when the line has none
    """
    content = _strip_line_ending(line)
    return line[len(content):] or "\n"


def _is_block_scalar_marker(value: str) -> bool:
    """Check whether a scalar value introduces a YAML block scalar.

    Args:
        value: Stripped scalar value from a 'key: value' line

    Returns:
        True for block markers like '|', '|-', '>', '>2'
    """
    if not value or value[0] not in "|>":
        return False
    return all(c in "+-0123456789" for c in value[1:])


def _block_continuation_end(lines: list[str], start: int, end: int) -> int:
    """Find the line index just past a block scalar's continuation lines.

    Continuation lines are indented; blank lines belong to the block only
    when a later indented line follows before the next non-indented line.

    Args:
        lines: Document lines (with or without line terminators)
        start: Index of the first line after the 'key: |' marker line
        end: Index to stop at, exclusive (the closing '---' of frontmatter)

    Returns:
        Index of the first line that is not part of the block scalar
    """
    i = start
    while i < end:
        content = _strip_line_ending(lines[i])
        if content.startswith((" ", "\t")):
            i += 1
            continue
        if content.strip() == "":
            j = i + 1
            while j < end and _strip_line_ending(lines[j]).strip() == "":
                j += 1
            if j < end and _strip_line_ending(lines[j]).startswith((" ", "\t")):
                i = j
                continue
        break
    return i


def _parse_key_value(line: str) -> tuple[str, str] | None:
    """Leniently parse a frontmatter line into a (key, value) pair.

    Args:
        line: Raw frontmatter line (terminator allowed)

    Returns:
        (key, stripped value) tuple, or None for blank lines, comment lines,
        indented continuation lines, and lines without a ':' separator
    """
    content = _strip_line_ending(line)
    if content.startswith((" ", "\t")):
        return None
    stripped = content.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if ":" not in content:
        return None
    key, _, value = content.partition(":")
    key = key.strip()
    if not key:
        return None
    return key, value.strip()


def _unquote(value: str) -> str:
    """Strip one layer of matching surrounding quotes from a scalar value.

    Quote escapes inside the value are resolved so a reader recovers exactly
    what a writer quoted (vibeboard-format.md §6): double-quoted values
    resolve ``\\"`` to ``"`` and ``\\\\`` to ``\\``; single-quoted values
    resolve ``''`` to ``'``.

    Args:
        value: Stripped scalar value

    Returns:
        Value with a single matching layer of quotes removed and its quote
        escapes resolved, or the input unchanged when it is not quoted
    """
    if len(value) < 2 or value[0] != value[-1] or value[0] not in "\"'":
        return value
    inner = value[1:-1]
    if value[0] == '"':
        return inner.replace('\\"', '"').replace("\\\\", "\\")
    return inner.replace("''", "'")


def _frontmatter_bounds(lines: list[str]) -> tuple[int, int] | None:
    """Locate the frontmatter delimiter lines of a ticket document.

    The closing delimiter must start at column 0 (trailing whitespace is
    tolerated, vibeboard-format.md \u00a76); an indented '---' \u2014 e.g. a Markdown
    horizontal rule inside a block scalar \u2014 never closes the frontmatter.

    Args:
        lines: Document lines (with or without line terminators)

    Returns:
        (open_index, close_index) of the '---' delimiter lines, or None when
        the document has no well-formed frontmatter block
    """
    if not lines:
        return None
    first = _strip_line_ending(lines[0]).lstrip("\ufeff").strip()
    if first != "---":
        return None
    for i in range(1, len(lines)):
        content = _strip_line_ending(lines[i])
        if not content.startswith((" ", "\t")) and content.strip() == "---":
            return 0, i
    return None


@dataclass
class Ticket:
    """A parsed vibeboard ticket.

    Attributes:
        path: File the ticket was read from
        fields: Raw frontmatter scalar values after lenient parse (duplicate
            keys last-win, one matching quote layer stripped)
        body: Everything after the closing frontmatter delimiter, raw; the
            whole file when frontmatter is missing or malformed
    """

    path: Path
    fields: dict[str, str]
    body: str

    def _raw(self, key: str) -> str | None:
        """Get a field value, treating empty and 'null' values as absent.

        Args:
            key: Frontmatter key

        Returns:
            The non-empty value, or None when missing, empty, or null
        """
        value = self.fields.get(key, "").strip()
        if not value or value.lower() == "null" or value == "~":
            return None
        return value

    @property
    def id(self) -> str:
        """Ticket id; falls back to the filename stem."""
        return self._raw("id") or self.path.stem

    @property
    def repo(self) -> str:
        """Repository name; falls back to the id minus its trailing -<digits>."""
        return self._raw("repo") or _ID_NUMBER_SUFFIX_RE.sub("", self.id)

    @property
    def title(self) -> str:
        """Card title; falls back to the id."""
        return self._raw("title") or self.id

    @property
    def branch(self) -> str | None:
        """Work branch, or None when missing/empty/null."""
        return self._raw("branch")

    @property
    def worktree(self) -> str | None:
        """Worktree path, or None when missing/empty/null."""
        return self._raw("worktree")

    @property
    def tool(self) -> str | None:
        """Coding tool (claude|codex|opencode), or None when missing/unknown."""
        value = self._raw("tool")
        if value is None:
            return None
        normalized = value.lower()
        return normalized if normalized in VALID_TOOLS else None

    @property
    def session_id(self) -> str | None:
        """Most recent coding-tool session id, or None when missing/empty/null."""
        return self._raw("session_id")

    @property
    def state(self) -> str:
        """Lifecycle state; defaults to 'todo' when missing or unrecognized."""
        value = self._raw("state")
        if value is None:
            return "todo"
        normalized = value.lower()
        return normalized if normalized in VALID_STATES else "todo"


def read_ticket(path: Path) -> Ticket:
    """Read a ticket file with lenient parsing (vibeboard-format.md §6).

    Tolerates missing or malformed frontmatter (the whole file becomes the
    body), CRLF line endings, '#' comment lines, quoted values, block
    scalars, empty values, and duplicate keys (last wins). Never fails on
    malformed content.

    Args:
        path: Path to the ticket markdown file

    Returns:
        Parsed Ticket

    Raises:
        OSError: If the file cannot be read at all
    """
    text = path.read_bytes().decode("utf-8", errors="replace")
    lines = text.split("\n")
    bounds = _frontmatter_bounds(lines)
    if bounds is None:
        return Ticket(path=path, fields={}, body=text)

    _, close_index = bounds
    fields: dict[str, str] = {}
    i = 1
    while i < close_index:
        parsed = _parse_key_value(lines[i])
        if parsed is None:
            i += 1
            continue
        key, value = parsed
        if _is_block_scalar_marker(value):
            block_end = _block_continuation_end(lines, i + 1, close_index)
            block = [_strip_line_ending(line) for line in lines[i + 1 : block_end]]
            fields[key] = textwrap.dedent("\n".join(block)).strip()
            i = block_end
            continue
        fields[key] = _unquote(value)
        i += 1

    body = "\n".join(lines[close_index + 1 :])
    return Ticket(path=path, fields=fields, body=body)


def list_tickets(store_dir: Path = VIBEBOARD_DIR) -> list[Ticket]:
    """List all tickets in the store, skipping anything that isn't a ticket.

    Directories, hidden files, and files not matching the '<repo>-<n>.md'
    naming rule (e.g. a README.md) are ignored (vibeboard-format.md §1); a
    file that fails to read never raises (it is skipped).

    Args:
        store_dir: Ticket store directory

    Returns:
        Tickets sorted by filename (empty list when the store doesn't exist)
    """
    if not store_dir.is_dir():
        return []

    tickets: list[Ticket] = []
    for entry in sorted(store_dir.iterdir()):
        if not _is_ticket_filename(entry.name) or not entry.is_file():
            continue
        try:
            tickets.append(read_ticket(entry))
        except Exception:  # never raise on a malformed/unreadable file
            continue
    return tickets


def find_ticket(ticket_id: str, store_dir: Path = VIBEBOARD_DIR) -> Ticket | None:
    """Find a ticket by id.

    Primary lookup is the conventional filename <id>.md in the store root
    (only when the id satisfies the ticket naming rule, vibeboard-format.md
    §1/§2); falls back to scanning every ticket's resolved id.

    Args:
        ticket_id: Ticket id to look up (e.g. 'vibe-12')
        store_dir: Ticket store directory

    Returns:
        The matching Ticket, or None when not found
    """
    if is_safe_ticket_id(ticket_id) and _is_ticket_filename(f"{ticket_id}.md"):
        candidate = store_dir / f"{ticket_id}.md"
        if candidate.is_file():
            try:
                return read_ticket(candidate)
            except OSError:
                pass

    for ticket in list_tickets(store_dir):
        if ticket.id == ticket_id:
            return ticket
    return None


def archive_resumed_ticket(ticket: Ticket) -> Path | None:
    """Soft-delete a resumed ticket by moving it into the `.resumed/` archive.

    The move is atomic (same-volume rename). The board stops showing the
    ticket (it lives in a hidden subdirectory), but `find_resumed_ticket` can
    recover it so re-resuming after an accidental close still works.

    Args:
        ticket: The ticket being resumed (must be file-backed)

    Returns:
        The new path inside `.resumed/`, or None on failure
    """
    archive_dir = ticket.path.parent / RESUMED_SUBDIR
    try:
        archive_dir.mkdir(parents=True, exist_ok=True)
        dest = archive_dir / ticket.path.name
        os.replace(ticket.path, dest)
        return dest
    except OSError as e:
        console.print(
            f"[yellow]Warning:[/] could not archive ticket {ticket.path}: {e}"
        )
        return None


def find_resumed_ticket(
    ticket_id: str, store_dir: Path = VIBEBOARD_DIR
) -> Ticket | None:
    """Find a soft-deleted ticket in the `.resumed/` archive by id.

    Args:
        ticket_id: Ticket id to look up
        store_dir: Ticket store directory

    Returns:
        The archived Ticket, or None when not found
    """
    if not is_safe_ticket_id(ticket_id) or not _is_ticket_filename(f"{ticket_id}.md"):
        return None
    candidate = store_dir / RESUMED_SUBDIR / f"{ticket_id}.md"
    if candidate.is_file():
        try:
            return read_ticket(candidate)
        except OSError:
            return None
    return None


def list_resumed_tickets(store_dir: Path = VIBEBOARD_DIR) -> list[Ticket]:
    """List the soft-deleted tickets in the `.resumed/` archive.

    Args:
        store_dir: Ticket store directory

    Returns:
        Parsed archived tickets; unreadable entries are skipped.
    """
    archive_dir = store_dir / RESUMED_SUBDIR
    if not archive_dir.is_dir():
        return []
    tickets: list[Ticket] = []
    for entry in sorted(archive_dir.iterdir()):
        if not entry.is_file() or entry.name.startswith(".") or entry.suffix != ".md":
            continue
        try:
            tickets.append(read_ticket(entry))
        except OSError:
            continue
    return tickets


def find_ticket_by_repo_branch(
    repo: str,
    branch: str,
    store_dir: Path = VIBEBOARD_DIR,
) -> Ticket | None:
    """Find the ticket attached to a repo + branch pair.

    Matches on the resolved repo and branch properties. When several tickets
    match, prefers one whose state is not 'archived', then the most recently
    updated one.

    Args:
        repo: Repository name (as resolved against the repo base)
        branch: Work branch name (real name, with slashes)
        store_dir: Ticket store directory

    Returns:
        The best matching Ticket, or None when no ticket matches
    """
    matches = [
        ticket
        for ticket in list_tickets(store_dir)
        if ticket.repo == repo and ticket.branch == branch
    ]
    if not matches:
        return None

    matches.sort(
        key=lambda t: (t.state != "archived", t.fields.get("updated", "")),
        reverse=True,
    )
    return matches[0]


def _format_value(value: str | None) -> str:
    """Format a scalar value for a frontmatter line (vibeboard-format.md §5.1).

    Args:
        value: Value to write; None becomes the literal 'null'

    Returns:
        The scalar as written on a 'key: value' line, double-quoted only when
        the value would otherwise be ambiguous YAML
    """
    if value is None:
        return "null"
    if value == "":
        return '""'
    needs_quoting = (
        ": " in value
        or value.endswith(":")
        or value[0] in _YAML_SPECIAL_LEAD
        or value.startswith("- ")
        or value == "-"
        or value != value.strip()
    )
    if needs_quoting:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def update_ticket_fields(path: Path, updates: dict[str, str | None]) -> bool:
    """Update frontmatter fields in a ticket file, preserving everything else.

    Line-level read-modify-write per vibeboard-format.md §5.2/§5.3: only the
    lines for the given keys change; unknown keys, comments, ordering, and
    the entire body round-trip byte-identical. Replacing a block-scalar value
    also removes its indented continuation lines; missing keys are inserted
    before the closing '---'; a file without frontmatter gets a new block
    prepended. 'updated' is always refreshed to now. The write is atomic
    (temp file in the same directory + os.replace).

    Args:
        path: Path to the ticket file
        updates: Field values to set; None writes the literal 'null'

    Returns:
        True on success, False on IO errors (a warning is printed)
    """
    try:
        raw = path.read_bytes().decode("utf-8", errors="surrogateescape")
    except OSError as error:
        console.print(f"[yellow]Warning: could not read ticket {path}: {error}[/yellow]")
        return False

    effective: dict[str, str | None] = dict(updates)
    effective["updated"] = now_iso()

    lines = raw.splitlines(keepends=True)
    bounds = _frontmatter_bounds(lines)

    if bounds is None:
        # No (well-formed) frontmatter: prepend a new block, body untouched
        newline = "\n"
        block = ["---" + newline]
        for key, value in effective.items():
            block.append(f"{key}: {_format_value(value)}{newline}")
        block.append("---" + newline)
        new_text = "".join(block) + raw
    else:
        open_index, close_index = bounds
        newline = _line_ending(lines[open_index])
        remaining = dict(effective)
        new_lines: list[str] = [lines[open_index]]
        i = open_index + 1
        while i < close_index:
            line = lines[i]
            parsed = _parse_key_value(line)
            if parsed is None or parsed[0] not in effective:
                new_lines.append(line)
                i += 1
                continue
            key, value = parsed
            new_lines.append(f"{key}: {_format_value(effective[key])}{newline}")
            remaining.pop(key, None)
            if _is_block_scalar_marker(value):
                # Drop the replaced block scalar's continuation lines
                i = _block_continuation_end(lines, i + 1, close_index)
            else:
                i += 1
        for key, value in remaining.items():
            new_lines.append(f"{key}: {_format_value(value)}{newline}")
        new_lines.append(lines[close_index])
        new_lines.extend(lines[close_index + 1 :])
        new_text = "".join(new_lines)

    try:
        fd, tmp_name = tempfile.mkstemp(
            dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(new_text.encode("utf-8", errors="surrogateescape"))
            os.replace(tmp_name, path)
        except OSError:
            with contextlib.suppress(OSError):
                os.unlink(tmp_name)
            raise
    except OSError as error:
        console.print(f"[yellow]Warning: could not update ticket {path}: {error}[/yellow]")
        return False
    return True
