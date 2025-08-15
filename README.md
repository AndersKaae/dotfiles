# Install on Mac

1) Download solarized theme from:
https://raw.githubusercontent.com/mbadolato/iTerm2-Color-Schemes/master/schemes/Solarized%20Dark%20-%20Patched.iTerm2-Color-Schemes

2) Open iTerm2 and go to iTerm2 -> Preferences -> Profiles -> Colors -> Color Presets -> Import and select the Solarized Dark theme file you just downloaded. 

3) In the iTerm2 preferences enable mouse reporting to make tmux work properly.

3) Install Install oh-my-zsh from https://ohmyz.sh/#install

4) Install the tmux plugin manager from https://github.com/tmux-plugins/tpm

5) Install the plugin in tmux by pressing <leader>+I

0) Run stow . in the dotfiles directory to symlink the dotfiles to your home directory.

# Install on Linux

## Non obvious packages to install
sudo pacman -S rofi hyprpaper waybar swayidle syncthing grim slurp swappy 

## Fancy Bash with Oh My Bash
Install Oh My Bash: https://github.com/ohmybash/oh-my-bash instead

## Handle closing of the lid and move screens out of the closed lid 
We use the script in .local/bin/lid-handler.sh
The service to make it run as a daemon is in .config/systemd/lid-handler.service
Install this: sudo pacman -S jq
We run it with:
systemctl --user daemon-reload
systemctl --user enable --now lid-handler.service
