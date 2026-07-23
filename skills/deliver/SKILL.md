---
name: deliver
description: Hand the user a build they can run — for macOS, drop a signed, double-clickable .app in a folder and give them the path; for iOS, drop the signed device build in a folder and print the xcrun command they paste to install it on their connected iPhone. Use when you've finished a user-visible change and the user would benefit from trying it, or when they ask for a build ("give me the app", "let me test it", "can I try it"). macOS and iOS (physical device) today; iOS Simulator and web delivery are not implemented yet.
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
script. You do the first part; `deliver-mac-app` does the second — and it is the only
thing that touches the delivered folder. You never place, move, rename, or copy the
`.app` yourself, on a first delivery or an update. Hand-moving a bundle onto a folder
that already holds a `.app` of the same name nests the new one *inside* the old instead
of replacing it — the exact silent failure this script exists to prevent.

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
stages the copy and swaps it into place so a half-copied or nested bundle never lands at
the clickable path, writes a `BUILD-INFO.txt` next to the app recording
branch/commit/dirty state, and prints the delivered path.

**Updating a delivered build is this same command, again.** Re-run it with the new build
and it replaces the previous bundle in place, at the same path the user is already
clicking. Keep pointing them at that path — don't move the delivered app somewhere
"nicer", and never `mv`/`cp` a fresh `.app` over the delivered one to freshen it. That
hand-move is exactly where the nesting trap bites; let the script do the replace.

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

## iOS — deliver to a physical device

Same shape as macOS: build signed once, then a script copies the app into the same
git-derived `_Builds/<project>/<branch>/` folder. The difference is the last step — an
iOS `.app` can't launch on the Mac, so instead of a clickable app you hand the user a
ready-to-paste `xcrun` command that installs it on their connected iPhone.

### 1. Build it — signed, for a device

Build the iOS scheme for a *device* destination (not the simulator), signed:

```bash
xcodebuild -project <proj> -scheme <scheme> \
  -destination 'generic/platform=iOS' -allowProvisioningUpdates \
  -derivedDataPath <dd> | xcbeautify
```

`generic/platform=iOS` (not `iOS Simulator`) is what makes it a device build; a simulator
or unsigned build can't install on a phone. The target device must already be registered
to the signing team — a one-time step done from Xcode or the developer portal. Same two
rules as macOS: build signed (never `CODE_SIGNING_ALLOWED=NO`), and don't build twice —
reuse the DerivedData path you compile-checked with.

### 2. Deliver it

```bash
BUILT=$(xcodebuild -showBuildSettings -project <proj> -scheme <scheme> \
  -destination 'generic/platform=iOS' -derivedDataPath <same-dd> 2>/dev/null \
  | awk -F' = ' '/ BUILT_PRODUCTS_DIR = /{d=$2} / FULL_PRODUCT_NAME = /{n=$2} END{print d"/"n}')
~/.claude/skills/deliver/deliver-ios-device "$BUILT"
```

Pass `-showBuildSettings` the *same* flags you built with (above all `-derivedDataPath`),
for the same reason as macOS: omit them and it resolves some other build entirely.

`deliver-ios-device` verifies the signature and that an `embedded.mobileprovision` is
present — refusing a simulator or unsigned build that wouldn't install — stages the copy
and swaps it into the git-derived folder so no half-copied or nested bundle lands at the
install path, writes `BUILD-INFO.txt`, and prints the `xcrun devicectl device install app`
command to paste on the host. As with macOS, updating is this same command again — it
replaces the delivered bundle in place; never `mv`/`cp` a fresh `.app` over it by hand.

Give the user that printed command verbatim, plus a one-line note of what's in the build.
They paste it in a Terminal on the host with the iPhone connected and unlocked, and the
app installs to the home screen. The device UDID has a personal default baked in for now;
pass a different UDID as the second argument to override it.

## Still not implemented

The iOS *Simulator* path and web apps over a tunnel are not built yet. If asked for
either, say so rather than improvising a delivery mechanism.
