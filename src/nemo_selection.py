# SPDX-License-Identifier: GPL-3.0-or-later
"""Read local GTK accessibility selection, without desktop-wide AT-SPI.

Nemo versions may defer MenuProvider callbacks until opening a menu.
Atk.Selection on the file view provides a fallback for mouse/keyboard changes.
"""
from pathlib import Path
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Atk
from preview_image import RAW
from preview_document import kind

IMAGE = RAW | {'.jpg', '.jpeg', '.jpe', '.png', '.tif', '.tiff', '.webp', '.gif',
               '.bmp', '.heic', '.heif', '.avif', '.jxl', '.svg'}

def selected_names(window):
    result = []
    queue = [window]
    seen = set()
    while queue:
        widget = queue.pop()
        if not widget.get_mapped():
            continue
        accessible = widget.get_accessible()
        if isinstance(accessible, Atk.Selection):
            count = min(Atk.Selection.get_selection_count(accessible), 256)
            for index in range(count):
                selected = Atk.Selection.ref_selection(accessible, index)
                if selected:
                    # Tree view selections can be rows/cells. Examine only the
                    # selected objects, not thousands of unselected file icons.
                    objects = [selected]
                    for _ in range(2):
                        children = []
                        for obj in objects:
                            name = obj.get_name()
                            if name and name not in seen:
                                seen.add(name); result.append(name)
                            children.extend(obj.ref_accessible_child(i) for i in range(min(obj.get_n_accessible_children(), 32)))
                        objects = [obj for obj in children if obj is not None]
        if isinstance(widget, Gtk.Container):
            queue.extend(widget.get_children())
    return result

def selection(window, directory, pane=None):
    # Limit accessibility reads to this tab/pane when Nemo exposes its slot
    # container, so equal filenames in split views do not cross between panes.
    scope = window
    ancestor = pane
    while ancestor is not None:
        if ancestor.__gtype__.name == 'NemoWindowSlot':
            scope = ancestor
            break
        ancestor = ancestor.get_parent()
    names = selected_names(scope)
    paths = []
    for name in names:
        # Never turn accessible text into an arbitrary path or parent traversal.
        if Path(name).name != name or name in ('.', '..'):
            continue
        path = directory / name
        if path.is_file() and kind(path) is not None:
            paths.append(path)
    return (paths[0] if paths else None), len(paths)
