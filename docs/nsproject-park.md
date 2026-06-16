# NSProject Park/Resume — Store Contract

The **NSProject board** (`docs/PM-system-design.md` §6, `CLAUDE.md` §6 in the NSProject repo) is the
single source of truth for parked work. `vibe park` (the `park` skill) and `vibe resume` (the Python
CLI) implement this contract. There is no flat `_vibeboard/` store any more — NSProject is the sole
backend.

This file is the normative reference for everything that touches parked work on the board: where the
board lives, how a park snapshot is recorded on a ticket, and how resume reconstructs it.

NSProject's own design already specified this feature (per-person continuity, the written summary as
the cross-person handoff — design doc §2.7, §6). This contract just makes it mechanical.

---

## 1. The board

- A ticket is a Markdown file in an NSProject state folder (`maybe/ up-next/ this-week/ done/
  archive/ not-now/`), inside the board's **`data/`** submodule. State is the folder; identity is
  the `id` (`<CODE>_<hash>`, e.g. `BZL_q7m2x`).
- **Board discovery** (both `vibe` and the skill): a valid board is a directory that contains both
  `CLAUDE.md` and `data/maybe/`. Resolve in order:
  1. the `NSPROJECT_BOARD` env var (a direct path to the board root), else
  2. scan known repo bases (`LOCAL_REPO_BASE`, its resolved target, `/Volumes/Repositories`) — the
     base itself, then its immediate children — for the first valid board, else
  3. fail with a clear message (set `NSPROJECT_BOARD`). Never guess a path; never `git clone`.
- All ticket reads/writes happen inside `data/`. Writers `git -C data pull --rebase` before editing
  and `git -C data` commit+push after; the infra-root submodule pointer is left dirty (NSProject §0).
- **Parking never pushes the product work branch** (the agent has no push rights there). It commits
  and pushes only the board (`data/`). A human may push the product branch manually to share code
  state.

---

## 2. Where a park snapshot lives — the `work[]` entry

Parking is an **event on an existing ticket**, not a new lifecycle. The ticket does not change
folders. Park enriches the parking person's entry in the ticket's `work[]` list and rewrites
`## Where I left off`.

```yaml
work:
  - repo: https://github.com/nonstrict-hq/Bezel.git   # canonical URL (NSProject identity)
    branch: bzl-task-q7m2x                              # the work branch; embeds the ticket hash
    by: mathijs                                         # person handle (§5)
    session: 736380d6-2a01-4cd5-bb01-5563347dca56       # coding-tool session id, best-effort
    base_branch: main                                   # NEW — switchback / worktree base
    tool: claude                                        # NEW — tool to relaunch (claude|codex|opencode)
    parked_at: 2026-06-16T14:30:00Z                     # NEW — board "is parked" marker; cleared on resume
```

- `repo`, `branch`, `by`, `session` are the existing NSProject `work[]` keys. `base_branch`, `tool`,
  `parked_at` are **new, AI-optional** keys this contract adds — they never appear in human board
  views (NSProject §2.5/§11.3).
- A `work[]` entry is keyed by **`branch`** within a repo: one entry per person+branch. Park
  finds-or-inserts that entry; it never rewrites other entries.
- `parked_at` (ISO-8601 UTC, `YYYY-MM-DDTHH:MM:SSZ`) present ⇒ "there is a resumable park snapshot."
  Resume clears it (the work is active again). Resume still works on an entry without `parked_at`
  (re-resume after an accidental close) — `parked_at` gates the board indicator, not resume itself.
- Stamp the ticket's `updated:` (bare `YYYY-MM-DD`) on any `work[]` or `## Where I left off` change
  (NSProject §5.2).

### Reading & writing (lenient / field-preserving — hard requirements)

- **Lenient read:** every key optional; unknown keys ignored. Tolerate quoted scalars, comments,
  CRLF, empty values. Never crash on a malformed ticket.
- **Field-preserving write:** edit only the child lines of the targeted `work[]` entry; preserve all
  other frontmatter, unknown keys, ordering, and the rest of the body byte-for-byte. Never parse the
  whole ticket into an object and reserialize. Land writes atomically (temp file in `data/` + rename).
- `work:` is a block list of maps: two-space indent for each `- ` entry, four-space child indent
  (NSProject §6.5). Inserting a new entry adds a `- ` block before the next top-level frontmatter key
  (or the closing `---`).
- Values that reach a shell or prompt (ids, branches, session ids) are validated against a
  conservative charset (`[A-Za-z0-9._/-]` for ids/branches, `[A-Za-z0-9-]` for session ids) or
  shell-quoted — tickets are hand-editable.

---

## 3. The body handoff — `## Where I left off`

- `## Where I left off` is the cross-person handoff and the **source of truth** (NSProject §6.1).
  Park rewrites this section's content (creating it if missing), leaving the rest of the body alone:
  what's done, what's next, what's uncertain, any human braindump, and loud warnings (dropped
  gitignored files, "local `main` carries N commits belonging to this ticket").
- Park also appends a dated entry to `## Log` (NSProject append-newest-at-bottom convention).
- Resume's bootstrap prompt (cross-dev / fresh) points the agent here:
  `Read NSProject ticket <id> via the nsproject skill and continue from its "Where I left off".`

---

## 4. Park commit & unwind (code state, local-only)

- Uncommitted work is captured by a single commit on the product branch with subject **exactly**
  `wip: park <id>` (e.g. `wip: park BZL_q7m2x`). `git add -A` captures tracked + untracked; an empty
  park may use `--allow-empty`.
- **This commit is never pushed.** It lives locally on the parking machine.
- **Unwind rule (resume):** unwind **only** when the worktree's tip commit subject equals
  `wip: park <id>` for *this* id (compare after trimming). Unwind = mixed `git reset HEAD~1`,
  restoring park-time working-tree state (tracked changes unstaged, untracked files back). Gated on
  the commit subject — never on `parked_at` — so it is correct regardless of board state.
- **Branch naming:** the work branch embeds the ticket hash (e.g. `<slug>-<hash>` / `task-<hash>`),
  so `vibe`/the skill can recover the ticket id from the branch.

---

## 5. The `by` person handle

NSProject's `work[].by` records the owner. Standardize a stable per-person handle, resolved in order:
1. `VIBE_PERSON` env var, else
2. `git config user.name`, normalized to a short lowercase token, else
3. `git config user.email` local-part.

Resume prefers the `work[]` entry whose `by` matches the local handle (the same-person fast path),
else the entry with the most recent `parked_at`. The match is a **heuristic**: session resume and
worktree reconstruction are self-validating, so a wrong handle never breaks resume — it just changes
the default entry chosen.

---

## 6. Repo URL → local checkout

`work[].repo` is a canonical URL; `vibe` needs the local checkout path:
1. candidate dir = URL basename minus `.git` → check `LOCAL_REPO_BASE/<name>`;
2. else scan `LOCAL_REPO_BASE/*` for a repo whose `origin` URL matches (normalize `git@…:` ↔
   `https://…`, trailing `.git`, case);
3. else fail and ask — never guess, never clone.

The worktree layout is unchanged: `LOCAL_WORKTREE_BASE/<repo-dir-name>/<encoded-branch>` (branch↔dir
encoding: `%`→`%25` then `/`→`%2F`).

---

## 7. Lifecycle

```
park   (skill)  -> find-or-create ticket; set work[].parked_at; wip-commit (local, not pushed)
resume (vibe)   -> reconstruct worktree from local branch + unwind; relaunch tool; clear parked_at
```

- **Park** finds the ticket (by branch hash → `grep -rl "id: <CODE>_<hash>" data/`; else a
  `Ticket: <id>` trailer in recent product commits) or, when none matches, **auto-creates one in
  `maybe/`** (NSProject §4.0): mint `<CODE>_<hash>` from the repo's product `code:`, write the
  required core + inferred `## What`/`## Why`, leave `## Done when` for a human to vet. **Always
  `maybe/`** — when park has to create the ticket, its right lane is unclear, so a human places it.
  Park never auto-promotes to `this-week/`.
- **Resume** (`vibe resume <id>`):
  - same dev, branch local → reconstruct/reuse the worktree, unwind the park commit, relaunch with
    `claude --resume <session>` (full conversation);
  - branch only on origin (a human pushed it) → tracking worktree; session resumed if local, else fresh;
  - branch nowhere / cross-dev → no worktree, launch fresh in the main checkout seeded with the
    bootstrap prompt pointing at `## Where I left off`;
  - non-Claude tools (codex/opencode) always relaunch fresh (no session restore).
  - On success, clear `work[].parked_at`, stamp `updated`, commit+push `data/`.
- **Post-session cleanup** (after a worktree session exits): the worktree is removed iff its **tip
  commit is a `wip: park ` marker** and the tree is clean. This is a local check on the worktree —
  no board access needed. A non-parked session keeps its worktree.

---

## 8. Concurrency

- Per-ticket files; the board is a normal Git repo (`data/`), one `main` branch, pull-then-push.
  Parallel inserts don't collide (the hash is in the filename).
- Same-ticket `work[]` updates are last-write-wins after a pull; the field-preserving edit keeps the
  blast radius to the touched entry.
