"""Tests for shared Claude Code and Codex skill installation."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


INSTALLER = Path(__file__).parents[1] / "install.sh"


def make_skill(root: Path, name: str) -> Path:
    """Create the minimum valid shape for an agent skill."""
    skill = root / name
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Test skill.\n---\n"
    )
    return skill


def run_installer(
    user_root: Path, source: Path, *, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Run the inline skill installer against an isolated user directory."""
    environment = os.environ.copy()
    environment["VIBE_AGENT_HOME"] = str(user_root)
    return subprocess.run(
        [
            "/bin/bash",
            "-c",
            'source "$1"; install_agent_skills "$2"',
            "test-agent-skill-install",
            str(INSTALLER),
            str(source),
        ],
        capture_output=True,
        check=False,
        cwd=cwd,
        env=environment,
        text=True,
    )


def test_fresh_install_links_both_agents(tmp_path: Path) -> None:
    """A fresh install should expose repository skills through both roots."""
    source = tmp_path / "source"
    expected = make_skill(source, "example")
    user_root = tmp_path / "user"

    result = run_installer(user_root, Path("source"), cwd=tmp_path)

    claude_skill = user_root / ".claude" / "skills" / "example"
    codex_root = user_root / ".agents" / "skills"
    assert result.returncode == 0, result.stderr
    assert claude_skill.resolve() == expected.resolve()
    assert codex_root.is_symlink()
    assert (codex_root / "example").resolve() == expected.resolve()


def test_matching_codex_directory_is_preserved_then_shared(tmp_path: Path) -> None:
    """Equivalent Codex links should be backed up before sharing the root."""
    source = tmp_path / "source"
    expected = make_skill(source, "example")
    user_root = tmp_path / "user"
    claude_root = user_root / ".claude" / "skills"
    codex_root = user_root / ".agents" / "skills"
    claude_root.mkdir(parents=True)
    codex_root.mkdir(parents=True)
    (claude_root / "example").symlink_to(expected)
    (codex_root / "example").symlink_to(expected)

    result = run_installer(user_root, source)

    backups = list((user_root / ".agents").glob("skills.before-shared-*"))
    assert result.returncode == 0, result.stderr
    assert codex_root.is_symlink()
    assert len(backups) == 1
    assert (backups[0] / "example").resolve() == expected.resolve()


def test_install_is_idempotent_and_future_skills_are_shared(tmp_path: Path) -> None:
    """Repeated installs should not add backups and new Claude skills stay visible."""
    source = tmp_path / "source"
    make_skill(source, "example")
    user_root = tmp_path / "user"

    first = run_installer(user_root, source)
    second = run_installer(user_root, source)
    future = make_skill(user_root / ".claude" / "skills", "future")

    codex_root = user_root / ".agents" / "skills"
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert not list((user_root / ".agents").glob("skills.before-shared-*"))
    assert (codex_root / "future").resolve() == future.resolve()


def test_conflicting_codex_skills_are_not_overwritten(tmp_path: Path) -> None:
    """A Codex-only skill should stop migration without losing its files."""
    source = tmp_path / "source"
    make_skill(source, "example")
    user_root = tmp_path / "user"
    unique = make_skill(user_root / ".agents" / "skills", "codex-only")

    result = run_installer(user_root, source)

    codex_root = user_root / ".agents" / "skills"
    assert result.returncode == 1
    assert "contains skills not mirrored" in result.stderr
    assert not codex_root.is_symlink()
    assert (unique / "SKILL.md").is_file()
