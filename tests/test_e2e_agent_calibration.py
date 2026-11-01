import json
import sys
import tempfile
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


def valid_repair_ledger():
    return {
        'schema': 'ads-agent-repair-ledger/v1',
        'test_id': 'agent-bounded-repair-save-refresh-export',
        'max_repairs': 1,
        'repair_attempts': 1,
        'observations': [
            {
                'ok': False, 'code': 'SAVE_HTTP_503',
                'status': 'Save failed: HTTP 503', 'attempts': 1, 'persisted': '',
            },
            {
                'ok': True, 'code': 'SAVE_VERIFIED', 'status': 'Saved',
                'selectedProjectId': '1', 'note': 'Reviewed in M0',
                'persisted': 'Reviewed in M0', 'attempts': 2,
            },
        ],
        'save_attempts': 3,
        'export_attempts': 1,
        'final_persisted': 'Reviewed in M0',
        'final_exported': 'Reviewed in M0',
    }


class E2EAgentCalibrationTests(unittest.TestCase):
    def test_prepare_binds_local_opencode_cli_profile_and_adapter(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = calibrate.prepare(
                Path(temporary) / 'workspace',
                'reference',
                agent=True,
                agent_backend='opencode-cli',
            )
            root = project.root
            self.assertTrue((root / 'e2e.agent.opencode-cli.config.ts').is_file())
            self.assertTrue((root / 'opencode-cli-model.ts').is_file())
            self.assertTrue((root / 'agent-repair.ts').is_file())
            self.assertTrue((root / 'tests/agent-journey.e2e.ts').is_file())
            self.assertIn("cache: 'off'", (root / 'e2e.config.ts').read_text())
            config = json.loads((root / 'ads.project.json').read_text())
            argvs = [check.get('argv', []) for check in config.get('checks', [])]
            self.assertTrue(any('e2e.agent.opencode-cli.config.ts' in argv for argv in argvs))

    def test_prepare_binds_console_profile_without_cli_adapter(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = calibrate.prepare(
                Path(temporary) / 'workspace',
                'reference',
                agent=True,
                agent_backend='opencode-console',
            )
            root = project.root
            self.assertTrue((root / 'e2e.agent.config.ts').is_file())
            self.assertFalse((root / 'opencode-cli-model.ts').exists())
            self.assertTrue((root / 'agent-repair.ts').is_file())
            config = json.loads((root / 'ads.project.json').read_text())
            argvs = [check.get('argv', []) for check in config.get('checks', [])]
            self.assertTrue(any('e2e.agent.config.ts' in argv for argv in argvs))

    def test_repair_ledger_requires_semantically_valid_single_repair_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'agent-repair-ledger.json'
            path.write_text(json.dumps(valid_repair_ledger()))
            data, status, digest = calibrate.validate_agent_repair_ledger(path)
            self.assertEqual(status, 'VALID')
            self.assertEqual(data['repair_attempts'], 1)
            self.assertRegex(digest, r'^[a-f0-9]{64}$')

            invalid = valid_repair_ledger()
            invalid['repair_attempts'] = 2
            path.write_text(json.dumps(invalid))
            _data, status, digest = calibrate.validate_agent_repair_ledger(path)
            self.assertEqual(status, 'INVALID')
            self.assertRegex(digest, r'^[a-f0-9]{64}$')

    def test_repair_ledger_missing_or_malformed_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'missing.json'
            self.assertEqual(calibrate.validate_agent_repair_ledger(path), (None, 'MISSING', None))
            path.write_text('{not-json')
            _data, status, _digest = calibrate.validate_agent_repair_ledger(path)
            self.assertEqual(status, 'INVALID')

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
