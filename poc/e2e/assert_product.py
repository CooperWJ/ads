"""冻结虚构案例的外部数据断言；不导入应用代码。"""
import io
import json
import sqlite3
import sys
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

db_path, export_path = map(Path, sys.argv[1:])
with sqlite3.connect(f'file:{db_path}?mode=ro', uri=True) as db:
    persisted = db.execute('SELECT notes FROM projects WHERE id=1').fetchone()[0]
assert persisted == 'Reviewed in M0', 'HTTP 显示保存成功，但 SQLite 未持久化'
with ZipFile(io.BytesIO(export_path.read_bytes())) as archive:
    assert archive.testzip() is None
    root = ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
ns = {'x': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
rows = [[cell.findtext('x:is/x:t', default='', namespaces=ns) for cell in row.findall('x:c', ns)]
        for row in root.findall('.//x:sheetData/x:row', ns)]
assert rows[0] == ['title','category','phase','owner','milestone_start','milestone_end','reference_code','notes'], '导出缺列或列序错误'
assert rows[1] == ['Project Echo','Research','Planning','Mira','2026-01-12','2026-07-18','DEMO-E01','Reviewed in M0'], '导出内容不符'
print(json.dumps({'persisted': persisted, 'exported': rows[1][-1]}))
