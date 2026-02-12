#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# PyWarp Universal Installer (Linux & macOS)
# ==============================================================================

APP_NAME="PyWarp"
REPO_OWNER="saeedmasoudie"
REPO_NAME="pywarp"

# --- Version Handling ---
VERSION="${1:-latest}"

if [[ "$VERSION" == "latest" ]]; then
    REPO_URL="https://github.com/${REPO_OWNER}/${REPO_NAME}/archive/refs/heads/main.zip"
else
    REPO_URL="https://github.com/${REPO_OWNER}/${REPO_NAME}/archive/refs/tags/v${VERSION}.zip"
fi

DEFAULT_INSTALL_DIR="$HOME/$APP_NAME"

# --- Colors ---
BLUE='\033[0;34m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

clear
echo -e "${BLUE}============================================================${NC}"
echo -e "${BLUE}              $APP_NAME Installer for Unix                  ${NC}"
echo -e "${BLUE}============================================================${NC}"

# ------------------------------------------------------------------------------
# 1. Pre-flight Checks
# ------------------------------------------------------------------------------

OS="$(uname -s)"

require_command() {
    if ! command -v "$1" &> /dev/null; then
        echo -e "${RED}[Error] Required command not found: $1${NC}"
        exit 1
    fi
}

require_command python3
require_command unzip

if command -v curl &> /dev/null; then
    DOWNLOADER="curl -L -o"
elif command -v wget &> /dev/null; then
    DOWNLOADER="wget -O"
else
    echo -e "${RED}[Error] curl or wget is required.${NC}"
    exit 1
fi

# ------------------------------------------------------------------------------
# 2. User Input
# ------------------------------------------------------------------------------

echo -e "Where would you like to install $APP_NAME?"
read -rp "Path [Default: $DEFAULT_INSTALL_DIR]: " INSTALL_DIR
INSTALL_DIR="${INSTALL_DIR:-$DEFAULT_INSTALL_DIR}"

if [[ -d "$INSTALL_DIR" ]]; then
    echo -e "${YELLOW}[Warning] Directory exists. Contents may be overwritten.${NC}"
fi

echo -e "\n${GREEN}Target:${NC} $INSTALL_DIR"
echo -e "${GREEN}System:${NC} $OS"
echo ""
read -rp "Press Enter to begin installation..."

# ------------------------------------------------------------------------------
# 3. Installation
# ------------------------------------------------------------------------------

echo -e "\n${BLUE}Step 1/3: Preparing Environment...${NC}"

mkdir -p "$INSTALL_DIR"

python3 -m venv "$INSTALL_DIR/venv" || {
    echo -e "${RED}Failed to create virtual environment.${NC}"
    exit 1
}

VENV_PYTHON="$INSTALL_DIR/venv/bin/python"
VENV_PIP="$INSTALL_DIR/venv/bin/pip"

echo -e "\n${BLUE}Step 2/3: Downloading & Installing...${NC}"

cd "$INSTALL_DIR"

echo "Downloading repository..."
$DOWNLOADER repo.zip "$REPO_URL"

echo "Extracting..."
unzip -o -q repo.zip
rm repo.zip

# Handle GitHub nested folder
EXTRACTED_DIR="$(find . -maxdepth 1 -type d -name "${REPO_NAME}-*" | head -n1 || true)"
if [[ -n "$EXTRACTED_DIR" ]]; then
    cp -r "$EXTRACTED_DIR"/* .
    rm -rf "$EXTRACTED_DIR"
fi

echo "Installing dependencies..."
"$VENV_PIP" install --upgrade pip > /dev/null

if [[ -f "requirements.txt" ]]; then
    "$VENV_PIP" install -r requirements.txt
else
    echo -e "${YELLOW}[Warning] requirements.txt not found.${NC}"
fi

# ------------------------------------------------------------------------------
# 4. OS Specific Shortcuts
# ------------------------------------------------------------------------------

echo -e "\n${BLUE}Step 3/3: Creating Shortcuts...${NC}"

if [[ "$OS" == "Darwin" ]]; then
    # ================= MACOS =================
    APP_BUNDLE="$HOME/Desktop/${APP_NAME}.app"
    CONTENTS="$APP_BUNDLE/Contents"

    rm -rf "$APP_BUNDLE"

    mkdir -p "$CONTENTS/MacOS"
    mkdir -p "$CONTENTS/Resources"

    cat > "$CONTENTS/MacOS/launcher" <<EOF
#!/usr/bin/env bash
"$VENV_PYTHON" "$INSTALL_DIR/main.py"
EOF

    chmod +x "$CONTENTS/MacOS/launcher"

    cat > "$CONTENTS/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>launcher</string>
    <key>CFBundleIdentifier</key>
    <string>com.pywarp.app</string>
    <key>CFBundleName</key>
    <string>${APP_NAME}</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
</dict>
</plist>
EOF

    if [[ -f "assets/logo.icns" ]]; then
        cp "assets/logo.icns" "$CONTENTS/Resources/AppIcon.icns"
    fi

    echo -e "${GREEN}Success! ${APP_NAME}.app created on Desktop.${NC}"

elif [[ "$OS" == "Linux" ]]; then
    # ================= LINUX =================
    DESKTOP_FILE="$HOME/.local/share/applications/pywarp.desktop"
    mkdir -p "$HOME/.local/share/applications"

    ICON_PATH="$INSTALL_DIR/assets/logo.png"

    cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Name=${APP_NAME}
Exec="${VENV_PYTHON}" "${INSTALL_DIR}/main.py"
Icon=${ICON_PATH}
Type=Application
Categories=Utility;Development;
Terminal=false
StartupNotify=true
EOF

    chmod +x "$DESKTOP_FILE"

    if [[ -d "$HOME/Desktop" ]]; then
        cp "$DESKTOP_FILE" "$HOME/Desktop/"
        chmod +x "$HOME/Desktop/pywarp.desktop"
    fi

    echo -e "${GREEN}Success! Shortcut added to Applications menu.${NC}"
fi

# ------------------------------------------------------------------------------
# 5. Uninstaller
# ------------------------------------------------------------------------------

cat > "$INSTALL_DIR/uninstall.sh" <<EOF
#!/usr/bin/env bash
rm -rf "$INSTALL_DIR"
if [[ "\$(uname -s)" == "Darwin" ]]; then
    rm -rf "\$HOME/Desktop/${APP_NAME}.app"
else
    rm -f "\$HOME/.local/share/applications/pywarp.desktop"
    rm -f "\$HOME/Desktop/pywarp.desktop"
fi
echo "${APP_NAME} has been removed."
EOF

chmod +x "$INSTALL_DIR/uninstall.sh"

echo -e "\n${GREEN}Installation Finished Successfully!${NC}"
echo -e "${GREEN}Run using shortcut or:${NC}"
echo -e "${GREEN}${VENV_PYTHON} ${INSTALL_DIR}/main.py${NC}"
exit 0
