# Vibe - Git Worktree Manager

## Project Overview

A Python CLI tool for managing git worktrees with remote SSH development support. Built with Typer and Rich.

## Setup

Install in development mode:
```bash
pip install -e ".[dev]"
```

Or use the install script (requires `uv`):
```bash
./install.sh
```

## Development Commands

### Run Tests (ALWAYS do this before completing work)
```bash
python3 -m pytest tests/ -v
```

### Run Tests with Coverage
```bash
python3 -m pytest tests/ -v --cov=vibe --cov-report=term-missing
```

### Run Specific Test File
```bash
python3 -m pytest tests/test_cli_integration.py -v
```

### Run the CLI During Development
```bash
python3 -m vibe --help
python3 -m vibe                      # Connect to current repo/worktree
python3 -m vibe feature-branch --cc  # Use cloud code
python3 -m vibe feature-branch --oc  # Use open code
```

## Project Structure

```
vibe/
├── __init__.py      # Package init
├── __main__.py      # Entry point for python -m vibe
├── cli.py           # Typer CLI interface
├── config.py        # Constants (paths, SSH settings)
├── connection.py    # SSH and local connection handling
├── cleanup.py       # Worktree cleanup operations
├── git_ops.py       # Git operations (worktree, branch management)
└── utils.py         # Shared utilities (console, formatting)

tests/
├── test_cli_integration.py  # CLI integration tests
├── test_cleanup.py          # Cleanup module tests
├── test_connection.py       # Connection module tests
└── test_git_ops.py          # Git operations tests
```

## Key Files

- `vibe/config.py` - All configurable constants (SSH key path, remote host, worktree paths)
- `vibe/cli.py` - Main entry point, handles all CLI flags and routing
- `pyproject.toml` - Project metadata, dependencies, and tool configuration

## Testing Requirements

- **Always run tests** before considering work complete
- Target: All 96+ tests passing
- Coverage target: >80%
- Tests use `pytest` with `pytest-cov` for coverage
- Mock external calls (subprocess, file system) in tests

## Code Style

- Python 3.9+ compatible (use `from __future__ import annotations`)
- Type hints on all functions
- Docstrings with Args/Returns sections
- Use `Path` objects for file paths
- Use `shlex.quote()` for shell escaping
