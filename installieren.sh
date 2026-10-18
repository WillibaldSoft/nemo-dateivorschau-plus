#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Keep this file beside nemo-dateivorschau-plus_2.14.1_amd64.deb.
set -eu
installer_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
installer_deb="$installer_dir/nemo-dateivorschau-plus_2.14.1_amd64.deb"
if ! command -v apt-get >/dev/null 2>&1; then
    echo 'Dieser Installer benötigt Debian/Ubuntu/Linux Mint mit apt-get.' >&2
    exit 1
fi
if [ ! -f "$installer_deb" ]; then
    echo "Paket nicht gefunden: $installer_deb" >&2
    exit 1
fi
echo 'Prüfe Paket und Abhängigkeiten; es wird noch nichts installiert …'
dpkg-deb --field "$installer_deb" Package Version Depends
apt-get --simulate install "$installer_deb"
if [ "${1:-}" = '--check' ]; then exit 0; fi
echo 'apt installiert fehlende Abhängigkeiten und verwendet passende vorhandene Pakete.'
if [ "$(id -u)" -eq 0 ]; then
    apt-get install "$installer_deb"
else
    sudo apt-get install "$installer_deb"
fi
echo 'Fertig. Nemo bzw. Thunar nach dem Schließen offener Dateivorgänge mit nemo -q bzw. thunar -q beenden und erneut öffnen.'
