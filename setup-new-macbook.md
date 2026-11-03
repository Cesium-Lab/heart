# Setting up new macbook 
`cskin@psyche`
## Name to make sure
```zsh
sudo scutil --set ComputerName "psyche"
sudo scutil --set LocalHostName "psyche"
sudo scutil --set HostName "psyche"
```
Check
```zsh
hostname
scutil --get ComputerName
scutil --get LocalHostName
scutil --get HostName
```


##  Actually getting homebrew
```zsh
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

```zsh
echo 'eval "$(/opt/homebrew/bin/brew shellenv zsh)"' >> /Users/$USER/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
source ~/.zprofile
```

```zsh
brew version  # Homebrew 7.0.11
brew doctor

# Needed to update CLI tools
softwareupdate --list

```
Verifying good?
```zsh
xcode-select -p  # /Library/Developer/CommandLineTools
pkgutil --pkg-info=com.apple.pkg.CLTools_Executables
```




## VS Code
```zsh
brew install --cask visual-studio-code
code --version
```

- autoDocstring
- C/C++
- C/C++ Extension Pack
- CMake tools
- Codex
- Even Better TOML
- Gitlens
- Jupyter
- Markdown All in One
- MATLAB
- Python
- Remote Explorer
- Ruff
- vscode-pdf

<!-- ```zsh
code --install-extension ms-python.python
code --install-extension charliermarsh.ruff
code --install-extension ms-vscode.cpptools
code --install-extension ms-vscode.cmake-tools
code --install-extension ms-toolsai.jupyter
code --install-extension mathworks.language-matlab
code --install-extension ms-vscode-remote.remote-ssh
``` -->




## Other

```zsh
brew install \
  tlrc \
  ffmpeg \
  pstree \
  git-lfs \
  pandoc \
  tio \
  ruff \
  libusb \
  python@3.12

echo 'export PATH="$(brew --prefix python@3.12)/libexec/bin:$PATH"' >> ~/.zprofile
```

```zsh
Codex
```

## GIT

```zsh
git config --global core.editor "nano -w"
git config --global user.email colinaskinner@gmail.com
git config --global user.name "Colin Skinner" 

git config --global --edit
```
config
```zsh
[alias]
        st = status
        fp = fetch --prune
        pf = push --force-with-lease
        co = checkout
        br = branch
        lo = log --oneline
        lg = log --graph --oneline
        publish = push -u origin HEAD
[push]
        autoSetupRemote = false
```

```zsh
brew install git-lfs
git lfs install
```

Then do this
```zsh
ssh-keygen -t ed25519 -C colinaskinner@gmail.com
cat ~/.ssh/id_ed25519.pub
```


## Apps

- Spotify
- Logic Pro X
- Google Chrome
  - Stanford Sign-in
- Daisy Disk
  - Colin Skinner
  - CZZH5P79-7L7BWLUU-5WYYAJYY-S3RF7RKY-8DR33LMB
- UTM
- WhatsApp
- MATLAB
- Al Dente (MAYBE? idk)
  - Set to 80%

## Settings
- Hot corners
  - Lock bottom left, screensaver top right, password immediately
- feedback when volume changes
- Trackpad
- Keyboard no caps, etc.

## Embedded

```zsh
brew install stlink picotool minicom
brew install --cask gcc-arm-embedded
```

## Pip
Global
```
pip3 -m pip install --upgrade pip
```
