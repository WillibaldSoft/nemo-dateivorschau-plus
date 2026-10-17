# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared GTK preview pane. No private Nemo widgets are changed."""
import concurrent.futures
import datetime
import stat as stat_module
import json
import os
from pathlib import Path
import subprocess
import signal
import tempfile
import weakref
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GdkPixbuf, GLib, Pango, Gio

from preview_document import kind as preview_kind, read_text, render_pdf
from preview_office import render_office
from preview_run import render_run_page
from run_stream import refresh as refresh_run, start_count, count_state
from formats import TEXT_KINDS
from speed_cache import CACHE as PREVIEW_CACHE
from preview_extra import archive_info, epub_text, media_preview, file_info

POOL = concurrent.futures.ThreadPoolExecutor(max_workers=2)
CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'bilddetails' / 'preview.json'


def settings():
    try:
        data = json.loads(CONFIG.read_text())
        return {'height': max(120, min(900, int(data.get('height', 260)))),
                'expanded': bool(data.get('expanded', True)),
                'width': max(180, min(1600, int(data.get('width', 380)))),
                'visible': bool(data.get('visible', True)),
                'slide_seconds': max(.5, min(60., float(data.get('slide_seconds', 3.)))),
                'startup': data.get('startup') if data.get('startup') in ('shown', 'hidden', 'last') else 'last'}
    except (OSError, ValueError, TypeError, AttributeError):
        return {'height': 260, 'expanded': True, 'width': 380, 'visible': True, 'startup': 'last', 'slide_seconds': 3.}


def write_settings(height=None, expanded=None, **changes):
    try:
        data = settings()
        if height is not None: data['height'] = height
        if expanded is not None: data['expanded'] = expanded
        data.update(changes)
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', dir=CONFIG.parent, delete=False) as f:
            json.dump(data, f)
        os.replace(f.name, CONFIG)
    except OSError:
        pass  # A read-only config directory must not break Nemo.


def worker(path):
    with tempfile.TemporaryDirectory(prefix='bilddetails-preview-') as folder:
        output = Path(folder) / 'preview.png'
        p = subprocess.Popen(['/usr/bin/python3', str(Path(__file__).with_name('preview_image.py')),
                              str(path), str(output)], stdout=subprocess.DEVNULL,
                             stderr=subprocess.PIPE, start_new_session=True)
        try:
            _, error = p.communicate(timeout=25)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            p.communicate()
            raise ValueError('Zeitlimit beim Laden der Vorschau (25 Sekunden).') from None
        if p.returncode:
            raise ValueError(error.decode('utf-8', 'replace').strip() or 'Keine Vorschau verfügbar.')
        return GdkPixbuf.Pixbuf.new_from_file(str(output))


class Preview(Gtk.Box):
    def __init__(self, standalone=False, sidebar=False):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4, margin=4)
        self.path = None
        self.signature = None
        self.pixbuf = None
        self.generation = 0
        self.future = None
        self.pending = None
        self.timer = 0
        self.closed = False
        self.playing = False
        self.play_timer = 0
        self.count_timer = 0
        self.detached = None
        self.kind = None
        self.page, self.pages = 1, 1
        self.text_points = 11
        self.zoom = 0  # Fit mode, then multiples of decoded preview size.
        self.options = settings()
        self.expander = Gtk.Expander(label='Dateivorschau' if sidebar else 'Nemo Dateivorschau Plus')
        self.pack_start(self.expander, True, True, 0)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.expander.add(body)
        bar = Gtk.Box(spacing=6)
        body.pack_start(bar, False, False, 0)
        self.name = Gtk.Label(label='Eine Datei in Nemo auswählen.', xalign=0, ellipsize=3)
        self.name.set_hexpand(True)
        body.reorder_child(bar, 0)
        body.pack_start(self.name, False, False, 0)
        body.reorder_child(self.name, 0)
        fit = Gtk.Button.new_from_icon_name('zoom-fit-best-symbolic', Gtk.IconSize.BUTTON) if sidebar else Gtk.Button(label='Einpassen')
        fit.set_tooltip_text('Vorschau einpassen / Textgröße zurücksetzen')
        fit.connect('clicked', lambda *_: self.set_zoom(0))
        bar.pack_start(fit, False, False, 0)
        for label, factor in [('−', .8), ('+', 1.25)]:
            button = Gtk.Button.new_from_icon_name('zoom-out-symbolic' if factor < 1 else 'zoom-in-symbolic', Gtk.IconSize.BUTTON) if sidebar else Gtk.Button(label=label)
            button.set_tooltip_text('Verkleinern' if factor < 1 else 'Vergrößern')
            button.connect('clicked', lambda _, f=factor: self.zoom_by(f))
            bar.pack_start(button, False, False, 0)
        if not standalone and not sidebar:
            bar.pack_start(Gtk.Label(label='Höhe:'), False, False, 0)
            self.height = Gtk.SpinButton.new_with_range(120, 900, 20)
            self.height.set_value(self.options['height'])
            self.height.connect('value-changed', self.resize)
            bar.pack_start(self.height, False, False, 0)
        if not standalone:
            detach = Gtk.Button.new_from_icon_name('window-new-symbolic', Gtk.IconSize.BUTTON) if sidebar else Gtk.Button(label='Eigenes Fenster')
            detach.set_tooltip_text('Vorschau in eigenem Fenster öffnen')
            detach.connect('clicked', self.detach)
            bar.pack_start(detach, False, False, 0)
        self.edit = Gtk.Button.new_from_icon_name('document-properties-symbolic', Gtk.IconSize.BUTTON) if sidebar else Gtk.Button(label='Details bearbeiten')
        self.edit.set_tooltip_text('Bilddetails anzeigen und bearbeiten')
        self.edit.set_sensitive(False)
        self.edit.connect('clicked', self.open_editor)
        bar.pack_start(self.edit, False, False, 0)
        self.open_button = Gtk.Button.new_from_icon_name('document-open-symbolic', Gtk.IconSize.BUTTON)
        self.open_button.set_tooltip_text('Datei in der zuständigen Anwendung öffnen')
        self.open_button.connect('clicked', self.open_external)
        bar.pack_start(self.open_button, False, False, 0)
        self.open_button.set_sensitive(False)
        self.pdf_bar = Gtk.Box(spacing=4)
        self.previous = Gtk.Button.new_from_icon_name('go-previous-symbolic', Gtk.IconSize.BUTTON)
        self.previous.set_tooltip_text('Vorherige Seite / vorheriges Bild')
        self.previous.connect('clicked', lambda *_: self.change_page(self.page - 1))
        self.next = Gtk.Button.new_from_icon_name('go-next-symbolic', Gtk.IconSize.BUTTON)
        self.next.set_tooltip_text('Nächste Seite / nächstes Bild')
        self.next.connect('clicked', lambda *_: self.change_page(self.page + 1))
        self.page_spin = Gtk.SpinButton.new_with_range(1, 1, 1)
        self.page_spin.set_tooltip_text('Seite / Bild auswählen')
        self.page_spin.connect('value-changed', lambda spin: self.change_page(spin.get_value_as_int()))
        self.page_label = Gtk.Label(label='/ 1')
        for control in (self.previous, self.page_spin, self.page_label, self.next):
            self.pdf_bar.pack_start(control, False, False, 0)
        body.pack_start(self.pdf_bar, False, False, 0)
        self.playback_bar = Gtk.Box(spacing=4)
        self.play_button = Gtk.Button(label='Start')
        self.play_button.set_tooltip_text('Fotoshow in der Vorschau starten / pausieren')
        self.play_button.set_sensitive(False)
        self.play_button.connect('clicked', self.toggle_playback)
        self.playback_bar.pack_start(self.play_button, False, False, 0)
        self.playback_bar.pack_start(Gtk.Label(label='Sekunden:'), False, False, 0)
        self.duration = Gtk.SpinButton.new_with_range(.5,60.,.5)
        self.duration.set_digits(1)
        self.duration.set_value(self.options['slide_seconds'])
        self.duration.set_tooltip_text('Anzeigedauer pro Bild (0,5–60 Sekunden)')
        self.duration.connect('value-changed',self.duration_changed)
        self.playback_bar.pack_start(self.duration, False, False, 0)
        body.pack_start(self.playback_bar,False,False,0)
        self.scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        self.scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.canvas = Gtk.DrawingArea()
        self.canvas.set_size_request(1, 1)
        self.canvas.get_style_context().add_class(Gtk.STYLE_CLASS_VIEW)
        self.canvas.connect('draw', self.draw)
        self.scroll.add(self.canvas)
        self.stack = Gtk.Stack(hexpand=True, vexpand=True)
        self.stack.add_named(self.scroll, 'image')
        self.text_view = Gtk.TextView(editable=False, cursor_visible=False, monospace=True,
                                      wrap_mode=Gtk.WrapMode.WORD_CHAR, left_margin=8, right_margin=8)
        self.text_scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        self.text_scroll.add(self.text_view)
        self.stack.add_named(self.text_scroll, 'text')
        buffer = self.text_view.get_buffer()
        for name, properties in {
            'heading': {'weight': Pango.Weight.BOLD, 'scale': 1.3},
            'bold': {'weight': Pango.Weight.BOLD}, 'italic': {'style': Pango.Style.ITALIC},
            'quote': {'style': Pango.Style.ITALIC, 'left_margin': 16},
            'code': {'family': 'monospace'}, 'link': {'underline': Pango.Underline.SINGLE},
            'keyword': {'weight': Pango.Weight.BOLD}, 'string': {'foreground': '#27934b'},
            'comment': {'style': Pango.Style.ITALIC, 'foreground': '#888888'},
            'number': {'foreground': '#a36ac7'}
        }.items(): buffer.create_tag(name, **properties)
        self.text_css = Gtk.CssProvider()
        self.text_view.get_style_context().add_provider(self.text_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.set_text_size(11)
        body.pack_start(self.stack, True, True, 0)
        if sidebar:
            self.scroll.set_min_content_height(140)
        if not standalone and not sidebar:
            self.scroll.set_size_request(-1, self.options['height'])
        self.scroll.connect('size-allocate', lambda *_: self.redraw())
        self.status = Gtk.Label(label='Vorschau folgt der Auswahl; bei Mehrfachauswahl wird die erste unterstützte Datei gezeigt.', xalign=0, wrap=True)
        if sidebar:
            self.status.set_max_width_chars(28)
            self.status.set_line_wrap_mode(2)
            self.set_size_request(180, -1)
        body.pack_start(self.status, False, False, 0)
        self.file_details = Gtk.Expander(label='Dateidetails')
        self.file_details_label = Gtk.Label(xalign=0, selectable=True, wrap=True)
        self.file_details_label.set_max_width_chars(32)
        self.file_details.add(self.file_details_label)
        body.pack_start(self.file_details, False, False, 0)
        self.detail_scroll = None
        self.quick_details = None
        if sidebar:
            from quick_details import QuickDetails
            self.quick_details = QuickDetails()
            detail_scroll = Gtk.ScrolledWindow()
            self.detail_scroll = detail_scroll
            detail_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            detail_scroll.set_min_content_height(180)
            detail_scroll.set_max_content_height(260)
            detail_scroll.set_propagate_natural_height(True)
            detail_scroll.add(self.quick_details)
            body.pack_start(detail_scroll, False, True, 0)
        self.expander.set_expanded(True if standalone or sidebar else self.options['expanded'])
        self.expander.connect('notify::expanded', self.expand)
        self.connect('destroy', self.cleanup)
        self.connect('unmap', lambda *_: self.pause_playback())
        self.show_all()
        self.pdf_bar.set_no_show_all(True)
        self.pdf_bar.hide()
        self.playback_bar.set_no_show_all(True)
        self.playback_bar.hide()
        if self.detail_scroll:
            self.detail_scroll.set_no_show_all(True)
            self.detail_scroll.hide()
        self.edit.set_no_show_all(True)
        self.edit.hide()

    def set_selection(self, path, count=1):
        if self.closed:
            return
        try:
            path = Path(path) if path else None
            stat = path.stat() if path else None
            signature = (str(path), stat.st_mtime_ns, stat.st_size, stat.st_ctime_ns, stat.st_ino) if stat else None
        except OSError:
            path, signature = None, None
        if self.detached is not None:
            self.detached.preview.set_selection(path, count)
        if signature == self.signature:
            return
        self.pause_playback()
        self.stop_count_watch()
        self.play_button.set_sensitive(False)
        self.path, self.signature = path, signature
        self.file_details.set_sensitive(path is not None)
        self.file_details_label.set_text(
            f'Name: {path.name}\nTyp: {path.suffix.lower() or "ohne Erweiterung"}\n'
            f'Größe: {stat.st_size:,} Bytes\n'
            f'Geändert: {datetime.datetime.fromtimestamp(stat.st_mtime):%d.%m.%Y %H:%M:%S}\n'
            f'Rechte: {stat_module.filemode(stat.st_mode)}\nPfad: {path.absolute()}' if path else '')
        self.kind = preview_kind(path) if path else None
        self.open_button.set_sensitive(path is not None)
        self.page, self.pages = 1, 1
        self.pdf_bar.set_visible(self.kind in ('pdf', 'office', 'run'))
        self.playback_bar.set_visible(self.kind == 'run')
        self.previous.set_sensitive(False); self.next.set_sensitive(False)
        self.page_spin.set_sensitive(False)
        self.page_label.set_text('/ …' if self.kind in ('pdf', 'office', 'run') else '/ 1')
        self.edit.set_visible(self.kind == 'image')
        self.edit.set_sensitive(self.kind == 'image')
        if self.detail_scroll: self.detail_scroll.set_visible(self.kind == 'image')
        if self.quick_details is not None:
            self.quick_details.set_path(path if self.kind == 'image' else None)
        self.stack.set_visible_child_name('text' if self.kind in TEXT_KINDS else 'image')
        self.text_view.get_buffer().set_text('')
        self.generation += 1
        self.pixbuf = None
        self.pending = None
        self.zoom = 0
        self.name.set_text(path.name + (f' ({count} ausgewählt)' if count > 1 else '') if path else 'Eine Datei in Nemo auswählen.')
        self.name.set_tooltip_text(str(path) if path else '')
        self.redraw()
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0
        if not path:
            self.status.set_text('Keine lokale Datei ausgewählt.')
            return
        if not self.expander.get_expanded():
            return
        self.status.set_text('Office-Vorschau wird vorbereitet …' if self.kind == 'office' else 'Vorschau wird geladen …')
        self.timer = GLib.timeout_add(90, self.schedule)

    def schedule(self):
        self.timer = 0
        self.pending = (self.generation, self.path, self.kind, self.page)
        self.start_pending()
        return False

    def start_pending(self):
        if self.closed or self.future is not None or self.pending is None:
            return
        generation, path, kind, page = self.pending
        self.pending = None
        def load():
            if kind == 'pdf': return render_pdf(path, page)
            if kind == 'office': return render_office(path, page)
            if kind == 'text': return read_text(path)
            if kind == 'archive': return archive_info(path)
            if kind == 'epub': return epub_text(path)
            if kind in ('audio', 'video'): return media_preview(path, kind == 'video')
            if kind == 'info': return file_info(path)
            if kind == 'run': return render_run_page(path, page)
            if kind == 'xcf': return {'kind': 'image', 'pixbuf': worker(path), 'note': 'XCF · zusammengesetzte Vorschau · Öffnen für Ebenenbearbeitung'}
            if kind == 'image': return {'kind': 'image', 'pixbuf': worker(path)}
            raise ValueError('Dateiformat wird nicht unterstützt.')
        self.future = POOL.submit(lambda: PREVIEW_CACHE.get(path, kind, page, load))
        ref = weakref.ref(self)
        def complete(future):
            def deliver():
                pane = ref()
                if pane is None or pane.closed:
                    return False
                pane.future = None
                if generation == pane.generation:
                    try:
                        result = future.result()
                        if result.get('stream_id'):
                            result=refresh_run(result)
                            pane.watch_count(result['stream_id'])
                        if result['kind'] == 'text':
                            pane.stack.set_visible_child_name('text')
                            buffer = pane.text_view.get_buffer()
                            buffer.set_text(result['text'])
                            for tag, start, end in result.get('spans', []):
                                buffer.apply_tag_by_name(tag, buffer.get_iter_at_offset(start), buffer.get_iter_at_offset(end))
                            pane.status.set_text(result['note'] + ' · Zoom +/− für Schriftgröße')
                        else:
                            pane.stack.set_visible_child_name('image')
                            pane.pixbuf = result['pixbuf']
                            if result['kind'] in ('pdf', 'run'):
                                pane.page, pane.pages = result['page'], result['pages']
                                pane.page_spin.set_range(1, pane.pages)
                                pane.page_spin.set_value(pane.page)
                                pane.page_spin.set_sensitive(True)
                                pane.previous.set_sensitive(pane.page > 1)
                                pane.next.set_sensitive(pane.page < pane.pages)
                                pane.page_label.set_text('/ ' + (str(pane.pages) if result.get('pages_known',True) else '?'))
                                if pane.kind == 'run' and pane.pages <= 1: pane.pause_playback()
                                pane.play_button.set_sensitive(pane.kind == 'run' and pane.pages > 1)
                                pane.arm_playback()
                                pane.status.set_text((result.get('office_label', 'Office-Druckvorschau') if result.get('office') else result.get('label', 'PDF')) + ' · ' + result.get('unit', 'Seite') + (f' {pane.page} von {pane.pages}' if result.get('pages_known',True) else f' {pane.page} · weitere Bilder bei Bedarf'))
                            else:
                                pane.status.set_text(result.get('note') or f'{pane.pixbuf.get_width()} × {pane.pixbuf.get_height()} Vorschaupixel · Zoom +/− oder Einpassen')
                    except Exception as exc:
                        pane.pause_playback()
                        pane.status.set_text('Vorschau: ' + str(exc))
                        if pane.kind in ('pdf', 'office', 'run'):
                            pane.pixbuf = None
                            pane.previous.set_sensitive(pane.page > 1)
                            pane.next.set_sensitive(pane.page < pane.pages)
                            pane.page_spin.set_sensitive(pane.pages > 1)
                    pane.redraw()
                pane.start_pending()
                return False
            GLib.idle_add(deliver)
        self.future.add_done_callback(complete)

    def fit_scale(self):
        if not self.pixbuf:
            return 1
        return min(max(1, self.scroll.get_allocated_width() - 24) / self.pixbuf.get_width(),
                   max(1, self.scroll.get_allocated_height() - 24) / self.pixbuf.get_height())

    def change_page(self, page):
        page = max(1, min(self.pages, page))
        if self.kind not in ('pdf', 'office', 'run') or page == self.page: return
        self.cancel_play_timer()
        self.page = page
        self.generation += 1
        self.previous.set_sensitive(False); self.next.set_sensitive(False)
        self.page_spin.set_sensitive(False)
        self.status.set_text(('Bild' if self.kind == 'run' else 'Seite') + f' {page} wird geladen …')
        if self.timer: GLib.source_remove(self.timer)
        self.timer = GLib.timeout_add(100, self.schedule)
        self.scroll.get_vadjustment().set_value(0)
        self.scroll.get_hadjustment().set_value(0)

    def stop_count_watch(self):
        if self.count_timer:
            GLib.source_remove(self.count_timer);self.count_timer=0

    def watch_count(self,key):
        self.stop_count_watch()
        generation=self.generation
        def begin():
            self.count_timer=0
            if self.closed or self.kind!='run' or generation!=self.generation:return False
            start_count(key)
            self.count_timer=GLib.timeout_add(250,poll)
            return False
        def poll():
            if self.closed or self.kind!='run' or generation!=self.generation:
                self.count_timer=0;return False
            state=count_state(key)
            if state and state['pages_known']:
                self.pages=state['pages']
                self.page_spin.set_range(1,self.pages)
                self.page_label.set_text('/ '+str(self.pages))
                self.next.set_sensitive(self.page<self.pages)
                self.play_button.set_sensitive(self.pages>1)
                if self.pages<=1:self.pause_playback()
                self.status.set_text(f'Fotoshow Studio · Bild {self.page} von {self.pages}')
                self.count_timer=0;return False
            return True
        self.count_timer=GLib.timeout_add(500,begin)

    def cancel_play_timer(self):
        if self.play_timer:
            GLib.source_remove(self.play_timer)
            self.play_timer = 0

    def pause_playback(self):
        self.playing = False
        self.cancel_play_timer()
        self.play_button.set_label('Start')

    def toggle_playback(self, *_):
        if self.playing:
            self.pause_playback()
        elif self.kind == 'run' and self.pages > 1 and self.pixbuf is not None:
            self.playing = True
            self.play_button.set_label('Pause')
            self.arm_playback()

    def duration_changed(self, *_):
        write_settings(slide_seconds=self.duration.get_value())
        if self.future is None and not self.timer: self.arm_playback()

    def arm_playback(self):
        self.cancel_play_timer()
        if (self.playing and self.kind == 'run' and self.pages > 1 and not self.closed
                and self.future is None and not self.timer):
            self.play_timer = GLib.timeout_add(round(self.duration.get_value()*1000),self.advance_playback)

    def advance_playback(self):
        self.play_timer = 0
        if not self.closed and self.playing and self.kind == 'run':
            self.change_page(self.page % self.pages + 1)
        return False

    def set_text_size(self, points):
        self.text_points = max(7, min(36, points))
        self.text_css.load_from_data(('textview { font-family: monospace; font-size: ' + str(self.text_points) + 'pt; }').encode())

    def zoom_by(self, factor):
        if self.stack.get_visible_child_name() == 'text': self.set_text_size(round(self.text_points * factor))
        else: self.set_zoom(max(.1, min(4, (self.zoom or self.fit_scale()) * factor)))

    def set_zoom(self, value):
        if self.stack.get_visible_child_name() == 'text':
            self.set_text_size(11)
            return
        self.zoom = value
        self.redraw()

    def redraw(self):
        if self.closed:
            return
        scale = self.zoom or self.fit_scale()
        width = int(self.pixbuf.get_width() * scale) if self.pixbuf else 1
        height = int(self.pixbuf.get_height() * scale) if self.pixbuf else 1
        requested = (max(1, width), max(1, height)) if self.zoom else (1, 1)
        if self.canvas.get_size_request() != requested:
            self.canvas.set_size_request(*requested)
        self.canvas.queue_draw()

    def draw(self, canvas, cr):
        from gi.repository import Gdk
        context = canvas.get_style_context()
        found, color = context.lookup_color('theme_base_color')
        if not found:
            color = context.get_background_color(Gtk.StateFlags.NORMAL)
        if color.alpha > 0:
            cr.set_source_rgba(color.red, color.green, color.blue, color.alpha)
            cr.paint()
        Gtk.render_background(context, cr, 0, 0, canvas.get_allocated_width(), canvas.get_allocated_height())
        if self.pixbuf:
            scale = self.zoom or self.fit_scale()
            w, h = self.pixbuf.get_width() * scale, self.pixbuf.get_height() * scale
            cr.translate(max(0, (canvas.get_allocated_width() - w) / 2), max(0, (canvas.get_allocated_height() - h) / 2))
            cr.scale(scale, scale)
            Gdk.cairo_set_source_pixbuf(cr, self.pixbuf, 0, 0)
            cr.paint()
        return False

    def resize(self, *_):
        self.options['height'] = self.height.get_value_as_int()
        self.scroll.set_size_request(-1, self.options['height'])
        write_settings(self.options['height'], self.expander.get_expanded())

    def expand(self, *_):
        expanded = self.expander.get_expanded()
        write_settings(self.options['height'], expanded)
        if expanded and self.path and self.pixbuf is None and not self.timer:
            self.timer = GLib.timeout_add(90, self.schedule)

    def detach(self, *_):
        if hasattr(self, 'on_detach'):
            self.on_detach()
            return
        if self.detached is None:
            self.detached = PreviewWindow()
            self.detached.connect('destroy', self.detached_closed)
            self.detached.preview.set_selection(self.path)
        self.detached.present()

    def detached_closed(self, *_):
        self.detached = None

    def open_external(self, *_):
        if self.path:
            try: Gio.AppInfo.launch_default_for_uri(self.path.absolute().as_uri(), None)
            except GLib.Error as exc: self.status.set_text('Öffnen: ' + exc.message)

    def open_editor(self, *_):
        if self.path:
            subprocess.Popen(['/usr/bin/nemo-dateivorschau-plus', str(self.path)], start_new_session=True)

    def cleanup(self, *_):
        self.stop_count_watch()
        self.pause_playback()
        self.closed = True
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0
        if self.detached:
            self.detached.destroy()


class PreviewWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title='Nemo Dateivorschau Plus')
        self.set_default_size(1000, 760)
        self.preview = Preview(standalone=True)
        self.add(self.preview)
        self.show_all()
