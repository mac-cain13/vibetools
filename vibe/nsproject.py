"""NSProject board — the sole backend for parked work.

`vibe resume` reads parked work from the NSProject board (the `park` skill
writes it). A parked snapshot lives in a ticket's `work[]` list entry plus its
`## Where I left off` body section; see docs/nsproject-park.md for the normative
contract.

This module implements the read side `vibe` needs (board discovery, locating a
ticket by id, parsing its `work[]` entries, resolving the canonical repo URL to
a local checkout) and the one write `vibe` performs on resume (clearing
`parked_at` and stamping `updated`, then committing+pushing the board). All
reads are lenient; the write is line-level and field-preserving.

`vibe` never pushes a product work branch and never creates tickets — those are
the `park` skill's job.
"""

from __future__ import annotations

import contextlib
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from vibe.config import LOCAL_REPO_BASE
from vibe.utils import console

# Coding tools resume understands (docs/nsproject-park.md §2). Unknown values
# fall back to "launch fresh" rather than failing.
VALID_TOOLS = frozenset({"claude", "codex", "opencode"})

# A valid board root contains both of these (docs/nsproject-park.md §1).
_BOARD_MARKER_FILE = "CLAUDE.md"
_BOARD_MARKER_DIR = Path("data") / "maybe"

# Environment overrides.
ENV_BOARD = "NSPROJECT_BOARD"  # direct path to the board root
ENV_PERSON = "VIBE_PERSON"  # the local person handle for work[].by

# Conservative charsets for values that reach shell commands / prompts
# (docs/nsproject-park.md §2) — tickets are hand-editable files.
_SAFE_TICKET_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_SAFE_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9-]+$")

# Frontmatter delimiter.
_DELIM = "---"


def now_iso() -> str:
    """Get the current UTC time in the park timestamp format.

    Returns:
        Timestamp like '2026-06-16T14:30:00Z' (second precision, UTC).
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today_iso() -> str:
    """Get today's date in the NSProject `updated` format.

    Returns:
        Bare date like '2026-06-16' (UTC).
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def is_safe_ticket_id(value: str) -> bool:
    """Check whether a ticket id is safe to embed in shell commands/prompts.

    Args:
        value: Candidate ticket id (e.g. 'BZL_q7m2x').

    Returns:
        True if the value matches the conservative ^[A-Za-z0-9._-]+$ charset.
    """
    return bool(_SAFE_TICKET_ID_RE.match(value))


def is_safe_session_id(value: str) -> bool:
    """Check whether a session id is safe to embed in shell commands.

    Args:
        value: Candidate session id.

    Returns:
        True if the value matches the conservative ^[A-Za-z0-9-]+$ charset.
    """
    return bool(_SAFE_SESSION_ID_RE.match(value))


# ---------------------------------------------------------------------------
# Board discovery
# ---------------------------------------------------------------------------


def _is_board(path: Path) -> bool:
    """Check whether a directory looks like an NSProject board root.

    Args:
        path: Candidate board root.

    Returns:
        True when it contains both CLAUDE.md and data/maybe/.
    """
    return (path / _BOARD_MARKER_FILE).is_file() and (
        path / _BOARD_MARKER_DIR
    ).is_dir()


def find_board(repo_base: Path | None = None) -> Path | None:
    """Locate the NSProject board root (docs/nsproject-park.md §1).

    Resolution order: the NSPROJECT_BOARD env var, then the repo base and its
    resolved target (the base may be a symlink, e.g.
    /Volumes/External/Repositories -> /Volumes/Repositories) — each base itself
    and then its immediate children — returning the first valid board. Never
    guesses a path and never clones.

    Args:
        repo_base: Primary base directory to search under (defaults to the
            configured LOCAL_REPO_BASE, read at call time for testability).

    Returns:
        The board root, or None when no valid board is found.
    """
    if repo_base is None:
        repo_base = LOCAL_REPO_BASE
    env = os.environ.get(ENV_BOARD)
    if env:
        candidate = Path(env).expanduser()
        if _is_board(candidate):
            return candidate

    seen: set[Path] = set()
    bases = [repo_base, repo_base.resolve()]
    for base in bases:
        try:
            base = base.resolve()
        except OSError:
            continue
        if base in seen or not base.is_dir():
            continue
        seen.add(base)

        if _is_board(base):
            return base
        try:
            children = sorted(p for p in base.iterdir() if p.is_dir())
        except OSError:
            continue
        for child in children:
            if _is_board(child):
                return child
    return None


def data_dir(board: Path) -> Path:
    """Get the board's content submodule directory.

    Args:
        board: Board root.

    Returns:
        The `data/` directory holding ticket state folders.
    """
    return board / "data"


# ---------------------------------------------------------------------------
# Person handle
# ---------------------------------------------------------------------------


def local_person(cwd: Path | None = None) -> str | None:
    """Resolve the local person handle for matching work[].by.

    Order (docs/nsproject-park.md §5): VIBE_PERSON, then a normalized
    git user.name, then the local-part of git user.email.

    Args:
        cwd: Directory to read git config from (defaults to current).

    Returns:
        A short lowercase handle, or None when none can be resolved.
    """
    env = os.environ.get(ENV_PERSON)
    if env and env.strip():
        return env.strip().lower()

    name = _git_config("user.name", cwd)
    if name:
        token = name.strip().split()[0] if name.strip().split() else ""
        if token:
            return token.lower()

    email = _git_config("user.email", cwd)
    if email and "@" in email:
        return email.split("@", 1)[0].strip().lower()
    return None


def _git_config(key: str, cwd: Path | None) -> str | None:
    """Read a git config value, returning None when unset.

    Args:
        key: Config key (e.g. 'user.name').
        cwd: Directory to read config from.

    Returns:
        The trimmed value, or None.
    """
    result = subprocess.run(
        ["git", "config", "--get", key],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


# ---------------------------------------------------------------------------
# Lenient frontmatter + work[] parsing
# ---------------------------------------------------------------------------


def _unquote(value: str) -> str:
    """Strip one matching layer of surrounding quotes from a scalar.

    Args:
        value: Stripped scalar value.

    Returns:
        The value with one matching quote layer removed (escapes resolved),
        or the input unchanged when it is not quoted.
    """
    if len(value) < 2 or value[0] != value[-1] or value[0] not in "\"'":
        return value
    inner = value[1:-1]
    if value[0] == '"':
        return inner.replace('\\"', '"').replace("\\\\", "\\")
    return inner.replace("''", "'")


def _scalar(value: str) -> str | None:
    """Normalize a frontmatter scalar value, treating empty/null as absent.

    Args:
        value: Raw value after the key's colon.

    Returns:
        The unquoted value, or None when empty, 'null', or '~'.
    """
    value = _unquote(value.strip())
    if not value or value.lower() == "null" or value == "~":
        return None
    return value


@dataclass
class WorkEntry:
    """One parsed `work[]` list entry, with line spans for editing.

    Attributes:
        fields: Child key -> value (lenient, one quote layer stripped).
        start: Line index of the entry's '- ' marker line.
        end: Exclusive line index where the entry ends.
        field_lines: Child key -> the line index it was read from.
    """

    fields: dict[str, str] = field(default_factory=dict)
    start: int = 0
    end: int = 0
    field_lines: dict[str, int] = field(default_factory=dict)

    def get(self, key: str) -> str | None:
        """Get a normalized child value (empty/null treated as absent)."""
        return _scalar(self.fields.get(key, ""))


@dataclass
class ParsedTicket:
    """A leniently parsed NSProject ticket.

    Attributes:
        path: File the ticket was read from.
        lines: The file's lines, terminators stripped.
        newline: The line terminator to write back ('\\n' or '\\r\\n').
        top: Top-level frontmatter key -> (line index, value).
        close_index: Line index of the closing '---', or None when malformed.
        work: Parsed work[] entries in file order.
    """

    path: Path
    lines: list[str]
    newline: str
    top: dict[str, tuple[int, str]]
    close_index: int | None
    work: list[WorkEntry]

    @property
    def id(self) -> str:
        """Ticket id; falls back to the filename stem."""
        if "id" in self.top:
            value = _scalar(self.top["id"][1])
            if value:
                return value
        return self.path.stem

    @property
    def title(self) -> str:
        """Card title; falls back to the id."""
        if "title" in self.top:
            value = _scalar(self.top["title"][1])
            if value:
                return value
        return self.id


def _split_keyvalue(stripped: str) -> tuple[str, str] | None:
    """Split a 'key: value' fragment, tolerating a leading '- '.

    Args:
        stripped: A frontmatter line with leading whitespace removed.

    Returns:
        (key, value) or None when there is no usable key.
    """
    if stripped.startswith("- "):
        stripped = stripped[2:].lstrip()
    elif stripped == "-":
        return None
    if stripped.startswith("#") or ":" not in stripped:
        return None
    key, _, value = stripped.partition(":")
    key = key.strip()
    if not key:
        return None
    return key, value.strip()


def parse_ticket(path: Path) -> ParsedTicket | None:
    """Parse a ticket's frontmatter and work[] entries leniently.

    Tolerates CRLF, trailing whitespace, comments, quoted values, and missing
    keys; never raises on malformed content (returns None only when the file
    cannot be read or has no frontmatter).

    Args:
        path: Path to the ticket markdown file.

    Returns:
        A ParsedTicket, or None when the file is unreadable / has no
        well-formed frontmatter.
    """
    try:
        text = path.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return None

    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.replace("\r\n", "\n").split("\n")

    if not lines or lines[0].lstrip("﻿").strip() != _DELIM:
        return None
    close_index: int | None = None
    for i in range(1, len(lines)):
        if not lines[i].startswith((" ", "\t")) and lines[i].strip() == _DELIM:
            close_index = i
            break
    if close_index is None:
        return None

    top: dict[str, tuple[int, str]] = {}
    work: list[WorkEntry] = []
    i = 1
    while i < close_index:
        line = lines[i]
        if line.startswith((" ", "\t")) or not line.strip():
            i += 1
            continue
        parsed = _split_keyvalue(line.strip())
        if parsed is None:
            i += 1
            continue
        key, value = parsed
        if key == "work" and not _scalar(value):
            i = _parse_work_block(lines, i + 1, close_index, work)
            top.setdefault("work", (i, ""))
            continue
        top[key] = (i, value)
        i += 1

    return ParsedTicket(
        path=path,
        lines=lines,
        newline=newline,
        top=top,
        close_index=close_index,
        work=work,
    )


def _parse_work_block(
    lines: list[str], start: int, end: int, out: list[WorkEntry]
) -> int:
    """Parse the indented entries of a `work:` block list.

    Args:
        lines: Document lines (terminators stripped).
        start: First line index after the `work:` marker.
        end: Exclusive stop index (the closing '---').
        out: List to append parsed WorkEntry objects to.

    Returns:
        The line index just past the work block (first non-indented line).
    """
    i = start
    current: WorkEntry | None = None
    while i < end:
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if not line.startswith((" ", "\t")):
            break  # back to top level — work block done
        stripped = line.strip()
        is_marker = stripped.startswith("- ") or stripped == "-"
        if is_marker:
            if current is not None:
                current.end = i
                out.append(current)
            current = WorkEntry(start=i, end=i + 1)
        if current is not None:
            parsed = _split_keyvalue(stripped)
            if parsed is not None:
                key, value = parsed
                current.fields[key] = value
                current.field_lines[key] = i
            current.end = i + 1
        i += 1
    if current is not None:
        out.append(current)
    return i


# ---------------------------------------------------------------------------
# Repo URL -> local checkout
# ---------------------------------------------------------------------------


def _normalize_remote(url: str) -> str:
    """Normalize a git remote URL for comparison.

    Collapses scp-style 'git@host:path' to 'host/path', drops a trailing
    '.git', strips a scheme, and lowercases.

    Args:
        url: A git remote URL.

    Returns:
        A normalized comparison key.
    """
    u = url.strip().lower()
    if u.endswith(".git"):
        u = u[: -len(".git")]
    if u.startswith("git@"):
        u = u[len("git@"):].replace(":", "/", 1)
    for scheme in ("https://", "http://", "ssh://", "git://"):
        if u.startswith(scheme):
            u = u[len(scheme):]
            break
    if u.startswith("git@"):
        u = u[len("git@"):]
    return u.rstrip("/")


def _repo_basename(url: str) -> str:
    """Get the repository directory name implied by a remote URL.

    Case is preserved (the local checkout directory keeps the repo's real
    casing); only origin-URL *comparison* lowercases (see _normalize_remote).

    Args:
        url: A git remote URL.

    Returns:
        The last path segment with a trailing '.git' removed.
    """
    u = url.strip().rstrip("/")
    if u.endswith(".git"):
        u = u[: -len(".git")]
    # Last path segment, also splitting an scp-style 'host:org/repo' colon.
    return u.replace(":", "/").rstrip("/").rsplit("/", 1)[-1]


def resolve_local_repo(
    repo_url: str, repo_base: Path | None = None
) -> Path | None:
    """Resolve a canonical repo URL to a local checkout (docs §6).

    First tries `repo_base/<basename>`; otherwise scans the base for a repo
    whose origin URL matches the canonical URL.

    Args:
        repo_url: Canonical repo URL from a work[] entry.
        repo_base: Base directory holding local checkouts (defaults to the
            configured LOCAL_REPO_BASE, read at call time).

    Returns:
        The local checkout path, or None when it can't be resolved.
    """
    if repo_base is None:
        repo_base = LOCAL_REPO_BASE
    basename = _repo_basename(repo_url)
    if basename:
        candidate = repo_base / basename
        if candidate.is_dir():
            return candidate

    target = _normalize_remote(repo_url)
    if not repo_base.is_dir():
        return None
    for child in sorted(repo_base.iterdir()):
        if not child.is_dir():
            continue
        origin = _git_config_in(child, "remote.origin.url")
        if origin and _normalize_remote(origin) == target:
            return child
    return None


def _git_config_in(repo: Path, key: str) -> str | None:
    """Read a git config value scoped to a repo directory.

    Args:
        repo: Repository directory.
        key: Config key.

    Returns:
        The trimmed value, or None.
    """
    result = subprocess.run(
        ["git", "-C", str(repo), "config", "--get", key],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


# ---------------------------------------------------------------------------
# ParkedWork — what resume consumes
# ---------------------------------------------------------------------------


@dataclass
class ParkedWork:
    """A resolved parked-work snapshot resume can act on.

    Attributes:
        id: Ticket id (e.g. 'BZL_q7m2x').
        title: Ticket title (for listings).
        board: Board root.
        ticket_path: The ticket file on disk.
        repo_path: Local checkout of the work entry's canonical repo.
        repo_name: Local checkout directory name (worktree path component).
        branch: Work branch (real name, may contain '/').
        base_branch: Branch the work is based on, or None.
        tool: Coding tool to relaunch (claude|codex|opencode), or None.
        session_id: Best-effort coding-tool session id, or None.
        by: The work entry's person handle, or None.
        parked_at: The work entry's park marker timestamp, or None.
    """

    id: str
    title: str
    board: Path
    ticket_path: Path
    repo_path: Path
    repo_name: str
    branch: str | None
    base_branch: str | None
    tool: str | None
    session_id: str | None
    by: str | None
    parked_at: str | None


def _ticket_files(board: Path):
    """Yield ticket file paths across the active board state folders.

    Args:
        board: Board root.

    Yields:
        Paths to `*.md` ticket files (deepest scan of data/ state folders).
    """
    data = data_dir(board)
    if not data.is_dir():
        return
    for state in ("this-week", "up-next", "maybe", "not-now", "done", "archive"):
        folder = data / state
        if not folder.is_dir():
            continue
        for entry in sorted(folder.iterdir()):
            if entry.is_file() and entry.suffix == ".md":
                yield entry


def _grep_ticket(board: Path, ticket_id: str) -> Path | None:
    """Find the ticket file declaring `id: <ticket_id>` (docs §7).

    Args:
        board: Board root.
        ticket_id: Ticket id to find.

    Returns:
        The matching ticket file, or None.
    """
    if not is_safe_ticket_id(ticket_id):
        return None
    for path in _ticket_files(board):
        parsed = parse_ticket(path)
        if parsed is not None and parsed.id == ticket_id:
            return path
    return None


def _select_work_entry(
    parsed: ParsedTicket, handle: str | None
) -> WorkEntry | None:
    """Pick the work entry resume should act on (docs §5).

    Prefers the entry whose `by` matches the local handle; otherwise the entry
    with the most recent `parked_at`; otherwise the last entry. Entries with a
    `parked_at` always rank above those without.

    Args:
        parsed: The parsed ticket.
        handle: The local person handle, or None.

    Returns:
        The chosen WorkEntry, or None when the ticket has no work entries.
    """
    entries = [e for e in parsed.work if e.get("branch")]
    if not entries:
        return None

    def rank(entry: WorkEntry) -> tuple[int, int, str]:
        mine = 1 if handle and (entry.get("by") or "").lower() == handle else 0
        parked = entry.get("parked_at") or ""
        return (mine, 1 if parked else 0, parked)

    return max(entries, key=rank)


def find_parked_work(
    ticket_id: str,
    board: Path | None = None,
    repo_base: Path | None = None,
    cwd: Path | None = None,
) -> ParkedWork | None:
    """Find the parked-work snapshot for a ticket id.

    Locates the ticket on the board, picks the relevant work entry (§5),
    resolves its canonical repo URL to a local checkout (§6), and returns a
    ParkedWork. Returns None when the board, ticket, work entry, or local
    checkout can't be resolved (the caller reports the specific failure).

    Args:
        ticket_id: NSProject ticket id (e.g. 'BZL_q7m2x').
        board: Board root; discovered when None.
        repo_base: Base directory holding local checkouts (defaults to the
            configured LOCAL_REPO_BASE).
        cwd: Directory used to resolve the local person handle.

    Returns:
        A ParkedWork, or None.
    """
    if repo_base is None:
        repo_base = LOCAL_REPO_BASE
    if board is None:
        board = find_board(repo_base)
    if board is None:
        return None

    path = _grep_ticket(board, ticket_id)
    if path is None:
        return None
    parsed = parse_ticket(path)
    if parsed is None:
        return None

    entry = _select_work_entry(parsed, local_person(cwd))
    if entry is None:
        return None

    repo_url = entry.get("repo")
    repo_path = resolve_local_repo(repo_url, repo_base) if repo_url else None
    if repo_path is None:
        return None

    tool = entry.get("tool")
    if tool is not None:
        tool = tool.lower()
        if tool not in VALID_TOOLS:
            tool = None

    return ParkedWork(
        id=parsed.id,
        title=parsed.title,
        board=board,
        ticket_path=path,
        repo_path=repo_path,
        repo_name=repo_path.name,
        branch=entry.get("branch"),
        base_branch=entry.get("base_branch"),
        tool=tool,
        session_id=entry.get("session"),
        by=entry.get("by"),
        parked_at=entry.get("parked_at"),
    )


@dataclass
class ResumableTicket:
    """A board ticket that carries resumable work (for listings)."""

    id: str
    title: str
    parked: bool


def list_resumable(
    board: Path | None = None, repo_base: Path | None = None
) -> list[ResumableTicket]:
    """List tickets that carry at least one work entry with a branch.

    Used for `vibe resume` id completion and the "available tickets" listing.
    Tickets with a parked entry are marked `parked`.

    Args:
        board: Board root; discovered when None.
        repo_base: Base directory (only used for discovery).

    Returns:
        Resumable tickets in board order (empty when no board is found).
    """
    if board is None:
        board = find_board(repo_base)
    if board is None:
        return []

    out: list[ResumableTicket] = []
    for path in _ticket_files(board):
        parsed = parse_ticket(path)
        if parsed is None:
            continue
        entries = [e for e in parsed.work if e.get("branch")]
        if not entries:
            continue
        parked = any(e.get("parked_at") for e in entries)
        out.append(ResumableTicket(id=parsed.id, title=parsed.title, parked=parked))
    return out


# ---------------------------------------------------------------------------
# The one write resume performs: clear parked_at + stamp updated
# ---------------------------------------------------------------------------


def mark_resumed(work: ParkedWork, push: bool = True) -> bool:
    """Clear a work entry's `parked_at` and stamp `updated`, then sync.

    Line-level, field-preserving edit (docs §2): only the matched entry's
    `parked_at` line is removed and the top-level `updated` line is set; the
    rest of the ticket round-trips byte-for-byte. The write is atomic; the
    board commit+push is best-effort (a failure warns, never aborts resume).

    Args:
        work: The parked work being resumed.
        push: Whether to commit and push the board change.

    Returns:
        True when the file was edited successfully (regardless of push).
    """
    parsed = parse_ticket(work.ticket_path)
    if parsed is None:
        return False

    entry = _match_entry_by_branch(parsed, work.branch, work.by)
    drop: set[int] = set()
    if entry is not None and "parked_at" in entry.field_lines:
        drop.add(entry.field_lines["parked_at"])

    lines = [ln for idx, ln in enumerate(parsed.lines) if idx not in drop]

    # Stamp `updated` to today (insert before the closing '---' when absent).
    # Recompute the close index after any drop.
    if drop:
        parsed = _reparse(lines, work.ticket_path) or parsed
    _stamp_updated(parsed, lines)

    text = parsed.newline.join(lines)
    if not _atomic_write(work.ticket_path, text):
        return False

    if push:
        _sync_board(work.board, work.ticket_path, work.id)
    return True


def _match_entry_by_branch(
    parsed: ParsedTicket, branch: str | None, by: str | None
) -> WorkEntry | None:
    """Find the work entry for a branch (preferring a matching `by`).

    Args:
        parsed: The parsed ticket.
        branch: Branch to match.
        by: Person handle to prefer on ties.

    Returns:
        The matching WorkEntry, or None.
    """
    if branch is None:
        return None
    matches = [e for e in parsed.work if e.get("branch") == branch]
    if not matches:
        return None
    if by is not None:
        for entry in matches:
            if (entry.get("by") or "") == by:
                return entry
    return matches[0]


def _stamp_updated(parsed: ParsedTicket, lines: list[str]) -> None:
    """Set the top-level `updated` to today, in place.

    Args:
        parsed: The (re)parsed ticket describing `lines`.
        lines: The lines being edited (mutated in place).
    """
    today = today_iso()
    if "updated" in parsed.top:
        idx = parsed.top["updated"][0]
        if 0 <= idx < len(lines):
            lines[idx] = f"updated: {today}"
            return
    if parsed.close_index is not None and 0 <= parsed.close_index <= len(lines):
        lines.insert(parsed.close_index, f"updated: {today}")


def _reparse(lines: list[str], path: Path) -> ParsedTicket | None:
    """Re-parse in-memory lines into a ParsedTicket (for post-edit indices).

    Args:
        lines: Document lines (terminators stripped).
        path: The ticket path (carried through for identity).

    Returns:
        A ParsedTicket over the given lines, or None when malformed.
    """
    if not lines or lines[0].lstrip("﻿").strip() != _DELIM:
        return None
    close_index: int | None = None
    for i in range(1, len(lines)):
        if not lines[i].startswith((" ", "\t")) and lines[i].strip() == _DELIM:
            close_index = i
            break
    if close_index is None:
        return None
    top: dict[str, tuple[int, str]] = {}
    work: list[WorkEntry] = []
    i = 1
    while i < close_index:
        line = lines[i]
        if line.startswith((" ", "\t")) or not line.strip():
            i += 1
            continue
        parsed = _split_keyvalue(line.strip())
        if parsed is None:
            i += 1
            continue
        key, value = parsed
        if key == "work" and not _scalar(value):
            i = _parse_work_block(lines, i + 1, close_index, work)
            continue
        top[key] = (i, value)
        i += 1
    return ParsedTicket(
        path=path, lines=lines, newline="\n", top=top,
        close_index=close_index, work=work,
    )


def _atomic_write(path: Path, text: str) -> bool:
    """Write text to a file atomically (temp file + rename in the same dir).

    Args:
        path: Destination file.
        text: Full file contents.

    Returns:
        True on success, False on IO error (a warning is printed).
    """
    if not text.endswith("\n"):
        text += "\n"
    try:
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(text.encode("utf-8", errors="surrogateescape"))
            os.replace(tmp, path)
        except OSError:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise
    except OSError as error:
        console.print(f"[yellow]Warning:[/] could not update ticket {path}: {error}")
        return False
    return True


def _git(data: Path, *args: str) -> bool:
    """Run a git command in the data/ repo, returning success.

    Args:
        data: The board's data/ directory.
        *args: Git arguments after 'git -C <data>'.

    Returns:
        True when git exits zero.
    """
    result = subprocess.run(
        ["git", "-C", str(data), *args],
        capture_output=True,
    )
    return result.returncode == 0


def _sync_board(board: Path, ticket_path: Path, ticket_id: str) -> None:
    """Commit the ticket change in data/ and push (best-effort).

    A push rejection is retried once after `pull --rebase`. Any failure warns
    but never raises — the local resume still succeeds (docs §1/§7).

    Args:
        board: Board root.
        ticket_path: The edited ticket file.
        ticket_id: Ticket id (for the commit message).
    """
    data = data_dir(board)
    try:
        rel = ticket_path.relative_to(data)
    except ValueError:
        rel = ticket_path

    if not _git(data, "add", str(rel)):
        console.print("[yellow]Warning:[/] could not stage the board change.")
        return
    # Nothing to commit (e.g. parked_at already clear) is fine.
    if not _git(data, "diff", "--cached", "--quiet"):
        if not _git(data, "commit", "-m", f"Update {ticket_id}: resume"):
            console.print("[yellow]Warning:[/] could not commit the board change.")
            return
    if not _git(data, "push"):
        _git(data, "pull", "--rebase")
        if not _git(data, "push"):
            console.print(
                "[yellow]Warning:[/] could not push the board; the resume is "
                "recorded locally — push the board's data/ repo when you can."
            )
