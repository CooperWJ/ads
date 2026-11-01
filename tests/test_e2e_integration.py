"""项目接入只增加官方 MCP 与技能源，不覆盖既有权威。"""
import json
from pathlib import Path
import tempfile
import unittest
from ads.cli import init
from ads.integrations import e2e, SUPERPOWERS_PLUGIN
from ads.project import Blocked


class E2EIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_combined_initialization_uses_original_upstream_skills_and_no_download(self):
        result = init(self.root, superpowers=True, e2e=True)
        config = json.loads((self.root/'opencode.json').read_text())
        self.assertEqual(config['plugins'], [SUPERPOWERS_PLUGIN])
        self.assertEqual(config['mcp']['servers']['e2e']['command'], ['npx','--no-install','e2e','mcp'])
        self.assertIn('./node_modules/e2e/skills', config['skills'])
        self.assertEqual(result['e2e']['runtime'], 'NOT_VERIFIED')
        self.assertFalse((self.root/'node_modules').exists())

    def test_existing_profile_router_permissions_and_server_are_preserved(self):
        init(self.root)
        profile = (self.root/'ads.project.json').read_bytes()
        router = self.root/'.opencode/skills/skill-router/SKILL.md'
        router.parent.mkdir(parents=True)
        router.write_text('用户权威增量')
        existing = {'mcp':{'servers':{'e2e':{'type':'local','command':['user-e2e']}}},
                    'skills':['./user-skills'],'permissions':[{'action':'shell','effect':'ask'}]}
        (self.root/'opencode.json').write_text(json.dumps(existing))
        init(self.root, e2e=True)
        e2e(self.root)
        config = json.loads((self.root/'opencode.json').read_text())
        self.assertEqual(config['mcp'], existing['mcp'])
        self.assertEqual(config['permissions'], existing['permissions'])
        self.assertEqual(config['skills'].count('./node_modules/e2e/skills'), 1)
        self.assertEqual((self.root/'ads.project.json').read_bytes(), profile)
        self.assertEqual(router.read_text(), '用户权威增量')

    def test_ambiguous_or_legacy_configuration_is_not_overwritten(self):
        config = self.root/'opencode.jsonc'
        config.write_text('{ // comments\n}')
        with self.assertRaises(Blocked): e2e(self.root)
        self.assertFalse((self.root/'opencode.json').exists())
