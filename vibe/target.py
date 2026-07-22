"""Resolve which VM / SSH host a vibe session should connect to.

vibe runs on the host and connects into a development VM over SSH. Local VMs are
addressed by their unique ``tart`` name — resolved to a current IP with
``tart ip`` — rather than mDNS. By default that is ``config.DEFAULT_VM``
(``vibecoding``), but you can run several clones side by side (e.g. one on a
macOS beta, one for GUI-heavy automation) and pick one with ``--vm``. This
sidesteps the ambiguity of ``.local`` resolution, which cannot tell clones apart
because they all inherit the ``vibecoding`` guest hostname.

Resolution precedence (first match wins):
    1. ``--host user@host``   explicit SSH target
    2. ``--vm <tart-name>``   resolved to ``<user>@<ip>`` via ``tart ip``
    3. ``VIBE_SSH_HOST`` env  explicit SSH target
    4. ``VIBE_VM`` env        resolved via ``tart ip``
    5. ``config.DEFAULT_VM``  the default local VM, resolved via ``tart ip``
    6. ``config.SSH_USER_HOST``  static host, only when there is no default VM
       (e.g. WSL, which has no tart)

Local VMs are addressed by tart name — mDNS/``.local`` is not used for the
default path. To reach a VM by its ``.local`` name anyway, pass it explicitly
as ``--host admin@vibecoding.local``.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field

from vibe.config import DEFAULT_VM, SSH_USER_HOST
from vibe.connection import EPHEMERAL_HOSTKEY_OPTS

# Username used for tart-resolved VMs. Derived from the default SSH target so a
# single place defines it (e.g. "admin" from "admin@vibecoding.local").
DEFAULT_USER = SSH_USER_HOST.split("@", 1)[0]

# How long to wait for `tart ip` before giving up (seconds).
TART_IP_TIMEOUT = 10

# Environment variable names for the no-flag defaults.
ENV_SSH_HOST = "VIBE_SSH_HOST"
ENV_VM = "VIBE_VM"


class TargetError(Exception):
    """A requested VM / SSH target could not be resolved."""


@dataclass(frozen=True)
class Target:
    """A resolved SSH connection target.

    Attributes:
        user_host: The ``user@host`` string to pass to ssh.
        ssh_opts: Extra ssh options inserted before the target (host-key
            handling for ephemeral, DHCP-addressed VMs). Empty for stable hosts.
    """

    user_host: str
    ssh_opts: list[str] = field(default_factory=list)


def tart_ip(name: str) -> str:
    """Resolve a tart VM's current IP address.

    Args:
        name: The tart VM name (as passed to ``tart run``).

    Returns:
        The VM's current IP address.

    Raises:
        TargetError: If tart is unavailable, times out, or the VM has no
            resolvable address (typically because it is not running).
    """
    try:
        result = subprocess.run(
            ["tart", "ip", name],
            capture_output=True,
            text=True,
            timeout=TART_IP_TIMEOUT,
        )
    except FileNotFoundError as exc:
        raise TargetError(
            "`tart` was not found — --vm / VIBE_VM only works on a macOS host "
            "with tart installed. Use --host to connect to any other target."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise TargetError(
            f"Timed out after {TART_IP_TIMEOUT}s resolving VM '{name}' via "
            "`tart ip` (is the VM running?)."
        ) from exc

    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise TargetError(
            f"Could not resolve VM '{name}' via `tart ip`"
            + (f": {detail}" if detail else " (is the VM running?)")
        )

    ip = result.stdout.strip()
    if not ip:
        raise TargetError(
            f"`tart ip {name}` returned no address (is the VM running?)."
        )
    return ip


def _target_for_vm(name: str) -> Target:
    """Build a Target for a tart VM by resolving its IP.

    tart clones share an SSH host key and get DHCP addresses, so the target
    carries the ephemeral host-key options to avoid a blocking host-key
    mismatch if an address is later reassigned.

    Args:
        name: The tart VM name.

    Returns:
        A Target addressing the VM by ``<user>@<ip>``.
    """
    ip = tart_ip(name)
    return Target(
        user_host=f"{DEFAULT_USER}@{ip}",
        ssh_opts=list(EPHEMERAL_HOSTKEY_OPTS),
    )


def resolve_target(vm: str | None = None, host: str | None = None) -> Target:
    """Resolve the SSH target for this session.

    Applies the documented precedence: an explicit ``--host`` wins, then
    ``--vm`` (resolved via tart), then the ``VIBE_SSH_HOST`` / ``VIBE_VM``
    environment defaults, then the default local VM (``config.DEFAULT_VM``,
    resolved via tart), and finally — only when no default VM is configured —
    the static ``config.SSH_USER_HOST``.

    Args:
        vm: The ``--vm`` flag value (a tart VM name), or None.
        host: The ``--host`` flag value (a ``user@host`` string), or None.

    Returns:
        The resolved Target.

    Raises:
        TargetError: If both ``--vm`` and ``--host`` are given, or a requested
            VM (explicit or the default) cannot be resolved via tart.
    """
    if vm and host:
        raise TargetError("Use either --vm or --host, not both.")
    if host:
        return Target(user_host=host)
    if vm:
        return _target_for_vm(vm)

    env_host = os.environ.get(ENV_SSH_HOST)
    if env_host:
        return Target(user_host=env_host)
    env_vm = os.environ.get(ENV_VM)
    if env_vm:
        return _target_for_vm(env_vm)

    # No explicit selection. Address the default local VM by its tart name
    # (resolved to a fresh IP) rather than mDNS. Hosts without a tart default
    # (e.g. WSL) use the static host instead.
    if DEFAULT_VM:
        return _target_for_vm(DEFAULT_VM)
    return Target(user_host=SSH_USER_HOST)
