#!/usr/bin/env bash
# Build dist/swirl_<version>_amd64.deb from the PyInstaller folder app.
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION=$(python -c "import swirl; print(swirl.__version__)")
pyinstaller --noconfirm --clean --distpath ../dist --workpath ../build swirl.spec

PKG=../build/deb/swirl_${VERSION}_amd64
rm -rf "$PKG"
mkdir -p "$PKG/DEBIAN" "$PKG/opt" "$PKG/usr/bin" "$PKG/usr/share/applications" "$PKG/usr/share/icons/hicolor/256x256/apps"
cp -r ../dist/swirl "$PKG/opt/swirl"
ln -s /opt/swirl/swirl "$PKG/usr/bin/swirl"
cp ../swirl/assets/swirl-256.png "$PKG/usr/share/icons/hicolor/256x256/apps/swirl.png"

cat > "$PKG/usr/share/applications/swirl-bubble.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Swirl
Comment=Drop files on the bubble to convert them
Exec=/usr/bin/swirl --bubble
Icon=swirl
Categories=Utility;
Terminal=false
DESKTOP

cat > "$PKG/DEBIAN/control" <<CONTROL
Package: swirl
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: amd64
Maintainer: Swirl <hello@example.com>
Depends: libegl1, libxkbcommon-x11-0, libxcb-cursor0, libfontconfig1
Recommends: ffmpeg, libreoffice-core, libreoffice-writer, pandoc
Description: Convert files from a wheel at your cursor
 Right-click files, pick a format from the wheel, and the converted copy is
 saved beside the original. Images, PDFs, video, audio and documents.
 Everything runs on your computer; files never leave it.
CONTROL

cat > "$PKG/DEBIAN/postinst" <<'POSTINST'
#!/bin/sh
echo "Swirl installed. Run 'swirl --install' (as your normal user) to add it to the right-click menu."
POSTINST
chmod 755 "$PKG/DEBIAN/postinst"

dpkg-deb --build --root-owner-group "$PKG" "../dist/swirl_${VERSION}_amd64.deb"
echo "built dist/swirl_${VERSION}_amd64.deb"
