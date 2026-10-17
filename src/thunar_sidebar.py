# SPDX-License-Identifier: GPL-3.0-or-later
"""Thunar 4.18/4.20 GTK3 adapter; shared preview, no file-manager process patches.

The file notebook and its pages retain their parents. Only the surrounding
content grid is placed in a right-hand paned. Unknown layouts are left alone.
"""
from pathlib import Path
import weakref
import warnings
import ctypes
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Gio
from nemo_sidebar import Sidebar, WindowState, descendants
from preview_document import kind
from preview_widget import Preview, PreviewWindow, settings
from preferences import show_preferences

WINDOWS = weakref.WeakKeyDictionary()
TIMER = 0
_NATIVE = None


def selected_files(view):
    global _NATIVE
    if _NATIVE is None:
        _NATIVE = ctypes.CDLL('/usr/lib/x86_64-linux-gnu/thunarx-3/dateivorschau-plus.so')
        _NATIVE.dateivorschau_selected_uris.argtypes = [ctypes.c_void_p]
        _NATIVE.dateivorschau_selected_uris.restype = ctypes.c_void_p
        _NATIVE.dateivorschau_free.argtypes = [ctypes.c_void_p]
    capsule = ctypes.pythonapi.PyCapsule_GetPointer
    capsule.argtypes = [ctypes.py_object, ctypes.c_char_p]
    capsule.restype = ctypes.c_void_p
    pointer = capsule(view.__gpointer__, None)
    data = _NATIVE.dateivorschau_selected_uris(pointer)
    if not data: return []
    try:
        uris = ctypes.string_at(data).decode('utf-8').splitlines()
    finally:
        _NATIVE.dateivorschau_free(data)
    paths = [Gio.File.new_for_uri(uri).get_path() for uri in uris]
    return [Path(path) for path in paths if path]



def content_grid(window):
    for widget in descendants(window):
        if isinstance(widget, Gtk.Notebook):
            parent = widget.get_parent()
            # 4.18 and 4.20: notebook -> split-view paned -> content grid.
            if isinstance(parent, Gtk.Paned):
                grid = parent.get_parent()
                if isinstance(grid, Gtk.Grid) and isinstance(grid.get_parent(), Gtk.Paned):
                    return grid
    raise ValueError('Unbekannter Thunar-Fensteraufbau; Vorschau nicht eingefügt.')


class ThunarSidebar(Sidebar):
    def __init__(self, grid, state):
        self.slot, self.state = grid, state
        self.closed, self.restore = False, True
        self.width, self.save_timer = settings()['width'], 0
        self.preview = Preview(sidebar=True)
        self.preview.on_detach = self.detach
        self.paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.paned.set_wide_handle(True)
        self.paned.set_name('bilddetails-thunar-preview-split')
        parent = grid.get_parent()
        first = parent.get_child1() == grid
        resize = parent.child_get_property(grid, 'resize')
        shrink = parent.child_get_property(grid, 'shrink')
        pack = parent.pack1 if first else parent.pack2
        parent.remove(grid)
        try:
            self.paned.pack1(grid, True, False)
            self.paned.pack2(self.preview, False, False)
            pack(self.paned, resize, shrink)
        except Exception:
            if grid.get_parent(): grid.get_parent().remove(grid)
            pack(grid, resize, shrink)
            self.paned.destroy()
            raise
        self.paned.connect('size-allocate', self.allocated)
        self.paned.connect('notify::position', self.position_changed)
        self.preview.show_all()
        self.paned.show()
        self.preview.set_no_show_all(True)
        self.preview.set_visible(state.visible)
        self.timer = GLib.timeout_add(100, self.poll)
        grid.connect('destroy', self.cleanup)
        self.active = None

    def selected(self):
        views = [widget for widget in descendants(self.slot)
                 if widget.get_mapped() and widget.find_property('current-directory')
                 and widget.find_property('selected-files')
                 and widget.__gtype__.name in ('ThunarIconView', 'ThunarDetailsView', 'ThunarCompactView')]
        focus = self.state.window.get_focus()
        focused = next((view for view in views if focus and (focus == view or focus.is_ancestor(view))), None)
        if focused is not None: self.active = weakref.ref(focused)
        active = self.active() if self.active else None
        view = active if active in views else (views[0] if views else None)
        if view is None: return None, 0
        paths = selected_files(view)
        selected = [path for path in paths if path.is_file() and kind(path) is not None]
        return (selected[0] if selected else None), len(paths)

    def poll(self):
        if self.closed: return False
        if self.slot.get_mapped() and (self.state.visible or self.state.detached):
            path, count = self.selected()
            if self.state.visible: self.preview.set_selection(path, count)
            if self.state.detached: self.state.detached.preview.set_selection(path, count)
        return True

    def detach(self):
        if self.state.detached is None:
            self.state.detached = PreviewWindow()
            self.state.detached.connect('destroy', lambda *_: setattr(self.state, 'detached', None))
        self.state.detached.preview.set_selection(*self.selected())
        self.state.detached.present()


class ThunarWindowState(WindowState):
    def __init__(self, window):
        grid = content_grid(window)
        super().__init__(window)
        self.slots[grid] = ThunarSidebar(grid, self)
        self.install_buttons()

    def install_buttons(self):
        toolbar = next((widget for widget in descendants(self.window)
                        if isinstance(widget, Gtk.Toolbar)), None)
        if toolbar is None: return
        button = Gtk.ToggleToolButton()
        button.set_icon_name('view-preview-symbolic')
        button.set_label('Dateivorschau Plus')
        button.set_tooltip_text('Dateivorschau Plus rechts ein-/ausblenden')
        button.set_active(self.visible)
        button.connect('toggled', self.toggled)
        toolbar.insert(button, -1)
        button.show_all()
        self.buttons.append(button)
        preferences = Gtk.ToolButton()
        preferences.set_icon_name('preferences-system-symbolic')
        preferences.set_tooltip_text('Dateivorschau-Plus-Einstellungen')
        preferences.connect('clicked', lambda *_: show_preferences(self.window))
        toolbar.insert(preferences, -1)
        preferences.show_all()
        self.preference_buttons.append(preferences)


def discover():
    for window in Gtk.Window.list_toplevels():
        if window.__gtype__.name != 'ThunarWindow' or window in WINDOWS: continue
        if not window.get_mapped(): continue
        try:
            WINDOWS[window] = ThunarWindowState(window)
            window.connect('destroy', lambda widget: WINDOWS.pop(widget, None))
        except (ValueError, TypeError, RuntimeError) as exc:
            # Mark unsupported windows to avoid repeated work/warnings.
            WINDOWS[window] = None
            warnings.warn(str(exc), RuntimeWarning)
    return True


def start():
    global TIMER
    if not TIMER:
        TIMER = GLib.timeout_add(500, discover)
