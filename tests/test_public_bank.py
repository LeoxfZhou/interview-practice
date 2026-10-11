import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from app import database as db
from app.constants import APP_ID
from scripts.validate_bank import load_rows, validate


class PublicBankTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'test.db'
        self.rows = load_rows()
        db.initialize_database(self.path)

    def test_fresh_start_and_saved_selection(self):
        bootstrap = db.get_bootstrap(self.path)
        self.assertEqual(bootstrap['stats']['total'], 239)
        self.assertEqual(bootstrap['stats']['correct'], 0)
        self.assertEqual(bootstrap['stats']['wrong'], 0)
        self.assertEqual(len(bootstrap['topics']), 15)
        db.save_selection(['python'], 'foundation', self.path)
        db.initialize_database(self.path)
        self.assertEqual(db.get_bootstrap(self.path)['selected_topics'], ['python'])
        self.assertEqual(db.get_bootstrap(self.path)['content_scope'], 'foundation')

    def test_scope_matrix_and_no_progress_from_library(self):
        with sqlite3.connect(self.path) as con:
            before = con.execute('SELECT * FROM question_stats ORDER BY question_id').fetchall()
        for topics in ([], ['python'], ['python','rag'], ['project']):
            for scope in ('foundation','combined'):
                expected = {r['id'] for r in self.rows if (not topics or set(topics).intersection(r['topics'])) and (scope=='combined' or r['content_type']=='foundation')}
                result = db.list_library_sections(topics, scope, self.path)
                rows = [r for section in result['sections'] for group in section['groups'] for r in group['items']]
                self.assertEqual(result['total'], len(expected))
                self.assertEqual({r['stable_id'] for r in rows}, expected)
                self.assertEqual(len(rows), len(expected))
        with sqlite3.connect(self.path) as con:
            self.assertEqual(con.execute('SELECT * FROM question_stats ORDER BY question_id').fetchall(), before)

    def test_release_integrity_and_privacy(self):
        ids = validate(self.rows)
        release = json.loads((db.DATA_DIR/'public_release.json').read_text())
        self.assertEqual(len(ids), release['total'])
        self.assertEqual(sum(r['content_type']=='interview' for r in self.rows), release['interview'])
        self.assertEqual(sum(r['content_type']=='foundation' for r in self.rows), release['foundation'])
        self.assertTrue(set(release['legacy_public_ids']) <= ids)
        self.assertEqual(len(release['legacy_public_ids']), 42)
        self.assertEqual(APP_ID, 'interview-practice-public')

    def test_upgrade_preserves_every_legacy_stat_and_selection(self):
        ids = json.loads((db.DATA_DIR/'public_release.json').read_text())['legacy_public_ids']
        legacy = [dict(r, answer='旧版答案') for r in self.rows if r['id'] in ids]
        seed = Path(self.temp.name)/'legacy.json'
        seed.write_text(json.dumps(legacy))
        path = Path(self.temp.name)/'upgrade.db'
        db.initialize_database(path, seed_path=seed, foundation_path=None)
        db.save_selection(['python','rag'], 'foundation', path)
        with sqlite3.connect(path) as con:
            for i, qid in enumerate(ids):
                con.execute('UPDATE question_stats SET seen_count=?, last_seen_at=?, result=? WHERE question_id=?', (i+1,'2026-01-01T00:00:00Z', 'correct' if i%2 else 'wrong', qid))
            before = dict((r[0], r[1:]) for r in con.execute('SELECT * FROM question_stats'))
            settings = con.execute('SELECT * FROM app_settings ORDER BY key').fetchall()
        db.initialize_database(path)
        db.initialize_database(path)
        with sqlite3.connect(path) as con:
            after = dict((r[0], r[1:]) for r in con.execute('SELECT * FROM question_stats'))
            self.assertEqual({key:after[key] for key in before}, before)
            self.assertEqual(con.execute('SELECT * FROM app_settings ORDER BY key').fetchall(), settings)
            self.assertEqual(con.execute('SELECT count(*) FROM questions').fetchone()[0], 239)
        self.assertEqual(db.get_bootstrap(path)['selected_topics'], ['python','rag'])


if __name__ == '__main__':
    unittest.main()
