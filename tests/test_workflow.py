"""Synthetic offline fixtures only; no scientific assertions or real DOI validation."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from introlab import workflow as w
from introlab.cli import main
from introlab.crossref import to_record, request_json
from introlab.store import connect, upsert_paper, mark_checked, review_claim, export_data


def payload(batch=1, start=0):
    return {'schema_version': 1, 'batch_id': batch, 'papers': [
        {'doi': f'10.1000/fixture-{i}', 'title': 'Synthetic test fixture',
         'urls': [f'https://example.org/paper/{i}'], 'relevance': 'Synthetic relevance',
         'ligand_match': False, 'claims': [
             {'id': f'c{i}', 'statement': '합성 시험용 주장이다.', 'kind': 'experimental_fact',
              'locator': 'Figure 1', 'evidence': 'Synthetic evidence, not a publication',
              'source_url': f'https://example.org/paper/{i}', 'access': 'accessible'}]}
        for i in range(start, start + 5)],
        'sentences': [{'text': '합성 시험용 결과가 보고되었다.', 'claim_ids': [f'c{start}']}]}


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / '한글 프로젝트' / 'research.db'
        self.db = connect(self.path)
        w.configure(self.db, {'field': 'bioinorganic', 'metals': ['Mn'], 'ligands': [],
                             'reactions': [], 'substrates': [], 'style_rules': ['간결한 수동형']})
        w.plan(self.db)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def verify_first(self):
        doi = '10.1000/fixture-0'
        upsert_paper(self.db, to_record({'DOI': doi, 'title': ['Synthetic test fixture']}))
        mark_checked(self.db, doi, 'publisher', 'https://example.org/paper/0 Figure 1 checked')
        review_claim(self.db, 1, 'supported', 'Source evidence checked')
        mark_checked(self.db, doi, 'followup', 'Independent literature checked through test date')

    def test_import_never_approves_and_is_idempotent(self):
        p = payload()
        p['papers'][0]['metadata_verified'] = True
        p['papers'][0]['claims'][0]['review_status'] = 'supported'
        w.import_research(self.db, p)
        self.assertEqual(self.db.execute('SELECT metadata_verified FROM papers LIMIT 1').fetchone()[0], 0)
        self.assertEqual(self.db.execute('SELECT review_status FROM claims LIMIT 1').fetchone()[0], 'pending')
        self.assertIn('Already imported', w.import_research(self.db, p))
        self.assertEqual(self.db.execute('SELECT count(*) FROM claims').fetchone()[0], 5)
        with self.assertRaises(ValueError): w.review_sentence(self.db, 1, 'review')

    def test_atomic_import_rolls_back_bad_late_record(self):
        p = payload(); p['papers'][-1]['claims'][0]['source_url'] = 'invalid'
        with self.assertRaises(ValueError): w.import_research(self.db, p)
        self.assertEqual(self.db.execute('SELECT count(*) FROM papers').fetchone()[0], 0)
        self.assertEqual(self.db.execute('SELECT status FROM batches WHERE id=1').fetchone()[0], 'planned')

    def test_discovery_excludes_previous_results_and_refreshes_prompt(self):
        w.import_research(self.db, payload())
        with self.assertRaises(ValueError): w.import_research(self.db, payload(2))
        self.assertIn('10.1000/fixture-0', w.batch_prompt(self.db, 2))
        self.assertEqual(self.db.execute('SELECT count(*) FROM papers').fetchone()[0], 5)

    def test_only_actual_reviewed_batches_count(self):
        self.assertEqual(self.db.execute("SELECT count(*) FROM batches WHERE status='completed'").fetchone()[0], 0)
        with self.assertRaises(ValueError): w.review_batch(self.db, 1, 'Not browsed')
        w.import_research(self.db, payload())
        w.review_batch(self.db, 1, 'Actual links and relevance manually checked')
        self.assertEqual(self.db.execute("SELECT count(*) FROM batches WHERE status='completed'").fetchone()[0], 1)
        with self.assertRaises(ValueError): w.plan(self.db, 9)

    def test_korean_citations_edits_and_revalidation(self):
        w.import_research(self.db, payload())
        self.verify_first()
        w.review_sentence(self.db, 1, 'Korean wording entails claim 1')
        text, cmap = w.korean_draft(self.db, '기전 연구')
        self.assertIn('합성 시험용 결과가 보고되었다. [1]', text)
        self.assertEqual(cmap['sentences'][0]['sources'][0]['claim_id'], 1)
        w.save_sentence(self.db, 1, '사용자가 수정한 문장이 보존되었다.', [1])
        self.assertEqual(self.db.execute('SELECT count(*) FROM sentence_history').fetchone()[0], 1)
        w.review_sentence(self.db, 1, 'Edit reviewed')
        self.assertIn('사용자가 수정한', w.korean_draft(self.db, 'Test')[0])
        review_claim(self.db, 1, 'uncertain', 'Evidence questioned')
        self.assertNotIn('사용자가 수정한', w.korean_draft(self.db, 'Test')[0])

    def test_metadata_and_source_checks_are_independent(self):
        w.import_research(self.db, payload())
        doi = '10.1000/fixture-0'
        mark_checked(self.db, doi, 'publisher', 'Read source')
        mark_checked(self.db, doi, 'followup', 'Checked later literature')
        review_claim(self.db, 1, 'supported', 'Checked evidence')
        self.assertFalse(w.eligible(self.db, [1]))

    def test_inaccessible_and_interpretations_not_facts(self):
        p = payload(); p['papers'][0]['claims'][0]['access'] = 'inaccessible'
        w.import_research(self.db, p)
        mark_checked(self.db, '10.1000/fixture-0', 'publisher', 'Landing page only')
        with self.assertRaises(ValueError): review_claim(self.db, 1, 'supported', 'Bad approval')
        self.db.execute("UPDATE claims SET access='accessible',kind='interpretation' WHERE id=1")
        self.db.commit()
        self.verify_first()
        self.assertFalse(w.eligible(self.db, [1]))

    def test_conflict_blocks_draft(self):
        w.import_research(self.db, payload())
        self.verify_first()
        w.review_sentence(self.db, 1, 'Reviewed')
        self.db.execute("INSERT INTO relations(source,target,kind,note,created_at) VALUES (2,1,'contradicts','Conflict','test')")
        self.db.commit()
        self.assertEqual(w.korean_draft(self.db, 'Test')[1]['sentences'], [])

    def test_full_ten_rounds_and_resultlab(self):
        for i in range(10):
            w.import_research(self.db, payload(i + 1, i * 5))
            w.review_batch(self.db, i + 1, 'Synthetic browsing fixture reviewed')
        self.db.execute("INSERT INTO gaps(question,related_dois,created_at) VALUES ('specific TS','[]','test')")
        self.db.commit()
        a = {k: {'score': 4, 'reason': 'Synthetic assessment'} for k in
             ('importance','novelty','experiment_link','dft_feasibility','discriminating_prediction')}
        a.update(status='shortlisted', novelty_sources=['https://example.org/followup'],
                 followup_scope='Synthetic independent follow-up check',
                 plan={k: 'Use established protocol' for k in ('reactant','intermediate','transition_state','irc','spin_states')})
        w.assess_gap(self.db, 1, a)
        self.assertEqual(len(w.resultlab_export(self.db)['candidates']), 1)
        a['status'] = 'resolved'; w.assess_gap(self.db, 1, a)
        self.assertEqual(w.resultlab_export(self.db)['candidates'], [])

    def test_shortlist_before_ten_rounds_rejected(self):
        self.db.execute("INSERT INTO gaps(question,related_dois,created_at) VALUES ('specific TS','[]','test')")
        self.db.commit()
        a = {k: {'score': 5, 'reason': 'Test'} for k in
             ('importance','novelty','experiment_link','dft_feasibility','discriminating_prediction')}
        a.update(status='shortlisted',novelty_sources=['https://example.org'],followup_scope='Test',
                 plan={k:'Test' for k in ('reactant','intermediate','transition_state','irc','spin_states')})
        with self.assertRaises(ValueError): w.assess_gap(self.db, 1, a)

    def test_reopen_migration_and_export(self):
        w.import_research(self.db, payload())
        self.db.close(); self.db = connect(self.path)
        data = export_data(self.db)
        self.assertEqual(data['format_version'], 2)
        self.assertEqual(len(data['claims']), 5)
        self.assertIn('project_results', data)

    def test_cli_failure_is_safe_and_logged(self):
        with patch('introlab.cli.search_works', side_effect=RuntimeError('offline')):
            self.assertEqual(main(['--db', str(self.path), 'discover', 'Mn', '--journal', 'JACS']), 1)
        self.assertEqual(self.db.execute('SELECT status FROM searches').fetchone()[0], 'failed')

    def test_cli_korean_path_export_and_review(self):
        target = Path(self.tmp.name) / '한글 출력.json'
        self.assertEqual(main(['--db', str(self.path), 'export', '--out', str(target)]), 0)
        self.assertEqual(json.loads(target.read_text(encoding='utf-8'))['format_version'], 2)
        self.assertEqual(main(['--db', str(self.path), 'review', '--out', str(target)]), 0)

    def test_malformed_crossref_payload(self):
        from io import StringIO
        with patch('introlab.crossref.urlopen', return_value=StringIO('[]')):
            with self.assertRaises(RuntimeError): request_json('/works')


if __name__ == '__main__': unittest.main()
