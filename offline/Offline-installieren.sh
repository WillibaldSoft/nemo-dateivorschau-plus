#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail
bundle_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
check_only=false
case "${1:-}" in
  --check) check_only=true ;;
  '') ;;
  *) echo 'Aufruf: bash Offline-installieren.sh [--check]' >&2; exit 2 ;;
esac
. /etc/os-release
if [[ ${ID:-} != linuxmint || ${VERSION_ID:-} != 22* || ${UBUNTU_CODENAME:-} != noble ]]; then
    echo 'Dieses Offline-Paket ist für Linux Mint 22.x (Ubuntu Noble), nicht Mint 21/LMDE.' >&2
    exit 1
fi
if [[ $(dpkg --print-architecture) != amd64 ]]; then
    echo 'Dieses Offline-Paket benötigt AMD64 (x86-64).' >&2; exit 1
fi
if ! $check_only && [[ $(id -u) != 0 ]]; then
    exec sudo -- /bin/bash "$bundle_dir/Offline-installieren.sh"
fi
scratch=$(mktemp -d /tmp/nemo-offline.XXXXXXXX)
trap 'rm -rf -- "$scratch"' EXIT
chmod 755 "$scratch"
# Load no global APT hooks or third-party repositories for this transaction.
printf 'Dir::Etc::parts "%s/empty";\nDir::Etc::main "%s/empty-apt.conf";\n' "$scratch" "$scratch" > "$scratch/apt.conf"
export APT_CONFIG="$scratch/apt.conf"
echo 'Prüfe Vollständigkeit und SHA256 aller mitgelieferten Dateien …'
if ! (cd "$bundle_dir" && sha256sum --strict -c SHA256SUMS) > "$scratch/pruefung.log" 2>&1; then
    cat "$scratch/pruefung.log" >&2
    echo 'Prüfsummenfehler: Archiv erneut vollständig entpacken.' >&2; exit 1
fi
mkdir -p "$scratch/lists/partial" "$scratch/archives/partial" "$scratch/empty"
bundle_uri=$(/usr/bin/python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).as_uri())' "$bundle_dir")
printf 'deb [trusted=yes] %s ./\n' "$bundle_uri" > "$scratch/sources.list"
# Optional repositories follow the installed Office branch.
# Standard Mint installations keep the official Noble LibreOffice branch.
office_version=$(dpkg-query -W -f='${Version}' libreoffice-core 2>/dev/null || true)
if [[ "$office_version" == 4:25.8* ]]; then
    if [[ ! -f "$bundle_dir/office-still/Packages" ]]; then
        echo 'Ergänzung für vorhandenes LibreOffice 25.8 fehlt.' >&2; exit 1
    fi
    printf 'deb [trusted=yes] %s/office-still ./\n' "$bundle_uri" >> "$scratch/sources.list"
    echo 'Vorhandenes LibreOffice 25.8 erkannt: passende Still-Ergänzung aktiviert.'
fi
if [[ "$office_version" == 4:26.2* ]]; then
    if [[ ! -f "$bundle_dir/office-26/Packages" ]]; then
        echo 'Ergänzung für vorhandenes LibreOffice 26.2 fehlt.' >&2; exit 1
    fi
    printf 'deb [trusted=yes] %s/office-26 ./\n' "$bundle_uri" >> "$scratch/sources.list"
    echo 'Vorhandenes LibreOffice 26.2 erkannt: passende Backports-Ergänzung aktiviert.'
fi
# Populate the private APT cache. --no-download prohibits fetching anything;
# the only configured repository is the checksum-verified local bundle.
for package in "$bundle_dir"/pakete/*.deb "$bundle_dir"/office-still/pakete/*.deb "$bundle_dir"/office-26/pakete/*.deb; do
    [[ -f "$package" ]] || continue
    ln -s "$package" "$scratch/archives/$(basename "$package")"
done
apt_options=(
    -o "Dir::Etc::sourcelist=$scratch/sources.list"
    -o "Dir::Etc::sourceparts=$scratch/empty"
    -o "Dir::Etc::preferences=$scratch/empty-preferences"
    -o "Dir::Etc::preferencesparts=$scratch/empty"
    -o "Dir::State::lists=$scratch/lists"
    -o "Dir::Cache::archives=$scratch/archives"
    -o "Dir::Cache::pkgcache=$scratch/pkgcache.bin"
    -o "Dir::Cache::srcpkgcache=$scratch/srcpkgcache.bin"
    -o APT::Install-Recommends=false
    -o APT::Install-Suggests=false
    -o "APT::Sandbox::User=$(id -un)"
    -o Acquire::Languages=none
)
touch "$scratch/empty-preferences" "$scratch/empty-apt.conf"
apt-get "${apt_options[@]}" update
# Explicit requests also repair a previous dpkg-only, unconfigured install.
install_requests=(nemo-dateivorschau-plus=2.14.2 libreoffice-math)
legacy_status=$(dpkg-query -W -f='${db:Status-Status}' bilddetails 2>/dev/null || true)
case "$legacy_status" in
    installed|unpacked|half-configured|half-installed|triggers-pending|triggers-awaited)
        install_requests+=(bilddetails-) ;;
esac
# Reject unrelated package removals, and never allow automatic downgrades.
LC_ALL=C apt-get "${apt_options[@]}" --simulate --fix-broken --no-download install \
    "${install_requests[@]}" > "$scratch/plan.log" 2>&1 || {
    cat "$scratch/plan.log" >&2
    echo 'Die vorhandenen Paketversionen sind mit diesem Offline-Satz nicht auflösbar.' >&2
    echo 'Es wurde nichts installiert; bitte diese Ausgabe zur Prüfung weitergeben.' >&2
    exit 1
}
cat "$scratch/plan.log"
if grep -q 'The following packages will be DOWNGRADED:' "$scratch/plan.log"; then
    echo 'Abbruch: Diese Paketkombination würde vorhandene Pakete zurückstufen.' >&2
    exit 1
fi
if awk '$1 == "Remv" && $2 != "bilddetails" {bad=1} END {exit !bad}' "$scratch/plan.log"; then
    echo 'Abbruch: APT würde weitere vorhandene Pakete entfernen. Es wurde nichts installiert.' >&2
    exit 1
fi
if $check_only; then
    echo 'Offline-Prüfung bestanden. Es wurde nichts installiert.'; exit 0
fi
echo 'Installiere ausschließlich aus dem mitgelieferten Offline-Paketbestand …'
apt-get "${apt_options[@]}" --fix-broken --no-download install "${install_requests[@]}"
echo 'Fertig. Nach Abschluss offener Dateivorgänge Nemo bzw. Thunar neu starten.'
echo 'Nemo: nemo -q   |   Thunar: thunar -q'
