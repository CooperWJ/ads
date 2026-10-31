"""现有评分器的 Docker 服务适配器：候选不获得评分器/参考解/宿主根目录。"""
import argparse
from contextlib import contextmanager
from functools import partial
import json
import os
from pathlib import Path
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from evaluator import grade as G


def docker(*args, timeout=120):
    return subprocess.run(['docker', *args], check=True, text=True, capture_output=True, timeout=timeout)


@contextmanager
def service(workdir, outdir, *, image):
    if not re.fullmatch(r'[a-zA-Z0-9./:_-]+@sha256:[0-9a-f]{64}', image):
        raise ValueError('需要固定镜像 digest')
    if not shutil.which('docker'):
        raise RuntimeError('Docker 不可用，不能退回宿主进程执行')
    workdir, outdir = Path(workdir), Path(outdir)
    name = 'ads-slice-' + uuid.uuid4().hex[:12]
    network = name + '-net'
    built = network_created = False
    proc = None
    with tempfile.TemporaryDirectory(prefix='ads-slice-image-') as temporary:
        context = Path(temporary)
        for file in G.ALLOWED_PATHS:
            target = context / file
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(workdir / file, target)
        (context / 'launcher.py').write_text('''import app
from http.server import ThreadingHTTPServer
with app.database():
    pass
ThreadingHTTPServer(('0.0.0.0', 8000), app.Handler).serve_forever()
''')
        (context / 'Dockerfile').write_text(f'FROM {image}\nWORKDIR /work\nCOPY . /work/\nCMD ["python", "-B", "launcher.py"]\n')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        db = workdir / 'runtime.sqlite'
        # 只挂载一个空数据库文件，候选不能用替换目录项让宿主跟随任意符号链接。
        sqlite3.connect(db).close()
        try:
            docker('build', '--network', 'none', '-t', name, str(context))
            built = True
            docker('network', 'create', '--internal', network)
            network_created = True
            with (outdir / 'app.log').open('w') as log:
                command = ['docker', 'run', '--name', name, '--network', network,
                           '--publish', f'127.0.0.1:{port}:8000', '--read-only',
                           '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                           '--pids-limit', '128', '--memory', '512m', '--cpus', '1',
                           '--user', f'{os.getuid()}:{os.getgid()}',
                           '--tmpfs', '/tmp:rw,nosuid,noexec,size=64m',
                           '--tmpfs', '/data:rw,nosuid,noexec,size=64m,mode=1777',
                           '--mount', f'type=bind,src={db.resolve()},dst=/data/runtime.sqlite',
                           '--env', 'ADS_DB_PATH=/data/runtime.sqlite', name]
                proc = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, text=True)
                base = f'http://127.0.0.1:{port}'
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    if proc.poll() is not None:
                        raise RuntimeError('候选容器提前退出；参见 app.log')
                    try:
                        status, data, _ = G.http(base, '/health')
                        if status == 200 and json.loads(data).get('ok') is True:
                            break
                    except Exception:
                        pass
                    time.sleep(.05)
                else:
                    raise RuntimeError('容器服务启动超时')
                inspected = json.loads(docker('inspect', name).stdout)[0]
                network_info = json.loads(docker('network', 'inspect', network).stdout)[0]
                host = inspected['HostConfig']
                mounts = inspected['Mounts']
                valid = (host['ReadonlyRootfs'] is True and network_info['Internal'] is True
                         and 'ALL' in host['CapDrop']
                         and any(x.startswith('no-new-privileges') for x in host['SecurityOpt'])
                         and len(mounts) == 1 and mounts[0]['Destination'] == '/data/runtime.sqlite'
                         and Path(mounts[0]['Source']).resolve() == db.resolve())
                if not valid:
                    raise RuntimeError('实际容器配置不符合最小隔离边界')
                (outdir / 'runtime-isolation.json').write_text(json.dumps({
                    'read_only_root': True, 'internal_network': True, 'cap_drop_all': True,
                    'no_new_privileges': True, 'mounted_scope': 'one disposable database file',
                    'candidate_image_id': inspected['Image'], 'memory_bytes': host['Memory'],
                    'nano_cpus': host['NanoCpus'], 'pids_limit': host['PidsLimit'],
                }, indent=2))
                yield base
        finally:
            subprocess.run(['docker', 'rm', '-f', name], capture_output=True, timeout=30)
            if proc is not None:
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
            if network_created:
                subprocess.run(['docker', 'network', 'rm', network], capture_output=True, timeout=30)
            if built:
                subprocess.run(['docker', 'image', 'rm', name], capture_output=True, timeout=30)


def evaluate(candidate, image, out, profile='full'):
    if candidate == 'empty':
        patch = None
    elif candidate.endswith('.patch'):
        patch = Path(candidate).resolve()
    elif candidate in ('reference_m1', 'm1_missing_menu', 'm1_silent_error'):
        patch = G.CASE / 'patches' / f'{candidate}.patch'
    else:
        raise ValueError('未知候选')
    report = G.evaluate(patch, profile, 'pass', 'current', out, m1_enabled=True,
                        service_factory=partial(service, image=image))
    report['execution_mode'] = 'candidate service in constrained Docker; evaluator and browser outside candidate'
    report['runtime_image'] = image
    report['qa_scope'] = 'synthetic calibration only; independent QA NOT_IMPLEMENTED'
    report['protected_ci'] = 'NOT_VERIFIED'
    (Path(out) / 'grade.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--image', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--profile', choices=('backend', 'integration', 'full'), default='full')
    args = parser.parse_args()
    try:
        report = evaluate(args.candidate, args.image, args.out, args.profile)
    except Exception as exc:
        report = {'status': 'INFRA_ERROR', 'error_type': type(exc).__name__}
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / 'grade.json').write_text(json.dumps(report))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report['status'] == 'PASS':
        return 0 if report['delivery_verdict']['status'] == 'PASS' else 2
    return 1 if report['status'] == 'FAIL' else 2


if __name__ == '__main__':
    sys.exit(main())
