# SPDX-License-Identifier: GPL-3.0-or-later
"""Inline metadata editor: immutable save targets and per-file drafts."""
import concurrent.futures
from pathlib import Path
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
from editor import FIELDS, DIRECT, load, save, validate

POOL = concurrent.futures.ThreadPoolExecutor(max_workers=2)
INLINE = [(0, 'Hersteller'), (1, 'Kamera'), (2, 'Objektiv'), (3, 'Aufnahme'), (4, 'Urheber'), (8, 'Stichwörter')]


def stamp(path):
    try:
        stat = path.stat()
        return stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns
    except FileNotFoundError:
        return None


class QuickDetails(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.path = None
        self.original = None
        self.drafts = {}
        self.loading = False
        self.saving = False
        self.closed = False
        self.token = 0
        self.future = None
        self.pending = None
        self.entries = {}
        heading = Gtk.Label(label='Bilddetails direkt bearbeiten', xalign=0)
        self.pack_start(heading, False, False, 0)
        self.form = Gtk.Grid(column_spacing=6, row_spacing=4)
        extra = Gtk.Grid(column_spacing=6, row_spacing=4)
        for index, label in INLINE:
            grid = self.form if index in (1, 2, 3, 8) else extra
            row = (1, 2, 3, 8).index(index) if index in (1, 2, 3, 8) else (0, 4).index(index)
            grid.attach(Gtk.Label(label=label, xalign=0), 0, row, 1, 1)
            entry = Gtk.Entry(hexpand=True, width_chars=12)
            entry.set_placeholder_text('z. B. Urlaub; Familie' if index == 8 else 'Nicht vorhanden')
            entry.set_tooltip_text(FIELDS[index][0] + (' · JJJJ:MM:TT HH:MM:SS' if index == 3 else ''))
            entry.connect('changed', self.changed)
            self.entries[index] = entry
            grid.attach(entry, 1, row, 1, 1)
        self.pack_start(self.form, False, False, 0)
        self.more = Gtk.Expander(label='Hersteller und Urheber')
        self.more.add(extra)
        self.pack_start(self.more, False, False, 0)
        self.note = Gtk.Label(xalign=0, wrap=True, max_width_chars=28, selectable=True)
        self.note.set_line_wrap_mode(2)
        self.pack_start(self.note, False, False, 0)
        buttons = Gtk.Box(spacing=6)
        self.save_button = Gtk.Button(label='Speichern')
        self.save_button.connect('clicked', self.store)
        self.reset_button = Gtk.Button(label='Verwerfen')
        self.reset_button.connect('clicked', self.reset)
        buttons.pack_start(self.save_button, True, True, 0)
        buttons.pack_start(self.reset_button, True, True, 0)
        self.pack_start(buttons, False, False, 0)
        self.connect('destroy', self.cleanup)
        self.set_sensitive(False)

    def values(self):
        values = self.original[:] if self.original else [''] * len(FIELDS)
        for index, entry in self.entries.items():
            values[index] = entry.get_text()
        return values

    def changed(self, *_):
        if self.loading: return
        dirty = bool(self.original is not None and self.values() != self.original)
        if self.path is not None and self.original is not None:
            changes = {index: entry.get_text() for index, entry in self.entries.items()
                       if entry.get_text() != self.original[index]}
            if changes: self.drafts[self.path] = changes
            else: self.drafts.pop(self.path, None)
        self.save_button.set_sensitive(dirty and not self.saving)
        self.reset_button.set_sensitive(dirty and not self.saving)
        if dirty: self.note.set_text('Ungespeicherte Änderungen · Speichern oder Verwerfen. Beim Bildwechsel bleibt der Entwurf erhalten.')

    def set_path(self, path, force=False):
        path = Path(path) if path else None
        if self.closed or (path == self.path and not force): return
        self.path = path
        self.token += 1
        self.original = None
        self.loading = True
        for entry in self.entries.values(): entry.set_text('')
        self.loading = False
        self.set_sensitive(False)
        self.pending = (self.token, path) if path else None
        self.note.set_text('Metadaten werden gelesen …' if path else 'Ein Bild auswählen.')
        self.start_pending()

    def start_pending(self):
        if self.closed or self.future is not None or self.pending is None: return
        token, path = self.pending
        self.pending = None
        def read():
            info = load(path)
            return info, stamp(path), stamp(info[1])
        self.future = POOL.submit(read)
        def complete(future):
            def deliver():
                if self.closed: return False
                self.future = None
                if token == self.token:
                    try:
                        (self.filetype, self.companion, values), self.image_stamp, self.side_stamp = future.result()
                        self.original = values
                        self.loading = True
                        for index, entry in self.entries.items():
                            entry.set_text(self.drafts.get(path, {}).get(index, values[index]))
                        self.loading = False
                        self.set_sensitive(True)
                        self.form.set_sensitive(not self.saving); self.more.set_sensitive(not self.saving)
                        self.note.set_text('Speichern: ' + ('im Bild · mit Originalsicherung' if self.filetype in DIRECT else 'in XMP-Begleitdatei · Bild bleibt unverändert'))
                        self.changed()
                    except Exception as exc:
                        self.loading = False
                        self.note.set_text('Metadaten: ' + str(exc))
                self.start_pending()
                return False
            GLib.idle_add(deliver)
        self.future.add_done_callback(complete)

    def store(self, *_):
        if self.original is None or self.saving or self.path is None: return
        path, companion, filetype = self.path, self.companion, self.filetype
        before, after = self.original[:], self.values()
        try:
            for index, _ in INLINE:
                if before[index] != after[index]: validate(after[index], FIELDS[index][3])
            if stamp(path) != self.image_stamp or (filetype not in DIRECT and stamp(companion) != self.side_stamp):
                raise ValueError('Die Datei wurde zwischenzeitlich geändert. Zu einem anderen Bild und zurück wechseln; der Entwurf bleibt erhalten.')
        except (ValueError, OSError) as exc:
            self.note.set_text(str(exc)); return
        self.saving = True
        self.form.set_sensitive(False); self.more.set_sensitive(False)
        self.save_button.set_sensitive(False)
        self.reset_button.set_sensitive(False)
        self.note.set_text('Metadaten werden gespeichert …')
        changes = self.drafts.get(path, {}).copy()
        future = POOL.submit(save, path, filetype, companion, before, after, filetype not in DIRECT)
        def complete(future):
            def deliver():
                self.saving = False
                try:
                    message = future.result()
                    if self.drafts.get(path) == changes: self.drafts.pop(path, None)
                    if not self.closed and self.path == path:
                        self.set_path(path, force=True)
                        self.note.set_text(message)
                except Exception as exc:
                    if not self.closed:
                        self.form.set_sensitive(True); self.more.set_sensitive(True)
                        self.changed()
                        self.note.set_text('Speicherfehler für ' + path.name + ': ' + str(exc))
                if not self.closed:
                    self.form.set_sensitive(not self.saving); self.more.set_sensitive(not self.saving)
                    self.changed()
                return False
            GLib.idle_add(deliver)
        future.add_done_callback(complete)

    def reset(self, *_):
        if self.saving or self.path is None: return
        self.drafts.pop(self.path, None)
        self.set_path(self.path, force=True)

    def cleanup(self, *_):
        self.closed = True
        self.pending = None
