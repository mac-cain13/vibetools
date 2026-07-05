---
name: sentry
description: Investigate production errors, crashes, and user-reported issues with the `sentry` CLI (Sentry's first-party command-line tool). Use whenever a bug, crash, exception, failed request, performance regression, or "a user is seeing X" comes up and the project reports to Sentry — to search for the error, find similar occurrences, read stack traces and events, or pull Sentry's AI (Seer) analysis. Also for releases, replays, traces, logs, and dashboards.
---

# Sentry CLI

`sentry` is Sentry's official first-party CLI (installed via Homebrew at
`/opt/homebrew/bin/sentry`). It talks to the Sentry API: issues, events, traces,
logs, releases, replays, dashboards, and Seer AI analysis. When someone
describes a bug, a crash, or "a user is having an issue," reach for this to see
whether it's already in Sentry, find similar occurrences, and read the details.

## When to use it

- A user/report describes an error, crash, or misbehavior → search Sentry for a
  matching issue before guessing at causes.
- You're fixing a bug and want the real stack trace, breadcrumbs, frequency,
  affected releases, or a specific event's payload.
- You want Sentry's AI take: `sentry issue explain <issue>` (root-cause
  analysis) and `sentry issue plan <issue>` (suggested fix plan) via Seer.

Most read commands accept `--json`, so pipe into `jq` when you need to extract
fields or feed results into further work.

## Discovering commands (do this instead of memorizing them)

The CLI is broad and evolves — **don't rely on a hardcoded command list, ask the
tool itself.** These stay correct no matter how Sentry changes it:

```bash
sentry --help              # top-level command groups
sentry <group> --help      # e.g. sentry issue --help, sentry explore --help
sentry help <command>...   # long-form help with examples
sentry schema <resource>   # field/attribute schema for querying (e.g. issues)
```

Start with `sentry --help` to see the current surface, then drill in. Common
starting points are `sentry issue list`, `sentry issue view <issue>`, and
`sentry explore` for ad-hoc queries — but confirm flags via `--help` rather than
assuming.

## Auth & context

- Check auth with `sentry auth status`; `sentry auth login` if needed.
- Commands act against an org/project. If one isn't configured or inferable,
  `sentry org list` / `sentry project list` show what's available, and most
  issue commands take an `<org/project>` argument.
