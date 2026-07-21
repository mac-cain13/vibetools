---
name: deliver
description: Hand the user a build they can click to run — build the app, then drop a signed, double-clickable .app in a folder on their machine and give them the path. Use when you've finished a user-visible change to a macOS app and the user would benefit from clicking through it, or when they ask for a build ("give me the app", "let me test it", "can I try it"). macOS only today; iOS and web delivery are not implemented yet.
---

# Deliver — hand the user something they can click

Your job is to turn work you've finished into an app the user launches with one
double-click: no Xcode, no build step, no drag to /Applications. They click the path
you give them and the app opens.

**This is not the `run` or `verify` skill.** Those are for *you* to exercise a change
and check your own work. `deliver` is for handing a *human* something to click through.
Reach for it when the value is in them seeing the feature, not in them reading the diff
— they can review code in Xcode themselves.

Skip it when there's nothing to look at: refactors, backend-only work, or when the
user asked for a code review.

## The two steps

Building is different in every project. Delivering is the same everywhere, so it's a
script. You do the first part; `deliver-mac-app` does the second.

### 1. Build it — signed, once

Find the project's canonical build command rather than inventing one. In order:

1. The project's `CLAUDE.md` or `README.md` — most projects document it (e.g. a
   `## Build Commands` section, or a required `-derivedDataPath` workaround when the
   source sits on a network mount).
2. Otherwise `xcodebuild -list` and pick the macOS scheme — prefer a develop/debug
   variant over a release or App Store one.

Two rules that matter:

- **Build signed.** Pass `-allowProvisioningUpdates`; never `CODE_SIGNING_ALLOWED=NO`.
  An unsigned app cannot launch on another Mac, and `deliver-mac-app` will refuse it.
- **Don't build twice.** Use the *same* command, scheme and DerivedData path you'd use
  to check that your change compiles. Then that build *is* the delivered build, and
  delivery costs a copy instead of a second wait. If you compile-check unsigned and
  then rebuild signed to deliver, you've made the user wait twice for one result.

Pipe the build through `xcbeautify`, as always.

### 2. Deliver it

Resolve the built product, then hand it to the script from inside the project's repo:

```bash
BUILT=$(xcodebuild -showBuildSettings -project <proj> -scheme <scheme> -configuration <config> \
  -derivedDataPath <same-path-you-built-to> 2>/dev/null \
  | awk -F' = ' '/ BUILT_PRODUCTS_DIR = /{d=$2} / FULL_PRODUCT_NAME = /{n=$2} END{print d"/"n}')
~/.claude/skills/deliver/deliver-mac-app "$BUILT"
```

**Pass `-showBuildSettings` every flag you passed to the build** — above all
`-derivedDataPath`. Omit it and it reports the *default* DerivedData, so you resolve
some other build entirely: Xcode's, or another agent's. It won't error; it hands you a
real, plausible, wrong `.app`, and the user tests something you never built. If the
project builds to a custom DerivedData, this is the single easiest way to deliver a
stale app.

It figures out where the build belongs from git alone — no configuration, in any
project, from any worktree. It refuses to deliver an app that would crash on launch,
writes a `BUILD-INFO.txt` next to the app recording branch/commit/dirty state, and
prints the delivered path.

Then tell the user, in one line: the clickable path, and what's in the build (the
branch and what changed). Parallel worktrees get their own folder per branch, so two
agents working at once never overwrite each other's build.

## What to tell the user when it matters

- **It's a development build**, so it only runs on Macs registered to the signing team.
  On an unregistered Mac it won't launch — that needs the device added to the team.
- **Gatekeeper is not a problem.** `spctl` rejects development-signed apps, but that
  assessment only applies to *quarantined* files, and a build copied over a local mount
  or share never gets the quarantine flag. It just opens.
- **Apps with extensions** (File Provider, Finder, share extensions) register
  independently of the app. If an Xcode-built copy of the same bundle id is also
  registered, the system may keep using the old extension and the user will think they're
  looking at a stale build. Check the project for a registration-cleanup script.
- **Replacing a running app** is confusing — if a copy is already open, ask them to quit
  it first. The script warns when it sees one.

## Other platforms

Not implemented yet — this skill only delivers macOS apps today. iOS builds to a
physical device, and web apps over a tunnel, are the intended next steps. If asked for
either, say so rather than improvising a delivery mechanism.
