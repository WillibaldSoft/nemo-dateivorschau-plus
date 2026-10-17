# Änderungen

## 2.13.0

Die Gesamtzahl großer Fotoshow-Archive wird 0,5 Sekunden nach dem ersten
angezeigten Bild unabhängig und mit niedriger Prozesspriorität gezählt.
Die Anzeige aktualisiert sich auch bei Pause. Der Zähler dekodiert keine
Bilder und erzeugt keinen vollständigen Tar-Puffer. Nach fünf Minuten wird
eine nicht abgeschlossene Zählung beendet; die Bildvorschau bleibt nutzbar.

Quellcode für Git-Veröffentlichung bereinigt, GPL-3.0-or-later ergänzt und
portable Makeself-Testfixtures bereitgestellt.

## 2.12.0

Bedarfsgesteuerter Leser für große Fotoshows ohne frühere 512-MiB-Gesamtgrenze.

## 2.11.0

Start/Pause, Anzeigedauer und Inline-Stichwörter. Flexible Bildnamen im Archiv.
