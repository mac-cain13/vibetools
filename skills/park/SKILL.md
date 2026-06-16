---
name: park
description: Parks the current work onto the Vibe Board — the durable registry of parked (on-hold) work. Use when the user says "park", "park this", "wrap this up for now", "wrap up for now", "set this aside", or otherwise asks to stop work on something for now but keep it resumable. Writes the park commit, captures a next-step note, and records the ticket as on hold.
---

# Vibe Board — the park interface

You are the in-session writer for the Vibe Board ticket store. Your one job is
**park**: capture the current piece of work so it can be picked up later with
`vibe resume <id>`. This file embeds the full on-disk contract — there is no
external spec or library. Read tickets leniently, write them precisely.

**One state.** The store holds exactly one kind of thing: **parked** work. A
ticket exists *only while its work is on hold*. Park creates the ticket; `vibe
resume` deletes it when the work is picked back up. There are no todo / doing /
ready / archived states — those workflows live in other tools.

## The store

- Location: `/Volumes/External/Repositories/_vibeboard` — a **flat directory**
  of ticket files, one per ticket, named `<id>.md`. Use this exact absolute
  path (it resolves on both the Mac and the VM via the path-aligned symlink).
- Create the directory if missing: `mkdir -p /Volumes/External/Repositories/_vibeboard`.
- Ignore anything that is not a `*.md` file matching `<repo>-<number>.md`
  (e.g. `.DS_Store`, temp files, a `README`).

## Ticket format (embedded contract)

A ticket is UTF-8 Markdown with YAML-style frontmatter: a `---` line as the
very first line, `key: value` lines, a closing `---` line, then a freeform
Markdown body.

```markdown
---
id: vibe-12
title: Retry logic for upload client
description: Add bounded retry with backoff to the upload client.
repo: vibe
base_branch: main
branch: feature/retry-upload
worktree: null
tool: claude
session_id: 736380d6-2a01-4cd5-bb01-5563347dca56
state: on_hold
created: 2026-06-10T14:30:00Z
updated: 2026-06-10T14:30:00Z
---

Freeform body (background, the human's comments).

## Braindump

What the human told you to keep in mind for next time, in their words —
omitted entirely when they parked without one.

## Next step

Wire the backoff cap into the retry loop, then rerun the upload tests.
```

Field reference (every field is **optional on read**):

| Field | Values | Notes |
|---|---|---|
| `id` | `<repo-name>-<number>` | Mirrors the filename. |
| `title` | string | Short card title. |
| `description` | string, or `\|` block (two-space indented continuation) | Short blurb. |
| `repo` | string | Repository **name** (directory name under the repo base). |
| `base_branch` | string | Usually `main`. |
| `branch` | string | The parked branch — always set (you name it at park time). |
| `worktree` | absolute path or `null` | The worktree the work lives in, when it has one. `vibe` clears it after cleanup. |
| `tool` | `claude` \| `codex` \| `opencode` | Tool to relaunch on resume. |
| `session_id` | string | Best-effort; refreshed at park. |
| `state` | `on_hold` | Always `on_hold` (a ticket exists only while parked). |
| `created` / `updated` | ISO 8601 UTC, `YYYY-MM-DDTHH:MM:SSZ` | Get with `date -u +%Y-%m-%dT%H:%M:%SZ`. |

`priority` is a **retired** field: don't write it, but if a legacy ticket has
it, preserve it on write like any other unknown key.

Body conventions:

- The body is freeform Markdown: background, notes, and the human's comments
  (added later in the Mac app).
- The park ritual owns **two** sections; it creates each if missing or replaces
  its content if present, and leaves the rest of the body alone:
  - **`## Braindump`** — the human's own words about what this is and what they
    think should happen next, captured from what they said when invoking park.
    Write it **only when the human gave a braindump**; when they parked without
    one, omit the section entirely (and on a re-park with no new braindump,
    leave any existing `## Braindump` untouched — never invent or paraphrase it).
  - **`## Next step`** — your dump: the context the next session needs and what
    to do next (plus any loud warnings). This is yours, not the human's.
  - When both are present, `## Braindump` comes first, then `## Next step`.
- Park commit marker, exactly: **`wip: park <id>`** (e.g. `wip: park vibe-12`).

## Reading tickets (lenient — never crash on a ticket)

- **Locating a ticket by id:** look for `$STORE/<id>.md`. If it is not there, a
  ticket you just resumed lives in `$STORE/.resumed/<id>.md` — `vibe resume`
  soft-deletes (archives) the ticket there when it picks the work up. (When
  `vibe resume` seeds a fresh session with "continue from its next step", the
  ticket is in `.resumed/`.)
- Unknown keys: ignore, but preserve on write.
- Missing keys: default `state` → `on_hold`, `title` → the id, `id` → the
  filename stem, `repo` → id minus the trailing `-<digits>`, `description` →
  first paragraph of the body.
- No frontmatter at all: treat the whole file as body; id from the filename.
- Tolerate CRLF, trailing whitespace, `#` comments in frontmatter, quoted
  values (strip one layer), empty values (treat as absent).
- Tickets are hand-editable: before a ticket value goes into a shell command,
  validate it (`[A-Za-z0-9._/-]` for ids/branches, `[A-Za-z0-9-]` for session
  ids) or shell-quote it.

## Updating tickets (field-preserving — hard requirement)

You update a ticket only when re-parking work that already has a ticket this
session (see step 1). When you do:

- **Edit only the lines you mean to change.** Use targeted line edits (the
  Edit tool with the exact existing line as old string). Unknown keys,
  comments, key order, and the rest of the body stay byte-identical. **Never**
  parse the ticket into an object and re-serialize the whole file.
- **Land updates atomically (temp file, then rename).** The board watches the
  store live, and an interrupted in-place write leaves a torn ticket on disk.
  Copy the ticket to a temp file **in the store**, edit the temp copy, then
  `mv` it over the original — a same-volume rename is atomic.
  ```bash
  TMP=$(mktemp "$STORE/.$ID.md.tmp.XXXXXX")
  cp "$FILE" "$TMP"
  # ...targeted line edits on "$TMP"...
  mv "$TMP" "$FILE"
  ```
  After any update, re-read the ticket and confirm it still parses cleanly.
- Replacing a key whose value is a `|` block: also remove the block's indented
  continuation lines.
- Setting a key the file lacks: insert a new `key: value` line **before the
  closing `---`**.
- Write `null` as the literal `null`. No quoting unless the value contains
  `: ` or starts with a YAML-special character — then double-quote.
- **Always refresh `updated`** on every write.

## Identifying the current repo and checkout

```bash
TOP=$(git rev-parse --show-toplevel)
case "$TOP" in
  */_vibecoding/*) REPO=$(basename "$(dirname "$TOP")") ;;  # worktree: .../_vibecoding/<repo>/<dir>
  *)               REPO=$(basename "$TOP") ;;               # main checkout: <repo-base>/<repo>
esac
```

Main checkout vs linked worktree: it is the main checkout when
`git rev-parse --git-dir` equals `git rev-parse --git-common-dir`.

## Creating a new ticket (exclusive create — hard requirement)

Id allocation: next number = 1 + the highest `<number>` among existing
`<repo>-<number>.md` files (1 if none). Two writers may race, so a NEW ticket
file must be created with no-clobber semantics — never via the Write tool and
never via temp+rename (rename replaces and silently clobbers). Recipe:

```bash
STORE=/Volumes/External/Repositories/_vibeboard
mkdir -p "$STORE"
LAST=$(ls "$STORE" 2>/dev/null | sed -nE "s/^${REPO}-([0-9]+)\.md$/\1/p" | sort -n | tail -1)
FILE="$STORE/${REPO}-$(( ${LAST:-0} + 1 )).md"
( set -o noclobber; cat > "$FILE" <<'EOF'
---
id: ...
...
---

...
EOF
)
```

The redirect **fails if the file already exists** — on failure, re-scan and
retry with the next number. Fill in the full frontmatter template above
(`created` = `updated` = now).

---

# The park ritual ("wrap this up for now")

Your job ends at *note → commit → ticket*. You **never push** and you **never
remove the worktree** (you are running inside it; `vibe` removes it after the
session exits). Steps, in order:

1. **Find or create the ticket.** A ticket is the durable id for this work, so
   reuse the same one across park → resume → re-park rather than minting a new
   id. Note the current branch first (`BRANCH=$(git rev-parse --abbrev-ref HEAD)`),
   then, **in order**:
   - **Reuse a live ticket** — an on-hold ticket for this repo + branch still in
     the store root (you parked, kept working, and are parking again without a
     resume in between):
     `grep -l "^branch: $BRANCH$" "$STORE/$REPO"-*.md 2>/dev/null`. Update it.
   - **Recover an archived ticket** — `vibe resume` soft-deletes a ticket into
     `$STORE/.resumed/` when you pick work up. If you're re-parking work you
     resumed this session, its ticket is there with its **id and body (your
     earlier comments) intact**. Match it and **move it back to the store root**
     so it returns to the board unchanged-in-identity:
     `grep -l "^branch: $BRANCH$" "$STORE/.resumed/$REPO"-*.md 2>/dev/null`, then
     `mv "$STORE/.resumed/$ID.md" "$STORE/$ID.md"`. Update it (do not create a
     new id, and do not rewrite the body except the `## Next step` section).
   - **Otherwise create one** (the common first-park case): title/description
     from the work's content, plus `repo` and `base_branch`.

   On the **main checkout** with no work branch yet, `BRANCH` is `main`/your
   original branch and the matches above find nothing — create a ticket; its
   real branch is named in step 2 and written in step 5.

2. **Ensure a branch.** `BRANCH=$(git rev-parse --abbrev-ref HEAD)`. If you are
   in a worktree on its own branch, use it. If you are on the **main checkout**
   — even on `main` itself — remember the original branch, then create a
   logically-named branch at HEAD from the work's content (lowercase-kebab;
   slashes are fine, e.g. `fix/upload-retry`): `git switch -c "$BRANCH"` (this
   carries uncommitted changes along).

3. **Park commit.** First, BEFORE committing, check for newly created files that
   are gitignored — `git add -A` will silently drop them, which destroys trust
   in park:
   ```bash
   git status --ignored=matching --porcelain   # '!!' lines = ignored files
   ```
   Identify `!!` entries that are new this session. If any: **warn the user
   loudly**, list them, and let them decide (`git add -f`, copy the content into
   the ticket note, or accept the loss) before continuing. Then:
   ```bash
   git add -A
   git commit -m "wip: park $ID"
   ```
   **A park with no code changes is still a park** — if there is nothing to
   commit, skip the commit (or use `git commit --allow-empty -m "wip: park $ID"`)
   and still write the note and the ticket. Never push.

4. **Main checkout only: switch back and (maybe) reset `main`.** Switch the
   checkout back to its original branch, leaving it clean:
   `git switch "$ORIGINAL_BRANCH"`. Then the conservative reset rule — a reset
   is allowed only when it is provably lossless. Do **not** assume the branch
   from step 2 captured everything; prove it with the capture check:
   - Check `git rev-parse --verify -q origin/main` (no remote-tracking main →
     leave `main` alone) and `git log --format='%h %s' origin/main..main`.
   - **Capture check (mandatory):** every commit the reset would discard must
     be reachable from the park branch, and that branch must be a real ref
     distinct from `main`:
     ```bash
     [ "$BRANCH" != "main" ] && git merge-base --is-ancestor main "$BRANCH"
     ```
     Both must succeed. This catches the cases where the reset WOULD lose work:
     step 2's branch creation failed (so `$BRANCH` is `main` or a stale ref), or
     you committed to `main` itself earlier this session so the park branch does
     not contain `main`'s tip.
   - **Only if** the capture check passes AND local `main` is ahead of
     `origin/main` AND **every** commit in `origin/main..main` is one you made
     during THIS session (verify the hashes/subjects against what you know you
     committed — do not guess), you may run `git reset --hard origin/main` on
     `main`.
   - **In every other case** — capture check failed, any commit you did not
     make, no remote, any doubt at all — leave `main` untouched, park anyway,
     and **record loudly in the next-step note** that `main` carries N commits
     belonging to this ticket. Never reset on uncertainty. Never ask the user to
     untangle git mid-park.

5. **Write the note and create/update the ticket.** This is the auto-capture
   that makes resume cheap — you have the context now; the next session will not.
   - **Capture the human's braindump.** If the human gave any guidance when
     asking to park — what this work is, what they think should happen on resume,
     things to remember — write it (in their words/spirit) as the **`## Braindump`**
     section, above `## Next step`. If they parked with no such guidance, omit
     the section; on a re-park with no new braindump, leave any existing one
     untouched. Never fabricate a braindump or move your own analysis into it —
     `## Braindump` is the human's voice, `## Next step` is yours.
   - Write the **`## Next step`** section (in a new ticket's body, or replacing
     it in an existing one): what to do next, why the work is parked, and any
     loud warnings (dropped gitignored files, "`main` carries N commits
     belonging to this ticket").
   - Capture the session id (below).
   - Frontmatter: `state: on_hold`, `branch: <branch>`, `base_branch`, `tool:
     claude`, `session_id: <captured id>`, `worktree: <path>` when the work is
     in a worktree (else `null`), `created`/`updated` = now (refresh `updated`
     on a re-park).

## Session-id capture (best-effort)

Claude Code writes this conversation to a `.jsonl` under
`~/.claude/projects/<project-dir>/`, where `<project-dir>` is the session's
cwd with every non-alphanumeric character replaced by `-`:

```bash
PROJ=~/.claude/projects/$(pwd | sed 's/[^A-Za-z0-9]/-/g')
NEWEST=$(ls -t "$PROJ"/*.jsonl 2>/dev/null | head -1)
```

**Sanity-check that the newest file is THIS conversation** before trusting it:
grep it for a distinctive phrase from a recent user message in this session
(e.g. `grep -q 'distinctive phrase' "$NEWEST"`). If it matches, write its
basename without the `.jsonl` extension to `session_id`. If the check fails or
the directory does not exist, **leave `session_id` unset** — it is best-effort,
and resume degrades gracefully.

---

# Hard rules

- Never push to a remote.
- Never remove a worktree — `vibe` does that after the session exits.
- Never reset `main` unless the step-4 conditions provably hold.
- Never rewrite a ticket from a parsed object; line-level edits only.
- Never create a new ticket file without exclusive-create semantics.
