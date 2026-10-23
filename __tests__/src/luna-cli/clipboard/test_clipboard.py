import base64
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("clipboard", Path(__file__).resolve().parents[4] / "src/luna-cli/clipboard/clipboard.py")
clipboard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(clipboard)


class ClipboardTests(unittest.TestCase):
    def test_changed_focus_never_receives_paste(self):
        with patch.object(clipboard, "decode", return_value=b"hello"), patch.object(clipboard, "run") as run, patch.object(clipboard.time, "sleep"), patch.object(clipboard, "active_window", return_value={"address": "0x2"}):
            with self.assertRaisesRegex(ValueError, "focus changed"):
                clipboard.paste("1", "0x1")
            self.assertFalse(any(call.args[0] == "wtype" for call in run.call_args_list))

    def test_paste_shortcut_matches_target(self):
        for app, shift in [("kitty", True), ("zen", False)]:
            with self.subTest(app=app), patch.object(clipboard, "decode", return_value=b"\nhello\n"), patch.object(clipboard, "run") as run, patch.object(clipboard.time, "sleep"), patch.object(clipboard, "active_window", return_value={"address": "0x1", "class": app}):
                clipboard.paste("1", "0x1")
                self.assertEqual(run.call_args_list[0].kwargs["data"], b"\nhello\n")
                keys = run.call_args.args
                self.assertEqual(keys[0], "wtype")
                self.assertEqual("shift" in keys, shift)

    def test_invalid_target_or_id_rejected(self):
        with self.assertRaises(ValueError):
            clipboard.paste("1", "")
        with self.assertRaises(ValueError):
            clipboard.decode("1;echo bad")

    @unittest.skipUnless(shutil.which("cliphist"), "cliphist required")
    def test_real_history_preserves_text_images_and_promotes(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"CLIPHIST_DB_PATH": directory + "/history.db", "XDG_RUNTIME_DIR": directory}):
            self.assertEqual(clipboard.listing(), [])
            text = "  नेपाली 😀\nsecond line\t\n".encode()
            image = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=")
            clipboard.run("cliphist", "store", data=text)
            first = clipboard.listing()[0]["id"]
            clipboard.run("cliphist", "store", data=image)
            image_entry = clipboard.listing()[0]
            second = image_entry["id"]
            self.assertEqual(image_entry["name"], "Image")
            self.assertTrue(image_entry["image"].startswith("file://"))
            self.assertEqual(clipboard.decode(first), text)
            self.assertEqual(clipboard.decode(second), image)
            self.assertEqual(clipboard.preview(first)["text"], text.decode())
            self.assertTrue(clipboard.preview(second)["mime"].startswith("image/"))
            self.assertEqual(clipboard.preview(second)["image"], image_entry["image"])
            clipboard.run("cliphist", "store", data=text)
            self.assertEqual(clipboard.decode(clipboard.listing()[0]["id"]), text)
            self.assertEqual(len(clipboard.listing()), 2)
