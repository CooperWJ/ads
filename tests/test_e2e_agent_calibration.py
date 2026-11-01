import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'poc' / 'e2e'))
import calibrate  # noqa: E402


def observed_agent():
    return {
        'status': 'OBSERVED',
        'mode': 'AGENT_PLUS_DETERMINISTIC',
        'agent_steps': 1,
        'act_steps': 1,
        'deterministic_assertions_after_act': 1,
        'model_calls': 2,
        'model_provenance': 'OBSERVED',
        'cache_modes': {
            'self-finalized': 0,
            'agent-concluded': 0,
            'missed': 0,
            'unobserved': 1,
        },
    }


class E2EAgentCalibrationTests(unittest.TestCase):
    def test_only_live_agent_plus_deterministic_run_can_pass(self):
        self.assertEqual(calibrate.agent_status(observed_agent(), True), 'PASS')
        self.assertEqual(calibrate.agent_status(observed_agent(), False), 'FAIL')

    def test_missing_or_replayed_model_execution_is_blocked(self):
        cases = []
        no_calls = observed_agent()
        no_calls['model_calls'] = 0
        cases.append(no_calls)
        replayed = observed_agent()
        replayed['cache_modes']['self-finalized'] = 1
        cases.append(replayed)
        unknown_model = observed_agent()
        unknown_model['model_provenance'] = 'NOT_REPORTED'
        cases.append(unknown_model)
        blocked = observed_agent()
        blocked['status'] = 'BLOCKED'
        cases.append(blocked)
        missing = None
        cases.append(missing)
        for evidence in cases:
            with self.subTest(evidence=evidence):
                self.assertEqual(calibrate.agent_status(evidence, True), 'BLOCKED')

    def test_agent_execution_failure_is_not_relabelled_as_blocked(self):
        failed = observed_agent()
        failed['status'] = 'FAILED'
        self.assertEqual(calibrate.agent_status(failed, True), 'FAIL')

    def test_agent_without_post_action_assertion_cannot_pass(self):
        no_assertion = observed_agent()
        no_assertion['mode'] = 'AGENT_WITHOUT_DETERMINISTIC_ASSERTION'
        no_assertion['deterministic_assertions_after_act'] = 0
        self.assertEqual(calibrate.agent_status(no_assertion, True), 'FAIL')


if __name__ == '__main__':
    unittest.main()
