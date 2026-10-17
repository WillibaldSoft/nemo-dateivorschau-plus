# SPDX-License-Identifier: GPL-3.0-or-later
"""Executed by GIMP 3's Python batch interpreter, never by Nemo directly."""
import os
from gi.repository import Gimp, Gio

image = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(os.environ['BILDDETAILS_SOURCE']))
if image is None:
    raise ValueError('XCF nicht lesbar.')
try:
    width, height = image.get_width(), image.get_height()
    factor = min(1.0, 1920 / max(width, height))
    if factor < 1:
        image.scale(max(1, round(width * factor)), max(1, round(height * factor)))
    image.merge_visible_layers(Gimp.MergeType.CLIP_TO_IMAGE)
    image.convert_precision(Gimp.Precision.U8_NON_LINEAR)
    procedure = Gimp.get_pdb().lookup_procedure('file-png-export')
    config = procedure.create_config()
    config.set_property('run-mode', Gimp.RunMode.NONINTERACTIVE)
    config.set_property('image', image)
    config.set_property('file', Gio.File.new_for_path(os.environ['BILDDETAILS_DESTINATION']))
    config.set_property('compression', 1)
    status = procedure.run(config).index(0)
    if status != Gimp.PDBStatusType.SUCCESS:
        raise ValueError('PNG-Export fehlgeschlagen: ' + str(status))
finally:
    image.delete()
