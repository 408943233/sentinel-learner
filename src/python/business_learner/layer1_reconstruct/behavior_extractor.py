"""
Layer 1 行为提取器

从 rrweb incremental 事件中提取 JS 驱动的 DOM 行为，
生成人类可读的 HTML 注释，供 LLM 理解页面交互行为。

提取的行为模式：
- Toast/通知消息的出现和消失 → 操作反馈
- 按钮样式状态变化 → loading/pressed 状态
- CSS 动画类切换 → 过渡效果
- 条件内容区显示/隐藏 → 状态切换
- 输入框校验反馈 → 表单行为
"""

import json
import re
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Optional, Any


class BehaviorExtractor:
    """DOM 行为提取器"""

    # 行为模式定义
    TOAST_PATTERNS = [
        'el-message', 'el-notification', 'toast', 'snackbar',
        'ant-message', 'ant-notification', 'MuiSnackbar-', 'MuiAlert-',
        'alert-success', 'alert-info', 'alert-warning', 'alert-danger',
        'v-snackbar', 'n-notification',
    ]
    LOADING_PATTERNS = [
        'loading', 'spinner', 'skeleton',
        'ant-spin', 'MuiCircularProgress', 'MuiLinearProgress',
        'v-progress', 'n-spin',
    ]
    ANIMATION_PATTERNS = [
        'fade', 'slide', 'transition', 'collapse', 'expand',
        'ant-motion', 'MuiCollapse', 'MuiFade', 'MuiGrow', 'MuiSlide', 'MuiZoom',
    ]
    VALIDATION_PATTERNS = [
        'error', 'warning', 'is-error', 'is-warning', 'is-invalid', 'el-form-item__error',
        'has-error', 'has-danger', 'Mui-error', 'ant-form-item-has-error',
        'v-messages__error', 'was-validated',
    ]

    @classmethod
    def extract_page_behaviors(cls, task_path: Path, page_event_id: str,
                                snapshot_file: str) -> Dict[str, Any]:
        """
        提取一个页面上的所有交互行为

        Args:
            task_path: task 目录路径
            page_event_id: 页面加载事件的 eventId (page-load-start 的 id)
            snapshot_file: FullSnapshot 文件名

        Returns:
            {
                'behaviors': [...],        # 行为描述列表
                'inline_annotations': {}   # {css_selector: "注释文本"}
            }
        """
        manifest_path = task_path / 'training_manifest.jsonl'
        dom_dir = task_path / 'dom'

        if not manifest_path.exists():
            return {'behaviors': [], 'inline_annotations': {}}

        # 加载 manifest
        lines = manifest_path.read_text(encoding='utf-8').strip().split('\n')
        events = [json.loads(line) for line in lines if line.strip()]

        # 找到该页面的 page-load-start 事件
        page_start = next((e for e in events if e.get('eventId') == page_event_id), None)
        if not page_start:
            return {'behaviors': [], 'inline_annotations': {}}

        page_start_ts = page_start.get('timestamp', 0)
        page_url = page_start.get('url', '')

        # 找到下一个 page-load-start 作为时间边界
        next_start = next(
            (e for e in events
             if e.get('type') == 'page-load-start' and e.get('timestamp', 0) > page_start_ts),
            None
        )
        page_end_ts = next_start.get('timestamp', float('inf')) if next_start else float('inf')

        # 收集该页面期间的用户交互事件
        page_interactions = [
            e for e in events
            if page_start_ts <= e.get('timestamp', 0) < page_end_ts
            and e.get('type') in ('click', 'input', 'keydown')
        ]

        behaviors = []
        inline_annotations = {}

        for evt in page_interactions:
            fn = (evt.get('metadata') or {}).get('domSnapshotFileName', '')
            if not fn:
                continue

            snap_path = dom_dir / fn
            if not snap_path.exists():
                continue

            with open(snap_path, 'r') as f:
                snap = json.load(f)

            rrweb = snap.get('rrwebEvent', {})
            if rrweb.get('type') != 3:
                continue

            evt_behaviors = cls._analyze_incremental(
                rrweb, evt, snapshot_file
            )
            behaviors.extend(evt_behaviors)

            # 收集 inline annotation targets
            if evt.get('type') == 'click':
                selector = (evt.get('userAction') or {}).get('selector', '')
                if selector and evt_behaviors:
                    descriptions = [b['description'] for b in evt_behaviors]
                    existing = inline_annotations.get(selector, [])
                    inline_annotations[selector] = list(set(existing + descriptions))

        # 压缩：合并同类行为
        merged = cls._merge_behaviors(behaviors)

        return {
            'behaviors': merged,
            'inline_annotations': inline_annotations
        }

    @classmethod
    def _analyze_incremental(cls, rrweb: Dict, event: Dict,
                              snapshot_file: str) -> List[Dict]:
        """分析单个 incremental snapshot"""
        data = rrweb.get('data', {})
        behaviors = []
        evt_desc = (event.get('metadata') or {}).get('description', event.get('type', ''))

        # 1. 检查新增元素 (adds)
        adds = data.get('adds', [])
        for add in adds:
            node = add.get('node', add)
            tag = node.get('tagName', '')
            attrs = node.get('attributes', {})
            css_class = attrs.get('class', '')
            text = (node.get('textContent') or '').strip()

            # Toast 通知
            if any(p in css_class for p in cls.TOAST_PATTERNS):
                toast_type = 'success' if 'success' in css_class else \
                             'error' if 'error' in css_class else \
                             'warning' if 'warning' in css_class else 'info'
                behaviors.append({
                    'type': 'toast',
                    'action': evt_desc,
                    'description': f'操作后弹出{toast_type}提示消息: "{text[:80]}"'
                })

            # 弹窗/对话框
            dialog_patterns = ['el-dialog', 'modal', 'dialog', 'ant-modal', 'MuiDialog',
                               'drawer', 'ant-drawer', 'MuiDrawer', 'overlay', 'backdrop', 'popup']
            if any(p in css_class.lower() for p in dialog_patterns):
                behaviors.append({
                    'type': 'modal',
                    'action': evt_desc,
                    'description': f'触发弹窗/对话框：{tag}.{css_class.replace(" ", ".")}'
                })

            # 下拉菜单/折叠面板
            if ('dropdown' in css_class.lower() or
                'collapse' in css_class.lower() or
                'menu' in css_class.lower()):
                behaviors.append({
                    'type': 'expand',
                    'action': evt_desc,
                    'description': f'展示下拉/展开区域：{tag}.{css_class.replace(" ", ".")}'
                })

            # loading 状态元素
            if any(p in css_class.lower() for p in cls.LOADING_PATTERNS):
                behaviors.append({
                    'type': 'loading',
                    'action': evt_desc,
                    'description': f'触发加载状态 (loading indicator 出现)'
                })

        # 2. 属性变化 (attributes)
        attrs_changes = data.get('attributes', [])
        for attr_change in attrs_changes:
            new_attrs = attr_change.get('attributes', {})
            new_class = new_attrs.get('class', '')
            new_style = new_attrs.get('style', '')

            # CSS 动画类切换
            for anim_pat in cls.ANIMATION_PATTERNS:
                if anim_pat in new_class.lower():
                    behaviors.append({
                        'type': 'animation',
                        'action': evt_desc,
                        'description': f'触发CSS过渡动画: {anim_pat} (class变化: {new_class[:60]})'
                    })
                    break

            # 按钮状态变化
            if 'el-button' in new_class or 'btn' in new_class.lower():
                if '--el-button-bg-color' in new_style or 'background' in new_style.lower():
                    behaviors.append({
                        'type': 'button_state',
                        'action': evt_desc,
                        'description': f'按钮进入激活/加载状态 (style变化)'
                    })

        # 3. 删除元素 (removes)
        removes = data.get('removes', [])
        if removes:
            behaviors.append({
                'type': 'dismiss',
                'action': evt_desc,
                'description': f'关闭/移除 {len(removes)} 个元素（可能是通知消失或面板折叠）'
            })

        return behaviors

    @classmethod
    def _merge_behaviors(cls, behaviors: List[Dict]) -> List[Dict]:
        """合并同类行为，去重"""
        seen = set()
        merged = []
        for b in behaviors:
            key = f"{b['type']}:{b['description']}"
            if key not in seen:
                seen.add(key)
                merged.append(b)
        return merged

    @classmethod
    def generate_behavior_html(cls, behaviors: List[Dict],
                                 inline_annotations: Dict[str, List[str]]) -> str:
        """生成行为注释 HTML 片段"""
        if not behaviors and not inline_annotations:
            return ''

        parts = []
        parts.append('\n<!-- ===== PAGE BEHAVIORS (extracted from user interactions) =====')

        for b in behaviors:
            parts.append(f"  [{b['action']}] → {b['description']}")

        if inline_annotations:
            parts.append('\n  Element-specific behaviors:')
            for selector, descriptions in inline_annotations.items():
                for d in descriptions:
                    parts.append(f'  {selector}: {d}')

        parts.append('=============================================================== -->\n')
        return '\n'.join(parts)
