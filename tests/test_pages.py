import json
from pathlib import Path
import re
import tempfile
import unittest

from scripts.build_pages import build


class PagesBuildTests(unittest.TestCase):
    def test_build_only_publishes_safe_static_files_and_relative_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)/'site'
            build(out)
            files = {str(p.relative_to(out)) for p in out.rglob('*') if p.is_file()}
            self.assertEqual(len(files), 7)
            self.assertTrue(all(p in {'index.html','.nojekyll'} or re.fullmatch(r'(static/[\w-]+\.(css|js)|data/bank-[a-f0-9]+\.json)',p) for p in files))
            html = (out/'index.html').read_text()
            self.assertNotIn('src="/', html)
            self.assertNotIn('href="/static', html)
            self.assertIn('记录仅存此浏览器',html)
            self.assertIn('Content-Security-Policy',html)
            for url in re.findall(r'(?:src|href)="(\./[^"]+)"',html):
                self.assertTrue((out/url).is_file(),url)
            bank = json.loads(next((out/'data').glob('*.json')).read_text())
            self.assertEqual(len(bank['questions']),239)
            self.assertEqual(len(bank['topics']),15)
            self.assertNotIn('progress',bank)
            with self.assertRaises(ValueError):
                build(out)


if __name__ == '__main__':
    unittest.main()
