"""官方插件配置与薄路由；不把配置测试当成模型技能调用。"""
import json
from pathlib import Path
import tempfile
import unittest

from ads.cli import init
from ads.engineering import route
from ads.integrations import superpowers, SUPERPOWERS_PLUGIN
from ads.project import Blocked


class SuperpowersIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_init_registers_pinned_official_plugin_and_native_skill_guidance(self):
        result = init(self.root, superpowers=True)
        config = json.loads((self.root / 'opencode.json').read_text())
        self.assertEqual(config['plugins'], [SUPERPOWERS_PLUGIN])
        self.assertEqual(result['superpowers']['runtime'], 'NOT_VERIFIED')
        command = (self.root / '.opencode/commands/ads-develop.md').read_text()
        for skill in ('systematic-debugging', 'test-driven-development', 'verification-before-completion'):
            self.assertIn(skill, command)
        self.assertFalse((self.root / '.opencode/skills/superpowers').exists())

    def test_existing_project_and_user_authority_are_preserved(self):
        init(self.root)
        profile = (self.root / 'ads.project.json').read_bytes()
        router = self.root / '.opencode/skills/skill-router/SKILL.md'
        router.parent.mkdir(parents=True)
        router.write_text('用户的权威路由增量')
        command = self.root / '.opencode/commands/opsx-apply.md'
        command.write_text('既有 OpenSpec 入口')
        config = {'plugins': ['other-plugin'], 'model': 'synthetic/model',
                  'permissions': [{'action': 'shell', 'resource': '*', 'effect': 'ask'}]}
        (self.root / 'opencode.json').write_text(json.dumps(config))
        result = init(self.root, superpowers=True)
        merged = json.loads((self.root / 'opencode.json').read_text())
        self.assertEqual(merged['plugins'], ['other-plugin', SUPERPOWERS_PLUGIN])
        for key in ('model', 'permissions'):
            self.assertEqual(merged[key], config[key])
        self.assertEqual((self.root / 'ads.project.json').read_bytes(), profile)
        self.assertEqual(router.read_text(), '用户的权威路由增量')
        self.assertEqual(command.read_text(), '既有 OpenSpec 入口')
        self.assertEqual(result['status'], 'CONFIGURED')

    def test_existing_superpowers_pin_is_not_replaced(self):
        path = self.root / 'opencode.json'
        path.write_text(json.dumps({'plugins': ['superpowers@git+https://github.com/obra/superpowers.git#user-pin']}))
        before = path.read_bytes()
        superpowers(self.root)
        superpowers(self.root)
        self.assertEqual(path.read_bytes(), before)

    def test_jsonc_and_v1_are_preserved_for_explicit_migration(self):
        config = self.root / 'opencode.jsonc'
        config.write_text('{ // user settings\n}')
        with self.assertRaises(Blocked):
            superpowers(self.root)
        self.assertFalse((self.root / 'opencode.json').exists())
        config.unlink()
        legacy = self.root / 'opencode.json'
        legacy.write_text('{"plugin": ["existing-v1"]}')
        before = legacy.read_bytes()
        with self.assertRaises(Blocked):
            superpowers(self.root)
        self.assertEqual(legacy.read_bytes(), before)

    def test_suspected_defect_routes_to_debugging_without_brainstorming(self):
        result = route('已有页面分页不显示')
        self.assertEqual(result['route'], 'bug-fix')
        self.assertEqual(result['skills'][0], 'systematic-debugging')
        self.assertNotIn('brainstorming', result['skills'])
