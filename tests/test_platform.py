"""Tests for platform detection module."""

from __future__ import annotations

from unittest.mock import mock_open, patch

import pytest

from vibe.platform import Platform, Shell, detect_platform


class TestPlatform:
    """Tests for Platform enum."""

    def test_macos_value(self) -> None:
        """Should have correct value for MACOS."""
        assert Platform.MACOS.value == "macos"

    def test_wsl_value(self) -> None:
        """Should have correct value for WSL."""
        assert Platform.WSL.value == "wsl"


class TestDetectPlatform:
    """Tests for detect_platform function."""

    def test_env_override_wsl(self) -> None:
        """Should return WSL when VIBE_PLATFORM=wsl."""
        with patch.dict("os.environ", {"VIBE_PLATFORM": "wsl"}):
            assert detect_platform() == Platform.WSL

    def test_env_override_macos(self) -> None:
        """Should return MACOS when VIBE_PLATFORM=macos."""
        with patch.dict("os.environ", {"VIBE_PLATFORM": "macos"}):
            assert detect_platform() == Platform.MACOS

    def test_env_override_case_insensitive(self) -> None:
        """Should handle case-insensitive env var values."""
        with patch.dict("os.environ", {"VIBE_PLATFORM": "WSL"}):
            assert detect_platform() == Platform.WSL

        with patch.dict("os.environ", {"VIBE_PLATFORM": "MACOS"}):
            assert detect_platform() == Platform.MACOS

    def test_darwin_detected_as_macos(self) -> None:
        """Should detect darwin as macOS."""
        with patch.dict("os.environ", {}, clear=True):
            with patch("vibe.platform.sys") as mock_sys:
                mock_sys.platform = "darwin"
                assert detect_platform() == Platform.MACOS

    def test_linux_with_microsoft_in_proc_version(self) -> None:
        """Should detect Linux with 'microsoft' in /proc/version as WSL."""
        with patch.dict("os.environ", {}, clear=True):
            with patch("vibe.platform.sys") as mock_sys:
                mock_sys.platform = "linux"
                proc_content = (
                    "Linux version 5.15.90.1-microsoft-standard-WSL2 "
                    "(gcc (GCC) 11.2.0)"
                )
                with patch("builtins.open", mock_open(read_data=proc_content)):
                    assert detect_platform() == Platform.WSL

    def test_linux_with_wsl_in_proc_version(self) -> None:
        """Should detect Linux with 'WSL' in /proc/version as WSL."""
        with patch.dict("os.environ", {}, clear=True):
            with patch("vibe.platform.sys") as mock_sys:
                mock_sys.platform = "linux"
                proc_content = "Linux version 5.15.90.1-WSL2 (gcc 11.2.0)"
                with patch("builtins.open", mock_open(read_data=proc_content)):
                    assert detect_platform() == Platform.WSL

    def test_linux_without_wsl_markers(self) -> None:
        """Should detect plain Linux as WSL (project assumption)."""
        with patch.dict("os.environ", {}, clear=True):
            with patch("vibe.platform.sys") as mock_sys:
                mock_sys.platform = "linux"
                proc_content = "Linux version 6.1.0-generic (gcc 12.3.0)"
                with patch("builtins.open", mock_open(read_data=proc_content)):
                    assert detect_platform() == Platform.WSL

    def test_linux_proc_version_not_readable(self) -> None:
        """Should fall back to WSL when /proc/version is not readable."""
        with patch.dict("os.environ", {}, clear=True):
            with patch("vibe.platform.sys") as mock_sys:
                mock_sys.platform = "linux"
                with patch("builtins.open", side_effect=OSError):
                    assert detect_platform() == Platform.WSL

    def test_unknown_platform_falls_back_to_macos(self) -> None:
        """Should fall back to macOS for unknown platforms."""
        with patch.dict("os.environ", {}, clear=True):
            with patch("vibe.platform.sys") as mock_sys:
                mock_sys.platform = "win32"
                assert detect_platform() == Platform.MACOS

    def test_env_override_takes_priority_over_sys_platform(self) -> None:
        """Env var should override sys.platform detection."""
        with patch.dict("os.environ", {"VIBE_PLATFORM": "wsl"}):
            with patch("vibe.platform.sys") as mock_sys:
                mock_sys.platform = "darwin"
                assert detect_platform() == Platform.WSL

    def test_empty_env_var_ignored(self) -> None:
        """Should ignore empty VIBE_PLATFORM env var."""
        with patch.dict("os.environ", {"VIBE_PLATFORM": ""}):
            with patch("vibe.platform.sys") as mock_sys:
                mock_sys.platform = "darwin"
                assert detect_platform() == Platform.MACOS


class TestShell:
    """Tests for Shell enum."""

    def test_wsl_value(self) -> None:
        """Should have correct value for WSL."""
        assert Shell.WSL.value == "wsl"

    def test_powershell_value(self) -> None:
        """Should have correct value for POWERSHELL."""
        assert Shell.POWERSHELL.value == "powershell"
