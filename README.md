# Install on Mac

1. Download solarized theme from:
   https://raw.githubusercontent.com/mbadolato/iTerm2-Color-Schemes/master/schemes/Solarized%20Dark%20-%20Patched.iTerm2-Color-Schemes

2. Open iTerm2 and go to iTerm2 -> Preferences -> Profiles -> Colors -> Color Presets -> Import and select the Solarized Dark theme file you just downloaded.

3. In the iTerm2 preferences enable mouse reporting to make tmux work properly.

4. Install Install oh-my-zsh from https://ohmyz.sh/#install

5. Install the tmux plugin manager from https://github.com/tmux-plugins/tpm

6. Install the plugin in tmux by pressing <leader>+I

7. Run stow . in the dotfiles directory to symlink the dotfiles to your home directory.

# Install on Linux

## Install all required apps

Run `./arch-install-apps.sh` (requires `yay` for AUR packages).

## Non obvious packages to install
sudo pacman -S rofi hyprpaper waybar swayidle syncthing grim slurp swappy pamixer swaylock brightnessctl playerctl mako 


## Fancy Bash with Oh My Bash

Install Oh My Bash: https://github.com/ohmybash/oh-my-bash instead

## VPN Setup (UniFi L2TP)

The VPN requires the NetworkManager L2TP plugin and some kernel modules.

1. Install the required packages:
   `sudo pacman -S networkmanager-l2tp strongswan xl2tpd`

2. Configure NetworkManager to use the `iwd` backend (if you are using iwd):
   `sudo nvim /etc/NetworkManager/conf.d/iwd.conf`
   Add:

   ```ini
   [device]
   wifi.backend=iwd
   ```

   Then restart: `sudo systemctl restart NetworkManager`

3. Ensure conflicting system services are stopped:
   `sudo systemctl stop strongswan xl2tpd`
   `sudo systemctl disable strongswan xl2tpd`

4. Run the setup script to create the connection:
   `./.local/bin/setup-vpn.sh`
   (Enter your Username, Password, and PSK when prompted)

5. Toggle the VPN using the icon in Waybar or via CLI:
   `nmcli connection up UniFi-VPN`

We use the script in .local/bin/lid-handler.sh
The service to make it run as a daemon is in .config/systemd/lid-handler.service
Install this: sudo pacman -S jq
We run it with:
systemctl --user daemon-reload
systemctl --user enable --now lid-handler.service
