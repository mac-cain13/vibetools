---
name: linear-cli
description: Manage Linear issues, projects, and cycles from the command line with the `linear` CLI. Use whenever the user references Linear — a Linear issue/ticket (e.g. ENG-123), "my Linear issues", creating/updating/commenting on issues, projects, cycles, initiatives, or milestones — to read and mutate Linear without leaving the terminal.
---

# Linear CLI

`linear` is schpet's first-party-style CLI for [Linear](https://linear.app),
installed via Homebrew at `/opt/homebrew/bin/linear` (`brew install
schpet/tap/linear`). It manages issues, comments, projects, cycles, initiatives,
milestones, labels, and teams, with git/jj branch-name integration, and can drop
to the raw GraphQL API when the CLI doesn't cover something.

> This skill is a compact, brew-binary-oriented trim of Linear's upstream skill.
> Canonical source: https://github.com/schpet/linear-cli/blob/main/skills/linear-cli/SKILL.md
> The upstream version ships full `references/` docs and `scripts/`. Re-sync the
> gotchas below from upstream occasionally, or read a command's `--help`.

## When to use it

- The user names a Linear issue (`ENG-123`), asks to create/update/comment on
  one, or wants "my issues" → `linear issue view ENG-123`, `linear issue mine`,
  `linear issue create`, `linear issue comment add`.
- Working a ticket whose branch/dir encodes the issue → `linear issue view` and
  `linear issue start` infer the issue from the current git branch name.
- Projects, cycles, initiatives, milestones, labels, teams → the matching
  top-level command group.

## Discovering commands (do this instead of memorizing them)

The CLI is broad and moves quickly — **ask the tool, don't rely on a hardcoded
list.** These stay correct no matter how Linear changes it:

```bash
linear --version
linear --help                # top-level command groups
linear <group> --help        # e.g. linear issue --help
linear <group> <cmd> --help  # e.g. linear issue create --help  (shows required flags)
```

## Auth & context

- Check with `linear auth whoami`; log in with `linear auth login`.
- Most commands act against a team. If it can't be inferred from the current
  directory/branch, pass `--team <KEY>`; `linear team list` shows the keys.

## Non-obvious gotchas

- **Markdown content → use file-based flags, not inline.** For issue
  descriptions and comment bodies, prefer `--description-file` (on `issue
  create`/`issue update`) and `--body-file` (on `comment add`/`comment update`)
  over `--description`/`--body`. Passing multi-line markdown inline mangles
  formatting and leaks literal `\n`. Write the body to a temp file, then pass the
  path. Inline flags are fine only for simple single-line content.
- **`issue list` needs a sort and usually a team.** It requires `--sort`
  (`manual` or `priority`; or the `LINEAR_ISSUE_SORT` env var / `issue_sort`
  config), plus `--team <KEY>` unless the team is inferable from the directory.
- **`--no-pager` is only valid on `issue list`.** Passing it elsewhere (e.g.
  `project list`) errors.

## GraphQL API fallback

**Prefer the CLI for anything it supports.** Only drop to `linear api` for
queries the CLI doesn't cover.

```bash
# Inspect the schema first
linear schema -o "${TMPDIR:-/tmp}/linear-schema.graphql"
grep -A 30 "^type Issue " "${TMPDIR:-/tmp}/linear-schema.graphql"

# Simple query (no non-null "!" markers) can go inline
linear api '{ viewer { id name email } }' | jq '.data.viewer'

# Queries with non-null type markers (String!, Int! …) MUST use heredoc stdin —
# inline shell escaping breaks the "!" markers
linear api --variable term=onboarding <<'GRAPHQL'
query($term: String!) { searchIssues(term: $term, first: 20) { nodes { identifier title } } }
GRAPHQL
```

For full HTTP control, `linear auth token` yields a bearer token for `curl` against `https://api.linear.app/graphql`.
