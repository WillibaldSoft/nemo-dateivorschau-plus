# Nemo Dateivorschau Plus

Früher **Bilddetails**, jetzt **Nemo Dateivorschau Plus**.

Rechte, verstellbare Dateivorschau mit Zoom, PDF-/Office-Seitenwechsel,
XCF-Unterstützung über einen separaten GIMP-3-Decoder und Bildmetadateneditor.
Fotoshow-Studio-Archive lassen sich durchblättern und mit Start/Pause abspielen.
Große Shows werden schrittweise geladen; die Gesamtzahl wird nach dem ersten
Bild unabhängig im Hintergrund ermittelt.

## Installation

```sh
sudo apt install ./nemo-dateivorschau-plus_2.13.0_amd64.deb
nemo -q
```

Nemo danach erneut öffnen. Bedienung und Grenzen: [README.txt](README.txt),
Formate: [FORMATE.txt](FORMATE.txt).

## Bauen

Ziel: Linux Mint/Ubuntu/Debian auf AMD64 mit GTK 3 und Nemo 6.x.
Benötigt werden `dpkg-deb` mit Zstandard-Unterstützung, Python 3, curl und
sha256sum. Die Laufzeitabhängigkeiten stehen in `build.sh`.

```sh
sh fetch-gimp3-runtime.sh
sh build.sh "$PWD/dist"
```

Das Fetch-Skript lädt die offizielle GIMP-3.2.6-AppImage, prüft deren festgelegte
SHA256-Prüfsumme und entpackt sie in ein benachbartes Build-Verzeichnis.
Die Runtime wird nicht in Git abgelegt. Das fertige `.deb` ist wegen der
enthaltenen Runtime deutlich größer als der Quellcode.

## Tests

Benötigt werden die Paketabhängigkeiten und zusätzlich `imagemagick`,
`makeself`, `gimp-console-2.10` für die Legacy-XCF-Fixtures sowie ein GTK-Display. Bei installiertem Fotoshow Studio wird dessen
Generator optional im Integrationstest verwendet; sonst stehen eigenständige
Makeself-Fixtures bereit. Beispiel für eine isolierte Sitzung:

```sh
broadwayd -a 127.0.0.1 -p 18087 :39 &
test_display_pid=$!
trap 'kill "$test_display_pid" 2>/dev/null || true' EXIT
GDK_BACKEND=broadway BROADWAY_DISPLAY=:39 \
BILDDETAILS_GIMP3_RUNTIME="$PWD/../gimp32-runtime/squashfs-root" \
/usr/bin/python3 -m unittest discover -s . -p 'test_*.py' -v
```

Die Tests umfassen Metadaten, Quellen-Unverändertheit, echte Office-Dateien,
XCF-Effekte, Archive, Fotoshow-Navigation/Wiedergabe und Hintergrundzählung.
[TESTERGEBNISSE.txt](TESTERGEBNISSE.txt) beschreibt die Release-Prüfung.

## Veröffentlichung

Dieses Repository enthält weder Pakete noch Runtime, Caches oder private
Benutzerdateien. `main` und der Tag `v2.13.0` sind vorbereitet. Nach dem Anlegen
eines eigenen öffentlichen Repositorys kann ein Remote ergänzt werden:

```sh
git remote add origin <REPOSITORY-URL>
git push -u origin main --follow-tags
```

Pakete und Prüfsummen als Release-Anhänge hochladen, nicht in die Git-Historie.
Die Veröffentlichung erfolgt unter `WillibaldSoft/nemo-dateivorschau-plus`.

## Lizenz

GPL-3.0-or-later, siehe [LICENSE](LICENSE). Für die unverändert übernommene
GIMP-Runtime und enthaltene Bibliotheken gelten ihre jeweiligen Lizenzen.
Bezugsquellen und Prüfsummen: [GIMP3-RUNTIME.txt](GIMP3-RUNTIME.txt).

## Umstieg von Bilddetails

Das neue Paket ersetzt `bilddetails` über die Paketverwaltung. Die bisherigen
Einstellungen und Caches unter dem alten internen Namen bleiben verwendbar.
Der Befehl `bilddetails` bleibt als Kompatibilitätsalias erhalten. Nach dem
Update Nemo vollständig neu starten.
