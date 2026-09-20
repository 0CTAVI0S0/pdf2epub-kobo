#!/usr/bin/env bash
# Build a Linux binary and, if appimagetool is available, wrap it as AppImage.
set -euo pipefail
python3 -m pip install -r requirements.txt pyinstaller
python3 -m PyInstaller --noconfirm pdf2epub.spec
echo "Binario: dist/pdf2epub-kobo"

if command -v appimagetool >/dev/null 2>&1; then
  APPDIR=dist/pdf2epub-kobo.AppDir
  rm -rf "$APPDIR"
  mkdir -p "$APPDIR/usr/bin"
  cp dist/pdf2epub-kobo "$APPDIR/usr/bin/"
  cat > "$APPDIR/pdf2epub-kobo.desktop" <<'EOF'
[Desktop Entry]
Name=PDF to EPUB for Kobo
Exec=pdf2epub-kobo
Icon=pdf2epub-kobo
Type=Application
Categories=Office;
EOF
  cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/pdf2epub-kobo" "$@"
EOF
  chmod +x "$APPDIR/AppRun"
  appimagetool "$APPDIR" dist/pdf2epub-kobo.AppImage
  echo "AppImage: dist/pdf2epub-kobo.AppImage"
else
  echo "appimagetool no está instalado; se deja el binario de PyInstaller."
  echo "Instálalo desde https://github.com/AppImage/appimagetool para generar el .AppImage."
fi
