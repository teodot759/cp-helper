#!/usr/bin/env bash
# Build a standalone Linux bundle.
#
#   packaging/build-linux.sh            -> dist/CppHelper/CppHelper
#   packaging/build-linux.sh appimage   -> also tries appimagetool

set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -x .venv/bin/python ]]; then
    python3 -m venv .venv
    .venv/bin/pip install -e .
fi

if ! .venv/bin/python -c "import PyInstaller" 2>/dev/null; then
    .venv/bin/pip install pyinstaller
fi

.venv/bin/pyinstaller packaging/cpp-helper.spec --noconfirm --clean
echo "Built: $(pwd)/dist/CppHelper/CppHelper"

if [[ "${1:-}" == "appimage" ]]; then
    APPDIR="build/AppDir"
    rm -rf "$APPDIR"
    mkdir -p "$APPDIR/usr/bin"
    cp -r dist/CppHelper/* "$APPDIR/usr/bin/"
    cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/CppHelper" "$@"
EOF
    chmod +x "$APPDIR/AppRun"
    cp cppjudge/resources/icon.svg "$APPDIR/cpp-helper.svg"
    cat > "$APPDIR/cpp-helper.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=C++ Helper
Exec=CppHelper
Icon=cpp-helper
Categories=Development;
EOF
    if command -v appimagetool >/dev/null; then
        appimagetool "$APPDIR" dist/CppHelper-x86_64.AppImage
        echo "Built: $(pwd)/dist/CppHelper-x86_64.AppImage"
    else
        echo "appimagetool not found; AppDir prepared at $APPDIR" >&2
    fi
fi
