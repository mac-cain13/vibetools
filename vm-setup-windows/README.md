# Vibe VM (Windows / Hyper-V / WSL)

This is a bit of a mess, some things are not how I've set it up, but it gives a rough idea what you should think of when setting up Windows.

## Overview

This setup creates a Windows guest VM running under Hyper-V, where coding tools run inside WSL2 on the guest. The architecture is:

```
Windows Host WSL2 → SSH → Hyper-V Windows Guest → wsl -e → Guest WSL2
```

- Repos live on the Windows host at `C:\Users\<user>\Repositories`
- Host WSL sees them at `/mnt/c/Users/<user>/Repositories`
- Guest VM's WSL gets them via SMB share mounted at `/mnt/repos`

## Setup

### 1. Host Setup

#### Enable Hyper-V

- Settings > Apps > Optional Features > More Windows Features
- Check **Hyper-V** and reboot

#### Install WSL2 on Host

```powershell
wsl --install
```

Reboot, then set up the default Ubuntu distro.

#### Create SMB Share for Repositories

- Create the folder `C:\Users\<user>\Repositories` if it doesn't exist
- Right-click > Properties > Sharing > Advanced Sharing
- Check **Share this folder**, share name: `Repositories`
- Permissions: grant your user Full Control

#### Configure Host WSL

Inside the host WSL distro:

```bash
# Install zsh and oh-my-zsh
sudo apt update && sudo apt install -y zsh
chsh -s $(which zsh)
sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"

# Install powerlevel10k
git clone --depth=1 https://github.com/romkatv/powerlevel10k.git \
  "${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/themes/powerlevel10k"

# Install zsh-autosuggestions (via apt)
sudo apt install -y zsh-autosuggestions

# Setup SSH key for VM access
mkdir -p ~/.ssh
# Generate or copy your id_vibecoding key pair into ~/.ssh/
```

Install the vibe tool:

```bash
pip install -e "/mnt/c/Users/<user>/Repositories/vibetools[dev]"
```

### 2. Guest VM Setup (from pristine Windows VM)

#### Create the VM in Hyper-V

- Open Hyper-V Manager
- New > Virtual Machine
- Generation 2, 16 GB RAM (dynamic), 8+ vCPUs, 512 GB VHD
- Install Windows from ISO
- Complete the Windows OOBE wizard

_Pristine VM ready._

#### Install WSL2 in Guest

Open PowerShell as Administrator in the guest:

```powershell
wsl --install
```

Reboot the guest VM, then configure the default Ubuntu distro (username: `admin`).

#### Configure Windows OpenSSH Server

SSH lands in Windows; we then use `wsl -e` to enter WSL.

```powershell
# Install OpenSSH Server
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0

# Start and enable the service
Start-Service sshd
Set-Service -Name sshd -StartupType Automatic
```

Edit `C:\ProgramData\ssh\sshd_config`:

```
PubkeyAuthentication yes
PasswordAuthentication no
```

For admin users, add your public key to `C:\ProgramData\ssh\administrators_authorized_keys` (not `~/.ssh/authorized_keys`):

```powershell
# Add your public key
echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPGiURHzpEStKP4pi6TH5o6BXxzzwVA1imslB/ID5Vk3 id_vibecoding" | Out-File -Encoding utf8 C:\ProgramData\ssh\administrators_authorized_keys

# Fix permissions (required for admin authorized_keys)
icacls C:\ProgramData\ssh\administrators_authorized_keys /inheritance:r /grant "SYSTEM:F" /grant "Administrators:F"

# Restart SSH
Restart-Service sshd
```

#### Set Hostname

```powershell
Rename-Computer -NewName "vibecoding" -Restart
```

#### Configure Firewall

Ensure the SSH rule exists (it should be created automatically):

```powershell
Get-NetFirewallRule -Name *ssh*
# If missing:
New-NetFirewallRule -Name sshd -DisplayName 'OpenSSH Server' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22
```

#### Mount Host SMB Share in Guest WSL

Inside the guest WSL distro:

```bash
# Install cifs-utils
sudo apt update && sudo apt install -y cifs-utils

# Create mount point
sudo mkdir -p /mnt/repos

# Create credentials file
sudo bash -c 'cat > /etc/smbcredentials <<EOF
username=<host-windows-user>
password=<host-windows-password>
EOF'
sudo chmod 600 /etc/smbcredentials

# Add to /etc/fstab for automatic mounting
echo '//<host-ip>/Repositories /mnt/repos cifs credentials=/etc/smbcredentials,uid=1000,gid=1000,file_mode=0775,dir_mode=0775 0 0' | sudo tee -a /etc/fstab

# Mount now
sudo mount -a
```

Verify with `ls /mnt/repos` -- you should see your repositories.

### 3. Guest WSL Environment

#### Install Shell Tools

```bash
# Install zsh and set as default shell
sudo apt update && sudo apt install -y zsh git curl
chsh -s $(which zsh)

# Install oh-my-zsh
sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"

# Install powerlevel10k
git clone --depth=1 https://github.com/romkatv/powerlevel10k.git \
  "${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/themes/powerlevel10k"

# Install zsh-autosuggestions (via apt)
sudo apt install -y zsh-autosuggestions
```

#### Install Coding Tools

```bash
# Install nvm and Node.js (needed for Codex and OpenCode)
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/master/install.sh | bash
source ~/.nvm/nvm.sh
nvm install --lts

# Install Claude Code
curl -fsSL https://claude.ai/install.sh | bash

# Install Codex
npm install -g @openai/codex

# Install OpenCode
npm install -g opencode
```

#### Install CLI Utilities

```bash
sudo apt install -y ripgrep jq fd-find fzf bat tree yq htmlq gh git-delta hyperfine watch tldr pandoc imagemagick ffmpeg

# Install jump (directory bookmarks)
wget https://github.com/gsamokovarov/jump/releases/download/v0.67.0/jump_0.67.0_amd64.deb && sudo dpkg -i jump_0.67.0_amd64.deb
```

#### Copy Dotfiles

Copy dotfiles from `vm-setup-windows/` into the guest WSL:

```bash
# Copy zshrc and p10k config
cp zshrc ~/.zshrc
cp p10k.zsh ~/.p10k.zsh

# Copy Claude.md
mkdir -p ~/.claude
cp Claude.md ~/.claude/claude.md

# Copy wrapper scripts
mkdir -p ~/.config/zsh
cp claude-wrapper.zsh ~/.config/zsh/claude-wrapper.zsh
cp codex-wrapper.zsh ~/.config/zsh/codex-wrapper.zsh
```

#### Login to Tools

```bash
# Login to Codex
codex

# Login to Claude Code (go through interactive wizard)
claude
```

### 4. Guest Auto-Start WSL on Boot (Optional)

To ensure WSL starts when the VM boots (so SSH + `wsl -e` works immediately), create a scheduled task:

```powershell
$action = New-ScheduledTaskAction -Execute "wsl.exe" -Argument "-e bash -c 'sleep infinity'"
$trigger = New-ScheduledTaskTrigger -AtStartup
Register-ScheduledTask -TaskName "StartWSL" -Action $action -Trigger $trigger -User "SYSTEM" -RunLevel Highest
```

## Using the VM

### Start the VM

```powershell
Start-VM -Name "vibecoding"
```

### Stop the VM

```powershell
Stop-VM -Name "vibecoding"
```

### SSH into the Guest WSL

From the host WSL:

```bash
ssh -i ~/.ssh/id_vibecoding admin@vibecoding "wsl -e bash -c 'cd /mnt/repos && exec zsh -l'"
```

Or in two steps:

```bash
# SSH into the Windows guest
ssh -i ~/.ssh/id_vibecoding admin@vibecoding

# Then enter WSL
wsl -e zsh -l
```

### Quick Test

```bash
# Verify SSH works
ssh -i ~/.ssh/id_vibecoding admin@vibecoding "wsl -e bash -c 'echo WSL is running && cat /etc/os-release | head -2'"

# Verify repos are mounted
ssh -i ~/.ssh/id_vibecoding admin@vibecoding "wsl -e bash -c 'ls /mnt/repos'"
```

_Tip: You can also use Remote Desktop (mstsc) to connect to the guest VM's GUI._
