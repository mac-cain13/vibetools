# Vibe VM

## Setup

### Setup VM

- Install macOS: `tart create tahoe-pristine --from-ipsw Tahoe_Restore.ipsw --disk-size 512`
- Config VM: `tart set tahoe-pristine --cpu 16 --memory 32768 --display-refit`

_Pristine VM ready._

### Post-install wizard

- Clone VM: `tart clone tahoe-pristine tahoe-base`

- Lang: English / Region: NL
- User: admin / admin
- No FileVault
- No Apple ID login
- Enable location services
- No screen time / Siri
- Auto dark mode
- Updates download only

### Change macOS Settings

- Enable automatic login in setting for admin
- Sharing: Enable SSH & Screen Sharing
- Sharing: Set local hostname to `virtualmachine.local`
- General > About: Set local hostname to `Virtual Machine`
- Turn Firewall on
- Lock screen; Turn off display: Never / Require password after screen saver: Never
- Energy; Prevent automatic sleep: Yes / Put hard disks to sleep: No
- Start screen saver: Never
- Date & Time; Set timezone to Amsterdam, NL
- Software Updates; Turn off except for security responses

- Desktop: Remove widgets
- Dock: Remove all apps except for Finder, Safari and Settings
- Dock: Add Terminal to the dock

### Install base tooling

- Install the MesloLGS NF fonts
- Update Apple Terminal fonts: Preferences → Profiles → Text, click Change under Font and select MesloLGS NF family.
- Install oh-my-zsh: `sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"`
  - Note: This will trigger developer tool download to have git available, after it's finished try again
- Add dotfiles: `mv zshrc ~/.zshrc && mv p10k.zsh ~/.p10k.zsh`
- Install p10k: `git clone --depth=1 https://github.com/romkatv/powerlevel10k.git "${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/themes/powerlevel10k"`
- Setup SSH key: `mkdir -p ~/.ssh && echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPGiURHzpEStKP4pi6TH5o6BXxzzwVA1imslB/ID5Vk3 id_vibecoding" > ~/.ssh/authorized_keys`
- Install Homebrew: `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`
- Install with brew: `brew install jump zsh-autosuggestions aria2 xcodesorg/made/xcodes ripgrep jq fd fzf bat tree yq htmlq gh git-delta hyperfine watch tldr pandoc xcbeautify imagemagick ffmpeg chargepoint/xcparse/xcparse`
- Install Peekaboo (macOS screen capture + GUI automation, used by the coding agents): `brew install steipete/tap/peekaboo`
  - The `peekaboo` skill ships in this repo under `skills/peekaboo/` and is symlinked automatically by `./install.sh` (see the Claude Code section below).
  - Peekaboo needs **Screen Recording** and **Accessibility** permissions. Because the coding agent runs it over SSH, these must be granted to the SSH host process, not to peekaboo itself: in Settings > Privacy & Security, grant both **Screen Recording** and **Accessibility** to `sshd-keygen-wrapper` (`/usr/libexec/sshd-keygen-wrapper`). Add it via the `+` button (⌘⇧G → paste the path) if it isn't already listed, or answer the prompt that appears the first time peekaboo runs over SSH.
  - Verify with `peekaboo permissions status --json` (over SSH) — both should report authorized.
- Install the Sentry CLI (first-party tool for investigating production errors, crashes, and user-reported issues): `brew install getsentry/tools/sentry`
  - Authenticate with `sentry auth login`; check with `sentry auth status`.
  - The `sentry` skill ships in this repo under `skills/sentry/` and is symlinked automatically by `./install.sh` (see the Claude Code section below).
- Install the Linear CLI (manage Linear issues/projects/cycles from the terminal): `brew install schpet/tap/linear`
  - Note: `linear` collides with the Linear.app cask, so the tap-qualified `schpet/tap/linear` is required — a bare `brew install linear` would install the desktop app instead.
  - Authenticate with `linear auth login`; check with `linear auth whoami`.
  - The `linear-cli` skill ships in this repo under `skills/linear-cli/` and is symlinked automatically by `./install.sh` (see the Claude Code section below).
- Add PermissionAutoResponder.app to Applications, then;
  - add it as a login item: Settings > General > Login items > + Select the app
  - Give accessibility permissions!

_Base VM ready._

### Install Claude Code & Codex

- Clone VM: `tart clone tahoe-base tahoe-base-vibe`

- Install Claude Code: `curl -fsSL https://claude.ai/install.sh | bash`
- Install Codex: `npm install -g @openai/codex`
- Add wrappers:
  ```bash
  mkdir -p ~/.config/zsh
  mv claude-wrapper.zsh ~/.config/zsh/claude-wrapper.zsh
  mv codex-wrapper.zsh ~/.config/zsh/codex-wrapper.zsh
  ```

_Base vibe VM ready._

### Login to tooling

- Clone VM: `tart clone tahoe-base-vibe tahoe-vibecoding-template`

- General > About: Set local hostname to `Vibecoding VM`
- Sharing: Change hostname to `vibecoding`
  - _Note:_ `vibe` no longer connects over mDNS — it addresses local VMs by their
    **tart name** and resolves the IP via `tart ip`. This hostname is now only
    for self-identification (shell prompt, anything served on the local network),
    not for connectivity. See "Running multiple VMs side by side" below.
- Login to gh with `gh auth login` use the personal access token from 1Password (has reduces permissions)
- Login into Xcodes & install latest Xcode: 
  - `xcodes install --latest --experimental-unxip`
  - `xcodes install --latest-prerelease --experimental-unxip`
  - `xcodes select`
  - The install runtimes: `xcodes runtimes "iOS 26.0"`
- Drag Xcode into the dock
BROKEN: - Login to Xcode with `vibecoding@nonstrict.com` // TODO: Fix 2FA
- Go through wizard & login to claude code: `claude`
- Mount the network share `Repositories`:
  - Finder > Go > Connect to Server > `smb://hostname/Repositories`
  - Store credentials in keychain
  - macOS mounts it at `/Volumes/Repositories`
- Create symlink for path alignment:
  - `sudo mkdir -p /Volumes/External`
  - `sudo ln -s /Volumes/Repositories /Volumes/External/Repositories`
  - This ensures paths match between host (`/Volumes/External/Repositories/...`) and VM
- Add the share to Settings > General > Login items > + Select the mounted Repositories folder
- Symlink the user CLAUDE.md so it stays in sync with the repo: `mkdir -p ~/.claude && ln -sf /Volumes/External/Repositories/vibetools/vm-setup/Claude.md ~/.claude/CLAUDE.md`
- Install the park skill by symlinking it so it stays in sync with the repo (also works to update an existing install): `mkdir -p ~/.claude/skills && rm -rf ~/.claude/skills/park && ln -sf /Volumes/External/Repositories/vibetools/skills/park ~/.claude/skills/park`
  - Note: `./install.sh` already symlinks every skill in `skills/`, so this manual step is only needed if you haven't run it.

- Run some UITests from Xcode once so it will ask you for permission to modify other apps, access to external folders etc.
- Run UITests once over SSH, this will trigger a permission prompt for XCTests to allow it to run.

_Note:_ For Xcode to be able to build over SSH you need to unlock the keychain before building: `security -v unlock-keychain -p admin ~/Library/Keychains/login.keychain-db`

## Using the VM

- Clone VM: `tart clone tahoe-vibecoding-template vibecoding`
- Run VM: `tart run vibecoding --no-graphics --suspendable`
- SSH into the VM: `ssh -i ~/.ssh/id_vibecoding admin@$(tart ip vibecoding)`

_Tip: You can also use the Apple Screen Sharing app to get to the VM._

## Running multiple VMs side by side

You can clone the template more than once and run the clones concurrently — for
example, one on a macOS beta and one reserved for GUI-heavy automation so long
agent runs don't block each other.

```bash
# Clone the template under distinct tart names
tart clone tahoe-vibecoding-template vibecoding
tart clone tahoe-vibecoding-template vibecoding-beta

# Run both (each gets its own IP from tart)
tart run vibecoding --no-graphics --suspendable
tart run vibecoding-beta --no-graphics --suspendable
```

Connect to a specific clone with `vibe --vm <tart-name>`; vibe resolves the
right instance via `tart ip`, so the shared `vibecoding` guest hostname (which
would make every clone answer to `vibecoding.local`) is never used to pick a
machine:

```bash
vibe feature-branch --vm vibecoding-beta      # start work on the beta clone
export VIBE_VM=vibecoding-beta && vibe --cli   # or set a default for the shell
```

See the "Selecting a VM" section in the top-level `README.md` for the full
resolution precedence and host-key handling.

**Optional but recommended — give each clone a distinct hostname.** Selecting
the VM works without this, but both clones still *identify* as `vibecoding`
(shell prompt, and anything a coding agent serves back over the local network
resolves to the ambiguous `vibecoding.local`). To make each clone
self-identifying, set a unique hostname once per clone (from inside the guest):

```bash
sudo scutil --set HostName vibecoding-beta
sudo scutil --set LocalHostName vibecoding-beta
sudo scutil --set ComputerName "Vibecoding Beta"
```

> **Shared drive caution:** every clone mounts the *same* host worktree drive.
> Running two clones is safe as long as they work in **different** worktrees;
> pointing two at the same branch/worktree at once risks git index/ref races
> over SMB. Sizing: the template is 16 CPU / 32 GB, so two clones want ~32
> vCPU / 64 GB of host headroom on top of the host itself.