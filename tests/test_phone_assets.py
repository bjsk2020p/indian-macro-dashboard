"""Phone install assets (manifest + icons) and the phone CSS block. No network, no browser."""
import json
import os
import re
import struct
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, "india_macro_dashboard_v5.html")


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    assert head[:8] == b"\x89PNG\r\n\x1a\n", f"{path} is not a PNG"
    return struct.unpack(">II", head[16:24])


class PhoneAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "manifest.webmanifest"), encoding="utf-8") as f:
            cls.manifest = json.load(f)
        with open(PAGE, encoding="utf-8") as f:
            cls.html = f.read()

    def test_manifest_fields(self):
        m = self.manifest
        for k in ("name", "short_name", "start_url", "display", "icons", "theme_color", "background_color"):
            self.assertIn(k, m)
        self.assertEqual(m["display"], "standalone")
        self.assertLessEqual(len(m["short_name"]), 12)   # fits under a home-screen icon

    def test_icons_exist_with_declared_sizes(self):
        sizes = set()
        for icon in self.manifest["icons"]:
            w, h = png_size(os.path.join(ROOT, icon["src"]))
            self.assertEqual(f"{w}x{h}", icon["sizes"])
            sizes.add(w)
        self.assertTrue({192, 512} <= sizes)
        self.assertEqual(png_size(os.path.join(ROOT, "icons", "icon-180.png")), (180, 180))

    def test_no_service_worker(self):
        self.assertNotIn("serviceWorker", self.html)

    def test_install_tags_only_for_hosted_pages(self):
        # manifest/icons are injected by script for public https hosts only; never as static tags
        self.assertNotRegex(self.html, r'<link[^>]+rel="manifest"')
        self.assertIn("rel: 'manifest', href: 'manifest.webmanifest'", self.html)

    def test_phone_block_present_and_scoped(self):
        m = re.search(r"/\* <phone-layout>.*?\*/\s*@media \(max-width: 480px\) \{(.*?)\n  \}\n  /\* </phone-layout> \*/",
                      self.html, re.S)
        self.assertIsNotNone(m, "phone-layout block missing")
        self.assertIn("min-height: 44px", m.group(1))


if __name__ == "__main__":
    unittest.main()
