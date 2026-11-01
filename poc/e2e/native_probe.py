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
            return {'status':'PASS','opencode_version':version,'mcp':'CONNECTED',
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
