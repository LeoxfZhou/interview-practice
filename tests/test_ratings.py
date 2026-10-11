import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.database import (initialize_database, get_progress_stats, get_quiz_progress,
                          record_result, select_next_question, reset_progress,
                          get_bootstrap, save_selection, list_library_sections)


class RatingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'ratings.db'
        initialize_database(self.db)

    def test_regrade_skip_and_reset_persist(self):
        question = select_next_question([], database_path=self.db)
        qid = question['stable_id']
        self.assertEqual(get_progress_stats(self.db)['correct'], 0)
        record_result(qid, 'wrong', self.db)
        record_result(qid, 'correct', self.db)
        record_result(qid, 'correct', self.db)
        self.assertEqual(get_progress_stats(self.db)['correct'], 1)
        initialize_database(self.db)
        self.assertEqual(get_progress_stats(self.db)['correct'], 1)
        record_result(qid, 'unrated', self.db)
        self.assertEqual(get_progress_stats(self.db)['correct'], 0)
        with sqlite3.connect(self.db) as con:
            self.assertEqual(con.execute('SELECT result FROM question_stats WHERE question_id=?', (qid,)).fetchone()[0], 'unrated')
        save_selection(['rag'], 'foundation', self.db)
        record_result(qid, 'correct', self.db)
        reset_progress(self.db)
        self.assertEqual(get_progress_stats(self.db)['correct'], 0)
        self.assertEqual(get_bootstrap(self.db)['selected_topics'], ['rag'])

    def test_last_wrong_question_repeats_and_all_correct_completes(self):
        qid = select_next_question([], database_path=self.db)['stable_id']
        with sqlite3.connect(self.db) as con:
            con.execute("UPDATE question_stats SET result='correct'")
        self.assertIsNone(select_next_question([], database_path=self.db))
        self.assertEqual(get_quiz_progress([], database_path=self.db)['remaining'], 0)
        record_result(qid, 'wrong', self.db)
        self.assertEqual(select_next_question([], qid, database_path=self.db)['stable_id'], qid)
        record_result(qid, 'unrated', self.db)
        self.assertEqual(select_next_question([], qid, database_path=self.db)['stable_id'], qid)

    def test_round_excludes_seen_and_correct_questions(self):
        with sqlite3.connect(self.db) as con:
            ids = [r[0] for r in con.execute('SELECT question_id FROM question_stats LIMIT 3')]
        record_result(ids[0], 'wrong', self.db)
        record_result(ids[1], 'correct', self.db)
        with patch('app.database.random.SystemRandom') as rng:
            rng.return_value.choice.side_effect = lambda rows: rows[0]
            select_next_question([], database_path=self.db, excluded_ids=[ids[0], ids[2]])
            candidates = {r['stable_id'] for r in rng.return_value.choice.call_args.args[0]}
            self.assertTrue(set(ids).isdisjoint(candidates))

    def test_wrong_only_round_and_skipped_question(self):
        qid = select_next_question([], database_path=self.db)['stable_id']
        record_result(qid, 'wrong', self.db)
        self.assertEqual(select_next_question([], database_path=self.db, round_filter='wrong')['stable_id'], qid)
        self.assertIsNone(select_next_question([], database_path=self.db, round_filter='wrong', excluded_ids=[qid]))
        record_result(qid, 'unrated', self.db)
        self.assertIsNone(select_next_question([], database_path=self.db, round_filter='wrong'))
        self.assertGreater(get_quiz_progress([], database_path=self.db)['remaining'], 0)

    def test_library_filter_and_scope_counts_do_not_write_progress(self):
        cards = list_library_sections(['python', 'rag'], 'foundation', self.db)
        items = [q for s in cards['sections'] for g in s['groups'] for q in g['items']]
        record_result(items[0]['stable_id'], 'correct', self.db)
        record_result(items[1]['stable_id'], 'wrong', self.db)
        progress = get_quiz_progress(['python', 'rag'], 'foundation', self.db)
        self.assertEqual((progress['correct'], progress['wrong'], progress['total']), (1, 1, len(items)))
        before = get_progress_stats(self.db)
        for status in ['correct', 'wrong']:
            result = list_library_sections(['python', 'rag'], 'foundation', self.db, result_filter=status)
            filtered = [q for s in result['sections'] for g in s['groups'] for q in g['items']]
            self.assertEqual(len(filtered), 1)
            self.assertEqual(filtered[0]['result'], status)
        self.assertEqual(before, get_progress_stats(self.db))

    def test_upgrade_preserves_old_progress_and_settings(self):
        save_selection(['python'], 'foundation', self.db)
        qid = select_next_question([], database_path=self.db)['stable_id']
        with sqlite3.connect(self.db) as con:
            before = con.execute('SELECT question_id, seen_count, last_seen_at FROM question_stats ORDER BY question_id').fetchall()
            con.execute('ALTER TABLE question_stats DROP COLUMN result')
        initialize_database(self.db)
        with sqlite3.connect(self.db) as con:
            after = con.execute('SELECT question_id, seen_count, last_seen_at FROM question_stats ORDER BY question_id').fetchall()
        self.assertEqual(before, after)
        self.assertEqual(get_progress_stats(self.db)['correct'], 0)
        self.assertEqual(get_bootstrap(self.db)['selected_topics'], ['python'])
