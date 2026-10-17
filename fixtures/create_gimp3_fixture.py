# SPDX-License-Identifier: GPL-3.0-or-later
import os
from gi.repository import Gimp,Gio,Gegl
image=Gimp.Image.new(64,48,Gimp.ImageBaseType.RGB)
base=Gimp.Layer.new(image,'sichtbar',64,48,Gimp.ImageType.RGB_IMAGE,100,Gimp.LayerMode.NORMAL)
image.insert_layer(base,None,0)
Gimp.context_set_background(Gegl.Color.new('red'));base.fill(Gimp.FillType.BACKGROUND)
hidden=Gimp.Layer.new(image,'ausgeblendet',64,48,Gimp.ImageType.RGB_IMAGE,100,Gimp.LayerMode.NORMAL)
image.insert_layer(hidden,None,0)
Gimp.context_set_background(Gegl.Color.new('blue'));hidden.fill(Gimp.FillType.BACKGROUND);hidden.set_visible(False)
effect=Gimp.DrawableFilter.new(base,'gegl:invert-linear','Nichtdestruktiver Filter')
base.append_filter(effect)
assert Gimp.file_save(Gimp.RunMode.NONINTERACTIVE,image,Gio.File.new_for_path(os.environ['BILDDETAILS_TEST_XCF']),None)
image.delete()
