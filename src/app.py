#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bilddetails — GTK metadata viewer and editor for Nemo."""
import concurrent.futures
import sys
from pathlib import Path
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
from details import report
from editor import FIELDS, DIRECT, argument_path, load, save

class Window(Gtk.Window):
    def __init__(self, paths):
        super().__init__(title='Nemo Dateivorschau Plus – Bilddetails')
        self.set_default_size(1050, 800)
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.paths, self.path, self.original = [], None, []
        self.loading = self.busy = False
        self.connect('delete-event', self.close)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=12)
        self.add(outer)
        bar = Gtk.Box(spacing=8)
        outer.pack_start(bar, False, False, 0)
        open_button = Gtk.Button(label='Bilder öffnen …')
        open_button.connect('clicked', self.open_files)
        bar.pack_start(open_button, False, False, 0)
        self.selector = Gtk.ComboBoxText()
        self.selector.set_hexpand(True)
        self.selector.connect('changed', self.select)
        bar.pack_start(self.selector, True, True, 0)
        self.reload_button = Gtk.Button(label='Neu laden')
        self.reload_button.connect('clicked', self.reload)
        bar.pack_start(self.reload_button, False, False, 0)
        self.book = Gtk.Notebook()
        outer.pack_start(self.book, True, True, 0)
        self.text = Gtk.TextView(editable=False, cursor_visible=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        scroll = Gtk.ScrolledWindow()
        scroll.add(self.text)
        self.book.append_page(scroll, Gtk.Label(label='Alle Details / GPS / XMP'))
        edit = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=12)
        self.book.append_page(edit, Gtk.Label(label='Metadaten bearbeiten'))
        self.target = Gtk.CheckButton(label='In XMP-Begleitdatei speichern (Bild unverändert)')
        self.target.connect('toggled', self.target_changed)
        edit.pack_start(self.target, False, False, 0)
        self.target_label = Gtk.Label(xalign=0, selectable=True, wrap=True)
        edit.pack_start(self.target_label, False, False, 0)
        note = Gtk.Label(label='Nur geänderte Felder werden gespeichert. Ein geleertes Feld löscht den entsprechenden Eintrag.\n'
                              'Sicherung beim ersten Ändern: DATEINAME_original. Weitere Änderungen behalten diese erste Sicherung.',
                         xalign=0, wrap=True)
        edit.pack_start(note, False, False, 0)
        form_scroll = Gtk.ScrolledWindow()
        form_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        edit.pack_start(form_scroll, True, True, 0)
        grid = Gtk.Grid(column_spacing=16, row_spacing=10)
        form_scroll.add(grid)
        self.entries = []
        for row, (label, _, _, _) in enumerate(FIELDS):
            grid.attach(Gtk.Label(label=label, xalign=0), 0, row, 1, 1)
            entry = Gtk.Entry(hexpand=True)
            entry.connect('changed', self.changed)
            grid.attach(entry, 1, row, 1, 1)
            self.entries.append(entry)
        buttons = Gtk.Box(spacing=8)
        edit.pack_start(buttons, False, False, 0)
        self.save_button = Gtk.Button(label='Änderungen speichern …')
        self.save_button.connect('clicked', self.store)
        buttons.pack_end(self.save_button, False, False, 0)
        self.status = Gtk.Label(label='Bilder öffnen oder in Nemo auswählen.', xalign=0, wrap=True, selectable=True)
        outer.pack_end(self.status, False, False, 0)
        self.show_all()
        self.set_paths(paths)
        self.changed()

    def message(self, text, question=False):
        dialog = Gtk.MessageDialog(transient_for=self, modal=True,
            message_type=Gtk.MessageType.QUESTION if question else Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK_CANCEL if question else Gtk.ButtonsType.OK,
            text=text)
        result = dialog.run()
        dialog.destroy()
        return result == Gtk.ResponseType.OK

    def dirty(self):
        return bool(self.original) and self.original != [e.get_text() for e in self.entries]

    def discard(self):
        return not self.dirty() or self.message('Ungespeicherte Änderungen verwerfen?', True)

    def close(self, *_):
        if self.busy:
            self.message('Bitte warten, bis der laufende Vorgang abgeschlossen ist.')
            return True
        if not self.discard():
            return True
        self.pool.shutdown(wait=False)
        Gtk.main_quit()
        return False

    def changed(self, *_):
        self.save_button.set_sensitive(not self.busy and self.path is not None and self.dirty())

    def job(self, function, done):
        self.busy = True
        self.selector.set_sensitive(False)
        self.book.set_sensitive(False)
        self.reload_button.set_sensitive(False)
        self.changed()
        future = self.pool.submit(function)
        def finish():
            self.busy = False
            self.selector.set_sensitive(True)
            self.book.set_sensitive(True)
            self.reload_button.set_sensitive(True)
            try:
                done(future.result())
            except Exception as exc:
                self.status.set_text('Fehler: ' + str(exc))
                self.message(str(exc))
            self.changed()
            return False
        future.add_done_callback(lambda _: GLib.idle_add(finish))

    def set_paths(self, paths):
        self.loading = True
        self.selector.remove_all()
        self.paths = list(dict.fromkeys(paths))
        for index, path in enumerate(self.paths):
            self.selector.append_text(f'{index + 1}. {path}')
        self.loading = False
        if paths:
            self.selector.set_active(0)

    def open_files(self, *_):
        if self.busy or not self.discard():
            return
        dialog = Gtk.FileChooserDialog(title='Bilder auswählen', transient_for=self,
            action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons('Abbrechen', Gtk.ResponseType.CANCEL, 'Öffnen', Gtk.ResponseType.OK)
        dialog.set_select_multiple(True)
        if dialog.run() == Gtk.ResponseType.OK:
            paths = [Path(p) for p in dialog.get_filenames()]
            self.original = []
            self.set_paths(paths)
        dialog.destroy()

    def select(self, *_):
        if self.loading or self.selector.get_active() < 0:
            return
        selected = self.paths[self.selector.get_active()]
        if not self.discard():
            self.loading = True
            self.selector.set_active(self.paths.index(self.path))
            self.loading = False
            return
        self.path = selected
        self.original = []
        self.fetch()

    def reload(self, *_):
        if self.path and not self.busy and self.discard():
            self.fetch()

    def fetch(self, use_sidecar=None):
        path = self.path
        self.status.set_text('Metadaten werden gelesen …')
        def work():
            info = load(path, use_sidecar)
            return info, report(path)
        def done(result):
            (self.filetype, self.companion, values), text = result
            self.original = values
            for entry, value in zip(self.entries, values):
                entry.set_text(value)
            self.loading = True
            self.target.set_active(self.filetype not in DIRECT if use_sidecar is None else use_sidecar)
            self.target.set_sensitive(self.filetype in DIRECT)
            self.target_changed()
            self.loading = False
            self.text.get_buffer().set_text(text)
            self.status.set_text('Bereit. Bearbeitung gilt jeweils für das ausgewählte Bild.')
        self.job(work, done)

    def target_changed(self, *_):
        if not self.loading and hasattr(self, 'companion'):
            if not self.discard():
                self.loading = True
                self.target.set_active(not self.target.get_active())
                self.loading = False
                return
            self.fetch(self.target.get_active())
            return
        if hasattr(self, 'companion'):
            target = self.companion if self.target.get_active() else self.path
            self.target_label.set_text('Speicherziel: ' + str(target))

    def store(self, *_):
        new = [entry.get_text() for entry in self.entries]
        changed = [field[0] for field, a, b in zip(FIELDS, self.original, new) if a != b]
        target = self.companion if self.target.get_active() else self.path
        if not self.message('Änderungen speichern?\n\n' + str(target) + '\n\n' + '\n'.join(changed), True):
            return
        path, filetype, companion = self.path, self.filetype, self.companion
        old, use_sidecar = self.original[:], self.target.get_active()
        self.status.set_text('Änderungen werden gespeichert …')
        def done(message):
            self.original = new
            self.status.set_text(message)
            self.message(message)
            self.fetch(use_sidecar)
        self.job(lambda: save(path, filetype, companion, old, new, use_sidecar), done)


def main():
    if '--version' in sys.argv:
        print('Nemo Dateivorschau Plus 2.14.0')
        return
    if '--formats' in sys.argv:
        candidates = [Path(__file__).resolve().parent.parent / 'FORMATE.txt', Path('/usr/share/doc/nemo-dateivorschau-plus/FORMATE.txt')]
        print(next((path.read_text() for path in candidates if path.is_file()), 'Formatübersicht nicht gefunden.'))
        return
    if '--help' in sys.argv or '-h' in sys.argv:
        print('Aufruf: nemo-dateivorschau-plus [DATEI oder file://URI …]\nOhne Argumente öffnet sich die Bildauswahl. --formats zeigt die Formatübersicht. --settings öffnet die Vorschau-Einstellungen. Version: 2.14.0')
        return
    if not Gtk.init_check()[0]:
        print('Nemo Dateivorschau Plus benötigt eine grafische Desktop-Sitzung (GTK 3).', file=sys.stderr)
        sys.exit(1)
    if '--settings' in sys.argv:
        from preferences import show_preferences
        show_preferences()
        return
    paths = []
    errors = []
    for value in sys.argv[1:]:
        if value == '--':
            continue
        try:
            paths.append(argument_path(value))
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
    window = Window(paths)
    if errors:
        window.message('\n'.join(errors))
    Gtk.main()

if __name__ == '__main__':
    main()
