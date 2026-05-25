"""
Layer 1: rrweb 全量快照反序列化器

将 rrweb type=2 FullSnapshot 格式反序列化为 HTML DOM 字符串。
不需要 LLM，纯程序化处理。

rrweb node types:
    0 = Document
    1 = DocumentType
    2 = Element
    3 = Text
    4 = CDATA
    5 = Comment
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Any


VOID_ELEMENTS = {
    'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
    'link', 'meta', 'param', 'source', 'track', 'wbr'
}

SCRIPT_ELEMENTS = {'script', 'style', 'pre', 'code', 'textarea'}


class RrwebDeserializer:
    """rrweb 全量快照 → HTML"""

    def __init__(self):
        self.nodes: List[Dict] = []
        self._node_map: Dict[int, Dict] = {}

    def deserialize_file(self, snapshot_path: Path) -> Optional[str]:
        """从文件反序列化"""
        if not snapshot_path.exists():
            return None
        with open(snapshot_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return self.deserialize(data)

    def deserialize(self, snapshot_data: Dict) -> Optional[str]:
        """反序列化单个快照数据"""
        rrweb_event = snapshot_data.get('rrwebEvent')
        if not rrweb_event or rrweb_event.get('type') != 2:
            return None

        self.nodes = rrweb_event['data'].get('nodes', [])
        self._node_map = {n['id']: n for n in self.nodes}

        root_id = rrweb_event['data']['node']['id']
        return self._serialize_node(root_id)

    def _serialize_node(self, node_id: int) -> str:
        """递归序列化单个节点"""
        node = self._node_map.get(node_id)
        if not node:
            return ''

        node_type = node.get('type')

        if node_type == 0:  # Document
            parts = []
            for child_id in node.get('childNodes', []):
                parts.append(self._serialize_node(child_id))
            return ''.join(parts)

        elif node_type == 1:  # DocumentType
            name = node.get('name', 'html')
            public_id = node.get('publicId', '')
            system_id = node.get('systemId', '')
            if public_id or system_id:
                return f'<!DOCTYPE {name} PUBLIC "{public_id}" "{system_id}">'
            return f'<!DOCTYPE {name}>'

        elif node_type == 2:  # Element
            tag_name = node.get('tagName', 'div')
            attrs = self._serialize_attributes(node.get('attributes', {}))
            tag_open = f'<{tag_name}{attrs}'

            is_void = tag_name.lower() in VOID_ELEMENTS
            if is_void:
                return f'{tag_open}>'

            parts = [f'{tag_open}>']

            for child_id in node.get('childNodes', []):
                child_html = self._serialize_node(child_id)
                if child_html:
                    parts.append(child_html)

            parts.append(f'</{tag_name}>')
            return ''.join(parts)

        elif node_type == 3:  # Text
            return self._escape_text(node.get('textContent', ''))

        elif node_type == 4:  # CDATA
            text = node.get('textContent', '')
            return f'<![CDATA[{text}]]>'

        elif node_type == 5:  # Comment
            text = node.get('textContent', '')
            return f'<!--{text}-->'

        return ''

    def _serialize_attributes(self, attributes: Dict[str, str]) -> str:
        """序列化属性字典"""
        if not attributes:
            return ''
        parts = []
        for key, value in attributes.items():
            if value is True:
                parts.append(f' {key}')
            elif isinstance(value, str):
                escaped = value.replace('&', '&amp;').replace('"', '&quot;').replace('<', '&lt;')
                parts.append(f' {key}="{escaped}"')
            elif isinstance(value, (int, float)):
                parts.append(f' {key}={value}')
        return ''.join(parts)

    def _escape_text(self, text: str) -> str:
        """转义文本内容"""
        if not text:
            return ''
        text = text.replace('&', '&amp;')
        text = text.replace('<', '&lt;')
        text = text.replace('>', '&gt;')
        return text
