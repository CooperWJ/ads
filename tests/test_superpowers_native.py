"""可选真实 OpenCode 冒烟：官方插件注册和原生技能激活，不调用模型。"""
import base64
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import unittest
from urllib.request import Request, ProxyHandler, build_opener

from ads.integrations import SUPERPOWERS_PLUGIN


@unittest.skipUnless(os.environ.get('ADS_OPENCODE_EXECUTABLE'), '需要真实 OpenCode 可执行文件')
class NativeSuperpowersTests(unittest.TestCase):
    def test_official_plugin_registers_and_activates_required_skills(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'opencode.json').write_text(json.dumps({'plugins': [SUPERPOWERS_PLUGIN]}))
            subprocess.run(['git', 'init', '-q', directory], check=True)
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            log = root / 'native-private.log'
            with log.open('w') as stream:
                process = subprocess.Popen([os.environ['ADS_OPENCODE_EXECUTABLE'], 'serve',
                    '--hostname', '127.0.0.1', '--port', str(port)], cwd=root, stdout=stream, stderr=stream)
                try:
                    password = None
                    for _ in range(200):
                        password = next((line.removeprefix('server password ') for line in log.read_text().splitlines()
                                         if line.startswith('server password ')), None)
                        if password or process.poll() is not None:
                            break
                        time.sleep(.1)
                    self.assertIsNotNone(password, '原生服务未就绪；私有日志不输出到 CI')
                    opener = build_opener(ProxyHandler({}))
                    headers = {'Authorization': 'Basic ' + base64.b64encode(('opencode:' + password).encode()).decode(),
                               'Content-Type': 'application/json'}
                    def request(path, body=None):
                        req = Request(f'http://127.0.0.1:{port}' + path, headers=headers,
                                      data=None if body is None else json.dumps(body).encode())
                        with opener.open(req, timeout=60) as response:
                            raw = response.read()
                            return json.loads(raw) if raw else None
                    session = request('/api/session', {'title': 'ADS synthetic plugin smoke',
                                      'location': {'directory': directory}})['data']
                    matches = []
                    for _ in range(120):
                        plugins = request('/api/plugin')['data']
                        matches = [p for p in plugins if p['id'] in ('superpowers', SUPERPOWERS_PLUGIN)]
                        if matches and matches[0]['state']['status'] == 'active':
                            break
                        time.sleep(.25)
                    self.assertEqual(len(matches), 1, [p['id'] for p in plugins])
                    plugin = matches[0]
                    self.assertEqual(plugin['state']['status'], 'active')
                    required = {'systematic-debugging', 'test-driven-development', 'verification-before-completion'}
                    registered = {s['id'] for s in request('/api/skill')['data']}
                    self.assertTrue(required <= registered)
                    for skill in sorted(required):
                        request('/api/experimental/session/' + session['id'] + '/skill', {'id': skill, 'resume': False})
                    messages = request('/api/session/' + session['id'] + '/message')['data']
                    self.assertEqual(len(messages), len(required))
                finally:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
