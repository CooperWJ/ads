"""配置官方 OpenCode 插件；不复制上游 skills 或建立第二套执行器。"""
import json

from .project import path_in, require, write_json

SUPERPOWERS_COMMIT = '2ce8aa15d05bd57213e6f746f953aafb7ded7a8b'
SUPERPOWERS_PLUGIN = 'superpowers@git+https://github.com/obra/superpowers.git#' + SUPERPOWERS_COMMIT


def superpowers(root):
    target = path_in(root, 'opencode.json')
    require(not path_in(root, 'opencode.jsonc').exists(),
            '已有 opencode.jsonc，请在原配置的 plugins 中加入官方 Superpowers 插件；不生成竞争配置')
    config = json.loads(target.read_text()) if target.exists() else {}
    require(isinstance(config, dict), 'OpenCode 配置必须为对象')
    require('plugin' not in config, '检测到 V1 plugin 配置；请按官方说明迁移到 V2 plugins，保留原有插件')
    plugins = config.get('plugins', [])
    require(isinstance(plugins, list) and all(isinstance(p, str) for p in plugins), 'plugins 必须为字符串数组')
    existing = [p for p in plugins if p.startswith('superpowers@') or p.rstrip('/').endswith('/superpowers')]
    if not existing:
        config['plugins'] = [*plugins, SUPERPOWERS_PLUGIN]
        write_json(target, config)
    return {'status': 'CONFIGURED', 'plugin': existing[0] if existing else SUPERPOWERS_PLUGIN,
            'configuration': 'opencode.json', 'host': 'OpenCode V2 >= 2.0.4',
            'runtime': 'NOT_VERIFIED',
            'next': '重启 OpenCode，使用原生 skill 工具加载技能；配置存在不证明运行成功'}
