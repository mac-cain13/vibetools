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
- Add PermissionAutoResponder.app to Applications, then;
  - add it as a login item: Settings > General > Login items > + Select the app
  - Give accessibility permissions!

_Base VM ready._

### Install Claude Code

- Clone VM: `tart clone tahoe-base tahoe-base-vibe`

- Install Volta: `curl https://get.volta.sh | bash`
- Install node: `volta install node`
- Install Claude Code: `npm install -g @anthropic-ai/claude-code`
  - Migrate to local setup: `claude migrate-installer`
- Add cly wrapper to `mkdir -p ~/.config/zsh && mv claude-wrapper.zsh ~/.config/zsh/claude-wrapper.zsh`

_Base vibe VM ready._

### Login to tooling

- Clone VM: `tart clone tahoe-base-vibe tahoe-vibecoding-template`

- General > About: Set local hostname to `Vibecoding VM`
- Sharing: Change hostname to `vibecoding`
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
- Add `mv Claude.md ~/.claude/claude.md`

- Run some UITests from Xcode once so it will ask you for permission to modify other apps, access to external folders etc.
- Run UITests once over SSH, this will trigger a permission prompt for XCTests to allow it to run.

_Note:_ For Xcode to be able to build over SSH you need to unlock the keychain before building: `security -v unlock-keychain -p admin ~/Library/Keychains/login.keychain-db`

## Using the VM

- Clone VM: `tart clone tahoe-vibecoding-template vibecoding`
- Run VM: `tart run vibecoding --no-graphics --suspendable`
- SSH into the VM: `ssh -i ~/.ssh/id_vibecoding admin@$(tart ip vibecoding)`

_Tip: You can also use the Apple Screen Sharing app to get to the VM._