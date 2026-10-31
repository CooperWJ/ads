"""整项原始来源遗漏不能由规格内全绿掩盖。"""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).parent))
from test_ads_core import fixture
from ads import alignment, evidence
from ads.project import Project, Blocked, write_json


class SourceAlignmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = fixture(self.root)
        preview = alignment.reconcile(self.project, True)
        self.decisions = [{'unit_id':u['id'],'text_sha256':u['text_sha256'],
                           'reviewer':'synthetic-source-reviewer','decision_ref':'synthetic-decision',
                           'disposition':'CONTEXT' if u['kind']=='heading' else 'REQUIRED',
                           'reason':'source document title' if u['kind']=='heading' else '',
                           'obligations':[] if u['kind']=='heading' else ['normalize-label']}
                          for u in preview['units']]
        profile = self.project.config
        profile['source_review'] = 'source-review.json'
        write_json(self.root/'ads.project.json', profile)
        self.project = Project(self.root)

    def review(self, decisions):
        write_json(self.root/'source-review.json', {'schema':'ads-source-alignment-review/v1','decisions':decisions})

    def test_review_is_a_projection_not_approval(self):
        self.review(self.decisions)
        result = alignment.reconcile(self.project)
        self.assertEqual(result['status'], 'SCOPED_RECONCILED_LOCAL')
        self.assertEqual(result['independent_reviewer_identity'], 'NOT_VERIFIED')

    def test_dropping_whole_source_fragment_is_detected(self):
        self.review(self.decisions[:-1])
        result = alignment.reconcile(self.project)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertTrue(result['missing_units'])

    def test_spec_test_pass_does_not_override_known_source_gap(self):
        decisions = copy.deepcopy(self.decisions)
        for row in decisions:
            row.update(disposition='CONTEXT', obligations=[], reason='synthetic exclusion')
        self.review(decisions)
        self.assertEqual(evidence.run_checks(self.project)['status'], 'PASS')
        result = evidence.decide(self.project)
        self.assertEqual(result['requirements_alignment'], 'BLOCKED')
        self.assertEqual(result['development'], 'BLOCKED')

    def test_wrong_obligation_and_unresolved_review_cannot_pass(self):
        decisions = copy.deepcopy(self.decisions)
        decisions[-1]['obligations'] = ['invented-obligation']
        self.review(decisions)
        with self.assertRaises(Blocked):
            alignment.reconcile(self.project)
        decisions[-1].update(disposition='UNRESOLVED',obligations=[])
        self.review(decisions)
        self.assertEqual(alignment.reconcile(self.project)['status'], 'BLOCKED')


if __name__ == '__main__':
    unittest.main()
