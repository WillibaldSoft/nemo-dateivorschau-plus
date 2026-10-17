# SPDX-License-Identifier: GPL-3.0-or-later
import os, traceback, ctypes
from pathlib import Path
from gi.repository import Gtk, GLib, Gdk
import thunar_sidebar as adapter
native=ctypes.CDLL(os.environ['PREVIEW_NATIVE_MODULE'])
native.dateivorschau_selected_uris.argtypes=[ctypes.c_void_p];native.dateivorschau_selected_uris.restype=ctypes.c_void_p
native.dateivorschau_free.argtypes=[ctypes.c_void_p]
adapter._NATIVE=native
cap=ctypes.pythonapi.PyCapsule_GetPointer;cap.argtypes=[ctypes.py_object,ctypes.c_char_p];cap.restype=ctypes.c_void_p
gtk=ctypes.CDLL('libgtk-3.so.0'); exo=ctypes.CDLL('libexo-2.so.0')
gtk.gtk_tree_path_new_from_string.argtypes=[ctypes.c_char_p];gtk.gtk_tree_path_new_from_string.restype=ctypes.c_void_p
gtk.gtk_tree_path_free.argtypes=[ctypes.c_void_p]
exo.exo_icon_view_select_path.argtypes=[ctypes.c_void_p,ctypes.c_void_p]
exo.exo_icon_view_unselect_all.argtypes=[ctypes.c_void_p]

def select(view,index):
 for x in adapter.descendants(view):
  if isinstance(x,Gtk.TreeView): x.get_selection().unselect_all();x.get_selection().select_path(Gtk.TreePath.new_from_indices([index]));x.grab_focus();return
  if x.__gtype__.name=='ExoIconView':
   ptr=cap(x.__gpointer__,None);path=gtk.gtk_tree_path_new_from_string(str(index).encode())
   exo.exo_icon_view_unselect_all(ptr);exo.exo_icon_view_select_path(ptr,path);gtk.gtk_tree_path_free(path);x.grab_focus();return
 raise AssertionError('Kein auswählbares Dateiwidget')
stage=0

def tick():
 global stage
 try:
  assert adapter.WINDOWS, 'Adapter fehlt'
  w,state=next(iter(adapter.WINDOWS.items())); assert state is not None
  side=next(iter(state.slots.values()))
  views=[x for x in adapter.descendants(side.slot) if x.__gtype__.name in ('ThunarIconView','ThunarDetailsView','ThunarCompactView') and x.get_mapped()]
  assert views;view=views[0]
  if stage==0:
   assert len(state.buttons)==1
   state.buttons[0].set_active(True);select(view,0)
   stage=1;return True
  if stage==1:
   print('SELECTED',side.selected(),side.preview.path,side.preview.pixbuf,flush=True)
   assert side.preview.path and side.preview.path.name=='a.png'
   assert side.preview.pixbuf is not None
   assert side.preview.detail_scroll.get_visible()
   state.buttons[0].set_active(False);assert not side.preview.get_visible()
   state.buttons[0].set_active(True);assert side.preview.get_visible()
   side.detach();assert state.detached is not None
   state.detached.destroy();select(view,1)
   stage=2;return True
  if stage==2:
   print('TEXT',side.preview.path,side.preview.kind,flush=True)
   assert side.preview.path.name=='b.txt' and side.preview.kind=='text'
   assert not side.preview.detail_scroll.get_visible()
   Gtk.accel_groups_activate(w,Gdk.KEY_2,Gdk.ModifierType.CONTROL_MASK)
   stage=3;return True
  if stage==3:
   assert view.__gtype__.name=='ThunarDetailsView',view.__gtype__.name
   select(view,0);stage=4;return True
  if stage==4:
   assert side.preview.path.name=='a.png' and side.preview.pixbuf is not None
   Gtk.accel_groups_activate(w,Gdk.KEY_3,Gdk.ModifierType.CONTROL_MASK)
   stage=5;return True
  if stage==5:
   assert view.__gtype__.name=='ThunarCompactView',view.__gtype__.name
   select(view,1);stage=6;return True
  if stage==6:
   assert side.preview.path.name=='b.txt'
   Gtk.accel_groups_activate(w,Gdk.KEY_t,Gdk.ModifierType.CONTROL_MASK)
   stage=7;return True
  if stage==7:
   books=[x for x in adapter.descendants(side.slot) if isinstance(x,Gtk.Notebook)]
   assert books[0].get_n_pages()==2
   select(view,0);stage=8;return True
  if stage==8:
   assert side.preview.path.name=='a.png'
   Gtk.accel_groups_activate(w,Gdk.KEY_F3,Gdk.ModifierType(0))
   stage=9;return True
  if stage==9:
   books=[x for x in adapter.descendants(side.slot) if isinstance(x,Gtk.Notebook)]
   assert len(books)==2
   right=books[1].get_nth_page(books[1].get_current_page())
   select(right,1);stage=10;return True
  if stage==10:
   assert side.preview.path.name=='b.txt'
   select(view,2);stage=11;return True
  if stage==11:
   assert side.preview.kind=='pdf' and side.preview.pages==2
   assert not side.preview.detail_scroll.get_visible()
   side.preview.change_page(2);stage=12;return True
  if stage==12:
   assert side.preview.page==2 and side.preview.pixbuf is not None
   side.preview.zoom_by(1.25)
   total=side.paned.get_allocated_width()
   side.paned.set_position(max(180,total-400))
   stage=13;return True
  if stage==13:
   assert side.width >= 180
   print('PASS real Thunar: image/text/PDF, zoom/pages, details, toggle, width, detach, 3 views, tabs, split focus',flush=True)
   Path(os.environ['PREVIEW_TEST_RESULT']).write_text('PASS\n');w.destroy();GLib.timeout_add(200,lambda: os._exit(0));return False
 except BaseException:
  traceback.print_exc();Path(os.environ['PREVIEW_TEST_RESULT']).write_text('FAIL\n');os._exit(1)
GLib.timeout_add(1500,tick)
GLib.timeout_add_seconds(35,lambda: os._exit(2))
