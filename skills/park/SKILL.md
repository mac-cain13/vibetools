---
name: park
description: Parks the current work onto the NSProject board so it can be resumed with `vibe resume <id>`. Use when the user says "park", "park this", "wrap this up for now", "wrap up for now", "set this aside", or otherwise asks to stop work on something for now but keep it resumable. Writes the park commit, captures a "Where I left off" handoff, and records a parked work entry on the ticket.
---

# Park — the suspend interface for the NSProject board

You are the in-session writer for the NSProject board. Your one job is **park**:
capture the current piece of work so it can be picked up later with
`vibe resume <id>`. Parked work lives on the **NSProject board** (the team's
Markdown-in-Git project board) — there is no separate flat store. The normative
contract is `docs/nsproject-park.md` in the `vibetools` repo; this file embeds
what you need.

**Parking is an event on a ticket, not a new lifecycle.** A ticket is durable
and lives in a state folder; park records a *parked work entry* on it and
rewrites its `## Where I left off`. Park does **not** move the ticket between
folders. `vibe resume` later clears the parked marker.

## The board

- A ticket is a Markdown file in an NSProject state folder (`maybe/ up-next/
  this-week/ done/ archive/ not-now/`) inside the board's **`data/`** submodule.
  Identity is the frontmatter `id` (`<CODE>_<hash>`, e.g. `BZL_q7m2x`).
- **Find the board** (a valid board has both `CLAUDE.md` and `data/maybe/`):
  ```bash
  find_board() {
    if [ -n "$NSPROJECT_BOARD" ] && [ -f "$NSPROJECT_BOARD/CLAUDE.md" ] \
       && [ -d "$NSPROJECT_BOARD/data/maybe" ]; then echo "$NSPROJECT_BOARD"; return; fi
    # via the installed nsproject skill: <board>/skills/nsproject/SKILL.md
    local s; s=$(python3 -c 'import os;print(os.path.realpath(os.path.expanduser("~/.claude/skills/nsproject/SKILL.md")))' 2>/dev/null)
    s=$(dirname "$(dirname "$(dirname "$s")")" 2>/dev/null)
    [ -f "$s/CLAUDE.md" ] && [ -d "$s/data/maybe" ] && { echo "$s"; return; }
    # sibling of the product repo's main checkout, under the repo base
    local base; base=$(dirname "$REPO_ROOT")
    for d in "$base"/*/; do
      [ -f "${d}CLAUDE.md" ] && [ -d "${d}data/maybe" ] && { echo "${d%/}"; return; }
    done
    return 1
  }
  BOARD=$(find_board); DATA="$BOARD/data"
  ```
  If none resolves, **ask the user** where their NSProject clone is — don't guess
  a path, don't `git clone`.
- All ticket reads/writes happen inside `$DATA`. `git -C "$DATA" pull --rebase`
  before editing (mention if it fails); after writing, `git -C "$DATA"` add +
  commit + push. **Leave the infra root's `data` submodule pointer dirty**
  (NSProject `CLAUDE.md` §0 — never commit the board's repo root).
- **Never push the product work branch.** You have no rights on product repos;
  the park commit stays local. (A human may push it later to share code state.)

## Ticket format (embedded contract)

A ticket is UTF-8 Markdown with YAML frontmatter, then a Markdown body. Required
core (`id`, `title`, a `components:` or `products:` membership, `## What`,
`## Why`) is the human's; everything else is yours. A parked work snapshot is an
entry in the `work:` block list plus a rewritten `## Where I left off`:

```markdown
---
id: PW_q7m2x
title: Local Network permission improvements
components: [pw_mac]
created: 2026-06-16
updated: 2026-06-16
work:
  - repo: https://github.com/nonstrict-hq/PersonaWebcam.git   # CANONICAL url
    branch: pw-task-q7m2x
    by: mathijs
    session: 736380d6-2a01-4cd5-bb01-5563347dca56
    base_branch: main
    tool: claude
    parked_at: 2026-06-16T14:30:00Z
---

## What
...

## Where I left off
What's done, what's next, what's uncertain — the cross-person handoff.

## Log
- 2026-06-16 — note.
```

`work[]` entry fields (NSProject `CLAUDE.md` §6.5: block list of maps, two-space
indent for `- `, four-space child indent):

| Field | Meaning |
|---|---|
| `repo` | The repo's **canonical URL** (never a local path). |
| `branch` | The work branch — keys the entry; name it to embed the ticket hash. |
| `by` | Person handle (see below). |
| `session` | Most recent coding-tool session id, best-effort. |
| `base_branch` | Branch the work is based on (usually `main`). |
| `tool` | `claude` \| `codex` \| `opencode` — tool to relaunch. |
| `parked_at` | ISO-8601 UTC (`date -u +%Y-%m-%dT%H:%M:%SZ`) — present ⇒ resumable snapshot. |

`base_branch`, `tool`, `parked_at` are park-added keys; `repo`/`branch`/`by`/
`session` are the standard NSProject keys.

**Body sections park owns:** `## Where I left off` (the handoff — create if
missing, replace its content) and a dated `## Log` append. Leave the rest of the
body (`## What`, `## Why`, `## Done when`, `## Attachments`, other notes) alone.

**Park commit marker, exactly:** `wip: park <id>` (e.g. `wip: park PW_q7m2x`).

**The `by` handle:** resolve in order — `VIBE_PERSON` env; else `git config
user.name` (first token, lowercased); else the local-part of `git config
user.email`.

## Reading tickets (lenient — never crash on a ticket)

- **Locate by id:** `grep -rl "id: <id>" "$DATA"` (a ticket sits in exactly one
  state folder). Read `## Where I left off`, the `work:` entries, and
  `ls "$DATA/attachments/<id>/"`.
- Unknown keys: ignore, but preserve on write. Missing keys: tolerate. Tolerate
  CRLF, trailing whitespace, `#` comments, quoted values, empty values.
- Tickets are hand-editable: before a value goes into a shell command, validate
  it (`[A-Za-z0-9._/-]` for ids/branches, `[A-Za-z0-9-]` for session ids) or
  shell-quote it.

## Updating tickets (field-preserving — hard requirement)

When the ticket already exists (re-park, or a human-created ticket you're
attaching work to), edit it **in place at the line level** — never parse it into
an object and re-serialize:

- **Edit only the lines you mean to change** (the Edit tool with the exact
  existing line as the old string). Unknown keys, key order, and the rest of the
  body stay byte-identical.
- **Land updates atomically** (the board watches the store live):
  ```bash
  TMP=$(mktemp "$DATA/.tkt.XXXXXX")
  cp "$FILE" "$TMP"
  # ...targeted line edits on "$TMP"...
  mv "$TMP" "$FILE"
  ```
- **The `work[]` entry** is keyed by `branch` within the repo. To update it,
  find the `- ` entry whose `branch:` matches `$BRANCH` and edit/add its
  four-space child lines (`session`, `tool`, `base_branch`, `parked_at`); refresh
  `parked_at`. To add a new person+branch entry, insert a `- ` block (two-space
  `- repo:` then four-space children) **before the next top-level key or the
  closing `---`**. Refresh the top-level `updated:` to today.
- Write `null`/empty values sparingly; quote a scalar only when it contains `: `
  or starts with a YAML-special character.

## Identifying the repo, person, and product

```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
# Worktree vs main checkout: it's a worktree when git-dir != git-common-dir.
ORIGIN=$(git -C "$REPO_ROOT" remote get-url origin)         # canonical-ish URL
REPO_SLUG=$(basename "$ORIGIN" .git)                         # e.g. PersonaWebcam
BY=${VIBE_PERSON:-$(git config user.name | awk '{print tolower($1)}')}
```

**Resolve the product + code** (to mint an id for a new ticket): find the
component or product file whose `repos:` lists this repo, then read its product's
uppercase `code:`.
```bash
COMPFILE=$(grep -rliE "/$REPO_SLUG(\.git)?/?\$" "$DATA"/components/*.md "$DATA"/products/*.md 2>/dev/null | head -1)
# component -> its `product:` -> products/<product>.md `code:`  (a product file already has `code:`)
```
If nothing matches, **ask the user** which product/component this repo belongs to
(don't invent one).

## Creating a new ticket (the common first-park case)

When no ticket matches (see the ritual's step 1), auto-create one **born in
`maybe/`** (NSProject `CLAUDE.md` §4.0) — **always `maybe/`**, never
`this-week/`: when park has to create the ticket, its right lane is unclear, so a
human vets and places it.

```bash
CODE=...                       # product code, uppercase (from the product file)
# mint a unique id: 5 chars from base-31, grep-confirm
while :; do
  H=$(python3 -c "import secrets; a='23456789abcdefghjkmnpqrstuvwxyz'; print(''.join(secrets.choice(a) for _ in range(5)))")
  ID="${CODE}_${H}"; grep -rqs "id: $ID" "$DATA" || break
done
# append prefix for maybe/ (010 if empty, else highest + 10)
LAST=$(ls "$DATA/maybe" 2>/dev/null | sed -nE 's/^([0-9]+)-.*/\1/p' | sort -n | tail -1)
PREFIX=$(printf "%03d" $(( 10#${LAST:-0} + 10 )))
SLUG=...                       # short kebab-case from the title
FILE="$DATA/maybe/${PREFIX}-${H}-${SLUG}.md"
```
Write `$FILE` with the required core (`id`, `title`, a `components:`/`products:`
membership, `created`/`updated` = today), a short inferred `## What` and
`## Why`, the `work[]` entry, and the `## Where I left off` handoff. Leave
`## Done when` for a human to fill at vetting. Then `git -C "$DATA" add "$FILE" &&
git -C "$DATA" commit -m "Add $ID: <title>"`.

---

# The park ritual ("wrap this up for now")

Your job ends at *handoff → commit → ticket*. You **never push the product
branch** and you **never remove the worktree** (you are running inside it; `vibe`
removes it after the session exits). Steps, in order:

1. **Find or create the ticket.** Reuse the same ticket across park → resume →
   re-park rather than minting a new id. Note the branch first
   (`BRANCH=$(git rev-parse --abbrev-ref HEAD)`), then, **in order**:
   - **Branch embeds a ticket hash** — `grep -rl "id: <CODE>_<hash>" "$DATA"`
     where `<hash>` is the trailing hash of the branch name. Update that ticket.
   - **A `Ticket: <id>` trailer** in recent product-repo commits
     (`git log -20 --format='%b' | grep -oE 'Ticket: [A-Z]+_[0-9a-z]+'`). Update it.
   - **Otherwise auto-create** in `maybe/` (above).

   On the **main checkout** with no work branch yet, `BRANCH` is `main`/your
   original branch and the matches find nothing — create the ticket; its real
   branch is named in step 2 and written in step 5.

2. **Ensure a branch.** If you are in a worktree on its own branch, use it. If
   you are on the **main checkout** — even on `main` itself — remember the
   original branch, then create a logically-named branch at HEAD that **embeds
   the ticket hash** (lowercase-kebab; slashes are fine, e.g. `pw-task-q7m2x` or
   `fix/upload-q7m2x`): `git switch -c "$BRANCH"` (this carries uncommitted
   changes along).

3. **Park commit.** First, BEFORE committing, check for newly created files that
   are gitignored — `git add -A` will silently drop them:
   ```bash
   git status --ignored=matching --porcelain   # '!!' lines = ignored files
   ```
   Identify `!!` entries new this session. If any: **warn the user loudly**, list
   them, and let them decide (`git add -f`, copy the content into the ticket
   note, or accept the loss) before continuing. Then:
   ```bash
   git add -A
   git commit -m "wip: park $ID"
   ```
   **A park with no code changes is still a park** — if there is nothing to
   commit, skip the commit (or `git commit --allow-empty -m "wip: park $ID"`) and
   still write the handoff and the ticket. **Never push the product branch.**

4. **Main checkout only: switch back and (maybe) reset `main`.** Switch the
   checkout back to its original branch, leaving it clean:
   `git switch "$ORIGINAL_BRANCH"`. Then the conservative reset rule — a reset is
   allowed only when it is provably lossless. Do **not** assume the branch from
   step 2 captured everything; prove it with the capture check:
   - Check `git rev-parse --verify -q origin/main` (no remote-tracking main →
     leave `main` alone) and `git log --format='%h %s' origin/main..main`.
   - **Capture check (mandatory):** every commit the reset would discard must be
     reachable from the park branch, and that branch must be a real ref distinct
     from `main`:
     ```bash
     [ "$BRANCH" != "main" ] && git merge-base --is-ancestor main "$BRANCH"
     ```
     Both must succeed. This catches the cases where the reset WOULD lose work:
     step 2's branch creation failed (so `$BRANCH` is `main` or a stale ref), or
     you committed to `main` itself earlier this session so the park branch does
     not contain `main`'s tip.
   - **Only if** the capture check passes AND local `main` is ahead of
     `origin/main` AND **every** commit in `origin/main..main` is one you made
     during THIS session (verify the hashes/subjects — do not guess), you may run
     `git reset --hard origin/main` on `main`.
   - **In every other case** — capture check failed, any commit you did not make,
     no remote, any doubt at all — leave `main` untouched, park anyway, and
     **record loudly in `## Where I left off`** that `main` carries N commits
     belonging to this ticket. Never reset on uncertainty. Never ask the user to
     untangle git mid-park.

5. **Write the handoff and create/update the ticket.** This is the auto-capture
   that makes resume cheap — you have the context now; the next session will not.
   - **Rewrite `## Where I left off`** (create the section if missing, replace its
     content if present): what's done, what's next, what's uncertain, plus any
     loud warnings (dropped gitignored files; "local `main` carries N commits
     belonging to this ticket"). If the human gave a braindump when asking to
     park — what this is, what they think should happen next — fold it in (in
     their words). This section is the cross-person source of truth.
   - **Append a dated `## Log` entry** (newest at the bottom).
   - **Find-or-insert this person's `work[]` entry** (keyed by `$BRANCH`): `repo`
     = the canonical URL, `branch`, `by`, `session` (step 6), `base_branch`,
     `tool: claude`, `parked_at` = now (`date -u +%Y-%m-%dT%H:%M:%SZ`). Refresh
     `parked_at` on a re-park.
   - **Stamp the top-level `updated:`** to today (`date -u +%Y-%m-%d`).
   - **Commit + push the board:** `git -C "$DATA" add "$FILE" && git -C "$DATA"
     commit -m "Update $ID: park" && git -C "$DATA" push`. If the push fails,
     commit locally and **warn the user** (the handoff is saved; the board can be
     pushed later) — never lose the handoff. Leave the infra root's submodule
     pointer dirty.

## Session-id capture (best-effort)

Claude Code writes this conversation to a `.jsonl` under
`~/.claude/projects/<project-dir>/`, where `<project-dir>` is the session's cwd
with every non-alphanumeric character replaced by `-`:

```bash
PROJ=~/.claude/projects/$(pwd | sed 's/[^A-Za-z0-9]/-/g')
NEWEST=$(ls -t "$PROJ"/*.jsonl 2>/dev/null | head -1)
```

**Sanity-check that the newest file is THIS conversation** before trusting it:
grep it for a distinctive phrase from a recent user message in this session. If
it matches, write its basename without `.jsonl` to the `work[]` entry's
`session`. If the check fails or the directory does not exist, **leave `session`
unset** — it is best-effort, and resume degrades gracefully (a fresh session
seeded from `## Where I left off`).

---

# Hard rules

- Never push the product work branch (you may push only the board's `data/`).
- Never commit the board's infra root — only `data/` (NSProject `CLAUDE.md` §0).
- Never remove a worktree — `vibe` does that after the session exits.
- Never reset `main` unless the step-4 conditions provably hold.
- Never rewrite an existing ticket from a parsed object; line-level edits only.
- Auto-created tickets are born in `maybe/`, never `this-week/`.
- Confirm id uniqueness with `grep` before minting.
