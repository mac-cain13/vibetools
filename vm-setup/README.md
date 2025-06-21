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
- No Apple ID login
- Enable location services
- No screen time / Siri
- Auto dark mode
- Updates download only

### Change macOS Settings

- Enable automatic login in setting for admin
- Sharing: Enable SSH & Screen Sharing
NEW: - General > About: Set local hostname to `Virtual Machine`
- Sharing: Set local hostname to `virtualmachine.local`
- Turn Firewall on
- Lock screen; Turn off display: Never / Require password after screen saver: Never
- Energy; Prevent automatic sleep: Yes / Put hard disks to sleep: No
- Start screen saver: Never
- Date & Time; Set timezone to Amsterdam, NL
- Software Updates; Turn off except for security responses

- Dock: Remove all apps except for Finder, Safari and Settings
- Dock: Add Terminal to the dock

### Install base tooling

- Install the MesloLGS NF fonts
- Update Apple Terminal fonts: Preferences → Profiles → Text, click Change under Font and select MesloLGS NF family.
- Install oh-my-zsh: `sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"`
- Add dotfiles: `mv zshrc ~/.zshrc && mv p10k.zsh ~/.p10k.zsh`
- Install p10k: `git clone --depth=1 https://github.com/romkatv/powerlevel10k.git "${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/themes/powerlevel10k"`
  - Note: This will trigger developer tool download to have git available, after it's finished try again
- Setup SSH key: `mkdir -p ~/.ssh && echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPGiURHzpEStKP4pi6TH5o6BXxzzwVA1imslB/ID5Vk3 id_vibecoding" > ~/.ssh/authorized_keys`
- Install Homebrew: `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`
- Install with brew: `brew install jump zsh-autosuggestions aria2 xcodesorg/made/xcodes`

NEW: (Not yet in my VM templates)
- Install tools for Claude to use: `brew install ripgrep jq fd fzf bat tree yq htmlq gh git-delta hyperfine watch tldr pandoc xcbeautify`

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

NEW: - General > About: Set local hostname to `Vibecoding VM`
- Sharing: Change hostname to `vibecoding`
- Login into Xcodes & install latest Xcode: 
  - `xcodes install --latest --experimental-unxip`
  - `xcodes install --latest-prerelease --experimental-unxip`
  - `xcodes select`
  - The install runtimes: `xcodes runtimes "iOS 26.0"`
- Drag Xcode into the dock
- Go through wizard & login to claude code: `claude`
- Mount the network share `_vibecoding` store credentials in keychain
- Add the share to Settings > General > Login items > + Select the shared folder

NEW: - Add `claude.md` to `~/.claude/claude.md`

## Using the VM

- Clone VM: `tart clone tahoe-vibecoding-template vibecoding`
- Run VM: `tart run vibecoding --no-graphics --suspendable`
- SSH into the VM: `ssh -i ~/.ssh/id_vibecoding admin@$(tart ip vibecoding)`

_Tip: You can also use the Apple Screen Sharing app to get to the VM._

### Adding MCP servers

NEW: - `claude mcp add sequential-thinking -s user -- npx -y @modelcontextprotocol/server-sequential-thinking`