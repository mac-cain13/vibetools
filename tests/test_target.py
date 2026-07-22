"""Tests for SSH target resolution (--vm / --host and env fallbacks)."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from vibe.config import SSH_USER_HOST
from vibe.connection import EPHEMERAL_HOSTKEY_OPTS
from vibe.target import (
    DEFAULT_USER,
    ENV_SSH_HOST,
    ENV_VM,
    Target,
    TargetError,
    resolve_target,
    tart_ip,
)


def _completed(stdout: str = "", stderr: str = "", returncode: int = 0):
    """Build a fake CompletedProcess for `tart ip`."""
    proc = MagicMock()
    proc.stdout = stdout
    proc.stderr = stderr
    proc.returncode = returncode
    return proc


class TestTartIp:
    """Tests for tart_ip()."""

    def test_returns_stripped_ip(self) -> None:
        """Should return the trimmed address from `tart ip`."""
        with patch("vibe.target.subprocess.run") as mock_run:
            mock_run.return_value = _completed(stdout="192.168.64.7\n")
            assert tart_ip("beta") == "192.168.64.7"
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0] == ["tart", "ip", "beta"]

    def test_missing_tart_binary_raises(self) -> None:
        """Should raise a helpful error when tart is not installed."""
        with patch("vibe.target.subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(TargetError, match="tart` was not found"):
                tart_ip("beta")

    def test_timeout_raises(self) -> None:
        """Should raise when `tart ip` times out."""
        with patch(
            "vibe.target.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="tart", timeout=10),
        ):
            with pytest.raises(TargetError, match="Timed out"):
                tart_ip("beta")

    def test_nonzero_exit_raises_with_detail(self) -> None:
        """Should surface tart's stderr on a non-zero exit."""
        with patch("vibe.target.subprocess.run") as mock_run:
            mock_run.return_value = _completed(stderr="VM not found", returncode=1)
            with pytest.raises(TargetError, match="VM not found"):
                tart_ip("ghost")

    def test_empty_output_raises(self) -> None:
        """Should raise when tart reports success but no address."""
        with patch("vibe.target.subprocess.run") as mock_run:
            mock_run.return_value = _completed(stdout="  \n")
            with pytest.raises(TargetError, match="no address"):
                tart_ip("beta")


class TestResolveTarget:
    """Tests for resolve_target() precedence and shapes."""

    def test_default_resolves_default_vm(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No flags/env → the default local VM, resolved via tart (no mDNS)."""
        monkeypatch.setattr("vibe.target.DEFAULT_VM", "vibecoding")
        with patch("vibe.target.tart_ip", return_value="10.0.0.2") as mock_ip:
            target = resolve_target()
        mock_ip.assert_called_once_with("vibecoding")
        assert target.user_host == f"{DEFAULT_USER}@10.0.0.2"
        assert target.ssh_opts == EPHEMERAL_HOSTKEY_OPTS

    def test_default_vm_unresolvable_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The default VM is not silently degraded to mDNS/.local; it errors."""
        monkeypatch.setattr("vibe.target.DEFAULT_VM", "vibecoding")
        with patch(
            "vibe.target.tart_ip",
            side_effect=TargetError("is it running?"),
        ):
            with pytest.raises(TargetError, match="is it running?"):
                resolve_target()

    def test_default_static_host_when_no_default_vm(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Hosts without a tart default (e.g. WSL) use the static host."""
        monkeypatch.setattr("vibe.target.DEFAULT_VM", None)
        with patch("vibe.target.tart_ip") as mock_ip:
            target = resolve_target()
        mock_ip.assert_not_called()
        assert target == Target(user_host=SSH_USER_HOST, ssh_opts=[])

    def test_host_flag_literal(self) -> None:
        """--host is used verbatim with no ephemeral opts (stable target)."""
        target = resolve_target(host="admin@mac-mini.ts.net")
        assert target.user_host == "admin@mac-mini.ts.net"
        assert target.ssh_opts == []

    def test_vm_flag_resolves_via_tart(self) -> None:
        """--vm resolves to <user>@<ip> and carries ephemeral host-key opts."""
        with patch("vibe.target.tart_ip", return_value="10.0.0.5") as mock_ip:
            target = resolve_target(vm="beta")
        mock_ip.assert_called_once_with("beta")
        assert target.user_host == f"{DEFAULT_USER}@10.0.0.5"
        assert target.ssh_opts == EPHEMERAL_HOSTKEY_OPTS
        # A copy, not the shared module constant, so callers can't mutate it.
        assert target.ssh_opts is not EPHEMERAL_HOSTKEY_OPTS

    def test_vm_and_host_together_error(self) -> None:
        """Passing both --vm and --host is rejected."""
        with pytest.raises(TargetError, match="either --vm or --host"):
            resolve_target(vm="beta", host="admin@host")

    def test_host_flag_beats_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An explicit --host wins over VIBE_SSH_HOST."""
        monkeypatch.setenv(ENV_SSH_HOST, "admin@from-env")
        assert resolve_target(host="admin@from-flag").user_host == "admin@from-flag"

    def test_vm_flag_beats_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An explicit --vm wins over the env defaults."""
        monkeypatch.setenv(ENV_VM, "env-vm")
        monkeypatch.setenv(ENV_SSH_HOST, "admin@from-env")
        with patch("vibe.target.tart_ip", return_value="10.0.0.9") as mock_ip:
            target = resolve_target(vm="flag-vm")
        mock_ip.assert_called_once_with("flag-vm")
        assert target.user_host == f"{DEFAULT_USER}@10.0.0.9"

    def test_env_ssh_host(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """VIBE_SSH_HOST is used when no flags are given."""
        monkeypatch.setenv(ENV_SSH_HOST, "admin@env-host")
        target = resolve_target()
        assert target.user_host == "admin@env-host"
        assert target.ssh_opts == []

    def test_env_ssh_host_beats_env_vm(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """VIBE_SSH_HOST (literal) takes precedence over VIBE_VM."""
        monkeypatch.setenv(ENV_SSH_HOST, "admin@env-host")
        monkeypatch.setenv(ENV_VM, "env-vm")
        with patch("vibe.target.tart_ip") as mock_ip:
            target = resolve_target()
        mock_ip.assert_not_called()
        assert target.user_host == "admin@env-host"

    def test_env_vm_resolves_via_tart(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """VIBE_VM resolves through tart when it is the only signal."""
        monkeypatch.setenv(ENV_VM, "env-vm")
        with patch("vibe.target.tart_ip", return_value="10.0.0.42") as mock_ip:
            target = resolve_target()
        mock_ip.assert_called_once_with("env-vm")
        assert target.user_host == f"{DEFAULT_USER}@10.0.0.42"
        assert target.ssh_opts == EPHEMERAL_HOSTKEY_OPTS
