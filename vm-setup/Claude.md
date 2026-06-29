# About the setup

You're running in a Virtual Machine, we're working on the same files through a shared drive. I'm working on the host, so if I say something doesn't build on my machine, I'm talking about my host machine which might be slightly different from your machine. Also if you want to show something to me make sure to serve it on the local network so I can access it or if you present a file path use the /Volumes/External/ prefix path because that is the same on my machine.

# Branching

Don't create a new branch unless explicitly asked by the user. The default is that we want to commit on the branch we're working on, even if this is the main branchy.

# Swift Code Style

- **No `@unchecked Sendable`** - Never use `@unchecked Sendable` without explicit approval. Always implement proper `Sendable` conformance. Only as a last resort, with explicit user approval, is `@unchecked Sendable` allowed.
- **File headers** - Every Swift file should have a header comment aligning with other files in the project
- **Error logging** - Always log errors as `(error as NSError).debugDescription` for complete error information
- **Protocols only when needed** - Only create protocols when multiple implementations exist or for testing
- **SwiftDoc comments** - Write and maintain short and pragmatic documentation comments for all public and internal functions

# Improved Xcode builds

You must always pipe any `xcodebuild` command you execute through `xcbeautify` for a more compact build output that easier to parse and gives better error information.

Example: 
  This: `xcodebuild -project Bezel.xcodeproj -scheme "iOS" -destination "platform=iOS Simulator,name=iPhone 16 Pro Max"`
  Should become: `xcodebuild -project Bezel.xcodeproj -scheme "iOS" -destination "platform=iOS Simulator,name=iPhone 16 Pro Max" | xcbeautify`

# Available tools

These tools and their dependencies are installed and available to use if you might need them: ripgrep jq fd fzf bat tree yq htmlq gh git-delta hyperfine watch tldr pandoc xcbeautify imagemagick ffmpeg sentry
- If you need an iOS simulator use "iPhone 17 Pro" as other simulators might not be available. If you need to use another simulator first check `xcrun simctl list devices available` for available simulators instead of guessing as mentioning a non-existing simulator takes a lot of time.

# Git quirks

- **`fatal: unable to write new index file`** — this is transient and self-heals. Retry the same git command. It's perfectly fine for the retry to error too; just keep retrying — typically 3–5 attempts will get through. Do NOT attempt repair tactics (no inspecting `.git` internals, checking for `index.lock`, switching working directories, or rewriting the index). Those interventions cause more harm than the wait. Retry is the only correct response.
  - **How to retry**: prefer a bare retry of the same command — no leading `sleep`. The condition self-heals very quickly (often by the time the next tool call dispatches), so a bare retry usually works. If a retry still fails, you may chain a *short* sleep in front (e.g. `sleep 5 && git …`, `sleep 10 && git …`); the Bash runtime blocks long leading sleeps (≳30s) anyway, and a long sleep is the wrong shape — many short retries beat one big wait. Don't escalate the sleep duration past ~10s; just retry again.
