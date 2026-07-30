"""Tests for the herdr integration module."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from vibe.herdr import (
    _reexec_argv,
    clear_pane,
    ensure_agent_hint,
    in_herdr,
    resolve_agent,
)


class TestInHerdr:
    """Tests for in_herdr function."""

    def test_detects_pane_marker(self) -> None:
        """HERDR_ENV is the marker herdr exports into every pane."""
        assert in_herdr(env={"HERDR_ENV": "1"}) is True

    def test_detects_socket_path(self) -> None:
        """Should also accept the socket path marker."""
        assert in_herdr(env={"HERDR_SOCKET_PATH": "/tmp/herdr.sock"}) is True

    def test_false_outside_herdr(self) -> None:
        """Should be False with no herdr markers present."""
        assert in_herdr(env={"PATH": "/bin"}) is False

    def test_empty_marker_does_not_count(self) -> None:
        """An empty marker value should not read as being inside herdr."""
        assert in_herdr(env={"HERDR_ENV": ""}) is False


class TestResolveAgent:
    """Tests for resolve_agent function."""

    def test_maps_claude_wrapper(self) -> None:
        """Should map the Claude Code wrapper to the claude manifest."""
        assert resolve_agent("cly") == "claude"

    def test_maps_codex_wrapper(self) -> None:
        """Should map the Codex wrapper to the codex manifest."""
        assert resolve_agent("cdx") == "codex"

    def test_maps_opencode(self) -> None:
        """Should map OpenCode to the opencode manifest."""
        assert resolve_agent("opencode") == "opencode"

    def test_ignores_tool_arguments(self) -> None:
        """Should key off the executable, not the whole command."""
        assert resolve_agent("cly --resume abc123") == "claude"

    def test_maps_direct_commands(self) -> None:
        """Should map the PowerShell direct commands too."""
        assert resolve_agent("claude --dangerously-skip-permissions") == "claude"

    def test_returns_none_for_unknown_tool(self) -> None:
        """Should send no hint for a tool it does not recognise."""
        assert resolve_agent("some-other-agent") is None


class TestEnsureAgentHint:
    """Tests for ensure_agent_hint function."""

    @patch("vibe.herdr.os.execv")
    def test_reexecs_inside_herdr(self, mock_execv: MagicMock) -> None:
        """Should re-exec with HERDR_AGENT set when the hint is missing."""
        env = {"HERDR_ENV": "1"}
        with patch.dict("vibe.herdr.os.environ", env, clear=True):
            ensure_agent_hint("cly")

        mock_execv.assert_called_once()

    @patch("vibe.herdr.os.execv")
    def test_sets_hint_and_tool_before_reexec(self, mock_execv: MagicMock) -> None:
        """Should carry the agent and the resolved tool across the re-exec."""
        captured = {}
        mock_execv.side_effect = lambda *_: captured.update(
            __import__("os").environ
        )

        with patch.dict("vibe.herdr.os.environ", {"HERDR_ENV": "1"}, clear=True):
            ensure_agent_hint("cly")

        assert captured["HERDR_AGENT"] == "claude"
        assert captured["VIBE_CODING_TOOL"] == "cly"

    @patch("vibe.herdr.os.execv")
    def test_no_reexec_outside_herdr(self, mock_execv: MagicMock) -> None:
        """Should do nothing when not running inside a herdr pane."""
        with patch.dict("vibe.herdr.os.environ", {}, clear=True):
            ensure_agent_hint("cly")

        mock_execv.assert_not_called()

    @patch("vibe.herdr.os.execv")
    def test_no_reexec_when_hint_already_correct(self, mock_execv: MagicMock) -> None:
        """An existing correct hint is what stops the re-exec from looping."""
        env = {"HERDR_ENV": "1", "HERDR_AGENT": "claude"}
        with patch.dict("vibe.herdr.os.environ", env, clear=True):
            ensure_agent_hint("cly")

        mock_execv.assert_not_called()

    @patch("vibe.herdr.os.execv")
    def test_user_set_hint_wins_over_mapping(self, mock_execv: MagicMock) -> None:
        """`HERDR_AGENT=<name> vibe ...` should override vibe's own mapping."""
        env = {"HERDR_ENV": "1", "HERDR_AGENT": "kimi"}
        with patch.dict("vibe.herdr.os.environ", env, clear=True):
            ensure_agent_hint("cly")
            assert os.environ.get("HERDR_AGENT") == "kimi"

        mock_execv.assert_not_called()

    @patch("vibe.herdr.os.execv")
    def test_no_reexec_for_unknown_tool(self, mock_execv: MagicMock) -> None:
        """Should do nothing when the tool maps to no manifest."""
        with patch.dict("vibe.herdr.os.environ", {"HERDR_ENV": "1"}, clear=True):
            ensure_agent_hint("some-other-agent")

        mock_execv.assert_not_called()

    @patch("vibe.herdr.os.execv", side_effect=OSError(8, "Exec format error"))
    def test_survives_a_failed_reexec(self, mock_execv: MagicMock) -> None:
        """A failed re-exec should warn and continue, not crash the session."""
        with patch.dict("vibe.herdr.os.environ", {"HERDR_ENV": "1"}, clear=True):
            ensure_agent_hint("cly")  # must not raise

        import vibe.herdr as herdr_module

        assert herdr_module.os.environ.get("VIBE_CODING_TOOL") is None


class TestClearPane:
    """Tests for clear_pane function."""

    def test_clears_inside_herdr(self, capsys) -> None:
        """Should emit the clear sequence when running in a herdr pane."""
        with patch.dict("vibe.herdr.os.environ", {"HERDR_ENV": "1"}, clear=True):
            clear_pane()

        # erase-display is the part that purges herdr's detection buffer
        assert "\033[2J" in capsys.readouterr().out

    def test_silent_outside_herdr(self, capsys) -> None:
        """Should leave vibe's output alone when not inside herdr."""
        with patch.dict("vibe.herdr.os.environ", {}, clear=True):
            clear_pane()

        assert capsys.readouterr().out == ""


class TestReexecArgv:
    """Tests for _reexec_argv function."""

    def test_uses_module_form_for_python_m(self) -> None:
        """`python -m vibe` should be re-exec'd the same way."""
        with patch("vibe.herdr.sys.argv", ["/some/vibe/__main__.py", "branch"]):
            with patch("vibe.herdr.sys.executable", "/usr/bin/python3"):
                assert _reexec_argv() == [
                    "/usr/bin/python3",
                    "-m",
                    "vibe",
                    "branch",
                ]

    def test_resolves_console_script(self) -> None:
        """The installed console script should be re-exec'd by absolute path."""
        with patch("vibe.herdr.sys.argv", ["vibe", "branch", "--claude"]):
            with patch("vibe.herdr.shutil.which", return_value="/usr/local/bin/vibe"):
                assert _reexec_argv() == [
                    "/usr/local/bin/vibe",
                    "branch",
                    "--claude",
                ]

    def test_falls_back_to_argv0(self) -> None:
        """Should fall back to argv[0] when it is not on PATH."""
        with patch("vibe.herdr.sys.argv", ["./vibe", "branch"]):
            with patch("vibe.herdr.shutil.which", return_value=None):
                assert _reexec_argv() == ["./vibe", "branch"]

    def test_hands_a_plain_script_to_the_interpreter(self) -> None:
        """A .py entry point may lack a shebang, so run it via python."""
        with patch("vibe.herdr.sys.argv", ["/opt/run_vibe.py", "branch"]):
            with patch("vibe.herdr.sys.executable", "/usr/bin/python3"):
                assert _reexec_argv() == [
                    "/usr/bin/python3",
                    "/opt/run_vibe.py",
                    "branch",
                ]
