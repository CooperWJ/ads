"""来源全量枚举，复用现有/上游解析器，部分读取与语义完整性分别报告。"""
from discovery.sources import md_units, svg_units, xlsx_units
from .source_adapters import pdf_units, json_units
from .project import path_in, digest


def discover(project):
    sources, unknown = [], []
    decoders = {'.md': md_units, '.svg': svg_units, '.xlsx': xlsx_units,
                '.pdf': pdf_units, '.json': json_units}
    for name in project.config.get('source_dirs', []):
        root = path_in(project.root, name, exists=True)
        inventory, units, extracted = [], [], []
        unread = []
        for path in sorted(root.rglob('*')):
            label = str(path.relative_to(project.root))
            if path.is_symlink():
                unread.append({'path': label, 'reason': 'SYMLINK'})
                continue
            if not path.is_file():
                continue
            if path.stat().st_size > 10*1024*1024:
                inventory.append({'path': label, 'sha256': None, 'reason': 'OVERSIZED'})
                unread.append({'path': label, 'reason': 'OVERSIZED'})
                continue
            data = path.read_bytes()
            inventory.append({'path': label, 'sha256': digest(data)})
            try:
                decoder = decoders.get(path.suffix.lower())
                if decoder is None:
                    raise ValueError('UNSUPPORTED_FORMAT')
                found, meta = decoder(label, data)
                units.extend(found)
                extracted.append({'path': label, 'units': len(found), 'meta': meta})
                for reason in meta.get('unknown', []):
                    unread.append({'path': label, 'reason': reason})
            except Exception as exc:
                unread.append({'path': label, 'reason': str(exc)[:200]})
        sources.append({'root': name, 'inventory': inventory, 'extraction': {'units': units, 'files': extracted}})
        if unread or not inventory:
            unknown.append({'root': name, 'reason': 'PARTIAL_OR_EMPTY_SOURCE', 'inventory': inventory, 'unread': unread})
    return {'schema': 'ads-project-discovery/v1', 'status': 'INVENTORIED' if sources and not unknown else 'UNKNOWN',
            'sources': sources, 'unknown': unknown, 'semantic_completeness': 'NOT_VERIFIED'}
