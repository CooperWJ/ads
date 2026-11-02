"""真实 OpenCode V2 连接和技能激活冒烟；只输出低敏摘要，不调用模型。"""
import argparse
import base64
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import Request, ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from ads.integrations import e2e
from ads.project import write_json


def runtime_isolation_probe(executable, out, env):
    workspace = out / 'isolation-workspace'
    (workspace / '.opencode' / 'agents').mkdir(parents=True)
    config = {
        '$schema': 'https://opencode.ai/config.json',
        'update': 'disable',
        'plugins': [],
        'mcp': {},
        'instructions': [],
        'skills': [],
        'references': {},
        'permissions': [{'action': '*', 'resource': '*', 'effect': 'deny'}],
        'policies': [
            {'action': 'tool.use', 'resource': '*', 'effect': 'deny'},
            {'action': 'mcp.use', 'resource': '*', 'effect': 'deny'},
            {'action': 'skill.use', 'resource': '*', 'effect': 'deny'},
            {'action': 'plugin.use', 'resource': '*', 'effect': 'deny'},
            {'action': 'provider.use', 'resource': '*', 'effect': 'deny'},
            {'action': 'provider.use', 'resource': 'opencode', 'effect': 'allow'},
        ],
    }
    (workspace / 'opencode.json').write_text(json.dumps(config, indent=2) + '\n')
    agent = """---
description: Model-only isolation preflight
mode: primary
hidden: true
steps: 1
permissions:
  - action: "*"
    resource: "*"
    effect: deny
---
Return plain text. Do not call tools.
"""
    (workspace / '.opencode' / 'agents' / 'ads-e2e-model.md').write_text(agent)
    result = subprocess.run(
        [executable, '--standalone', '--pure', 'debug', 'config'],
        cwd=workspace, env=env, capture_output=True, text=True, timeout=45,
    )
    if result.returncode != 0:
        lines = (result.stderr or result.stdout).strip().splitlines()
        detail = lines[-1][:180] if lines else 'no CLI diagnostic'
        detail = detail.replace(str(workspace), '<isolated-workspace>')
        raise ValueError(f'OpenCode real CLI config preflight failed (exit={result.returncode}; {detail})')
    start = result.stdout.find('{')
    if start < 0:
        raise ValueError('OpenCode debug config did not return JSON')
    try:
        resolved, _ = json.JSONDecoder().raw_decode(result.stdout[start:])
    except json.JSONDecodeError as exc:
        raise ValueError('OpenCode debug config returned invalid JSON') from exc
    if not isinstance(resolved, dict):
        raise ValueError('OpenCode resolved config has an invalid shape')
    if resolved.get('plugins') != []:
        raise ValueError('OpenCode effective config contains external plugins')
    if resolved.get('mcp') != {}:
        raise ValueError('OpenCode effective config contains MCP servers')
    policies = resolved.get('policies')
    if not isinstance(policies, list):
        raise ValueError('OpenCode effective policies are unavailable')
    actions = ('tool.use', 'mcp.use', 'skill.use', 'plugin.use')
    for action in actions:
        deny_index = max((i for i, rule in enumerate(policies)
                          if rule.get('action') == action and rule.get('resource') == '*'
                          and rule.get('effect') == 'deny'), default=-1)
        if deny_index < 0 or any(rule.get('action') == action and rule.get('effect') == 'allow'
                                 for rule in policies[deny_index + 1:]):
            raise ValueError(f'OpenCode effective policy does not enforce final deny for {action}')
    return {
        'status': 'PASS',
        'plugins': 'EMPTY',
        'mcp': 'EMPTY',
        'tool_policies': 'FINAL_DENY',
        'skill_policies': 'FINAL_DENY',
        'plugin_policies': 'FINAL_DENY',
        'mode': 'STANDALONE_PURE',
        'model_execution': 'NOT_RUN',
    }


def probe(executable, out):
    out.mkdir(parents=True, exist_ok=False)
    workspace = out / 'workspace'
    workspace.mkdir()
    packages = ROOT / 'poc/e2e/node_modules'
    if not (packages / 'e2e/package.json').is_file():
        raise ValueError('需要先 npm ci 安装已固定的 e2e')
    (workspace / 'node_modules').symlink_to(packages, target_is_directory=True)
    (workspace / 'e2e.config.ts').write_text("export default {targets:[{name:'tools',platform:'tools'}]};\n")
    e2e(workspace)
    subprocess.run(['git','init','-q',str(workspace)],check=True,capture_output=True)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        port = sock.getsockname()[1]
    # 不读取宿主已有模型凭据或启动全局会话。
    env = {k:v for k,v in os.environ.items() if k in ('PATH','LANG','HTTP_PROXY','HTTPS_PROXY','NO_PROXY','http_proxy','https_proxy','no_proxy')}
    for key, name in (('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data'),('XDG_CACHE_HOME','cache'),('XDG_STATE_HOME','state')):
        env[key] = str(out / 'private' / name)
    runtime_isolation = runtime_isolation_probe(executable, out, env)
    log = out / 'native-private.log'
    with log.open('w') as stream:
        process = subprocess.Popen([executable,'serve','--hostname','127.0.0.1','--port',str(port)],
                                   cwd=workspace,env=env,stdout=stream,stderr=stream)
        try:
            password = None
            for _ in range(200):
                password = next((l.removeprefix('server password ') for l in log.read_text().splitlines() if l.startswith('server password ')),None)
                if password or process.poll() is not None:
                    break
                time.sleep(.1)
            if not password:
                raise ValueError('原生服务未就绪；不公开含临时凭据的日志')
            opener = build_opener(ProxyHandler({}))
            headers = {'Authorization':'Basic '+base64.b64encode(('opencode:'+password).encode()).decode(),'Content-Type':'application/json'}
            def request(path, body=None):
                req = Request(f'http://127.0.0.1:{port}'+path,headers=headers,data=None if body is None else json.dumps(body).encode())
                with opener.open(req,timeout=45) as response:
                    raw = response.read()
                    return json.loads(raw) if raw else None
            session = request('/api/session',{'title':'ADS upstream e2e no-model smoke','location':{'directory':str(workspace)}})['data']
            servers, skills = [], []
            for _ in range(160):
                servers = request('/api/mcp')['data']
                skills = request('/api/skill')['data']
                connected = any(s.get('name') == 'e2e' and s.get('status',{}).get('status') == 'connected' for s in servers)
                if connected and any(s['id'] == 'e2e' for s in skills):
                    break
                time.sleep(.25)
            else:
                raise ValueError('原生 MCP 未连接或上游技能未发现')
            request('/api/experimental/session/'+session['id']+'/skill',{'id':'e2e','resume':False})
            messages = request('/api/session/'+session['id']+'/message')['data']
            if not messages:
                raise ValueError('技能未实际激活')
            version = subprocess.check_output([executable,'--version'],env=env).decode().strip()
            return {'status':'PASS','opencode_version':version,'runtime_isolation':runtime_isolation,'mcp':'CONNECTED',
                    'skill':'e2e','activation':'OBSERVED','activation_message_count':len(messages),
                    'model_execution':'NOT_RUN','scope':'native transport and explicit skill activation; not autonomous model use'}
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--executable',required=True)
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    try:
        result = probe(str(Path(args.executable).resolve()),args.out.resolve())
    except Exception as exc:
        result = {'status':'BLOCKED','error_type':type(exc).__name__,'reason':str(exc)[:200]}
    write_json(args.out.resolve() / 'native-summary.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    sys.exit(0 if result['status'] == 'PASS' else 3)
