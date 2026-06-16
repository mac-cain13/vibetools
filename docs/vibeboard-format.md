# Vibe Board — Ticket Store Format Spec

This is the **contract** between the three independent implementers of the ticket
store: the **`park` Claude Code skill**, the **native Mac app**, and **Python
`vibe`**. There is no shared library; each side implements this spec with
**lenient reads** and **field-preserving writes**.

This document is the single normative reference for everything that touches the
store on disk: locations, naming, frontmatter, body conventions, and the
concurrency rules all writers must follow.

**Scope — one state, "parked".** The store holds exactly one kind of thing: work
that is **parked (on hold)**. A ticket file exists *if and only if* a piece of
work is parked. Park creates the ticket; resume **deletes** it (the work is now
active and lives in tmux + git, not in the store). There is no todo / doing /
ready / archived lifecycle — those workflows are handled by other tools. See §10.

---

## 1. Store location

```
<repo-base>/_vibeboard/
```

- On the Mac/tart setup (v1 scope), `<repo-base>` is `/Volumes/External/Repositories`,
  so the store is **`/Volumes/External/Repositories/_vibeboard`**.
- The VM reaches the same absolute path through the path-aligned symlink
  (`/Volumes/External/Repositories -> /Volumes/Repositories` on the VM), so every
  writer — including the agent on the VM — lands on the Mac's local filesystem.
- The store is a **flat directory** of ticket files. Readers must ignore anything
  that is not a `*.md` file matching the ticket naming rule (e.g. `.DS_Store`,
  temp files, a `README`), and must not descend into subdirectories.
- **`.resumed/`** is a reserved hidden subdirectory holding soft-deleted
  (resumed) tickets — see §10. Readers of the board ignore it; only `vibe`
  reads/prunes it.
- Writers create the directory on first use (`mkdir -p` semantics).

## 2. Ticket ids and file naming

- Ticket id: **`<repo-name>-<number>`**, e.g. `vibe-12`, `bezel-3`.
  `<repo-name>` is the repository directory name under `<repo-base>`; `<number>`
  is a positive integer with no padding.
- File name: **`<id>.md`** directly in the store root, e.g. `_vibeboard/vibe-12.md`.
- **Allocation:** next number = 1 + the highest `<number>` among existing files
  matching `^<repo-name>-(\d+)\.md$` (0 if none).
- **Exclusive create (hard requirement):** new ticket files must be created with
  `O_EXCL` semantics (Python `open(path, "x")`, Swift
  `Data.write(.withoutOverwriting)`, shell `set -o noclobber` + redirect). On
  collision, re-scan, increment, retry. Never create a new ticket via
  temp+rename (rename replaces and can silently clobber a concurrent create).
- Recovering the repo name from an id: prefer the `repo` frontmatter field; fall
  back to stripping the trailing `-<digits>` from the id.

## 3. Document structure

A ticket is UTF-8 Markdown with YAML-style frontmatter:

```markdown
---
id: vibe-12
title: Retry logic for upload client
state: on_hold
...
---

Freeform body.

## Braindump

Auth on the v2 API is flaky — maybe just pin v1 and move on.

## Next step

Wire the backoff cap into the retry loop, then rerun the upload tests.
```

- Frontmatter is delimited by a `---` line as the **first line** of the file and
  a closing `---` line. The closing delimiter must start at **column zero**
  (trailing whitespace is tolerated, §6); an indented `---` — e.g. a Markdown
  horizontal rule inside a `description: |` block scalar — is content, never a
  delimiter.
- The body is everything after the closing delimiter: freeform Markdown.

## 4. Frontmatter fields

**Every field is optional on read.** Writers should write the fields they know;
readers must never fail on a missing or unknown field.

| Field        | Type / values                          | Meaning, and who writes it |
|--------------|----------------------------------------|----------------------------|
| `id`         | string, `<repo>-<n>`                   | Ticket id; mirrors the filename. Written at creation (skill or app). |
| `title`      | string                                 | Short card title. Creation; editable in the app. |
| `description`| string (single line or `\|` block)     | Short card blurb. If absent, readers fall back to the body's first paragraph. |
| `repo`       | string                                 | Repository **name**, resolved against `<repo-base>`. Prefixes the id; groups tickets. |
| `base_branch`| string                                 | Branch the work is based on (usually `main`). |
| `branch`     | string                                 | The parked work branch (the agent names it at park time). Always set on a parked ticket. |
| `worktree`   | string (absolute path) or `null`       | Set by park when the work lives in a worktree; cleared (set `null`) by vibe when the worktree is removed after the parked session exits. Informational — resume reconstructs the path from `branch`. |
| `tool`       | `claude` \| `codex` \| `opencode`      | Coding tool to relaunch on resume. Non-Claude tools relaunch fresh (no session restore, no bootstrap prompt). |
| `session_id` | string                                 | Most recent coding-tool session id, **best-effort** (refreshed at park). Resume must degrade gracefully if stale. |
| `state`      | `on_hold`                              | Always `on_hold` — a ticket exists only while parked (§10). Kept as a self-documenting marker. |
| `created`    | ISO 8601 UTC, e.g. `2026-06-10T14:30:00Z` | Set once at creation. |
| `updated`    | ISO 8601 UTC                           | Refreshed by any writer that modifies the ticket. |

**Retired fields.** `priority` was removed. No writer produces it anymore, but
readers must still tolerate it on legacy tickets and **preserve it on write**
like any other unknown key (§5.2) — never strip it.

## 5. Writer rules

1. **Format written:** one `key: value` per line; flat scalars only, except
   `description` which may be a `|` block scalar with two-space indentation.
   Null is written as the literal `null`. No quoting unless the value contains
   `: ` or starts with a YAML-special character — then double-quote, escaping
   backslash as `\\` and double quote as `\"` inside the quotes.
2. **Field-preserving read-modify-write (hard requirement):** to update a
   ticket, read the whole file, change **only the lines for the keys you mean
   to change**, and write everything else back **byte-identical** — unknown
   keys, comments, ordering, and the entire body included. Practically this
   means line-level editing of the frontmatter block, not parse-to-object →
   serialize.
   - Replacing a key whose existing value is a block scalar must also remove
     the block's indented continuation lines.
   - Setting a key the file lacks inserts a new line **before the closing
     `---`**.
3. **Atomic update:** write to a temp file in the same directory, then rename
   over the original (`os.replace` / `FileManager.replaceItem` /
   `mv` on the same volume). Last-write-wins on a same-ticket collision is
   accepted for *updates* (not creation — §2).
4. **Timestamps:** UTC, second precision, `YYYY-MM-DDTHH:MM:SSZ`. Refresh
   `updated` on every write.
5. **Never delete or rewrite body content you don't own.** The park ritual owns
   the `## Braindump` and `## Next step` sections (§7); everything else in the
   body is appended to or left alone.

## 6. Reader rules (lenient parsing — hard requirement)

- Unknown frontmatter keys: ignore (but preserve on write, §5.2).
- Missing keys: apply defaults — `state` → `on_hold` (the only state),
  `branch`/`worktree`/`session_id` → absent,
  `description` → first paragraph of the body, `title` → the id, `id` → the
  filename stem, `repo` → id minus trailing `-<digits>`.
- Unrecognized **values** of `tool`: treat as absent; never crash, never
  refuse to show the ticket. (Any `state` value is treated as `on_hold`.)
- Malformed frontmatter (no opening `---`, no closing `---`): treat the entire
  file as body; derive `id` from the filename. The ticket still appears.
- Tolerate: CRLF line endings, trailing whitespace, `#` comment lines inside
  frontmatter, quoted scalar values (strip one layer of matching quotes,
  resolving `\"` → `"` and `\\` → `\` inside double quotes and `''` → `'`
  inside single quotes — the inverse of the §5.1 writer escaping),
  empty values (treat as absent / null).
- Values read from tickets that end up in **shell commands** (ids, session ids,
  branches) must be validated against a conservative charset first
  (`[A-Za-z0-9._/-]` for ids/branches, `[A-Za-z0-9-]` for session ids) or
  shell-quoted; tickets are hand-editable files.

## 7. Body conventions

- The body is freeform Markdown: background, notes, links, and the human's
  comments on the parked work.
Park owns **two** section headings. For each, park creates the section if
missing and replaces its content if present, leaving the rest of the body alone.
When both are present, `## Braindump` precedes `## Next step`.

- **`## Braindump`** — the human's own words, captured by park from what the
  user said when invoking it: what this work is and what they think should
  happen on resume. **Optional** — park writes it only when the user gave a
  braindump, and omits the section entirely otherwise (parking without a
  braindump is normal). It holds the human's voice, never the agent's analysis.
- **`## Next step`** — the agent's dump: the context the next session needs and
  what to do next, plus any loud warnings (e.g. "local `main` carries N commits
  belonging to this ticket"). Resume's bootstrap prompt points the agent at this
  section.

Readers match these headings case-insensitively and treat the section as
running from its heading to the next `## ` heading (or end of body). The Mac app
surfaces `## Braindump` and `## Next step` as distinct, labeled blocks and shows
the freeform remainder (the human's general comments) separately.

## 8. Park marker and unwind

- Park commit message (subject line), exactly: **`wip: park <id>`**, e.g.
  `wip: park vibe-12`.
- **Unwind rule:** resume may unwind **only** when the worktree's tip commit
  subject equals `wip: park <id>` for *this* ticket (compare after trimming
  whitespace). Unwind = **mixed `git reset HEAD~1`**, restoring park-time
  working-tree state (tracked changes unstaged, untracked files back).
- An empty park (no code changes) either skips the commit or uses
  `--allow-empty` with the same message; unwinding an empty park commit is a
  no-op on the tree and is fine.
- **Bootstrap prompt** (fixed text, used by `vibe resume` when seeding a fresh
  Claude session): `Read parked ticket <id> via the park skill and continue
  from its next step.` — no apostrophes, no freeform text, safe through quoting.
  (The ticket is in `.resumed/` at that point — resume archived it; the park
  skill knows to look there.)

## 9. Branch ↔ worktree directory mapping

Worktrees live at `<repo-base>/_vibecoding/<repo>/<dirname>`. Branch names may
contain `/`; directory names must not. The mapping is **deterministic and
reversible in both directions**:

- **Encode** (branch → dirname): replace `%` with `%25`, then `/` with `%2F`.
- **Decode** (dirname → branch): replace `%2F` with `/`, then `%25` with `%`.

Examples: `feature/retry-upload` ⇄ `feature%2Fretry-upload`;
`fix/50%-faster` ⇄ `fix%2F50%25-faster`; `main` ⇄ `main`.

All tooling that builds or parses worktree paths must go through this mapping.
The ticket's `branch` field stores the **real branch name** (with slashes).

## 10. Lifecycle

A ticket exists only while its work is parked. Two actions move it:

```
park   (skill)  -> ticket created on_hold        (find-or-create by repo + branch)
resume (vibe)   -> ticket soft-deleted -> .resumed/  (work is now active)
```

- **Park** (the Claude skill) writes the park commit and creates the ticket.
  If an `on_hold` ticket already exists for the same `repo` + `branch` (a
  re-park within a session), park **updates that ticket** instead of creating a
  duplicate — match on `repo` + `branch`, else create with a fresh id (§2).
- **Resume** (`vibe resume <id>`) recreates/reuses the worktree, unwinds the
  park commit (§8), launches the tool, and **soft-deletes the ticket** by moving
  it to `.resumed/<id>.md`. It leaves the board, but the work is recoverable:
  - `vibe resume <id>` with no live ticket **falls back to `.resumed/`** and
    reconnects (recreate/reuse the worktree, relaunch). This makes resume
    idempotent again — a session closed right after resuming can be picked up
    by id, rather than losing the ticket.
  - An archived ticket is **pruned once its worktree no longer exists** (the
    work was finished and the worktree cleaned). `vibe` prunes on each resume
    and during `vibe --clean`.
  - **Re-park reuses the ticket.** When park finds an archived ticket for the
    same `repo` + `branch` in `.resumed/`, it **moves it back to the store root**
    and updates it — preserving the id and body across park → resume → re-park,
    rather than minting a new id. (Park checks the store root first, then
    `.resumed/`, then creates.)
- The Mac app never changes the lifecycle: it reads parked tickets and edits
  their body (comments). Git/tmux facts may be shown as context, never as state.

## 11. Concurrency summary

- Per-ticket files; concurrent writers almost always touch different tickets.
- Updates: atomic temp+rename; same-ticket collisions are last-write-wins.
- Creation: `O_EXCL` only (§2).
- No locks, no daemons; the CLI and skill read fresh on every invocation; the
  Mac app watches the store directory with FSEvents.
