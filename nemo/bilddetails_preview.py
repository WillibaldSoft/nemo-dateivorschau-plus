# SPDX-License-Identifier: GPL-3.0-or-later
"""Attach the right preview to each Nemo slot via a location-widget marker."""
import sys
import weakref
import gi
gi.require_version('Nemo', '3.0')
gi.require_version('Gtk', '3.0')
from gi.repository import GObject, Nemo, Gtk, GLib
sys.path.insert(0, '/usr/lib/bilddetails')
from nemo_sidebar import WindowState

class BilddetailsPreview(GObject.GObject, Nemo.LocationWidgetProvider):
    def __init__(self):
        super().__init__()
        self.windows = weakref.WeakKeyDictionary()

    def get_widget(self, uri, window):
        if window is None or uri.startswith('x-nemo-desktop:'):
            return None
        state = self.windows.get(window)
        if state is None:
            state = WindowState(window)
            self.windows[window] = state
            window.connect('destroy', lambda *_: self.windows.pop(window, None))
        marker = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        marker.connect('parent-set', lambda widget, old: GLib.idle_add(state.attach, widget, uri) if widget.get_parent() else None)
        marker.show()
        return marker
