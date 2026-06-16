# Park/Resume on NSProject — Implementation Plan

**Status:** Plan, pre-implementation (drafted 2026-06-16).
**Goal:** Move Vibe Board's suspend/resume capability onto the **NSProject** board, making
NSProject the single source of truth for parked work. Retire the flat `_vibeboard/` store and the
VibeBoard menubar app.

This is a **backend swap, not a new system.** NSProject's design doc already specifies this feature
(`docs/PM-system-design.md` §2.7 "Continuity is per-person", §6 "Work, branches & resuming",
§11.2 #3 "Pick up where you left off"). It was specified as a *manual* "AI wraps up and writes the
summary" flow and never automated. `vibe` already has the automation (WIP-capture commit, worktree
reconstruction, tool relaunch with session restore). We point that automation at NSProject tickets.

---

## 1. Decisions locked (from the requester)

| # | Decision | Consequence |
|---|---|---|
| 1 | **NSProject is the sole backend.** | Retire the flat `_vibeboard/` store and the VibeBoard menubar app. Every park resolves to an NSProject ticket. |
| 2 | **Auto-create a ticket in `maybe/` when none matches.** | Work is never lost; park mints a lightweight ticket (id from product code, inferred `## What`/`## Why`), born in `maybe/` per NSProject §4.0. **Always `maybe/`** (never auto-promote to `this-week/`): when park has to create the ticket, where it belongs is genuinely unclear, so it lands in the intake pile for a human to vet and place. |
| 3 | **Same-dev conversation resume only.** | No transcript (`.jsonl`) ever leaves a machine. Cross-dev resume = fresh session seeded from `## Where I left off`. This is verbatim NSProject §2.7. |
| 4 | **Never push the product work branch.** | The agent has no push rights on product repos. Code-state resume is same-machine; a human may push the branch manually to share it. The **board (`data/`) is still committed+pushed** — that's normal NSProject operation (§0/§7), distinct from the product branch. |

---

## 2. Why the fit is clean — field mapping

NSProject already has a slot for almost everything Vibe Board captures:

| Vibe Board (`_vibeboard/`) | NSProject home | Status |
|---|---|---|
| `branch` | `work[].branch` | ✅ exists |
| `session_id` | `work[].session` ("resumable only by `by`, in their clone") | ✅ exists |
| repo (dir name) | `work[].repo` (**canonical URL**) | ✅ exists; needs URL→local-path resolver |
| `## Next step` | `## Where I left off` (explicit cross-person handoff, "source of truth") | ✅ exists |
| `## Braindump` | folds into `## Where I left off` (+ dated `## Log` entry) | ✅ exists |
| `tool` (claude/codex/opencode) | new key on the `work[]` map | ➕ add |
| `base_branch` | new key on the `work[]` map | ➕ add |
| `worktree` (informational) | omit — reconstruct from `branch` | — drop |
| `state: on_hold` | `parked_at` marker on the `work[]` map | ➕ add |
| `wip: park <id>` commit + unwind | not in NSProject | ➕ the genuinely new capability |
| `.resumed/` soft-delete archive | not needed — ticket is durable on the board | — drop |

All added keys are **AI-optional** (NSProject §2.5/§6.1) and stay out of human-facing board views
except the ticket detail / resume view (§11.3).

---

## 3. Behavioural model

### 3.1 Parking is an event on a ticket, not a new ticket lifecycle

In Vibe Board a ticket *exists only while parked*. In NSProject a ticket is durable and parking is a
state of its `work[]` entry. So:

- The ticket **does not move folders** on park (it's committed, in-progress work → it sits in
  `this-week/`, or wherever it already is). Park enriches the current dev's `work[]` entry and
  rewrites `## Where I left off`.
- `parked_at` (ISO-8601, on the `work[]` entry) is the "there is a resumable snapshot" marker.
- **Resume clears `parked_at`** (work is active again). The ticket and its `work[]` entry persist, so
  re-resume after an accidental close just finds the same entry — no `.resumed/` archive needed.
- The `wip: park <id>` commit lives on the **product branch in git** (local only; never pushed). The
  unwind on resume is the existing mixed `git reset HEAD~1`, gated on the tip subject equalling
  `wip: park <id>` for *this* id. Fully local; never needs the network.

### 3.2 Resume fidelity matrix

Code state and conversation degrade **independently**:

| Situation | Code state | Conversation |
|---|---|---|
| Same dev, same machine (branch + session local) | worktree reconstructed from local branch, park commit unwound | `claude --resume <session>` (full) |
| Same dev, branch pushed & fetched | tracking worktree from `origin/<branch>` | `--resume` if session local, else fresh |
| Cross dev (branch not pushed / not local) | no worktree; launch in main checkout | fresh session seeded from `## Where I left off` |
| Non-Claude tool (codex/opencode) | as above | always fresh (no session restore) |

The floor is always: **fresh session + the handoff note** (NSProject §2.7). Everything above the
floor is a same-person accelerator.

### 3.3 What park does NOT do (preserved from vibe's hard rules)

- Never pushes the product work branch (decision 4).
- Never removes the worktree (the `vibe` session lifecycle removes it after exit).
- Never resets `main` unless provably lossless (the existing capture-check rules in the park skill).
- Never rewrites a ticket from a parsed object — **line-level, field-preserving edits only**.

---

## 4. The NSProject `work[]` schema extension (the contract)

```yaml
work:
  - repo: https://github.com/nonstrict-hq/Bezel.git   # canonical URL (existing)
    branch: bzl-task-q7m2x                              # work branch (existing); embeds the hash
    by: mathijs                                         # person handle (existing; see §4.1)
    session: 736380d6-2a01-4cd5-bb01-5563347dca56       # session id (existing)
    base_branch: main                                   # NEW — for switchback / worktree base
    tool: claude                                        # NEW — tool to relaunch (claude|codex|opencode)
    parked_at: 2026-06-16T14:30:00Z                     # NEW — present ⇒ resumable snapshot; cleared on resume
```

Rules (mirror NSProject §6.5 + Vibe Board §5/§6):
- `work:` is a **block list of maps**, 2-space indent for `- `, 4-space child indent.
- **Lenient read:** every key optional; unknown keys ignored and **preserved on write**.
- **Field-preserving write:** edit only the child lines of the targeted entry; never reserialize.
- A `work[]` entry is keyed for park/resume by **`branch`** within the current repo (one entry per
  person+branch). Park finds-or-inserts that entry.
- Stamp the ticket's `updated:` (bare `YYYY-MM-DD`) on any work-entry or `## Where I left off` change
  (NSProject §5.2).

### 4.1 The `by` handle

NSProject examples use loose first-person handles (`by: me`, `by: tom`), which are ambiguous on a
shared board. **Standardize:** park writes a stable per-person handle for the machine it runs on,
resolved in this order:
1. `VIBE_PERSON` env var (or a `person:` line in a vibe config), else
2. `git config user.name` normalized to a short lowercase handle, else
3. prompt once and remember.

Resume prefers the `work[]` entry whose `by` matches the local handle (the same-person fast path),
else the most recently `parked_at` entry. The match is a **heuristic**, not a hard gate — session
resume and worktree reconstruction are both self-validating (a missing local branch or session
degrades to the floor), so a wrong handle never breaks resume, it just picks a less-ideal default.

---

## 5. Repo URL → local checkout resolution (new, shared by park & resume)

`work[].repo` is a canonical URL; vibe needs the local checkout path.

1. Derive the candidate dir name = URL basename minus `.git` (`…/Bezel.git` → `Bezel`); check
   `LOCAL_REPO_BASE/<name>`.
2. If absent or its `origin` URL doesn't match, **scan** `LOCAL_REPO_BASE/*` for a repo whose
   `git remote get-url origin` matches the canonical URL (normalize `git@…:` ↔ `https://…`, trailing
   `.git`, case).
3. If still unresolved, prompt the user for the local path (don't guess, don't clone — mirror the
   nsproject skill's "ask, don't invent a path" rule).

Worktrees keep vibe's existing layout `LOCAL_WORKTREE_BASE/<repo-dir>/<encoded-branch>` keyed on the
resolved repo **dir name**.

---

## 6. Board discovery (shared by park & resume)

Reuse the nsproject skill's discovery (NSProject `CLAUDE.md` §7, skill SKILL.md): a valid board =
a directory with `CLAUDE.md` **and** `data/maybe/`.
1. Resolve via the installed skill path (`~/.claude/skills/nsproject/` → board root), else
2. sibling-folder scan from the current repo's parent, else
3. ask the user.

All ticket I/O happens inside `data/`; `git -C data pull --rebase` before editing, commit+push
`data/` after, leave the infra root's submodule pointer dirty (NSProject §0).

---

## 7. Implementation phases

### Phase 0 — Reconcile current WIP — ✅ DONE (2026-06-16)

The working tree's uncommitted VibeBoard changes (the `## Braindump` body section + the tmux
resume-all command, with matching tests) were coherent, tested work — committed (not discarded) to
preserve history before the VibeBoard retirement. All migration work, including this WIP that Phase 5
will delete, lives on branch **`nsproject-park-integration`** (base commit `0f92831`,
`wip: Vibe Board braindump section + tmux resume-all`), keeping `main` clean and the effort
reversible.

### Phase 1 — Spec the contract

Replace `docs/vibeboard-format.md` with `docs/nsproject-park.md` — the normative contract for the
three implementers (park skill, `vibe` CLI, NSProject app): the §4 `work[]` schema, §3 lifecycle,
§5 URL resolution, §6 board discovery, the unwind rule, branch-naming (`<x>-<hash>`), `by` handle,
auto-create rules, never-push, board commit/push. *Optionally harden with the `refining-plans`
skill before building.*

### Phase 2 — `vibe` CLI: store-backend abstraction + NSProjectStore

- **New seam** in `vibe/tickets.py` (or a `vibe/store/` package): a `ParkedWork` value object
  (`ticket_id`, `local_repo_path`, `branch`, `base_branch`, `tool`, `session_id`, `by`, `parked_at`)
  and a store protocol: `find_work(ticket_id) -> ParkedWork | None`, `mark_resumed(work)`
  (clear `parked_at`, stamp `updated`, commit+push `data/`).
- **`NSProjectStore`** implementing it: board discovery (§6), `grep -rl "id: <id>" data/`, lenient
  parse of the `work[]` block list, URL→local-path resolver (§5), field-preserving edit of a
  `work[]` entry, `git -C data` commit+push.
- **`cli.py` `_handle_resume`** consumes `ParkedWork` instead of the flat `Ticket`:
  - drop the `.resumed/` archive + prune logic (ticket is durable);
  - keep worktree reconstruction / stranded-branch recovery / unwind / `_launch_resume` / tool
    degradation — these are store-agnostic and unchanged;
  - **new branch:** when the branch exists neither locally nor on origin (cross-dev, unpushed),
    don't hard-error — launch fresh in the main checkout with the bootstrap prompt pointing at the
    ticket's `## Where I left off`;
  - on success, `store.mark_resumed(work)`.
- **`config.py`**: remove `VIBEBOARD_DIR`; add board-discovery + `LOCAL_REPO_BASE` URL mapping.
- **Bootstrap prompt** retargets to NSProject: `Read NSProject ticket <id> via the nsproject skill
  and continue from its "Where I left off".`

### Phase 3 — Rewrite the `park` skill

Replace the embedded Vibe Board contract with the NSProject contract. New ritual order:
1. **Identify repo + person.** `git remote get-url origin` → canonical URL; resolve the `by` handle (§4.1).
2. **Resolve product/component + code.** Match the repo URL against `data/components/*` and
   `data/products/*` `repos:` lists → component → parent product → `code:` (for id minting). If no
   match, ask which product/component.
3. **Find-or-create the ticket** (find order):
   - branch already encodes a hash → `grep -rl "id: <CODE>_<hash>" data/`;
   - else a `Ticket: <id>` trailer in recent product-repo commits;
   - else **auto-create in `maybe/`** (decision 2): mint `<CODE>_<hash>` (NSProject §2), compute the
     `010`-gap prefix, write required core (`id`, `title`, `components`/`products`, `created`,
     `updated`) + inferred `## What`/`## Why`, leave `## Done when` for vetting, `git add` + commit.
4. **Ensure a branch** named with the hash (e.g. `<slug>-<hash>` or `task-<hash>`) so branch→ticket
   is recoverable. Same main-checkout switch-and-create logic as today.
5. **Park commit.** Gitignored-file safety check (warn loudly), `git add -A`,
   `git commit -m "wip: park <id>"`. **Never push the product branch.** Main-checkout switchback +
   the conservative `main`-reset capture-check rules carry over verbatim.
6. **Write the handoff into the ticket** (in `data/`):
   - rewrite `## Where I left off` (done / next / uncertain + any human braindump + loud warnings);
   - append a dated `## Log` entry;
   - find-or-insert this person's `work[]` entry: `repo` (URL), `branch`, `by`, `base_branch`,
     `tool: claude`, `session` (best-effort capture, unchanged), `parked_at: <now>`;
   - stamp `updated:` to today;
   - `git -C data add` + commit (`Update <id>: park`) + push; on push failure, **commit locally and
     warn** (don't fail the park).
7. **Session-id capture** — unchanged best-effort logic (sanity-check the newest `.jsonl` is this
   conversation).

`work[]` block-list edit recipe (the one tricky bit — detail in the skill): locate `work:`; within
it find the `- ` entry whose `branch:` matches (4-space children up to the next `- ` or the next
top-level key); edit/add its child lines in place; to add a new entry, insert a `- ` block before the
next top-level key (or before the closing `---`). Atomic temp-file + rename in `data/`.

### Phase 4 — NSProject app: surface parked work (in the NSProject repo; hand commits to a human)

- **BoardCore parser:** verify it tolerates and **round-trips** the new `work[]` keys when it stamps
  `updated` on a drag-move (it must not drop `base_branch`/`tool`/`parked_at`). Fix if it reserializes.
- **Resume view / card badge:** implement design §11.2 #3 ("Pick up where you left off") — list every
  ticket with a `work[]` entry, show branch + last `## Where I left off`, and for the matching `by`
  a copy-button for `vibe resume <id>` (reusing the `ResumeCommand` quoting logic, ported). A parked
  card gets a small badge when any `work[]` entry has `parked_at`.
- This is **additive** and lands in the human-committed infra repo — out of the critical path; can
  ship after Phases 1–3.

### Phase 5 — Retire Vibe Board

- Delete `VibeBoard/` (app + Swift sources + tests), `docs/vibeboard-format.md`.
- Remove flat-store code: `VIBEBOARD_DIR`, `.resumed/` archive functions, flat-store reads in
  `tickets.py`/`cleanup.py`/`cli.py` (keep the lenient frontmatter/parse helpers reused by
  `NSProjectStore`).
- Update `vibetools/CLAUDE.md` (project structure, the `skills/park` description), `README`, install
  scripts, and the skills list.

### Phase 6 — Tests & validation

- **Python (pytest, the repo's `tests/`):** `NSProjectStore` `work[]` parse + field-preserving
  round-trip (incl. unknown-key preservation); URL→local-path resolver (basename + origin-scan +
  ambiguous); resume flow with a mocked board (same-machine restore, cross-dev fresh-in-repo,
  parked_at cleared, stale-session degradation); auto-create id minting + prefix; **assert the
  product branch is never pushed**; board push-failure → warn-not-fail.
- **Skill dry-run:** park in a scratch repo against a scratch board clone → ticket gets `work[]` +
  `## Where I left off`; verify auto-create path and the find-by-branch-hash path.
- **Manual end-to-end:** real park → `vibe resume <id>` same machine restores worktree + unwind +
  `--resume`; confirm cross-dev path launches fresh with the handoff prompt.
- Target the repo's existing bar (all tests passing, >80% coverage per `vibetools/CLAUDE.md`).

---

## 8. Risks & open implementation details

- **BoardCore field preservation (Phase 4).** If the NSProject app reserializes frontmatter on a
  drag-move it could strip the new `work[]` keys. Must verify/fix before relying on the app — until
  then, only the skill + CLI touch `work[]` and they preserve unknown keys.
- **`by` handle standardization.** NSProject's loose `by: me` needs a stable handle (§4.1). Low risk
  (resume self-validates) but worth aligning with the human on the canonical handle per person.
- **Board reachability where the session runs.** Park runs inside the coding session (possibly on the
  VM); it needs a *writable* board clone reachable from there (NSProject §7 assumes a tokened clone on
  each VM). If the board isn't reachable/pushable, park must degrade: write the ticket to the local
  clone and warn, never lose the handoff.
- **Auto-create needs a product.** Park can only mint an id if it resolves the repo→product→`code`.
  Repos not yet registered as an NSProject component/product force a prompt (acceptable; one-time per
  repo) — or we add the component on the fly (a heavier, optional follow-up).
- **`this-week/` placement on auto-create — RESOLVED.** Auto-created tickets are **always** born in
  `maybe/` per NSProject §4.0, never auto-promoted to `this-week/`. When park has to create the
  ticket, its right home is genuinely unclear, so it lands in the intake pile for a human to vet and
  place. No surprise promotions.

---

## 9. Net effect

`vibe park`/`vibe resume` keep their entire worktree+unwind+relaunch engine; only the **store** moves
from `_vibeboard/` flat files to NSProject `work[]` entries + `## Where I left off`. NSProject gains
the one capability its own design doc said it lacked — automated suspend/resume — without adding a
field humans must maintain or a folder lifecycle, and within the per-person continuity model it
already chose (§2.7).
