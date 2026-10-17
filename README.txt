NEMO DATEIVORSCHAU PLUS 2.13.0 – Nemo-Dateivorschau und Bildmetadateneditor

INSTALLATION (AMD64 / Linux Mint Cinnamon, Ubuntu/Debian mit Nemo)
    sudo apt install ./nemo-dateivorschau-plus_2.13.0_amd64.deb
Alternativ Installationshelfer neben dem Paket speichern und ausführen:
    sh Nemo-Dateivorschau-Plus-2.13-installieren.sh
Nur Abhängigkeiten prüfen: gleicher Aufruf mit --check.
Nach Abschluss offener Dateioperationen Nemo mit nemo -q beenden und erneut
öffnen. Ältere Bilddetails-Versionen werden aktualisiert.

BEDIENUNG
Vorschau rechts neben der Dateiliste. Breite am Trenner ziehen; Vorschau am
Symbol ein-/ausblenden. Zahnrad: beim Start eingeblendet, ausgeblendet oder
letzten Zustand wiederherstellen. Zoom, Öffnen und separates Vorschaufenster.
Bei Bildern Kamera, Objektiv, Aufnahmedatum und Stichwörter direkt bearbeiten.
Mehrere Stichwörter mit Semikolon trennen. Speichern erzeugt eine Original-
sicherung; RAW-Änderungen werden in einer XMP-Begleitdatei gespeichert.

FORMATFAMILIEN
Bilder/RAW, XCF, PDF, Text/Markdown/Quelltext, Office samt Präsentationen,
EPUB-Text, Archivlisten, Audioinformationen und Video-Standbilder einschließlich
MPEG-TS. Vollständige Übersicht mit Grenzen: FORMATE.txt.
Ein isolierter GIMP-3.2.6-Decoder ist im Paket enthalten. Der installierte
GIMP-Editor und seine Einstellungen werden nicht ersetzt. Keine FUSE-Pflicht
und keine Runtime-Entpackung beim Laden eines Bildes.

FOTOSHOW STUDIO .run
Die enthaltenen Bilder werden gelesen, die Show und ihre Skripte nicht gestartet.
Zurück/Vor, Nummernfeld, Start/Pause, Wiederholung, Dauer von 0,5–60 Sekunden.
Die Anzeigedauer zählt ab dem fertig geladenen Bild; Ladezeit kann hinzukommen.
Dateiwechsel, Ausblenden, Fehler oder Schließen pausieren die Wiedergabe.
Keine Wiedergabe von Originalmusik, Effekten oder Überblendungen der Show.
Übliche Bildformate und ursprüngliche Namen/Unterordner werden unterstützt.

Große Shows werden schrittweise aus gzip gelesen statt vollständig entpackt.
Die Gesamtzahl erscheint zunächst als ?. Neu ab 2.13: 0,5 Sekunden nach dem
angezeigten ersten Bild startet ein unabhängiger Zähler mit niedriger CPU-
und, falls ionice vorhanden ist, niedriger I/O-Priorität. Er zählt Archiv-
Bildeinträge ohne Bilddekodierung und ohne Tar-Puffer. Die Anzeige aktualisiert
sich auch bei pausierter Vorschau automatisch. Kleine Shows sind schon direkt
vollständig indexiert. Ein zweiter vollständiger Archiv-Lesedurchlauf ist für
die exakte Zahl erforderlich; er läuft unabhängig vom Vorschau-Start.
Der Zähler bricht spätestens nach fünf Minuten ab. Bei beschädigten oder zu
langsamen Archiven kann die Zahl unbekannt bleiben; die Vorschau läuft weiter.
Kleine Shows: natürliche Namensreihenfolge. Streaming: Archiv-Reihenfolge.
Nach bekannter Zahl sind direkte Sprünge möglich; gzip muss für unbesuchte
oder aus dem Cache verdrängte Bilder eventuell erneut weit gelesen werden.

CACHE UND GRENZEN
Gemeinsamer RAM-Cache: 24 Vorschauen / ca. 96 MiB Inhaltsbudget, kein Gesamt-
RAM-Limit. Auswahlverzögerung 90 ms; Hintergrundladen verhindert UI-Blockaden.
Streaming: maximal zwei Shows, jeweils 64 PNG-Vorschauen / 128 MiB; bis 1920
Pixel Bildkante. Pro Bild 64 MiB Quelldaten und 20 Sekunden Ladezeit. Kein
512-MiB-Limit für das gesamte Streaming-Archiv. Kleine Vollindizes sind auf
512 MiB Tar-Daten begrenzt; große Archive wechseln zum Streaming-Modus.
Zähl-/Decoderprozesse werden beim Entfernen der Show aus dem Cache beendet.
Ein Dateiwechsel invalidiert den Cache anhand von Inode/Größe/Zeitstempeln.
XCF: eigener Plattencache 24 PNGs / 128 MiB; Bilder bis 1920 Pixel, PDF-Seiten
bis 1600 Pixel. Volle Originalauflösung in der zuständigen Anwendung öffnen.

CLI
    nemo-dateivorschau-plus --settings
    nemo-dateivorschau-plus --formats
    nemo-dateivorschau-plus --version

LIZENZ
Projektquellcode: GPL-3.0-or-later, siehe LICENSE. Mitgelieferte GIMP-Runtime
und Bibliotheken unter ihren jeweiligen Lizenzen; siehe GIMP3-RUNTIME.txt.

UMBENENNUNG
Nemo Dateivorschau Plus ist der Nachfolger von Bilddetails. Das Paket ersetzt
bilddetails automatisch. Einstellungen/Cache unter dem alten internen Namen
bleiben erhalten. Der Befehl bilddetails ist ein Kompatibilitätsalias.
