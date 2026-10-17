# SPDX-License-Identifier: GPL-3.0-or-later
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parent / 'src'))
import preview_widget
from preferences import Preferences, startup_visible
from nemo_sidebar import WindowState
from gi.repository import Gtk

class Tests(unittest.TestCase):
    def test_start_policy_persistence_and_toolbar_independence(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(preview_widget, 'CONFIG', Path(folder)/'preview.json'):
            self.assertEqual(preview_widget.settings()['startup'], 'last')
            for mode, last, expected in [('shown',False,True),('hidden',True,False),('last',False,False),('last',True,True)]:
                preview_widget.write_settings(startup=mode, visible=last, width=510)
                dialog = Preferences()
                self.assertEqual(dialog.startup.get_active_id(), mode)
                dialog.save(); dialog.destroy()
                window = Gtk.Window(); state = WindowState(window)
                self.assertEqual(state.visible, expected)
                button = Gtk.ToggleToolButton(); button.set_active(not expected)
                state.toggled(button)
                self.assertEqual(preview_widget.settings()['startup'], mode)
                self.assertEqual(preview_widget.settings()['width'], 510)
                self.assertEqual(startup_visible(), expected if mode != 'last' else not expected)
                window.destroy()
            preview_widget.CONFIG.write_text('{"startup":"invalid"}')
            self.assertEqual(preview_widget.settings()['startup'], 'last')
