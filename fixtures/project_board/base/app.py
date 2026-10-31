"""Synthetic project-board reference service. No production data or business logic."""
import argparse
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

HERE = Path(__file__).resolve().parent
FIELDS = ("title", "category", "phase", "owner", "milestone_start", "milestone_end", "reference_code")
COLUMN_NAMES = FIELDS + ("notes",)


def database():
    path = Path(os.environ.get("ADS_DB_PATH", str(HERE / "runtime.sqlite")))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY, title TEXT NOT NULL, category TEXT NOT NULL, phase TEXT NOT NULL, owner TEXT NOT NULL, milestone_start TEXT NOT NULL, milestone_end TEXT NOT NULL, reference_code TEXT NOT NULL, notes TEXT NOT NULL)")
    if db.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0:
        db.executemany("INSERT INTO projects VALUES (?,?,?,?,?,?,?,?,?)", [
            (1, 'Project Echo', 'Research', 'Planning', 'Mira', '2026-01-12', '2026-07-18', 'DEMO-E01', ''),
            (2, 'Project Delta', 'Operations', 'Testing', 'Jin', '2026-03-08', '2026-10-20', 'DEMO-D02', ''),
        ])
        db.commit()
    return db


def xlsx_bytes(record):
    """Small, genuine XLSX, built with stdlib to avoid optional runtime dependencies."""
    rows = [COLUMN_NAMES, tuple(str(record[key]) for key in COLUMN_NAMES)]
    cells = []
    for rowno, row in enumerate(rows, 1):
        for colno, val in enumerate(row):
            col = chr(ord('A') + colno)
            cells.append(f'<c r="{col}{rowno}" t="inlineStr"><is><t>{escape(str(val))}</t></is></c>')
    xml = '<?xml version="1.0" encoding="UTF-8"?>' + '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1">' + ''.join(cells[:len(COLUMN_NAMES)]) + '</row><row r="2">' + ''.join(cells[len(COLUMN_NAMES):]) + '</row></sheetData></worksheet>'
    buf = io.BytesIO()
    with ZipFile(buf, 'w', ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        z.writestr('_rels/.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml', '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Project" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr('xl/worksheets/sheet1.xml', xml)
    return buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def send(self, status, body, content_type='application/json', extra=None):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Cache-Control', 'no-store')
        if extra:
            for key, value in extra.items():
                self.send_header(key, value)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def json(self, status, payload):
        self.send(status, json.dumps(payload).encode())

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ('/', '/app.js'):
            target = HERE / 'web' / ('index.html' if path == '/' else 'app.js')
            self.send(200, target.read_bytes(), 'text/html; charset=utf-8' if path == '/' else 'application/javascript; charset=utf-8')
            return
        if path == '/health':
            self.json(200, {'ok': True})
            return
        if path == '/api/projects':
            with database() as db:
                self.json(200, [dict(r) for r in db.execute('SELECT id,title FROM projects ORDER BY id')])
            return
        parts = path.strip('/').split('/')
        if len(parts) >= 3 and parts[:2] == ['api', 'projects'] and parts[2].isdigit():
            with database() as db:
                row = db.execute('SELECT * FROM projects WHERE id=?', (int(parts[2]),)).fetchone()
            if row is None:
                self.json(404, {'error': 'not found'})
                return
            data = dict(row)
            if len(parts) == 3:
                self.json(200, {"id": data["id"]})  # Deliberately incomplete seed implementation
                return
            if len(parts) == 4 and parts[3] == 'export':
                self.send(200, xlsx_bytes(data), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', {'Content-Disposition': 'attachment; filename="project.xlsx"'})
                return
        self.json(404, {'error': 'not found'})

    def do_POST(self):
        parts = urlparse(self.path).path.strip('/').split('/')
        if len(parts) != 4 or parts[:2] != ['api', 'projects'] or not parts[2].isdigit() or parts[3] != 'notes':
            self.json(404, {'error': 'not found'})
            return
        if self.headers.get('X-Demo-Role', '') != 'editor':
            self.json(403, {'error': 'forbidden'})
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if size <= 0 or size > 4096:
                raise ValueError('invalid size')
            notes = json.loads(self.rfile.read(size))['notes']
            if not isinstance(notes, str) or len(notes) > 200:
                raise ValueError('invalid notes')
        except (ValueError, KeyError, json.JSONDecodeError):
            self.json(400, {'error': 'invalid payload'})
            return
        with database() as db:
            result = db.execute('UPDATE projects SET notes=? WHERE id=?', (notes, int(parts[2])))
            db.commit()
        if result.rowcount == 0:
            self.json(404, {'error': 'not found'})
            return
        self.json(200, {'saved': True, 'notes': notes})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    with database():
        pass
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print('READY ' + str(server.server_port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
