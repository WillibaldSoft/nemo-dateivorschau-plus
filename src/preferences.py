# SPDX-License-Identifier: GPL-3.0-or-later
"""Preview preferences shared by the Nemo toolbar and command line."""
from gi.repository import Gtk
from preview_widget import settings, write_settings


def startup_visible(options=None):
    options = settings() if options is None else options
    mode = options.get('startup', 'last')
    return True if mode == 'shown' else False if mode == 'hidden' else options['visible']


class Preferences(Gtk.Dialog):
    def __init__(self, parent=None):
        super().__init__(title='Dateivorschau – Einstellungen', transient_for=parent, modal=True)
        self.add_buttons('Abbrechen', Gtk.ResponseType.CANCEL, 'Speichern', Gtk.ResponseType.OK)
        box = self.get_content_area()
        box.set_border_width(16); box.set_spacing(10)
        box.pack_start(Gtk.Label(label='Vorschau beim Öffnen eines Nemo-Fensters:', xalign=0), False, False, 0)
        self.startup = Gtk.ComboBoxText()
        for key, label in [('shown', 'Immer eingeblendet'), ('hidden', 'Immer ausgeblendet'),
                           ('last', 'Letzten Zustand wiederherstellen')]:
            self.startup.append(key, label)
        self.startup.set_active_id(settings()['startup'])
        box.pack_start(self.startup, False, False, 0)
        box.pack_start(Gtk.Label(label='Gilt für neue Fenster und nach einem Nemo-Neustart.\nDas Vorschau-Symbol schaltet das aktuelle Fenster um.', xalign=0), False, False, 0)
        self.show_all()

    def save(self):
        write_settings(startup=self.startup.get_active_id())


def show_preferences(parent=None):
    dialog = Preferences(parent)
    if dialog.run() == Gtk.ResponseType.OK:
        dialog.save()
    dialog.destroy()
