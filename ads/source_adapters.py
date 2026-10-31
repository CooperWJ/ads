"""复用 PDF 解析器和上游结构化导出；只提取观察，不批准业务预期。"""
from io import BytesIO
import json

from discovery.sources import item
from .project import require


def pdf_units(name, data):
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ValueError('PDF 文本提取需要可选依赖 pypdf==6.10.0；图像页需独立 OCR/视觉复核') from exc
    reader = PdfReader(BytesIO(data))
    require(not reader.is_encrypted, '加密 PDF 不可静默跳过')
    require(0 < len(reader.pages) <= 200, 'PDF 页数缺失或超限')
    units, unknown = [], []
    for number, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ''
        if not text.strip():
            unknown.append(f'page:{number}:NO_TEXT_LAYER')
        for line_number, line in enumerate(text.splitlines(), 1):
            if line.strip():
                units.append(item(name, f'page:{number}/line:{line_number}', 'pdf_text', line.strip()))
    attachments = list(reader.attachments)
    if attachments:
        unknown.append('EMBEDDED_ATTACHMENTS_REQUIRE_SEPARATE_REVIEW')
    return units, {'pages': len(reader.pages), 'attachments': attachments, 'unknown': unknown,
                   'scope': 'text layer only; reading order, graphics and OCR not verified'}


def json_units(name, data):
    document = json.loads(data)
    units, unknown = [], []
    if document.get('schema_name') == 'DoclingDocument':
        for number, node in enumerate(document.get('texts', [])):
            text = node.get('text', '').strip()
            if text:
                units.append(item(name, f'texts/{number}', 'docling_text', text, provenance=node.get('prov', [])))
        for table_number, table in enumerate(document.get('tables', [])):
            grid = table.get('data', {}).get('grid', [])
            for row_number, row in enumerate(grid):
                for column, cell in enumerate(row):
                    text = cell.get('text', '').strip()
                    if text:
                        units.append(item(name, f'tables/{table_number}/{row_number}/{column}', 'docling_cell', text))
        if document.get('pictures'):
            unknown.append('PICTURES_REQUIRE_VISUAL_REVIEW')
        meta = {'format': 'DoclingDocument', 'pages': len(document.get('pages', {})),
                'tables': len(document.get('tables', [])), 'unknown': unknown}
    elif isinstance(document.get('document'), dict) and document['document'].get('type') == 'DOCUMENT':
        nodes = []
        def visit(node, route):
            require(isinstance(node, dict) and isinstance(node.get('id'), str), 'Figma 节点身份缺失')
            nodes.append({'id': node['id'], 'type': node.get('type'), 'visible': node.get('visible', True)})
            if node.get('type') == 'TEXT':
                text = node.get('characters')
                require(isinstance(text, str) and bool(text.strip()), 'Figma 文本节点内容缺失')
                units.append(item(name, route, 'figma_text', text, node_id=node['id'], visible=node.get('visible', True)))
            for index, child in enumerate(node.get('children', [])):
                visit(child, f'{route}/children/{index}')
        visit(document['document'], 'document')
        meta = {'format': 'FigmaFileExport', 'nodes': nodes, 'unknown': [],
                'scope': 'exported node/text inventory; visual meaning and dynamic behavior not verified'}
    else:
        raise ValueError('未知 JSON 来源格式，需要明确 Adapter，不猜测为空')
    require(bool(units) or bool(unknown), '结构化来源没有可读片段')
    return units, meta
