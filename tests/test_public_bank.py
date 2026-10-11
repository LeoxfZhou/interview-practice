import ast
import json
from pathlib import Path
import tempfile
import unittest

from app import database as db
from app.constants import APP_ID
from scripts.build_sample_bank import build


class PublicBankTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'test.db'
        db.initialize_database(self.path)

    def test_fresh_start_and_saved_selection(self):
        bootstrap = db.get_bootstrap(self.path)
        self.assertEqual(bootstrap['stats']['total'], 42)
        self.assertEqual(bootstrap['stats']['correct'], 0)
        self.assertEqual(bootstrap['stats']['wrong'], 0)
        self.assertEqual(len(bootstrap['topics']), 14)
        db.save_selection(['python'], 'foundation', self.path)
        db.initialize_database(self.path)
        self.assertEqual(db.get_bootstrap(self.path)['selected_topics'], ['python'])
        self.assertEqual(db.get_bootstrap(self.path)['content_scope'], 'foundation')

    def test_scope_matrix_and_no_progress_from_library(self):
        before = db.get_progress_stats(self.path)
        for topics, scope, expected in [([], 'foundation', 14), ([], 'combined', 42), (['python'], 'foundation', 1), (['python'], 'combined', 3), (['python','rag'], 'combined', 6)]:
            with self.subTest(topics=topics, scope=scope):
                result = db.list_library_sections(topics, scope, self.path)
                self.assertEqual(result['total'], expected)
                rows = [r for section in result['sections'] for group in section['groups'] for r in group['items']]
                self.assertEqual(len({r['stable_id'] for r in rows}), expected)
                self.assertTrue(all(r['answer'] for r in rows))
        self.assertEqual(db.get_progress_stats(self.path), before)

    def test_generated_data_matches_reviewed_source(self):
        questions, foundations = build()
        self.assertEqual(json.loads(db.SEED_PATH.read_text()), questions)
        self.assertEqual(json.loads((db.FOUNDATION_PATH/'basics.json').read_text()), foundations)
        rows = questions + foundations
        self.assertEqual(len({r['id'] for r in rows}), 42)
        self.assertEqual(len({db._normalize_prompt(r['prompt']) for r in rows}), 42)
        for r in rows:
            self.assertEqual(r['topics'], [r['primary_topic']])
            self.assertTrue(r['id'].startswith('public-'))
            self.assertTrue(r['source_ref'].startswith('scripts/'))
            self.assertNotIn('/Users/', json.dumps(r))
            self.assertNotIn('file://', json.dumps(r))
        self.assertEqual(APP_ID, 'interview-practice-public')

    def test_python_example(self):
        def squares(count):
            for number in range(count):
                yield number * number
        values = squares(3)
        self.assertEqual(next(values), 0)
        self.assertEqual(list(values), [1,4])
        self.assertEqual(list(values), [])
        import re
        for r in build()[1]:
            for code in re.findall(r'```python\n(.*?)```', r['answer'], re.S):
                ast.parse(code)


if __name__ == '__main__':
    unittest.main()
