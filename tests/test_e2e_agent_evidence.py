import json
import unittest
from unittest.mock import patch

from ads import evidence, qa
from ads.e2e_report import e2e
from ads.project import Blocked


def report():
    return {
        'schemaVersion': 'report-1',
        'run': {
            'specVersion': '0.1',
            'runner': {'name': 'e2e', 'version': '0.22.0'},
            'status': 'passed',
            'exitCode': 0,
            'errors': [],
            'serialGroups': [],
            'summary': {
                'discovered': 1, 'selected': 1, 'executed': 1, 'passed': 1,
                'failed': 0, 'interrupted': 0, 'flaky': 0, 'skipped': 0,
            },
            'results': [{
                'testId': 'tests/agent-flow.e2e.ts::save-refresh',
                'targetId': 'chromium',
                'agent': 'default',
                'repeat': 0,
                'selected': True,
                'status': 'passed',
                'attempts': [{
                    'status': 'passed',
                    'cleanup': 'complete',
                    'secondaryErrors': [],
                    'steps': [],
                }],
            }],
        },
    }


def agent_step(api='agent.act', model_calls=2, cache_mode='missed'):
    cache = {
        'mode': cache_mode,
        'replayedActions': 0 if cache_mode == 'missed' else 3,
        'totalActions': 3,
    }
    if cache_mode != 'self-finalized':
        cache['reason'] = 'no-entry' if cache_mode == 'missed' else 'end-mismatch'
    step = {
        'kind': 'agent',
        'api': api,
        'status': 'passed',
        'label': 'PRIVATE INSTRUCTION MUST NOT BE PROJECTED',
        'metrics': {
            'modelCalls': model_calls,
            'actionSteps': 3,
            'observationBytes': 1200,
            'contextBytes': 2400,
            'ledgerBytes': 300,
        },
        'cache': cache,
        'events': [{'kind': 'model', 'status': 'passed', 'detail': 'PRIVATE MODEL TRACE'}],
        'turns': [{'index': 1, 'calls': ['private.tool'], 'outcome': 'PRIVATE MODEL OUTPUT'}],
    }
    if model_calls:
        step['model'] = {
            'provider': 'deepseek',
            'model': 'deepseek-v4.1-flash-free',
            'endpoint': 'provider-default',
            'adapterVersion': 'test-adapter',
            'policyVersion': 'test-policy',
            'calls': model_calls,
            'tokenAccounting': 'provider',
            'peakTokensPerCall': 800,
            'inputTokens': 1200,
            'outputTokens': 220,
            'estimatedCostUsd': 0.002,
        }
    return step


def deterministic_assertion():
    return {
        'kind': 'assertion',
        'api': 'expect.toHaveText',
        'status': 'passed',
        'label': 'getByRole("status")',
    }


class E2EAgentEvidenceTests(unittest.TestCase):
    def evaluate(self, document):
        return e2e(json.dumps(document).encode())[0]

    def test_agent_act_and_deterministic_assertion_are_projected_and_model_usage_bound(self):
        doc = report()
        doc['run']['results'][0]['attempts'][0]['steps'] = [
            agent_step(), deterministic_assertion(),
        ]
        result = self.evaluate(doc)
        evidence = result['agent_evidence']
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(evidence['status'], 'OBSERVED')
        self.assertEqual(evidence['mode'], 'AGENT_PLUS_DETERMINISTIC')
        self.assertEqual(evidence['agent_steps'], 1)
        self.assertEqual(evidence['act_steps'], 1)
        self.assertEqual(evidence['deterministic_assertions'], 1)
        self.assertEqual(evidence['action_steps'], 3)
        self.assertEqual(evidence['model_calls'], 2)
        self.assertEqual(evidence['input_tokens'], 1200)
        self.assertEqual(evidence['output_tokens'], 220)
        self.assertAlmostEqual(evidence['estimated_cost_usd'], 0.002)
        self.assertEqual(evidence['models'], [{
            'provider': 'deepseek', 'model': 'deepseek-v4.1-flash-free',
        }])
        self.assertEqual(evidence['model_provenance'], 'OBSERVED')
        self.assertEqual(evidence['model_usage_status'], 'OBSERVED')
        self.assertEqual(evidence['model_cost_status'], 'OBSERVED')
        self.assertEqual(evidence['cache_modes']['missed'], 1)

    def test_projection_never_copies_agent_instruction_turn_or_event_detail(self):
        doc = report()
        doc['run']['results'][0]['attempts'][0]['steps'] = [
            agent_step(), deterministic_assertion(),
        ]
        result = self.evaluate(doc)
        serialized = json.dumps(result)
        self.assertNotIn('PRIVATE INSTRUCTION', serialized)
        self.assertNotIn('PRIVATE MODEL TRACE', serialized)
        self.assertNotIn('PRIVATE MODEL OUTPUT', serialized)
        self.assertNotIn('label', result['agent_evidence'])
        self.assertNotIn('turns', result['agent_evidence'])

    def test_replayed_agent_step_does_not_claim_live_model_usage(self):
        doc = report()
        doc['run']['results'][0]['attempts'][0]['steps'] = [
            agent_step(model_calls=0, cache_mode='self-finalized'),
            deterministic_assertion(),
        ]
        evidence = self.evaluate(doc)['agent_evidence']
        self.assertEqual(evidence['mode'], 'AGENT_PLUS_DETERMINISTIC')
        self.assertEqual(evidence['model_calls'], 0)
        self.assertEqual(evidence['model_provenance'], 'NO_MODEL_CALLS')
        self.assertEqual(evidence['cache_modes']['self-finalized'], 1)

    def test_agent_without_deterministic_assertion_is_explicitly_distinguished(self):
        for steps in ([agent_step()], [deterministic_assertion(), agent_step()]):
            doc = report()
            doc['run']['results'][0]['attempts'][0]['steps'] = steps
            evidence = self.evaluate(doc)['agent_evidence']
            self.assertEqual(evidence['mode'], 'AGENT_WITHOUT_DETERMINISTIC_ASSERTION')
            self.assertEqual(evidence['deterministic_assertions_after_act'], 0)

    def test_agent_step_failure_cannot_hide_inside_passed_attempt(self):
        doc = report()
        failed = agent_step()
        failed['status'] = 'failed'
        doc['run']['results'][0]['attempts'][0]['steps'] = [failed]
        self.assertEqual(self.evaluate(doc)['status'], 'FAIL')

    def test_agent_metrics_and_model_cost_fail_closed(self):
        for mutate in ('missing_metrics', 'negative_calls', 'negative_cost', 'calls_mismatch'):
            doc = report()
            step = agent_step()
            if mutate == 'missing_metrics':
                step.pop('metrics')
            elif mutate == 'negative_calls':
                step['metrics']['modelCalls'] = -1
            elif mutate == 'negative_cost':
                step['model']['estimatedCostUsd'] = -0.1
            else:
                step['model']['calls'] = 1
            doc['run']['results'][0]['attempts'][0]['steps'] = [step]
            with self.subTest(mutate=mutate), self.assertRaises(Blocked):
                self.evaluate(doc)

    def test_partial_model_metadata_never_reports_a_complete_cost(self):
        doc = report()
        first = agent_step()
        second = agent_step()
        second.pop('model')
        doc['run']['results'][0]['attempts'][0]['steps'] = [
            first, second, deterministic_assertion(),
        ]
        evidence = self.evaluate(doc)['agent_evidence']
        self.assertEqual(evidence['model_provenance'], 'PARTIAL')
        self.assertEqual(evidence['model_usage_status'], 'PARTIAL')
        self.assertEqual(evidence['model_cost_status'], 'PARTIAL')
        self.assertIsNone(evidence['estimated_cost_usd'])

    def test_unsafe_model_identifier_is_rejected(self):
        doc = report()
        step = agent_step()
        step['model']['provider'] = 'provider-with-secret-token value'
        doc['run']['results'][0]['attempts'][0]['steps'] = [step]
        with self.assertRaises(Blocked):
            self.evaluate(doc)

    def test_requirement_decision_exposes_report_bound_agent_evidence(self):
        ident = json.dumps(
            ['tests/agent-flow.e2e.ts::save-refresh', 'chromium', 'default', '0'],
            separators=(',', ':'),
        )
        summary = self.evaluate({
            **report(),
            'run': {
                **report()['run'],
                'results': [{
                    **report()['run']['results'][0],
                    'attempts': [{
                        'status': 'passed', 'cleanup': 'complete', 'secondaryErrors': [],
                        'steps': [agent_step(), deterministic_assertion()],
                    }],
                }],
            },
        })['agent_evidence']
        run = {
            'run_id': 'a' * 32,
            'subject': {'sha256': 'b' * 64},
            'status': 'PASS',
            'checks': [{
                'check_id': 'e2e', 'status': 'PASS', 'report': '.ads/runs/run/e2e/report.json',
                'report_sha256': 'c' * 64,
                'cases': [{'id': ident, 'status': 'PASS', 'agent_evidence': summary}],
            }],
        }

        class ProjectStub:
            config = {}

            def contract(self):
                return {'obligations': [{
                    'id': 'save-refresh',
                    'tests': [{'check': 'e2e', 'case': ident}],
                }]}

        with patch.object(evidence, 'load_current', return_value=run), \
             patch('ads.sources.discover', return_value={'status': 'INVENTORIED'}):
            decision = evidence.decide(ProjectStub())
        reference = decision['obligations'][0]['verification_evidence'][0]['reference']
        self.assertEqual(reference['agent_evidence'], summary)
        self.assertEqual(reference['report_sha256'], 'c' * 64)
        self.assertEqual(reference['subject_sha256'], 'b' * 64)

    def test_qa_execution_exposes_the_same_report_bound_agent_evidence(self):
        case_id = 'module/save-refresh'
        case_hash = 'd' * 64
        summary = {
            'status': 'OBSERVED',
            'mode': 'AGENT_PLUS_DETERMINISTIC',
            'agent_steps': 1,
            'act_steps': 1,
            'deterministic_assertions_after_act': 1,
            'model_calls': 2,
        }
        imported = {
            'cases': [{
                'id': case_id,
                'module': 'module',
                'source_locator': 'Cases!R2',
                'case_sha256': case_hash,
                'fields': {'expected': 'notes remain after refresh'},
            }],
            'source_sha256': 'e' * 64,
        }
        review = {
            case_id: {
                'case_sha256': case_hash,
                'reviewer': 'independent-qa',
                'decision_ref': 'review-001',
                'disposition': 'CONFIRMED',
                'tests': [{'check': 'e2e', 'case': 'native-case'}],
            },
        }
        run = {
            'run_id': 'f' * 32,
            'subject': {'sha256': 'a' * 64},
            'status': 'PASS',
            'checks': [{
                'check_id': 'e2e', 'status': 'PASS', 'failure': None,
                'report': '.ads/runs/run/e2e/report.json',
                'report_sha256': 'b' * 64,
                'cases': [{'id': 'native-case', 'status': 'PASS', 'agent_evidence': summary}],
            }],
        }
        with patch.object(qa, 'reviewed_baseline', return_value=(imported, review)), \
             patch.object(qa, 'load_current', return_value=run):
            result = qa.evaluate(object())
        reference = result['cases'][0]['verification_evidence'][0]['reference']
        self.assertEqual(reference['agent_evidence'], summary)
        self.assertEqual(reference['report_sha256'], 'b' * 64)
        self.assertEqual(reference['subject_sha256'], 'a' * 64)

    def test_serial_group_agent_evidence_uses_the_exact_member_steps(self):
        doc = report()
        result = doc['run']['results'][0]
        result['serialGroupId'] = 'group-1'
        result['attempts'] = []
        doc['run']['serialGroups'] = [{
            'id': 'group-1',
            'status': 'passed',
            'attempts': [{
                'status': 'passed',
                'cleanup': 'complete',
                'secondaryErrors': [],
                'members': [{
                    'testId': result['testId'],
                    'status': 'passed',
                    'steps': [agent_step(), deterministic_assertion()],
                    'secondaryErrors': [],
                }],
            }],
        }]
        evidence = self.evaluate(doc)['agent_evidence']
        self.assertEqual(evidence['mode'], 'AGENT_PLUS_DETERMINISTIC')
        self.assertEqual(evidence['model_calls'], 2)


if __name__ == '__main__':
    unittest.main()
