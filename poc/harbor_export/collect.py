"""在候选容器内运行：只采集真实 HTTP 导出，不包含评分预期。"""
import json
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import Request, urlopen


def collect(root=Path('/app'), out=Path('/logs/artifacts')):
    out.mkdir(parents=True, exist_ok=True)
    # 不把评分器放进候选环境；此观测仅用于受控校准，非通用可信证明。
    had_verifier = Path('/tests/grader.py').exists()
    proc = subprocess.Popen([sys.executable, 'app.py', '--port', '8123'], cwd=root,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            if proc.poll() is not None:
                raise RuntimeError('候选服务提前退出')
            try:
                with urlopen('http://127.0.0.1:8123/health', timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(.05)
        else:
            raise RuntimeError('候选服务启动超时')
        req = Request('http://127.0.0.1:8123/api/projects/1/notes',
                      data=json.dumps({'notes': 'Reviewed in M0'}).encode(), method='POST',
                      headers={'Content-Type': 'application/json', 'X-Demo-Role': 'editor'})
        with urlopen(req, timeout=3) as response:
            if response.status != 200:
                raise RuntimeError('保存失败')
        with urlopen('http://127.0.0.1:8123/api/projects/1/export', timeout=3) as response:
            data = response.read(2 * 1024 * 1024 + 1)
        if len(data) > 2 * 1024 * 1024:
            raise ValueError('导出过大')
        (out / 'export.xlsx').write_bytes(data)
        (out / 'capture.json').write_text(json.dumps({
            'run_id': (root / 'challenge.txt').read_text().strip(),
            'verifier_visible_before_attack': had_verifier,
        }))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)


if __name__ == '__main__':
    collect()
