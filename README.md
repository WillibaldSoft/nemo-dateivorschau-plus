# Nemo Dateivorschau Plus

Früher **Bilddetails**, jetzt **Nemo Dateivorschau Plus**.

Rechte, verstellbare Dateivorschau für **Nemo und Thunar** mit Zoom, PDF-/Office-Seitenwechsel,
XCF-Unterstützung über einen separaten GIMP-3-Decoder und Bildmetadateneditor.
Fotoshow-Studio-Archive lassen sich durchblättern und mit Start/Pause abspielen.
Große Shows werden schrittweise geladen; die Gesamtzahl wird nach dem ersten
Bild unabhängig im Hintergrund ermittelt.

## Installation

```sh
sudo apt install ./nemo-dateivorschau-plus_2.14.1_amd64.deb
nemo -q
```

Bei Thunar stattdessen `thunar -q` ausführen. Den Dateimanager danach erneut öffnen. Bedienung und Grenzen: [README.txt](README.txt),
Formate: [FORMATE.txt](FORMATE.txt).

## Offline installieren (Linux Mint 22.x / AMD64)

Das vollständige Offline-Archiv aus dem Release auf den Ziel-PC kopieren und
entpacken, dann im entpackten Ordner ausführen:

```sh
bash Offline-installieren.sh
```

Ohne Internet; 447 Basispakete einschließlich Hauptpaket und 24 zusätzliche
Pakete für bereits vorhandenes LibreOffice Still 25.8. Nicht für Mint 21,
LMDE oder ARM. SHA256-Prüfung und lokale APT-Auflösung sind integriert.
Nur prüfen: `bash Offline-installieren.sh --check`.
Einzelheiten und Grenzen: [Offline-Anleitung](offline/LIESMICH.txt).

## Bauen

Ziel: Linux Mint/Ubuntu/Debian auf AMD64 mit GTK 3 und Nemo 6.x bzw. Thunar 4.18/4.20 (GTK3).
Thunar 4.18.8 wurde direkt getestet; 4.20 verwendet denselben erkannten
Fensteraufbau, ist hier aber nicht als Laufzeit getestet. Unbekannte Aufbauten
werden unverändert gelassen.
Benötigt werden `dpkg-deb` mit Zstandard-Unterstützung, Python 3, ein C-Compiler (`gcc`), curl und
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

## Thunar

Die zusätzliche Leiste verwendet denselben Decoder, Cache, Metadateneditor und
alle Formate wie Nemo. Sie folgt der aktiven Dateiauswahl, auch in Tabs und
geteilten Ansichten. Eigenes Vorschau-Symbol und Zahnrad in der Werkzeugleiste;
Breite am Trenner ziehen. Die Einstellungen werden mit Nemo geteilt.
Thunars eingebaute einfache Bildvorschau kann unabhängig über Ansicht deaktiviert
werden, falls sie ebenfalls eingeschaltet ist. Unterstützt werden lokale Dateien.

Ein kleiner residenter Thunarx-Loader initialisiert die gemeinsame Python-
Vorschau im Thunar-Prozess. Die native Auswahl wird aus der GList-Eigenschaft
in Datei-URIs umgesetzt; es gibt kein globales Accessibility-Polling. Das Paket
benötigt kein `thunarx-python` und verändert keine vorhandenen Thunar-Dateien.
Die Python-Laufzeitabhängigkeit wird beim Paketbau ermittelt.

Reproduzierbarer Test mit echtem Thunar und isoliertem Profil/Display:

```sh
/usr/bin/python3 thunar/test_integration.py
```

Dieser Test verwendet ausschließlich eine temporäre Kopie der Thunarx-
Bibliothek zur Umleitung des Plugin-Suchpfads, ohne Systeminstallation.

## Veröffentlichung

Das öffentliche Repository liegt unter
[WillibaldSoft/nemo-dateivorschau-plus](https://github.com/WillibaldSoft/nemo-dateivorschau-plus).
Pakete und Prüfsummen gehören als Release-Anhänge außerhalb der Git-Historie.
Version 2.14.1 mit normalem `.deb`, Installationshelfer und vollständiger
Offline-Ausgabe: [GitHub-Release](https://github.com/WillibaldSoft/nemo-dateivorschau-plus/releases/tag/v2.14.1).

## Lizenz

GPL-3.0-or-later, siehe [LICENSE](LICENSE). Für die unverändert übernommene
GIMP-Runtime und enthaltene Bibliotheken gelten ihre jeweiligen Lizenzen.
Bezugsquellen und Prüfsummen: [GIMP3-RUNTIME.txt](GIMP3-RUNTIME.txt).

## Umstieg von Bilddetails

Das neue Paket ersetzt `bilddetails` über die Paketverwaltung. Die bisherigen
Einstellungen und Caches unter dem alten internen Namen bleiben verwendbar.
Der Befehl `bilddetails` bleibt als Kompatibilitätsalias erhalten. Nach dem
Update den verwendeten Dateimanager vollständig neu starten.
