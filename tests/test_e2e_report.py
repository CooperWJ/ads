"""上游报告语义的正常/故障反例；真实运行另由 e2e PoC 校准。"""
import json
import unittest

from ads.evidence import parse
from ads.project import Blocked


def report():
    return {'schemaVersion':'report-1', 'run': {
        'specVersion':'0.1', 'runner':{'name':'e2e','version':'0.22.0'},
        'status':'passed', 'exitCode':0, 'errors':[], 'serialGroups':[],
        'summary':{'discovered':1,'selected':1,'executed':1,'passed':1,'failed':0,'flaky':0,'skipped':0,'interrupted':0},
        'results':[{'testId':'tests/flow.e2e.ts::save','targetId':'web','agent':'default','repeat':0,
                    'selected':True,'status':'passed','attempts':[{'status':'passed','cleanup':'complete',
                    'secondaryErrors':[],'steps':[{'status':'passed','api':'expect.toHaveText'}]}]}]}}


class E2EReportTests(unittest.TestCase):
    def outcome(self, doc):
        return parse('e2e', json.dumps(doc).encode())

    def test_actual_attempt_is_required_and_identity_includes_target_agent_repeat(self):
        doc = report()
        case = self.outcome(doc)[0]
        self.assertEqual(case['status'], 'PASS')
        self.assertEqual(json.loads(case['id']), ['tests/flow.e2e.ts::save','web','default','0'])
        doc['run']['results'][0]['attempts'] = []
        self.assertEqual(self.outcome(doc)[0]['status'], 'FAIL')

    def test_flaky_exit_zero_does_not_become_pass(self):
        doc = report()
        run = doc['run']
        run['summary'].update(passed=0,flaky=1)
        run['results'][0].update(status='flaky',attempts=[{'status':'failed','cleanup':'complete'},
                                                        {'status':'passed','cleanup':'complete'}])
        self.assertEqual(self.outcome(doc)[0]['status'], 'FAIL')

    def test_skipped_filtered_and_interrupted_are_not_run(self):
        for state in ('skipped','interrupted'):
            doc = report()
            doc['run']['summary'].update(passed=0,**{state:1})
            doc['run']['results'][0]['status'] = state
            self.assertEqual(self.outcome(doc)[0]['status'], 'NOT_RUN')
        doc = report()
        doc['run']['results'][0]['selected'] = False
        doc['run']['summary'].update(selected=0,passed=0,executed=0)
        self.assertEqual(self.outcome(doc)[0]['status'], 'NOT_RUN')

    def test_failed_step_cleanup_and_prior_attempt_cannot_hide_behind_pass(self):
        for mutation in ('step','cleanup','attempt','secondary'):
            with self.subTest(mutation=mutation):
                doc = report()
                attempt = doc['run']['results'][0]['attempts'][0]
                if mutation == 'step': attempt['steps'][0]['status'] = 'failed'
                if mutation == 'cleanup': attempt['cleanup'] = 'forced'
                if mutation == 'attempt': doc['run']['results'][0]['attempts'].insert(0,{'status':'failed','cleanup':'complete'})
                if mutation == 'secondary': attempt['secondaryErrors'] = [{'code':'CLEANUP_FAILED'}]
                self.assertEqual(self.outcome(doc)[0]['status'], 'FAIL')

    def test_run_errors_unknown_protocol_missing_cases_and_carried_work_block(self):
        for mutation in ('error','schema','summary','empty','carried','explore','duplicate','boolean','repeat'):
            doc = report()
            if mutation == 'error': doc['run']['errors'] = [{'code':'APP_UNREACHABLE'}]
            if mutation == 'schema': doc['schemaVersion'] = 'report-999'
            if mutation == 'summary': doc['run']['summary']['passed'] = 5
            if mutation == 'empty': doc['run']['results'] = []
            if mutation == 'carried': doc['run']['carried'] = {'results':[{'status':'failed'}]}
            if mutation == 'explore': doc['run']['explore'] = {'goal':'explore'}
            if mutation == 'duplicate': doc['run']['results'] *= 2
            if mutation == 'boolean': doc['run']['summary']['selected'] = True
            if mutation == 'repeat': doc['run']['results'][0]['repeat'] = True
            with self.subTest(mutation=mutation), self.assertRaises(Blocked):
                self.outcome(doc)

    def test_serial_group_member_and_group_cleanup_both_matter(self):
        doc = report()
        item = doc['run']['results'][0]
        item['serialGroupId'] = 'group'
        doc['run']['serialGroups'] = [{'id':'group','status':'passed','attempts':[
            {'status':'passed','cleanup':'complete','secondaryErrors':[],
             'members':[{'testId':item['testId'],'status':'passed','steps':[]}]}]}]
        item['attempts'] = []
        self.assertEqual(self.outcome(doc)[0]['status'], 'PASS')
        doc['run']['serialGroups'][0]['status'] = 'failed'
        self.assertEqual(self.outcome(doc)[0]['status'], 'FAIL')
        doc['run']['serialGroups'][0]['status'] = 'passed'
        doc['run']['serialGroups'][0]['attempts'][0]['members'][0]['status'] = 'failed'
        self.assertEqual(self.outcome(doc)[0]['status'], 'FAIL')
