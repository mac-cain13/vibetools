---
name: peekaboo
description: "Use Peekaboo for macOS desktop automation, screenshots, visual UI maps, native accessibility inspection, and app/window/menu/dialog control. Use when you need the current macOS UI state, direct desktop control, or to click/type/drive a native app or browser chrome on this machine."
---

# Peekaboo

Peekaboo is a macOS automation CLI and agent runtime that combines high-fidelity screen capture, AI screen analysis, and native GUI automation. On our VMs it is installed via Homebrew and available on `PATH` as `peekaboo`. Prefer live `--help` and `peekaboo learn` over memorized flags — the command surface moves quickly.

> This skill is an adapted, brew-binary-oriented trim of Peekaboo's upstream skill.
> Canonical source: https://github.com/openclaw/Peekaboo/blob/main/skills/peekaboo/SKILL.md
> (The upstream version is written for the Peekaboo repo itself — building the CLI from
> source, repo lint/validation — which does not apply to our brew install. Re-sync the
> observation strategy / operating-rules sections from upstream occasionally.)

## Start Here

```bash
command -v peekaboo && peekaboo --version   # confirm install
peekaboo permissions status --json          # Screen Recording + Accessibility must be granted
peekaboo tools --json                        # current tool surface
peekaboo learn                               # full agent guide
peekaboo <command> --help                    # canonical, always-current help
```

If a capture or control fails, check `peekaboo permissions status --json` before assuming it's a bug — most failures are missing Screen Recording or Accessibility permission. Over SSH the permissions attach to the SSH host process (`sshd-keygen-wrapper`), not to peekaboo itself.

## Observation Strategy

- Use `peekaboo inspect-ui` for native macOS accessibility (AX) text, labels, buttons, text fields, control state, and element IDs when a screenshot would add noise.
- Use `peekaboo see` for screenshots, visual layout, annotated maps, pixels/colors, screen/menu-bar targets, or when AX text is missing or incomplete.
- Use `peekaboo browser` for browser page content, forms, DOM/a11y snapshots, console, network, and page screenshots when browser tooling is available.
- Use native Peekaboo tools for app chrome, browser toolbars, menus, dialogs, permissions, and windows.
- Treat element IDs from `see`/`inspect-ui` as valid only for the current visible state. After any mutating action, re-verify from the action result or fetch fresh state.

## Operating Rules

- Run `peekaboo see --json --path /tmp/<name>.png` or `peekaboo inspect-ui --json` before element interactions so you have fresh element IDs and a snapshot ID.
- Prefer the exact element ID string from the current snapshot for clicks/typing; treat ID shapes as opaque. Use labels when IDs are unavailable, and coordinates only as a last resort.
- Pass `--json` whenever another tool or agent needs to parse results.
- Respect the user's desktop: avoid destructive app/window actions unless requested. Write capture artifacts to `/tmp` so they don't land in user-visible locations.
- `see --json` element `bounds` are screen coordinates; snapshot IDs keep element actions tied to the observed UI.
- Background input delivery is the default when Peekaboo can resolve a target process. Use `--foreground` only when an app requires a key window, Space switch, or foreground mouse event.
- If a command fails because the UI changed, recapture with `see`/`inspect-ui` before retrying.

## Common Workflows

```bash
# AX-only state when a screenshot would add noise.
peekaboo inspect-ui --app-target Calculator --json > /tmp/peekaboo-calc-ax.json

# Visual layout plus element IDs and snapshot ID.
peekaboo see --app Calculator --path /tmp/calc.png --json > /tmp/calc.json

# Pull the snapshot ID + a slimmed element list from the capture.
ruby -rjson -e 'j=JSON.parse(File.read("/tmp/calc.json")); puts j.dig("data","snapshot_id"); puts JSON.pretty_generate((j.dig("data","ui_elements")||[]).map{|e| e.slice("id","label","identifier","bounds")})'

# Click an element discovered in the current snapshot (opaque ID + snapshot).
SNAP=$(ruby -rjson -e 'j=JSON.parse(File.read("/tmp/calc.json")); puts j.dig("data","snapshot_id")')
ELEMENT_ID="<element-id-from-current-snapshot>"
peekaboo click --on "$ELEMENT_ID" --snapshot "$SNAP" --json

# Type text into the focused/target field.
peekaboo type "hello" --json

# Direct accessibility action — cleanest way to prove a control fires, independent of pointer events.
peekaboo perform-action --on "$ELEMENT_ID" --action AXPress --snapshot "$SNAP" --json

# Menus and menu bar.
peekaboo menu list --app Safari --json

# Browser page content vs. browser chrome:
peekaboo browser status --json           # page content / DOM belongs to browser tooling
peekaboo menu list --app Safari --json   # toolbars, menus, native chrome stay with Peekaboo
```

## Input Paths

Peekaboo has two input paths, useful when smoke-testing which layer works:

- **UIAX/action path** — accessibility actions such as `AXPress`, `AXSetValue`. Use `peekaboo click --input-strategy actionOnly` or `peekaboo perform-action --action AXPress`. Success proves live AX re-resolution and action invocation.
- **Synthetic path** — pointer/keyboard CGEvent-style delivery. Use `peekaboo click --input-strategy synthOnly` (often with `--foreground`). Success proves coordinate resolution and event delivery, but verify resulting app state independently.

Coordinates cannot use `actionOnly` (they have no AX element to act on) — that's a useful negative control.

## Notes

- Keep this skill compact and rely on live help; don't hardcode the full command reference here.
- Homebrew install: `brew install steipete/tap/peekaboo`. There is also an MCP server (`npx -y @steipete/peekaboo`, Node 22+) if MCP integration is preferred over the CLI.
