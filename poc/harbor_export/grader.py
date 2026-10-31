"""只读检查传入数据；不导入、不执行候选代码。复用现有 XLSX 契约。"""
import io
import json
from pathlib import Path
import sys
from zipfile import ZipFile

sys.path.insert(0, '/tests/ads')
from evaluator.grade import EXPECTED, FIELDS, read_xlsx


def grade(artifacts, run_id):
    artifact = artifacts / 'export.xlsx'
    if artifact.is_symlink() or not artifact.is_file() or artifact.stat().st_size > 2 * 1024 * 1024:
        raise ValueError('缺失、链接或过大 XLSX')
    data = artifact.read_bytes()
    with ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if len(entries) > 32 or sum(x.file_size for x in entries) > 4 * 1024 * 1024:
            raise ValueError('XLSX 解压边界超限')
    rows = read_xlsx(data)
    expected = [list(FIELDS) + ['notes'], [EXPECTED[k] for k in FIELDS] + ['Reviewed in M0']]
    if rows != expected:
        raise ValueError('导出列或持久化值不符合冻结契约')
    captured = json.loads((artifacts / 'capture.json').read_text())
    if captured != {'run_id': run_id, 'verifier_visible_before_attack': False}:
        raise ValueError('运行绑定或候选初始评分器隔离观测不符')


def main():
    # 每次覆盖，拒绝继承候选伪造的奖励文件。
    logs = Path('/logs/verifier')
    logs.mkdir(parents=True, exist_ok=True)
    passed = False
    error = None
    try:
        grade(Path('/logs/artifacts'), Path('/tests/challenge.txt').read_text().strip())
        passed = True
    except Exception as exc:
        error = type(exc).__name__
    (logs / 'reward.txt').write_text('1' if passed else '0')
    (logs / 'boundary.json').write_text(json.dumps({
        'scope': 'isolated XLSX artifact calibration; not full delivery',
        'passed': passed, 'error_type': error,
        'run_id': Path('/tests/challenge.txt').read_text().strip(),
    }))
    return 0


if __name__ == '__main__':
    sys.exit(main())
