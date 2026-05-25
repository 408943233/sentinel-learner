"""
Layer 2: 因果链三元组提取器

从 training_manifest.jsonl 中提取因果三元组：
    {action: 用户操作, api_call: 触发的API, dom_change: DOM变化}

基于 lineage 链、network.requests 和 domSnapshotRelation 字段。
不需要 LLM，纯程序化处理。
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


@dataclass
class CausalTriple:
    """因果三元组"""
    event_id: str
    event_type: str           # click, input, keydown, page-load-start, etc.
    description: str           # 事件描述
    timestamp: int
    url: str
    # API 请求
    api_calls: List[Dict] = field(default_factory=list)
    # DOM 状态
    dom_snapshot: Optional[str] = None        # 关联的 DOM 快照文件名
    dom_relation: Optional[str] = None        # "effect" 或 "context"
    # 因果关系
    previous_event_id: Optional[str] = None
    next_event_id: Optional[str] = None

@dataclass
class PageNavigation:
    """页面导航记录"""
    from_url: str
    to_url: str
    trigger_event_id: str
    trigger_type: str

@dataclass
class TaskCausalGraph:
    """任务级别的因果图"""
    task_id: str
    triples: List[CausalTriple]
    navigations: List[PageNavigation]
    pages: Dict[str, List[str]]  # url -> 属于该页面的 event_id 列表


class CausalExtractor:
    """因果三元组提取器"""

    def __init__(self, task_path: Path):
        self.task_path = Path(task_path)
        self.manifest_path = self.task_path / 'training_manifest.jsonl'

    def extract(self) -> TaskCausalGraph:
        """提取完整因果图"""
        events = self._load_manifest()
        triples = []
        navigations = []
        pages = {}
        current_page_url = None
        _route_seen = False

        for event in events:
            triple = self._event_to_triple(event)

            # 追踪页面归属
            evt_type = event.get('type', '')
            if evt_type in ('page-load-start', 'page-load-complete'):
                url = event.get('url', '')
                if url:
                    current_page_url = url
            elif evt_type == 'route-change':
                to_url = event.get('to') or event.get('url', '')
                if to_url:
                    _route_seen = True
                    current_page_url = to_url
                    navigations.append(PageNavigation(
                        from_url=event.get('from', ''),
                        to_url=to_url,
                        trigger_event_id=event.get('eventId', ''),
                        trigger_type=event.get('triggerSource', event.get('source', 'spa-route'))
                    ))

            if event.get('type') == 'page-load-start' and current_page_url:
                prev = event.get('lineage', {}).get('previous_event_id')
                if prev and current_page_url:
                    pass

            if current_page_url:
                if current_page_url not in pages:
                    pages[current_page_url] = []
                pages[current_page_url].append(triple.event_id)

            self._collect_api_calls(event, triple)

            self._collect_dom_info(event, triple)

            triples.append(triple)

            if evt_type == 'page-load-start':
                if _route_seen:
                    _route_seen = False
                else:
                    prev_events = [t for t in triples if t.next_event_id == event.get('eventId')]
                    if prev_events:
                        prev = prev_events[-1]
                        navigations.append(PageNavigation(
                            from_url=prev.url or '',
                            to_url=event.get('url', ''),
                            trigger_event_id=prev.event_id,
                            trigger_type=prev.event_type
                        ))

        return TaskCausalGraph(
            task_id=self.task_path.name,
            triples=triples,
            navigations=navigations,
            pages=pages
        )

    def _load_manifest(self) -> List[Dict]:
        """加载 manifest"""
        if not self.manifest_path.exists():
            return []
        lines = self.manifest_path.read_text(encoding='utf-8').strip().split('\n')
        return [json.loads(line) for line in lines if line.strip()]

    def _event_to_triple(self, event: Dict) -> CausalTriple:
        """将一个事件转换为因果三元组"""
        meta = event.get('metadata', {})
        lineage = event.get('lineage', {})

        return CausalTriple(
            event_id=event.get('eventId', ''),
            event_type=event.get('type', ''),
            description=meta.get('description', ''),
            timestamp=event.get('timestamp', 0),
            url=event.get('url', ''),
            previous_event_id=lineage.get('previous_event_id'),
            next_event_id=lineage.get('next_event_id'),
        )

    def _collect_api_calls(self, event: Dict, triple: CausalTriple):
        """收集事件关联的 API 调用"""
        # 从 network.requests 字段
        requests = event.get('network', {}).get('requests', [])
        for req in requests:
            triple.api_calls.append({
                'request_id': req.get('requestId', ''),
                'type': req.get('type', ''),
                'method': req.get('method', ''),
                'url': req.get('url', ''),
                'status': req.get('status', 0),
                'response_summary': self._summarize_response(req.get('responseBody'))
            })

    def _summarize_response(self, response: Any) -> str:
        """摘要 API 响应"""
        if not response:
            return ''
        if isinstance(response, dict):
            # 提取关键字段
            data = response.get('data', response.get('result', response))
            if isinstance(data, list) and len(data) > 0:
                first = data[0]
                if isinstance(first, dict):
                    keys = list(first.keys())[:5]
                    return f'Array[{len(data)}] fields: {", ".join(keys)}'
                return f'Array[{len(data)}]'
            if isinstance(data, dict):
                keys = list(data.keys())[:5]
                return f'Object fields: {", ".join(keys)}'
            return str(type(data).__name__)
        if isinstance(response, str):
            return response[:100]
        return str(type(response).__name__)

    def _collect_dom_info(self, event: Dict, triple: CausalTriple):
        """收集 DOM 关联信息"""
        meta = event.get('metadata', {})
        triple.dom_snapshot = meta.get('domSnapshotFileName')
        triple.dom_relation = meta.get('domSnapshotRelation')

    def get_action_summary(self) -> Dict[str, Any]:
        """生成操作摘要，用于喂给 LLM"""
        graph = self.extract()

        summaries = []
        for triple in graph.triples:
            if triple.event_type in ('user_context', 'error', 'scroll', 'route-change'):
                continue

            summary = {
                'action': triple.description,
                'type': triple.event_type,
                'url': triple.url,
            }

            if triple.api_calls:
                summary['api_calls'] = [
                    {
                        'url': api['url'].split('/')[-1] if '/' in api['url'] else api['url'],
                        'method': api['method'],
                        'response': api['response_summary'],
                        'full_url': api['url'],
                    }
                    for api in triple.api_calls
                ]

            if triple.dom_snapshot:
                summary['dom_snapshot'] = triple.dom_snapshot
                summary['dom_relation'] = triple.dom_relation

            summaries.append(summary)

        return {
            'task_id': graph.task_id,
            'total_events': len(graph.triples),
            'pages': {url: len(events) for url, events in graph.pages.items()},
            'navigations': [
                {'from': n.from_url, 'to': n.to_url, 'trigger': n.trigger_type}
                for n in graph.navigations
            ],
            'actions': summaries,
        }

    def extract_anchor_events(self) -> Dict[str, Any]:
        """提取锚点事件，用于时间对齐"""
        events = self._load_manifest()
        anchors = []
        seen_urls = set()

        anchor_types = {
            'page-load-start', 'page-load-complete', 'route-change',
            'click', 'submit', 'file_io'
        }

        for evt in events:
            evt_type = evt.get('type', '')
            if evt_type not in anchor_types:
                continue

            url = evt.get('url', '') or evt.get('to', '')
            ts = evt.get('timestamp', 0)
            event_id = evt.get('eventId', '')

            has_api = bool(evt.get('network', {}).get('requests', []))

            is_significant = (
                evt_type in ('page-load-start', 'page-load-complete') or
                (evt_type == 'click' and has_api) or
                evt_type == 'route-change'
            )

            url_key = f"{url}|{evt_type}"
            if url_key in seen_urls and not is_significant:
                continue

            anchor = {
                'event_id': event_id,
                'timestamp': ts,
                'event_type': evt_type,
                'url': url[:200] if url else '',
                'source': 'manifest',
                'confidence': 0.95 if is_significant else 0.7,
                'description': f"{evt_type}: {url[:80] if url else 'unknown'}"
            }

            meta = evt.get('metadata', {})
            if meta.get('description'):
                anchor['description'] = meta['description'][:100]

            anchors.append(anchor)

            if is_significant:
                seen_urls.add(url_key)

        first_event = events[0] if events else {}
        last_event = events[-1] if events else {}

        return {
            'anchor_points': anchors,
            'total_anchors': len(anchors),
            'time_range': {
                'start_timestamp': first_event.get('timestamp', 0),
                'end_timestamp': last_event.get('timestamp', 0),
                'start_url': first_event.get('url', ''),
                'end_url': last_event.get('url', '')
            }
        }
