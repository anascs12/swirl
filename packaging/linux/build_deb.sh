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

cat > "$PKG/usr/share/applications/swirl-studio.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Swirl Studio
GenericName=PDF tools
Comment=Merge, split, compress, convert, edit and sign PDFs offline
Exec=/usr/bin/swirl --studio %F
Icon=swirl
Categories=Office;Utility;
Keywords=pdf;merge;split;compress;convert;sign;
MimeType=application/pdf;image/png;image/jpeg;image/webp;image/gif;image/bmp;image/tiff;application/vnd.openxmlformats-officedocument.wordprocessingml.document;application/msword;application/vnd.oasis.opendocument.text;application/rtf;application/vnd.openxmlformats-officedocument.presentationml.presentation;application/vnd.ms-powerpoint;application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;application/vnd.ms-excel;text/html;text/markdown;text/plain;video/mp4;video/quicktime;video/x-matroska;video/webm;audio/mpeg;audio/x-wav;audio/ogg;audio/flac;
Terminal=false
DESKTOP

# "Open With → Convert with Swirl": the wheel for the chosen files
cat > "$PKG/usr/share/applications/swirl-convert.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Convert with Swirl
Comment=Convert or compress these files from the Swirl wheel
Exec=/usr/bin/swirl %F
Icon=swirl
NoDisplay=true
MimeType=application/pdf;image/png;image/jpeg;image/webp;image/gif;image/bmp;image/tiff;application/vnd.openxmlformats-officedocument.wordprocessingml.document;application/msword;application/vnd.oasis.opendocument.text;application/rtf;application/vnd.openxmlformats-officedocument.presentationml.presentation;application/vnd.ms-powerpoint;application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;application/vnd.ms-excel;text/html;text/markdown;text/plain;video/mp4;video/quicktime;video/x-matroska;video/webm;audio/mpeg;audio/x-wav;audio/ogg;audio/flac;application/x-ipynb+json;
Terminal=false
DESKTOP

cat > "$PKG/usr/share/applications/swirl-bubble.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Swirl Bubble
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
Maintainer: Anas Khan <anaskhanbjr84@gmail.com>
Depends: libegl1, libxkbcommon-x11-0, libxcb-cursor0, libfontconfig1
Recommends: ffmpeg, libreoffice-core, libreoffice-writer, pandoc
Description: Convert files from a wheel at your cursor
 Right-click files, pick a format from the wheel, and the converted copy is
 saved beside the original. Images, PDFs, video, audio and documents.
 Everything runs on your computer; files never leave it.
CONTROL

cat > "$PKG/DEBIAN/preinst" <<'PREINST'
#!/bin/sh
# Stop a running Swirl (e.g. the bubble) so the old version isn't left handling files.
pkill -f '^/opt/swirl/swirl' 2>/dev/null || true
exit 0
PREINST
chmod 755 "$PKG/DEBIAN/preinst"

cat > "$PKG/DEBIAN/postinst" <<'POSTINST'
#!/bin/sh
pkill -f '^/opt/swirl/swirl' 2>/dev/null || true
update-desktop-database -q /usr/share/applications 2>/dev/null || true
echo "Swirl installed. Run 'swirl --install' (as your normal user) to add it to the right-click menu."
POSTINST
chmod 755 "$PKG/DEBIAN/postinst"

dpkg-deb --build --root-owner-group "$PKG" "../dist/swirl_${VERSION}_amd64.deb"
echo "built dist/swirl_${VERSION}_amd64.deb"
