# Vibe Board — Product Design Doc

> Working title. The system is referred to here as **Vibe Board**; the unit of work is a **ticket**. Name is open.

**Status:** Draft v3 — incorporates review rounds 1–2 (against the `vibetools` codebase); cleared to build · **Owner:** (you) · **Audience:** implementer handoff

---

## 1. Problem

I run several pieces of work in parallel through Claude Code, one per terminal tab (tmux + iTerm). The tab becomes the only record that a piece of work exists and what state it's in. So I don't close tabs — closing one feels like deleting the work. High-priority work gets finished; everything else hangs in a tab for days or quietly dies.

**Root issue:** the terminal tab is acting as a *storage medium for in-flight work*, and it's a bad one. It's volatile (a reboot wipes it), it has no aggregate view (N tabs is N separate mental loads, not one overview), and it fuses two things that should be separate — "this process/session is alive" and "this work item exists and needs a decision."

The fix is not "a board" for its own sake. It's a **durable registry of work-in-flight, decoupled from the running process**, plus a workflow cheap enough that I actually use it.

## 2. Core insight (the design constraint everything follows from)

Most of what I'm afraid of losing when I close a tab is *already persisted*:

- The Claude Code conversation — on disk, resumable.
- Committed code — in git (branch/worktree).

The only genuinely volatile things are **uncommitted changes** and **the human context** ("what was I doing, what's the next step, why is this parked"). The registry only needs to durably hold those two, plus give me one view across everything.

Two principles fall out:

1. **Capture cheaply; never rely on memory.** Anything that depends on me remembering to update it will rot exactly like the tabs did — my demonstrated behavior is defer-and-forget. Near-zero upkeep comes from two moves, not from scanning the world: (a) the agent auto-captures the next-step note at the one moment context is hot (park time), and (b) state is an explicit field changed by actions that are themselves cheap (park is a sentence, resume is a command). We deliberately do *not* try to derive state from git/tmux/sessions — that was an earlier idea, rejected as fragile (§5).
2. **Make closing safe by making resuming trivial.** I'll only close a tab if reopening is one command. Resume is as important as capture. This is what lets parking become a constant, low-friction habit instead of a ceremony.

If park/resume is genuinely cheap, the hardest problem disappears: nothing needs to stay "warm but hidden." **tmux holds only today's active work.** The instant something stops being today's work, it cold-parks to a branch and any worktree is cleaned up. Everything off-screen is durable by construction.

## 3. Goals / Non-goals

**Goals**
- One view of all in-flight work, grouped by state, always current with near-zero manual upkeep.
- A trivially cheap "wrap this up for now" → park, and "pick this back up" → resume, the latter usable from anywhere via a ticket id.
- Integrate with the existing `vibe` CLI rather than replace it.
- A native Mac app kanban for browsing tickets and adding notes.
- Local-only, single user.

**Scope — v1 is the Mac setup only.** `vibetools` has two independent setups. v1 targets the **Mac/tart** setup, where repos live under a base directory the Mac hosts and the VM mounts as a share — this is what makes the storage and FSEvents design (§8.1) work. The **Windows/Hyper-V** setup (repos on the Windows host's disk, Mac not in the loop) is explicitly **out of scope for v1**. Picking a store layout relative to the repo base (§8.1) keeps the door open for a per-setup store on Windows later, and sidesteps cross-setup ticket-id collisions.

**Non-goals**
- Team features, sharing, assignment, comments-from-others.
- A general task manager / replacement for Linear/Jira. This tracks *work tied to a codebase*, not arbitrary tasks.
- Keeping detached-but-running processes alive as a parking strategy (explicitly rejected — see §2).
- The Windows/Hyper-V setup, and any cross-machine cloud sync, in v1.

## 4. Relationship to `vibe`

`vibe` already: points at a branch, creates/connects a git worktree, launches the AI coding tool (Claude Code / Codex / OpenCode) locally or over SSH, and handles connection/path/cleanup boilerplate.

Vibe Board is **not a separate app that drives vibe**. It's a **shared ticket store plus three clients that read and write it**, each tied to *where I physically am* when I touch the work:

- **The `vibe` CLI — resume (and worktree cleanup).** When I pick work back up I'm *outside* any agent (a fresh terminal). `vibe resume <ticket>` is the only thing I type. Not a skill — there's no agent running yet. vibe also handles deferred worktree cleanup (below).
- **The Claude Code skill — park, and jot.** When I park I'm *inside* the live session, the one place the context to write a good next-step note exists. The skill is the agent's interface to the vibeboard: it teaches the agent how to park the current work (incl. creating a ticket and/or branch on the fly), and how to jot a Todo or add a note when I ask mid-session.
- **The board UI (native Mac app) — browse and annotate.** I read the kanban here, add Todos and notes, drag tickets between states, and **copy** a `vibe resume <ticket>` command to paste into iTerm myself.

This collapses the user-facing surface to **one CLI verb + one skill + one board UI.** I never type `vibe park`, `vibe board`, or `vibe todo`.

Two consequences worth stating up front:

- **Park writes a simple, recognizable marker — not a rigid contract, and not a shared library.** A park commit (`wip: park <ticket>`) plus the ticket's explicit state field is all that's needed. The **skill itself carries the ticket format, store location, and naming rules**, and the agent writes the markdown directly; the Mac app parses tickets with its own Swift code. There is no shared read/write library and no plumbing CLI. The discipline that replaces a shared library is **lenient parsing everywhere** (§8.1).
- **No derivation engine.** State is an explicit field on the ticket (§5), so the board simply reads the store. Git facts (uncommitted changes, commits-ahead) can be shown *as context* beside a ticket, but never change its state.

## 5. The ticket and the four states

The **ticket is the durable primary key for the whole lifecycle.** It exists before any branch (Todo) and after the branch is gone (Ready to release). Git artifacts attach only during the active middle of its life: branch/worktree/session are *attributes that come and go*; the ticket is the spine.

A subtlety that shapes the flows: **the branch attaches at park, not at start.** Work often begins as plain `vibe` on the main checkout — sometimes on `main` itself — with no dedicated branch or worktree. So `branch: null` and `worktree: null` can persist well into Doing, and the branch is named (by the agent) at the first park.

| State | Set by (explicit action) | Where the work lives | tmux | Worktree |
|---|---|---|---|---|
| **Todo** | Created in board, or "note this down" to the agent | Registry note only | — | — |
| **Doing** | Starting a Todo, or `vibe resume` | tmux (today's work) | live | present, *or* the main checkout (none) |
| **On hold** | park (the skill) | A non-main branch (WIP in a park commit) | closed | removed (by vibe, post-session) |
| **Ready to release** | Merged → moved by me or the agent | Registry note only (freeform tail) | — | removed |

Lifecycle: `Todo → Doing → (On hold ⇄ Doing)* → Ready to release → Archived`.

Notice the symmetry: **registry-only at both ends, git-backed in the middle.** Todo and Ready-to-release have no branch — which is exactly why the ticket, not the branch, must be the key.

**State is an explicit field on the ticket, changed only by actions:**
- Create a Todo (board or agent) → **Todo**
- Start it, or `vibe resume` → **Doing**
- park (the skill) → **On hold**
- Merge, then move it (me on the board, or the agent right after merging) → **Ready to release**
- Tail work done → **Archived** (I move it)

No scanning, no inference — the board shows exactly the state the last action set. The agent can move or comment on a ticket directly when that's natural, and can read `wip: park <ticket>` plus the ticket note to figure out where to pick up. Git facts may appear as *context* next to a ticket but never change its state.

**Create-on-park is the common case.** Most work has no ticket when park is invoked (today's main flow `vibe <branch> --claude` creates none). So if no ticket references the current work, the skill **creates one at park time**. This is the norm, not an edge case.

The one known gap, accepted for now: if I close a tmux window *without* parking, its ticket stays marked Doing. Park is the only blessed exit and it's a one-sentence habit, so this should be rare; the idempotent resume rules (§6.3) absorb it when I come back. We'll see whether it bites before adding anything to catch it.

## 6. Key workflows

### 6.1 Capture a future idea (→ Todo)
Two doors, both low-friction: add it in the board UI, or tell the active agent "note this down for later" and the skill creates a Todo ticket. Either way it's a registry note with no code attached. Starting it later does **not** require inventing a branch up front — work can begin on the current checkout, and the branch is named at the first park.

### 6.2 Wrap up for now (Doing → On hold) — the park ritual
Always triggered from inside the live session: I tell the agent "let's wrap this up for now" and the skill takes over. The skill's job ends at *note → commit → state*; **it does not remove the worktree** (it's running inside that worktree — see §6.3 cleanup). Steps:

1. **Find or create the ticket.** If no ticket references the current work, create one (create-on-park).
2. **Ensure there's a branch.** If the work is in a worktree on its own branch, use it. If the work is on the **main checkout** (possibly on `main`), the agent creates a logically-named branch from the work's content.
3. **Write the park commit** on that branch: stage everything including untracked (`git add -A`), commit `wip: park <ticket>`.
   - **Warn loudly** about new files that are gitignored — `git add -A` won't include them, and a silently-dropped file destroys trust in park. List them; let me decide.
   - **A park with no code changes is still a park.** The conversation context is worth capturing — skip the commit (or use `--allow-empty`) and still write the note + state.
   - No remote push (decided). Durability rests on wherever the repo lives (the share).
4. **If the work was on the main checkout, switch the checkout back to its original branch**, leaving it clean so the next session inherits nothing. This is also required for correctness: resume can't create a worktree for a branch still checked out in the main checkout. Handling session commits to local `main` (agents commit mid-session routinely) follows a deliberately conservative rule:
   - Branching at HEAD (step 2) already captured everything onto the park branch — **park never loses work.**
   - After switching back, check whether `main` is ahead of `origin/main` **and** whether *every* commit in `origin/main..main` was made during this session (the agent knows what it committed; verify before acting).
   - **Only if that holds**, reset local `main` to `origin/main` — the commits live on the park branch and `main` is clean.
   - **In every other case** (commits it didn't make, no remote, any doubt): leave `main` untouched, park anyway, and record loudly in the next-step note that `main` carries N commits belonging to this ticket. Never reset on uncertainty; never ask me to untangle git mid-park. A wrong reset silently discards someone's commits (trust-destroying); not resetting is just today's status quo (harmless, and loud).
5. **Write the next step into the ticket** (the agent has the context — this is the auto-capture that makes resume cheap) and set `state: on_hold`. For worktree-based work, nothing is removed here.

Worktree removal is **deferred to vibe** (§6.3 / §8.4): when the session vibe launched exits, vibe checks the ticket and removes the worktree if it's now `on_hold`. `vibe --clean` is the backstop sweep.

### 6.3 Pick it back up (On hold → Doing) — the resume ritual
`vibe resume <ticket>` from anywhere. Not a skill — there's no agent running yet.

**Resume must be idempotent across the full state × worktree matrix.** This one requirement absorbs partial-park failures, the closed-without-parking gap, reboots, and cleanup races:

- `todo` / any ticket with `branch: null` → resolve the repo and launch the tool on the repo's **main checkout** (seeded with the bootstrap prompt), set `doing`. **Create nothing** — no branch, no worktree. The branch is named by the agent at the first park, exactly like all other ad-hoc work; this keeps one rule for branch creation (park, and only park).
- `on_hold` + no worktree → recreate worktree from the branch, **unwind only if the tip commit is the park marker**, launch, set `doing`.
- `on_hold` + worktree exists → use it; unwind only if the tip is the park marker; launch; set `doing`.
- `doing` + branch + worktree exists → reconnect; launch.
- `doing` + branch but no worktree (post-reboot) → recreate worktree from the branch; launch.

Accepted consequence: todos resumed onto the main checkout share it, so two can't run in parallel until at least one has parked onto its own branch. That mirrors how work starts today and is self-resolving — park one, resume it, and it's in a worktree.

Normative rules:
- **Never unwind without verifying the tip commit message matches the park marker.**
- **Unwind = mixed `git reset HEAD~1`** so the park commit's contents come back as working-directory changes — exactly the state at park time (untracked files reappear, tracked changes return unstaged).
- **Launch plumbing.** `--resume <session-id>` must thread through both paths: the macOS SSH path (the tool command is embedded in a quoted `zsh -c` string) and the local path (`connect_locally` currently runs a bare single-element argv and can't take args — fix needed). For fresh sessions, seed with a **fixed bootstrap prompt** ("Read ticket `<id>` via the vibeboard skill and continue from its next step") so no freeform text travels through shell quoting.
- **Non-Claude tools (`tool: codex|opencode`).** Session restore and the bootstrap prompt are Claude features; for other tools, resume launches the recorded tool **fresh** (no restore, no prompt) — everything else (worktree resolution, unwind, state) works identically. No refusal.

### 6.4 Finish the non-code tail (Ready to release → Archived)
When the branch is merged, the ticket moves to Ready to release — by me dragging it on the board, or the agent doing it right after it merges. The ticket carries a freeform note for the non-coding tail (notify users, publish the release, etc.); no structured checklist. When that's done I move the ticket to Archived and it leaves the board.

## 7. Visual board

A **native Mac app** (decided — for FSEvents now and deeper integrations later: menu-bar presence, tmux/iTerm awareness, notifications). Columns map 1:1 to the four states. It reads the ticket store and renders each ticket's explicit state.

Capabilities:
- Browse tickets grouped by state; each card shows `title`, a short description, branch, and any git context (e.g. uncommitted changes) shown as info.
- Add/edit freeform notes and set priority on a ticket (the small writable surface).
- Drag a ticket to a new state (e.g. into Ready to release, or Archived).
- **Copy a `vibe resume <ticket>` command** to the clipboard (no resume button, no spawning a terminal — I paste it into iTerm myself). This removes the no-TTY problem from v1 entirely; terminal management isn't the pain point.

It is **read-mostly for status**: state lives in the ticket and changes on actions; the board lets me annotate and perform state-moving actions, but doesn't infer state behind my back.

## 8. Technical spec

### 8.1 Storage and source of truth
- **Store location is relative to the repo base: `<repo-base>/_vibeboard`.** It lives on the Mac's local disk and the VM mounts it via the share, so every write — including the agent's — lands on the Mac's local filesystem (this is what makes FSEvents work; see Propagation). Anchoring to the repo base (rather than a per-machine `~/.config`) keeps the multi-setup door open: a Windows setup later gets its own store under its own base.
- **One file per ticket: Markdown with YAML frontmatter.** Frontmatter holds structured fields; the body holds freeform notes. Hand-editable, diff-able, git-backable, concurrency-friendly.
- **State is an explicit field, stored in the ticket** (§5). Git/tmux facts are never the source of truth for state.
- **Lenient parsing everywhere (hard requirement).** With no shared library, readers must tolerate drift: a missing or unknown frontmatter field must never break a reader, because fields will be added and removed over time. **Every field is optional on read.** The writer side is kept precise by instructions in the skill.
- **Unknown-field preservation on write (hard requirement).** The other half of "no shared library": every writer (skill, Swift app, vibe) must **round-trip frontmatter keys and body content it doesn't understand** when updating a ticket. Otherwise the first writer on an older schema silently strips newer fields. Read-modify-write preserves the whole document; it only changes the keys it means to.

**Why a folder of files, not one shared SQLite DB.** SQLite explicitly warns against placing its database on a network filesystem: it coordinates concurrent access with file locks, and lock semantics over NFS/SMB are unreliable — two simultaneous writers risk corruption. That's exactly our setup, so it's the configuration to avoid. A per-ticket markdown file sidesteps it: the two of us almost always touch *different* tickets. SQLite's query power isn't needed at this scale; its locking weakness is precisely our failure mode.

**Concurrency.** Edits use atomic write (temp + rename); a rare same-ticket collision is last-write-wins, acceptable for edits. **New-ticket creation is the one place last-write-wins is not acceptable** (temp+rename *replaces*, so two simultaneous new tickets could silently clobber): use **exclusive-create (`O_EXCL`) semantics** where cheaply available so two writers can't collide on a fresh id. Low-hanging fruit only — concurrent parks are rare at this scale.

**Propagation — asymmetric, and that's what makes it simple.** Only one consumer needs to be live (the board), and it's the one that can be. Because the store is local to the Mac, the board gets true push via **FSEvents** — no polling — and the VM's writes land on local disk, so FSEvents fires for them too. The agent needs no notifications: the CLI and skill read fresh on every invocation. This rests on **the Mac hosting the share** (the v1 scope, §3). If that ever flips, the fallback is a writer-emitted ping, not filesystem watching.

Proposed frontmatter (all fields optional on read):
```yaml
id: vibe-12              # <repo-name>-<number>
title: Retry logic for upload client   # short; what the card shows
description: |           # short card blurb; if absent, use the body's first paragraph
  Add bounded retry with backoff to the upload client.
repo: vibe               # repo NAME, resolved against the configured repo base; also
                         # prefixes the id and groups tickets (replaces the old `project`)
base_branch: main
branch: null             # null until the first park (work may run on main/current branch)
worktree: null           # set only while a worktree exists; null otherwise
tool: claude             # claude|codex|opencode — relaunched on resume; non-Claude tools
                         # launch fresh (no session restore / bootstrap prompt)
session_id: <best-effort>      # most recent session seen for this work
state: on_hold           # explicit; one of todo|doing|on_hold|ready|archived
priority: normal
created: 2026-06-10T...
updated: 2026-06-10T...
```
Body = freeform notes, including a clearly-marked **Next step** section the park ritual writes, and (once merged) the freeform release tail.

### 8.2 State (explicit)
`state` is a field on the ticket; nothing scans to compute it. It only moves on actions:
```
create todo                  -> todo
start / vibe resume          -> doing
park (skill)                 -> on_hold
merge + move (me or agent)   -> ready
tail done (me)               -> archived
```
The board may *read* git facts (`git status --porcelain`, commits-ahead) to show context beside a ticket, but it never changes `state` on its own. (No drift nudge for now — see §11.)

### 8.3 Session linking and capture
The chain ticket → branch → worktree → session drifts. **Branch/worktree is the primary attachment; `session_id` is best-effort,** refreshed on park/resume. Resume must degrade gracefully to a fresh seeded session if the id is stale.

**Capture is done by the agent per skill instructions — no hooks.** At park, the agent scans the newest `.jsonl` under the project's session directory and **sanity-checks that it is *this* conversation** (not a newer unrelated session) before writing `session_id` to the ticket.

### 8.4 Park / resume internals
- Park commit marker: the conventional message `wip: park <ticket>`, so resume can reliably detect and unwind it. **Resume never unwinds unless the tip message matches.**
- Untracked handling: `git add -A`; detect and warn on ignored-but-new files; never silently drop. Empty park allowed (`--allow-empty` / skip commit) — still writes note + state.
- **Worktree removal is deferred, not done by the skill.** The skill runs inside the worktree; git refuses to remove the current working tree. So: when the launched session exits, vibe looks up the ticket for the worktree it connected to — **matched by repo + branch** — and removes the worktree if that ticket is `on_hold`. `vibe --clean` is a backstop sweep over all `on_hold` worktrees. **Cleanup never uses `--force`:** a worktree dirtied after park is skipped and surfaced, mirroring existing `--clean` behavior.
- Resume unwinds with a mixed `git reset HEAD~1` to working-tree state before relaunch.
- Park commits can ride into history on merge — handled deliberately by the merger (squash-merge); not the board's concern.

### 8.5 Surfaces and language
User-facing: **one CLI verb + one skill + one board UI** (§4).
- **vibe (Python CLI):** `vibe resume <ticket>` (resolve → recreate/connect worktree → unwind if tip is the marker → relaunch → set `doing`; non-Claude tools launch fresh), plus **post-session worktree cleanup** (match by repo + branch, no `--force`) and the **`vibe --clean`** sweep of `on_hold` worktrees. vibe is a **third implementer of the ticket format** — it writes `state: doing` and clears `worktree` on cleanup — so it needs its own lenient, field-preserving frontmatter read/update.
- **Claude Code skill (the vibeboard skill):** the agent's in-session interface — park (incl. create-on-park, the main-checkout flow, the empty-park case; ends at note → commit → state, **no worktree removal**), create a Todo / add a note / move a ticket, and session-id capture via the `.jsonl` scan. It **embeds the ticket format spec** and must be **installed on the VM (`~/.claude`)** — the vm-setup guide needs a line for this. No resume skill; resume is CLI-only. No hooks.
- **Native Mac app (the board):** Swift parser (lenient), FSEvents watch (no poll), add Todos/notes, set priority, drag between states, **copy-`vibe resume`-command button**.

## 9. Prerequisite work in `vibe`

**Fix branch names containing `/` before building on top.** The example branch `feature/retry-upload` breaks vibe today: the worktree nests as `_vibecoding/<repo>/feature/retry-upload` and context detection misparses the worktree name. Since the agent will be *inventing* branch names at park, slashes will happen. This is a prerequisite, not a nice-to-have. Whatever encoding replaces `/` in worktree directory names, **branch ↔ directory must map deterministically in both directions** — resume reconstructs the worktree path from the ticket's `branch` field, so the mapping has to be reversible.

## 10. Deliverables

Four artifacts plus a prerequisite. The **store format** is the shared contract; **three independent implementers** — the skill, the Swift app, and Python `vibe` — each read and write it, with no shared library.

**0. Prerequisite:** the `vibe` slash-in-branch-name fix, with a reversible branch ↔ directory mapping (§9).

**1. Store location + format spec** — the contract.
- The `<repo-base>/_vibeboard` location and file-naming rules.
- A written ticket format spec (frontmatter schema §8.1 + body conventions). No read/write library; the skill, the Swift app, **and Python `vibe`** each implement it, with **lenient reads and field-preserving writes** on all three sides.

**2. `vibe resume` + worktree lifecycle** (extends existing `vibe`).
- `vibe resume <ticket>`: idempotent across the state × worktree matrix (§6.3), unwind-only-if-marker, launch plumbing for SSH + local paths and the fixed bootstrap prompt.
- Post-session worktree cleanup + `vibe --clean` sweep of `on_hold` worktrees.

**3. The vibeboard skill** (installed on the VM, `~/.claude`).
- Park: create-on-park, the main-checkout branch-and-switch-back flow, the park commit (incl. empty-park), next-step note, `state: on_hold`. No worktree removal.
- Todo / note / move-ticket on request.
- Session-id capture via the `.jsonl` scan with the this-conversation sanity check.
- Embeds the format spec.

**4. The native Mac app** — the board.
- Swift ticket parser (lenient), FSEvents watch (no polling), kanban with the four state columns.
- Add/edit Todos and notes, set priority, drag between states, copy-`vibe resume`-command button.
- Show git context as information, never as state.

**Build order — step zero is an FSEvents spike.** Before committing the app architecture, run a low-fidelity check that FSEvents fires on the Mac for writes arriving from the VM through the share. First task of the build.

**Testing.** New `vibe` CLI behavior gets the same pytest treatment and coverage bar as the existing tooling. Highest-value test surfaces: the resume **state × worktree matrix** and the **park-commit unwind** logic.

## 11. Decisions and open questions

**Decided:**
- **v1 = Mac/tart setup only**; Windows/Hyper-V out of scope (§3).
- **Store at `<repo-base>/_vibeboard`**, a folder of per-ticket markdown files (not SQLite — §8.1). Board watches via **FSEvents (no poll)**; CLI/skill read fresh-on-invocation.
- **No shared library / plumbing CLI** — three independent implementers (skill, Swift app, Python vibe); **lenient reads + field-preserving writes** everywhere (round-trip unknown keys/body), every field optional on read.
- **Board copies a `vibe resume` command** — no resume button, no spawned terminal.
- **Worktree removal is deferred to vibe** (post-session, matched by repo + branch, never `--force`; plus `--clean`); the skill never removes the worktree it's running in.
- **Branch attaches at park, not at start**; **create-on-park** is the common case; park supports the **main-checkout** flow and **empty parks**.
- **Resume of a `todo` / `branch: null` ticket launches on the repo's main checkout and creates nothing** — branch is named only at park. Consequence: such todos share the main checkout until one parks onto its own branch.
- **Main-checkout park resets local `main` only when provably safe** — i.e. `main` is ahead of `origin/main` and every such commit was made this session; otherwise leave `main` alone and record it loudly. Never reset on uncertainty.
- **Non-Claude tools launch fresh on resume** (no session restore / bootstrap prompt); worktree, unwind, and state behave identically.
- **Session-id via `.jsonl` scan**, sanity-checked — no hooks.
- **Ticket id = `<repo-name>-<number>`**, exclusive-create on new tickets. Single `repo` field (name); the old `project` field is folded into it.
- **No remote push**; **freeform tickets, no checklists**; **park only on explicit wrap-up**; **no merge detection**; **no drift nudge** (a `doing` ticket whose window closed without parking stays `doing`; idempotent resume absorbs it).
- **Resume rebuild trade-off**: park removes the worktree (via vibe), resume recreates it; gitignored env is rebuilt and needed-but-ignored files (`.env`) are a known wrinkle — iterate in practice (optional per-repo setup command, or symlink stable-location files).

**Resolved / explicitly not concerns:**
- Park commits reaching main history on merge — the merger's responsibility (squash-merge); deliberate.
- Windows quoting / PowerShell arg-threading — out of scope with the Windows setup.
- Hook-based session capture — rejected in favor of the `.jsonl` scan.

**Still open:** Nothing blocking. Remaining choices (the exact number source within `<repo-name>-<number>`, the per-repo resume-setup behavior) surface naturally during implementation.