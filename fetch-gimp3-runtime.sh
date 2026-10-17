#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu
source_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
runtime_root="$source_root/../gimp32-runtime"
mkdir -p "$runtime_root"
cd "$runtime_root"
name=GIMP-3.2.6-x86_64.AppImage
if [ ! -f "$name" ]; then
    curl --fail --location --output "$name.part" "https://download.gimp.org/gimp/v3.2/linux/$name"
    mv "$name.part" "$name"
fi
printf '%s  %s\n' '79ea41bc9b06f78fda181849a9ca8e42d83f1124dedb756f4d52352e2465010f' "$name" | sha256sum --check -
chmod 755 "$name"
"./$name" --appimage-extract > extract.log
python3 - <<'PY'
from pathlib import Path
root = Path('squashfs-root')
script = (root / 'AppRun').read_text()
assert '/usr/bin/org.gimp.GIMP.Stable' in script
script = script.replace('/usr/bin/org.gimp.GIMP.Stable', '/usr/bin/gimp-console-3.2')
assert (root / 'usr/bin/gimp-console-3.2').exists()
(root / 'bilddetails-console').write_text(script)
(root / 'bilddetails-console').chmod(0o755)
PY
