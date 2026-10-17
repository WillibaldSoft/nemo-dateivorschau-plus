#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu
cd "$(dirname "$0")"
out=${1:-"$PWD/dist"}
mkdir -p "$out"
out=$(cd "$out" && pwd)
root="$PWD/package"
rm -rf "$root"
mkdir -p "$root/DEBIAN" "$root/usr/bin" "$root/usr/lib/nemo-dateivorschau-plus" "$root/usr/share/applications" "$root/usr/share/nemo/actions" "$root/usr/share/doc/nemo-dateivorschau-plus" "$root/usr/share/nemo-python/extensions" "$root/usr/share/icons/hicolor/scalable/actions"
cat > "$root/DEBIAN/control" <<'EOF'
Package: nemo-dateivorschau-plus
Conflicts: bilddetails
Replaces: bilddetails
Provides: bilddetails (= 2.14.0)
Version: 2.14.0
Section: graphics
Priority: optional
Architecture: amd64
Depends: python3 (>= 3.8), python3-gi, gir1.2-gtk-3.0, libimage-exiftool-perl, nemo-python, @PYTHON_RUNTIME@, gir1.2-gdkpixbuf-2.0, python3-gi-cairo, poppler-utils, libreoffice-writer, libreoffice-calc, python3-uno, libreoffice-impress, libreoffice-draw, libreoffice-math, libarchive-tools, ffmpeg
Recommends: nemo | thunar
Maintainer: Nemo Dateivorschau Plus <nemo-dateivorschau-plus@localhost>
Description: Datei-Vorschau und Bildmetadateneditor fuer Nemo und Thunar
 Grafischer GTK-Viewer und Editor fuer Kamera-, Objektiv-, Aufnahme-,
 EXIF- und XMP-Daten. RAW-Bilder werden ueber XMP-Begleitdateien bearbeitet.
 Rechte Vorschau fuer Bilder, Office, PDF, EPUB, Text, Medien und Archive.
 Mit Zoom, Folien-/Seitenwechsel, verschiebbarem Trenner und Ausblendsymbol.
EOF
cat > "$root/usr/bin/nemo-dateivorschau-plus" <<'EOF'
#!/bin/sh
exec /usr/bin/python3 /usr/lib/nemo-dateivorschau-plus/app.py "$@"
EOF
ln -s nemo-dateivorschau-plus "$root/usr/bin/bilddetails"
cp assets/*.svg "$root/usr/share/icons/hicolor/scalable/actions/"
cp src/*.py "$root/usr/lib/nemo-dateivorschau-plus/"
python_soname=$(/usr/bin/python3 -c 'import sysconfig; print(sysconfig.get_config_var("INSTSONAME"))')
python_library=$(/usr/bin/python3 -c 'import sysconfig; print(sysconfig.get_config_var("LIBDIR"))')/$python_soname
python_runtime=$(dpkg-query -S "$python_library" | head -n 1 | cut -d: -f1)
test -n "$python_runtime"
sed -i "s/@PYTHON_RUNTIME@/$python_runtime/" "$root/DEBIAN/control"
mkdir -p "$root/usr/lib/x86_64-linux-gnu/thunarx-3"
cc -shared -fPIC -O2 -Wall -Wextra -Werror -DPYTHON_SONAME="\"$python_soname\"" thunar/loader.c -o "$root/usr/lib/x86_64-linux-gnu/thunarx-3/dateivorschau-plus.so" -ldl
cp nemo/bilddetails_preview.py "$root/usr/share/nemo-python/extensions/"
cat > "$root/usr/share/applications/nemo-dateivorschau-plus.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Nemo Dateivorschau Plus
Comment=Bild-, Kamera- und EXIF-Informationen anzeigen und bearbeiten
Exec=nemo-dateivorschau-plus %U
TryExec=nemo-dateivorschau-plus
Icon=camera-photo
Terminal=false
Categories=Graphics;Photography;
MimeType=image/jpeg;image/png;image/tiff;image/webp;image/heif;image/heic;image/x-canon-cr2;image/x-canon-cr3;image/x-nikon-nef;image/x-adobe-dng;image/x-sony-arw;image/x-fuji-raf;image/x-panasonic-rw2;image/x-olympus-orf;
StartupNotify=true
EOF
cat > "$root/usr/share/nemo/actions/bilddetails.nemo_action" <<'EOF'
[Nemo Action]
Active=true
Name=Bilddetails anzeigen / bearbeiten
Comment=Datei-, Kamera-, GPS-, EXIF- und XMP-Informationen
Exec=nemo-dateivorschau-plus %U
Icon-Name=camera-photo
Selection=notnone
Extensions=jpg;jpeg;jpe;png;tif;tiff;heic;heif;webp;cr2;cr3;crw;dng;nef;nrw;arw;srf;sr2;orf;rw2;raf;pef;ptx;srw;3fr;fff;iiq;kdc;dcr;mrw;mos;raw;rwl;x3f;
Dependencies=nemo-dateivorschau-plus;exiftool;
Quote=double
Terminal=false
UriScheme=file
EOF
cp LICENSE README.txt FORMATE.txt "$root/usr/share/doc/nemo-dateivorschau-plus/"
runtime=${BILDDETAILS_BUILD_GIMP3:-"$PWD/../gimp32-runtime/squashfs-root"}
if [ ! -x "$runtime/bilddetails-console" ]; then
    echo "Geprüfte GIMP-3-Runtime fehlt: $runtime" >&2
    exit 1
fi
cp -a "$runtime" "$root/usr/lib/nemo-dateivorschau-plus/gimp3"
cp GIMP3-RUNTIME.txt "$root/usr/share/doc/nemo-dateivorschau-plus/"
cp /usr/share/common-licenses/GPL-3 "$root/usr/share/doc/nemo-dateivorschau-plus/GIMP-GPL-3.txt"
chmod -R u=rwX,go=rX "$root"
chmod 755 "$root/usr/bin/nemo-dateivorschau-plus"
find "$root" -type d -exec chmod 755 {} +
installed_size=$(du -sk "$root/usr" | cut -f1)
printf 'Installed-Size: %s\n' "$installed_size" >> "$root/DEBIAN/control"
dpkg-deb --threads-max=2 -Zzstd -z6 --root-owner-group --build "$root" "$out/nemo-dateivorschau-plus_2.14.0_amd64.deb"

cp installieren.sh "$out/Nemo-Dateivorschau-Plus-2.14-installieren.sh"
chmod 755 "$out/Nemo-Dateivorschau-Plus-2.14-installieren.sh"
