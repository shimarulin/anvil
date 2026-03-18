#!/usr/bin/env bash

set -euo pipefail

# ============================================================
#  Colors
# ============================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC}    $*"; }
ok()      { echo -e "${GREEN}[OK]${NC}      $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}    $*"; }
err()     { echo -e "${RED}[ERROR]${NC}   $*"; exit 1; }
section() { echo -e "\n${CYAN}${BOLD}── $* ──${NC}"; }

# ============================================================
#  Configuration — edit these arrays to add/remove packages
# ============================================================

SYSTEM_PACKAGES=(
    git
    curl
    wget
    unzip
    make
    ripgrep
)

# Format: "apt|brew|pacman|dnf"  ("-" = same as apt)
MAPPED_PACKAGES=(
    "build-essential|gcc|base-devel|gcc"
)

NPM_PACKAGES=(
    tree-sitter-cli
    # neovim
    # typescript
    # prettier
)

PIP_PACKAGES=(
    pynvim
    # black
    # ruff
    # debugpy
)

NERD_FONT="JetBrainsMono"
VENV_DIR="$HOME/.local/share/nvim-deps-venv"

# ============================================================
#  OS / Package manager detection
# ============================================================
OS=""
PKG=""

detect_os() {
    case "$(uname -s)" in
        Linux*)
            OS="linux"
            if   command -v apt-get &>/dev/null; then PKG="apt"
            elif command -v dnf     &>/dev/null; then PKG="dnf"
            elif command -v yum     &>/dev/null; then PKG="yum"
            elif command -v pacman  &>/dev/null; then PKG="pacman"
            elif command -v zypper  &>/dev/null; then PKG="zypper"
            elif command -v apk     &>/dev/null; then PKG="apk"
            else err "Could not detect Linux package manager"; fi
            ;;
        Darwin*)
            OS="macos"
            if ! command -v brew &>/dev/null; then
                warn "Homebrew not found — installing..."
                /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
                [[ -f /opt/homebrew/bin/brew ]] && eval "$(/opt/homebrew/bin/brew shellenv)"
                [[ -f /usr/local/bin/brew ]]    && eval "$(/usr/local/bin/brew shellenv)"
            fi
            PKG="brew"
            ;;
        *) err "Unsupported OS: $(uname -s)" ;;
    esac
    info "OS: ${OS}  Package manager: ${PKG}"
}

# ============================================================
#  Low-level helpers
# ============================================================
has() { command -v "$1" &>/dev/null; }

pkg_update() {
    info "Updating package index..."
    case "$PKG" in
        apt)    sudo apt-get update -y ;;
        dnf)    sudo dnf check-update -y || true ;;
        yum)    sudo yum check-update -y || true ;;
        pacman) sudo pacman -Sy --noconfirm ;;
        zypper) sudo zypper refresh ;;
        apk)    sudo apk update ;;
        brew)
            local dead_taps
            dead_taps="$(brew tap 2>/dev/null | grep -E 'cask-fonts|cask-drivers' || true)"
            for tap in $dead_taps; do
                warn "Removing dead tap: ${tap}"
                brew untap "$tap" 2>/dev/null || true
            done
            brew update
            ;;
    esac
}

pkg_install() {
    local p="$1"
    case "$PKG" in
        apt)    sudo apt-get install -y "$p" ;;
        dnf)    sudo dnf install -y "$p" ;;
        yum)    sudo yum install -y "$p" ;;
        pacman) sudo pacman -S --needed --noconfirm "$p" ;;
        zypper) sudo zypper install -y "$p" ;;
        apk)    sudo apk add "$p" ;;
        brew)   brew install "$p" ;;
    esac
}

pkg_install_mapped() {
    local apt_name brew_name pacman_name dnf_name
    IFS='|' read -r apt_name brew_name pacman_name dnf_name <<< "$1"
    [[ "$brew_name"   == "-" ]] && brew_name="$apt_name"
    [[ "$pacman_name" == "-" ]] && pacman_name="$apt_name"
    [[ "$dnf_name"    == "-" ]] && dnf_name="$apt_name"

    local name
    case "$PKG" in
        apt)     name="$apt_name" ;;
        brew)    name="$brew_name" ;;
        pacman)  name="$pacman_name" ;;
        dnf|yum) name="$dnf_name" ;;
        *)       name="$apt_name" ;;
    esac

    info "Installing ${name}..."
    pkg_install "$name"
    ok "$name"
}

pkg_bin() {
    case "$1" in
        ripgrep)          echo "rg" ;;
        build-essential)  echo "gcc" ;;
        base-devel)       echo "gcc" ;;
        tree-sitter-cli)  echo "tree-sitter" ;;
        *)                echo "$1" ;;
    esac
}

# ============================================================
#  System packages
# ============================================================
install_system_packages() {
    section "System packages"

    for p in "${SYSTEM_PACKAGES[@]}"; do
        local bin
        bin="$(pkg_bin "$p")"
        if has "$bin"; then
            ok "${p} — already installed"
        else
            info "Installing ${p}..."
            pkg_install "$p"
            ok "$p"
        fi
    done

    for entry in "${MAPPED_PACKAGES[@]}"; do
        local first_name
        first_name="$(echo "$entry" | cut -d'|' -f1)"
        local bin
        bin="$(pkg_bin "$first_name")"
        if has "$bin"; then
            ok "${first_name} — already installed"
        else
            pkg_install_mapped "$entry"
        fi
    done
}

# ============================================================
#  Neovim
# ============================================================
install_neovim() {
    section "Neovim"

    case "$PKG" in
        brew)
            if has nvim; then
                if brew outdated --formula | grep -q '^neovim$'; then
                    info "Upgrading neovim..."
                    brew upgrade neovim
                else
                    ok "neovim — already up to date"
                fi
            else
                info "Installing neovim..."
                brew install neovim
            fi
            ;;
        pacman)
            info "Installing neovim..."
            sudo pacman -S --needed --noconfirm neovim
            ;;
        apt)
            install_neovim_github
            ;;
        *)
            pkg_install neovim
            ;;
    esac

    # Verify minimum version 0.11
    if has nvim; then
        local ver minor
        ver="$(nvim --version | head -1)"
        minor="$(echo "$ver" | grep -oE '[0-9]+\.[0-9]+' | head -1 | cut -d. -f2)"
        if [[ -n "$minor" ]] && (( minor < 11 )); then
            warn "Installed ${ver} is too old (need >= 0.11). Fetching from GitHub..."
            install_neovim_github
        fi
    fi

    has nvim \
        && ok "neovim — $(nvim --version | head -1)" \
        || err "Failed to install Neovim"
}

install_neovim_github() {
    local arch tarball
    arch="$(uname -m)"

    case "${OS}-${arch}" in
        linux-x86_64)  tarball="nvim-linux-x86_64.tar.gz" ;;
        linux-aarch64) tarball="nvim-linux-arm64.tar.gz" ;;
        *) err "No prebuilt Neovim binary for ${OS}-${arch}. Install manually." ;;
    esac

    local tag
    tag="$(curl -fsSL https://api.github.com/repos/neovim/neovim/releases/latest \
           | grep '"tag_name"' | head -1 | cut -d'"' -f4)"
    info "Latest release: ${tag}"

    local url="https://github.com/neovim/neovim/releases/download/${tag}/${tarball}"
    local tmp
    tmp="$(mktemp -d)"

    info "Downloading ${url}..."
    curl -fsSL "$url" -o "${tmp}/${tarball}"
    tar -xzf "${tmp}/${tarball}" -C "${tmp}"

    local extracted
    extracted="$(find "$tmp" -maxdepth 1 -type d -name 'nvim-*' | head -1)"

    sudo rm -rf /opt/nvim
    sudo mv "$extracted" /opt/nvim
    sudo ln -sf /opt/nvim/bin/nvim /usr/local/bin/nvim
    rm -rf "$tmp"
}

# ============================================================
#  Nerd Font
# ============================================================
install_nerd_font() {
    section "Nerd Font (${NERD_FONT})"

    local font_dir
    [[ "$OS" == "macos" ]] \
        && font_dir="$HOME/Library/Fonts" \
        || font_dir="$HOME/.local/share/fonts"

    if find "$font_dir" -maxdepth 2 -name "*${NERD_FONT}*NerdFont*" 2>/dev/null | grep -q .; then
        ok "${NERD_FONT} Nerd Font — already installed"
        nerd_font_hint
        return 0
    fi

    local url="https://github.com/ryanoasis/nerd-fonts/releases/latest/download/${NERD_FONT}.zip"
    local tmp
    tmp="$(mktemp -d)"

    info "Downloading ${NERD_FONT} Nerd Font..."
    curl -fsSL "$url" -o "${tmp}/font.zip"

    mkdir -p "$font_dir"
    unzip -o "${tmp}/font.zip" -d "$font_dir" >/dev/null 2>&1
    rm -rf "$tmp"

    if [[ "$OS" == "linux" ]] && has fc-cache; then
        fc-cache -f "$font_dir" >/dev/null 2>&1
    fi

    local count
    count="$(find "$font_dir" -maxdepth 2 -name "*${NERD_FONT}*" 2>/dev/null | wc -l | tr -d ' ')"
    ok "Installed ${count} font files into ${font_dir}"
    nerd_font_hint
}

nerd_font_hint() {
    echo ""
    echo -e "  ${YELLOW}${BOLD}⚠  Set your terminal font manually:${NC}"
    echo -e "     ${GREEN}${NERD_FONT} Nerd Font${NC}            ← correct (full-size icons)"
    echo -e "     ${RED}${NERD_FONT} Nerd Font Mono${NC}       ← icons will be small"
    echo ""
    echo -e "  Where to change:"
    echo -e "    iTerm2       → Preferences → Profiles → Text → Font"
    echo -e "    Alacritty    → ~/.config/alacritty/alacritty.toml"
    echo -e "    Kitty        → ~/.config/kitty/kitty.conf   (font_family)"
    echo -e "    WezTerm      → ~/.config/wezterm/wezterm.lua"
    echo -e "    GNOME Term   → Preferences → Profile → Custom font"
    echo ""
}

# ============================================================
#  Node.js + npm
# ============================================================
ensure_node() {
    if has node && has npm; then return 0; fi

    section "Node.js"
    info "Installing Node.js..."

    case "$PKG" in
        brew)   brew install node ;;
        pacman) sudo pacman -S --needed --noconfirm nodejs npm ;;
        apt)    sudo apt-get install -y nodejs npm ;;
        dnf)    sudo dnf install -y nodejs npm ;;
        yum)    sudo yum install -y nodejs npm ;;
        zypper) sudo zypper install -y nodejs npm ;;
        apk)    sudo apk add nodejs npm ;;
    esac

    has node && ok "node $(node --version)" || err "Failed to install Node.js"
    has npm  && ok "npm $(npm --version)"   || err "Failed to install npm"
}

# ============================================================
#  npm packages
# ============================================================
install_npm_packages() {
    [[ ${#NPM_PACKAGES[@]} -eq 0 ]] && return 0

    section "npm packages"
    ensure_node

    for p in "${NPM_PACKAGES[@]}"; do
        local bin
        bin="$(pkg_bin "$p")"
        if has "$bin"; then
            ok "${p} — already installed"
        else
            info "npm install -g ${p}..."
            npm install -g "$p"
            ok "$p"
        fi
    done
}

# ============================================================
#  Python + pip (PEP 668 / Arch safe)
# ============================================================
ensure_python() {
    if has python3; then return 0; fi

    section "Python"
    info "Installing Python..."

    case "$PKG" in
        brew)   brew install python ;;
        pacman) sudo pacman -S --needed --noconfirm python ;;
        apt)    sudo apt-get install -y python3 python3-pip python3-venv ;;
        dnf)    sudo dnf install -y python3 python3-pip ;;
        yum)    sudo yum install -y python3 python3-pip ;;
        zypper) sudo zypper install -y python3 python3-pip ;;
        apk)    sudo apk add python3 py3-pip ;;
    esac

    has python3 && ok "python3 $(python3 --version)" || err "Failed to install Python"
}

is_externally_managed() {
    [[ "$PKG" == "pacman" ]] && return 0
    [[ "$PKG" == "brew" ]]   && return 0
    local stdlib
    stdlib="$(python3 -c 'import sysconfig; print(sysconfig.get_path("stdlib"))' 2>/dev/null)"
    [[ -f "${stdlib}/EXTERNALLY-MANAGED" ]] && return 0
    return 1
}

pip_install() {
    local pkg="$1"

    if is_externally_managed; then
        if [[ ! -d "$VENV_DIR" ]]; then
            info "Creating venv at ${VENV_DIR} (PEP 668 / externally managed)..."
            python3 -m venv "$VENV_DIR"
        fi
        "${VENV_DIR}/bin/pip" install --upgrade "$pkg"

        mkdir -p "$HOME/.local/bin"
        for bin_file in "${VENV_DIR}/bin/"*; do
            local name
            name="$(basename "$bin_file")"
            case "$name" in python*|pip*|activate*|Activate*) continue ;; esac
            ln -sf "$bin_file" "$HOME/.local/bin/${name}"
        done
    else
        python3 -m pip install --user --upgrade "$pkg"
    fi
}

install_pip_packages() {
    [[ ${#PIP_PACKAGES[@]} -eq 0 ]] && return 0

    section "Python packages"
    ensure_python

    for p in "${PIP_PACKAGES[@]}"; do
        info "pip install ${p}..."
        pip_install "$p"
        ok "$p"
    done

    if is_externally_managed; then
        info "Packages installed in venv: ${VENV_DIR}"
        info "Binaries symlinked to ~/.local/bin"
        echo -e "  ${YELLOW}Make sure ${GREEN}\$HOME/.local/bin${YELLOW} is in your \$PATH${NC}"
    fi

    configure_nvim_python
}

# ============================================================
#  Neovim Python provider (global plugin — works for ALL configs)
# ============================================================
configure_nvim_python() {
    local venv_python="${VENV_DIR}/bin/python3"
    [[ ! -x "$venv_python" ]] && return 0

    if ! "$venv_python" -c "import pynvim" 2>/dev/null; then
        warn "pynvim not importable from ${venv_python}"
        return 1
    fi

    section "Neovim Python provider"

    # Global plugin loaded by every Neovim config automatically
    # ~/.local/share/nvim/site/plugin/ is always in runtimepath
    local plugin_dir="$HOME/.local/share/nvim/site/plugin"
    local plugin_file="${plugin_dir}/python3_host.lua"

    if [[ -f "$plugin_file" ]]; then
        if grep -q "$venv_python" "$plugin_file" 2>/dev/null; then
            ok "Global plugin already configured: ${plugin_file}"
            return 0
        fi
    fi

    mkdir -p "$plugin_dir"

    cat > "$plugin_file" << EOF
-- Auto-generated by install.sh
-- Points Neovim Python 3 provider to the venv with pynvim.
-- Applies to ALL Neovim configs (NvChad, LazyVim, kickstart, custom, etc.)
-- Any config can override by setting vim.g.python3_host_prog itself.
-- To undo: delete this file.
if not vim.g.python3_host_prog then
  vim.g.python3_host_prog = "${venv_python}"
end
EOF

    ok "Created global plugin: ${plugin_file}"
    info "Applies to every Neovim config automatically"
    info "To undo: rm ${plugin_file}"
}

# ============================================================
#  Verification
# ============================================================
verify() {
    section "Verification"

    local cmds=(nvim git node npm rg python3 tree-sitter)
    local all_ok=true

    for cmd in "${cmds[@]}"; do
        if has "$cmd"; then
            local ver=""
            case "$cmd" in
                nvim)        ver="$(nvim --version | head -1)" ;;
                git)         ver="$(git --version)" ;;
                node)        ver="node $(node --version 2>/dev/null)" ;;
                npm)         ver="npm $(npm --version 2>/dev/null)" ;;
                rg)          ver="$(rg --version | head -1)" ;;
                python3)     ver="$(python3 --version)" ;;
                tree-sitter) ver="$(tree-sitter --version 2>/dev/null || echo 'installed')" ;;
            esac
            ok "✓ ${cmd}: ${ver}"
        else
            warn "✗ ${cmd}: not found"
            all_ok=false
        fi
    done

    # Check font
    local font_dir
    [[ "$OS" == "macos" ]] \
        && font_dir="$HOME/Library/Fonts" \
        || font_dir="$HOME/.local/share/fonts"

    if find "$font_dir" -maxdepth 2 -name "*${NERD_FONT}*NerdFont*" 2>/dev/null | grep -q .; then
        ok "✓ ${NERD_FONT} Nerd Font: installed"
    else
        warn "✗ ${NERD_FONT} Nerd Font: not found"
        all_ok=false
    fi

    # Check Neovim Python provider
    local venv_python="${VENV_DIR}/bin/python3"
    local plugin_file="$HOME/.local/share/nvim/site/plugin/python3_host.lua"
    if [[ -f "$plugin_file" ]] && [[ -x "$venv_python" ]]; then
        ok "✓ Neovim Python provider: global plugin active"
    else
        warn "✗ Neovim Python provider: not configured"
        all_ok=false
    fi

    echo ""
    if $all_ok; then
        echo -e "  ${GREEN}${BOLD}All dependencies are ready!${NC}"
    else
        echo -e "  ${YELLOW}${BOLD}Some items are missing — check warnings above.${NC}"
    fi
}

# ============================================================
#  Main
# ============================================================
main() {
    echo ""
    echo -e "${BOLD}Neovim development environment setup${NC}"
    echo ""

    detect_os
    pkg_update

    install_system_packages
    install_neovim
    install_nerd_font
    install_npm_packages
    install_pip_packages

    verify

    echo ""
    ok "Done! Restart your terminal and set the Nerd Font."
    echo ""
}

main "$@"
