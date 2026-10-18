# Änderungen

## 2.14.2

Offline-Ergänzung für bereits installiertes LibreOffice 26.2.5.2 aus
Noble-Backports. Automatische Auswahl des getrennten 26.2-Paketbestands;
Math und seine Oberfläche passen zu vorhandenem Office 26.2. Standard-
Office 24.2 und vorhandenes Still 25.8 bleiben unterstützt. Neue Paket- und
Offline-Ausgabe mit Versionsstand 2.14.2; Vorschaufunktionen unverändert.

## 2.14.1

Frischer Paketbau mit eindeutigem Versionsstand 2.14.1 und BUILD-INFO.txt
(UTC-Bauzeit und Quellcode-Commit) im Paket. Neuer normaler Installationshelfer
und neu gepackte vollständige Offline-Ausgabe für Mint 22.x AMD64 mit exakt
diesem Hauptpaket, lokaler APT-Auflösung und Wiederherstellung eines nur
entpackten Pakets. Die Vorschaufunktionen bleiben auf dem Stand von 2.14.0.

## 2.14.0

Zusätzliche rechte Vorschauleiste in Thunar mit gemeinsamem Decoder, Cache und
Metadateneditor. Breitenanpassung, Symbol zum Ein-/Ausblenden, Startverhalten,
separates Fenster, Zoom und Navigation wie in Nemo. Auswahl folgt Symbol-,
Listen- und Kompaktansicht, Tabs und Fokus in geteilten Ansichten.
Kleiner Thunarx-Loader mit sicherer Python-Symbolauflösung; native Auswahl über
GList statt ATK (ExoIconView bietet hier keine ATK-Auswahlschnittstelle).
Kein zusätzliches thunarx-python nötig. Vorhandene Dateimanager bleiben erhalten.

## 2.13.0

Veröffentlicht als Nemo Dateivorschau Plus, Nachfolger von Bilddetails.
Paketwechsel über Conflicts/Replaces; bisherige Einstellungen und CLI-Alias
bleiben erhalten.

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
