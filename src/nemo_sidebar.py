# SPDX-License-Identifier: GPL-3.0-or-later
"""Version-checked GTK sidebar adapter for Nemo 6.x.

Wrap the existing view overlay, never its contents: Nemo keeps ownership of
its file view and can replace that view on list/icon/compact transitions.
"""
from pathlib import Path
import weakref
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
from preview_widget import Preview, PreviewWindow, settings, write_settings
from nemo_selection import selection
from preferences import startup_visible, show_preferences


def ancestor(widget, name):
    while widget is not None:
        if widget.__gtype__.name == name:
            return widget
        widget = widget.get_parent()
    return None


def descendants(widget):
    yield widget
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            yield from descendants(child)


class Sidebar:
    def __init__(self, slot, state):
        overlays = [child for child in slot.get_children() if isinstance(child, Gtk.Overlay)]
        if len(overlays) != 1:
            raise ValueError('Nemo-Fensteraufbau wird nicht unterstützt; rechte Vorschau nicht eingefügt.')
        self.slot, self.state = slot, state
        self.directory = None
        self.closed = False
        self.restore = True
        self.width = settings()['width']
        self.save_timer = 0
        self.preview = Preview(sidebar=True)
        self.preview.on_detach = self.detach
        self.paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.paned.set_wide_handle(True)
        self.paned.set_name('bilddetails-preview-split')
        overlay = overlays[0]
        index = slot.get_children().index(overlay)
        packing = slot.query_child_packing(overlay)
        # Python keeps the overlay alive while the GTK parent reference changes.
        slot.remove(overlay)
        try:
            self.paned.pack1(overlay, True, False)
            self.paned.pack2(self.preview, False, False)
            slot.pack_start(self.paned, *packing[:3])
            slot.reorder_child(self.paned, index)
        except Exception:
            if overlay.get_parent(): overlay.get_parent().remove(overlay)
            slot.pack_start(overlay, *packing[:3])
            slot.reorder_child(overlay, index)
            self.paned.destroy()
            raise
        self.paned.connect('size-allocate', self.allocated)
        self.paned.connect('notify::position', self.position_changed)
        self.paned.show_all()
        self.preview.set_no_show_all(True)
        self.preview.set_visible(state.visible)
        self.timer = GLib.timeout_add(100, self.poll)
        slot.connect('destroy', self.cleanup)

    def allocated(self, *_):
        total = self.paned.get_allocated_width()
        if self.restore and total > 360 and self.state.visible:
            self.restore = False
            self.paned.set_position(max(160, total - min(self.width, total - 160)))

    def position_changed(self, *_):
        if not self.restore and self.state.visible and self.preview.get_visible():
            self.width = max(180, self.paned.get_allocated_width() - self.paned.get_position())
            if self.save_timer: GLib.source_remove(self.save_timer)
            self.save_timer = GLib.timeout_add(350, self.persist)

    def persist(self):
        self.save_timer = 0
        write_settings(width=self.width)
        return False

    def set_visible(self, visible):
        if not visible:
            self.preview.hide()
        else:
            self.restore = True
            self.preview.expander.set_expanded(True)
            self.preview.show()
            self.paned.queue_resize()

    def poll(self):
        if self.closed: return False
        if self.slot.get_mapped():
            path, count = selection(self.state.window, self.directory, self.preview) if self.directory else (None, 0)
            # Collapsing hides the widget and avoids decoding while detached
            # previews still receive selection changes.
            if self.state.visible:
                self.preview.set_selection(path, count)
            focus = self.state.window.get_focus()
            active = focus is None or focus == self.slot or focus.is_ancestor(self.slot)
            if active:
                self.state.current = weakref.ref(self)
                if self.state.detached:
                    self.state.detached.preview.set_selection(path, count)
        return True

    def detach(self):
        if self.state.detached is None:
            self.state.detached = PreviewWindow()
            self.state.detached.connect('destroy', lambda *_: setattr(self.state, 'detached', None))
        self.state.current = weakref.ref(self)
        path, count = selection(self.state.window, self.directory, self.preview) if self.directory else (None, 0)
        self.state.detached.preview.set_selection(path, count)
        self.state.detached.present()

    def cleanup(self, *_):
        if self.closed: return
        self.closed = True
        GLib.source_remove(self.timer)
        self.preview.pixbuf = None
        self.state.slots.pop(self.slot, None)
        if self.save_timer:
            GLib.source_remove(self.save_timer)
            self.persist()


class WindowState:
    def __init__(self, window):
        self.window = window
        self.visible = startup_visible()
        self.slots = weakref.WeakKeyDictionary()
        self.buttons = []
        self.preference_buttons = []
        self.current = None
        self.detached = None
        self.syncing = False
        window.connect('destroy', self.cleanup)
        window.connect('delete-event', self.before_close)

    def attach(self, marker, uri):
        if marker.get_parent() is None: return False
        slot = ancestor(marker, 'NemoWindowSlot')
        if slot is None: return False
        try:
            controller = self.slots.get(slot)
            if controller is None:
                controller = Sidebar(slot, self)
                self.slots[slot] = controller
            from gi.repository import Gio
            path = Gio.File.new_for_uri(uri).get_path()
            controller.directory = Path(path) if path else None
            controller.preview.set_selection(None)
            marker.controller = controller
            self.install_buttons()
        except (ValueError, TypeError, RuntimeError) as exc:
            if not marker.get_children():
                label = Gtk.Label(label=str(exc), wrap=True)
                marker.pack_start(label, False, False, 0)
                label.show()
        return False

    def install_buttons(self):
        for toolbar in descendants(self.window):
            if not isinstance(toolbar, Gtk.Toolbar): continue
            if ancestor(toolbar, 'NemoToolbar') is None: continue
            if any(button.get_parent() == toolbar for button in self.buttons): continue
            button = Gtk.ToggleToolButton()
            button.set_label('Dateivorschau')
            button.set_tooltip_text('Dateivorschau rechts ein-/ausblenden')
            button.set_icon_name('bilddetails-preview-symbolic')
            button.get_accessible().set_name('Dateivorschau rechts ein-/ausblenden')
            button.set_active(self.visible)
            button.connect('toggled', self.toggled)
            toolbar.insert(button, -1)
            button.show_all()
            self.buttons.append(button)
            preferences = Gtk.ToolButton()
            preferences.set_icon_name('preferences-system-symbolic')
            preferences.set_label('Vorschau-Einstellungen')
            preferences.set_tooltip_text('Dateivorschau-Einstellungen: Verhalten beim Start')
            preferences.connect('clicked', lambda *_: show_preferences(self.window))
            toolbar.insert(preferences, -1)
            preferences.show_all()
            self.preference_buttons.append(preferences)

    def toggled(self, button):
        if self.syncing: return
        self.visible = button.get_active()
        self.syncing = True
        for other in self.buttons:
            other.set_active(self.visible)
        for controller in self.slots.values():
            if not controller.closed: controller.set_visible(self.visible)
        self.syncing = False
        write_settings(visible=self.visible)

    def before_close(self, *_):
        editors = [controller.preview.quick_details for controller in self.slots.values()
                   if controller.preview.quick_details is not None]
        if any(editor.saving for editor in editors):
            dialog = Gtk.MessageDialog(transient_for=self.window, modal=True,
                buttons=Gtk.ButtonsType.OK, message_type=Gtk.MessageType.INFO,
                text='Metadaten werden gespeichert. Bitte danach das Fenster schließen.')
            dialog.run(); dialog.destroy()
            return True
        if any(editor.drafts for editor in editors):
            dialog = Gtk.MessageDialog(transient_for=self.window, modal=True,
                buttons=Gtk.ButtonsType.NONE, message_type=Gtk.MessageType.QUESTION,
                text='Ungespeicherte Bilddetails verwerfen und Fenster schließen?')
            dialog.add_buttons('Abbrechen', Gtk.ResponseType.CANCEL, 'Verwerfen und schließen', Gtk.ResponseType.OK)
            result = dialog.run(); dialog.destroy()
            return result != Gtk.ResponseType.OK
        return False

    def cleanup(self, *_):
        if self.detached: self.detached.destroy()
        for controller in list(self.slots.values()): controller.cleanup()
        self.buttons.clear()
        self.preference_buttons.clear()
        self.current = None
