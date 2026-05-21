"""
Layer 3: LLM 系统理解器

基于 Layer 1（准确页面）和 Layer 2（因果链）的输出，
让 LLM 理解目标系统，产出 PM 级别的系统认知。
"""

import json
import os
import requests
from pathlib import Path
from typing import Dict, List, Optional, Any


SYSTEM_ANALYSIS_PROMPT = """你是一名资深产品经理，目标是做产品迭代设计。下面是一个网站系统的完整数据。

## 页面列表
{pages_summary}

## 用户操作与 API 调用链（因果链）
{causal_chain}

{design_preview}

## 要求
请从产品经理迭代设计的视角，分析这个系统。输出 JSON：

{{
  "system_name": "系统名称",
  "functional_modules": [{{"name": "模块名", "purpose": "用途", "pages": ["所属页面URL"]}}],
  "data_flows": [{{"api": "API路径", "purpose": "用途", "data_fields": ["关键字段"], "renders_to": "渲染到的页面区域"}}],
  "user_paths": [{{"name": "路径名", "steps": ["步骤描述序列"]}}],
  "navigation_graph": [{{"from": "源页面", "to": "目标页面", "trigger": "触发条件"}}],
  "data_entities": [{{"name": "实体名", "fields": ["关键字段"], "related_apis": ["相关API"]}}],
  "design_system": {{"colors": ["品牌色列表"], "fonts": ["字体族"], "component_framework": "检测到的 UI 框架", "icon_style": "图标风格描述"}},
  "interaction_patterns": [{{"name": "模式名", "description": "描述", "occurs_in": ["页面URL"], "states": ["状态列表"]}}],
  "user_roles": [{{"name": "角色名", "visible_pages": ["可见页面"], "typical_flow": "典型操作流程"}}],
  "api_contracts": [{{"path": "API模式路径", "method": "GET/POST", "params": {{"param": "说明"}}, "response_type": "分页列表/单对象/无", "auth_required": true}}],
  "tech_stack": {{"frontend": "推断的前端框架", "ui_library": "UI 组件库", "third_party": ["第三方集成"]}},
  "optimization_opportunities": [{{"area": "优化域", "current_issue": "当前问题", "suggestion": "改进建议", "priority": "高/中/低", "effort": "预估工作量"}}],
  "user_intents": [{{"action_type": "操作类型(click/input/navigate/search等)", "target_element": "操作目标元素描述", "description": "意图描述，如'用户想查看邮件详情'", "confidence": 0.9, "url": "所在页面URL"}}],
  "business_flows": [{{"flow_id": "流程ID", "name": "流程名称", "description": "流程描述", "start_url": "起始页面", "end_url": "结束页面", "steps": [{{"step_number": 1, "action": "操作描述", "url": "页面URL", "expected_result": "预期结果"}}]}}]
}}

只输出 JSON，不要任何解释。"""

SYSTEM_DESIGN_PROMPT = """你是一个网站系统的设计系统分析专家。根据下面的 CSS 规则摘要，提取设计 Token。

## CSS 摘要
{css_summary}

## 要求
提取以下内容并以 JSON 输出：
{{
  "colors": {{"primary": "主色hex", "secondary": "辅色列表", "text": "正文色", "background": "背景色列表", "accent": "强调色"}},
  "typography": {{"heading_font": "标题字体", "body_font": "正文字体", "sizes": {{"h1": "px", "h2": "px", "body": "px", "small": "px"}}, "weights": ["使用的字重"]}},
  "spacing": {{"unit": "基础间距单位", "common_values": ["常用间距值"]}},
  "border_radius": ["常用圆角值"],
  "shadows": ["常用阴影"],
  "breakpoints": [{{"name": "断点名", "min_width": "px", "max_width": "px"}}]
}}

只输出 JSON。"""


class SystemAnalyzer:
    """LLM 系统分析器"""

    def __init__(self, llm_api_key: Optional[str] = None,
                 api_base: str = "https://api.deepseek.com/v1",
                 model: str = "deepseek-chat"):
        self.api_key = llm_api_key or os.environ.get('LLM_API_KEY', '')
        self.api_base = api_base
        self.model = model

    def _call_llm(self, prompt: str, system_prompt: str = "") -> str:
        if not self.api_key:
            raise SystemExit("❌ SystemAnalyzer: 未配置 LLM_API_KEY，无法调用 LLM")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 8000,
            "temperature": 0.3
        }

        try:
            response = requests.post(
                f"{self.api_base}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120
            )
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            else:
                print(f"  ❌ API error: {response.status_code}")
                return None
        except Exception as e:
            print(f"  ❌ Request error: {e}")
            return None

    def analyze(self, pages: Dict[str, str], causal_graph: Dict, output_dir: Path) -> Dict:
        """
        分析系统

        Args:
            pages: 页面名 -> 页面 HTML 文件路径 的映射
            causal_graph: Layer 2 的因果图输出
            output_dir: 输出目录

        Returns:
            系统分析结果
        """
        pages_summary = self._build_pages_summary(pages)
        causal_chain = self._format_causal_chain(causal_graph)
        design_preview = self._build_design_preview(pages)

        prompt = SYSTEM_ANALYSIS_PROMPT.format(
            pages_summary=pages_summary,
            causal_chain=causal_chain,
            design_preview=design_preview
        )

        content = self._call_llm(prompt, "你是资深产品经理。只输出JSON。")
        if not content:
            return {}

        try:
            content = content.strip()
            if content.startswith('```'):
                lines = content.split('\n')
                content = '\n'.join(lines[1:]) if len(lines) > 1 else content
            if content.endswith('```'):
                content = content[:-3]
            analysis = json.loads(content)
        except json.JSONDecodeError:
            analysis = {'raw_response': content}

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / 'system_analysis.json'
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(analysis, f, ensure_ascii=False, indent=2)

        user_intents = analysis.get('user_intents', [])
        if user_intents:
            intents_path = output_dir / 'user_intents.json'
            with open(intents_path, 'w', encoding='utf-8') as f:
                json.dump({'user_intents': user_intents}, f, ensure_ascii=False, indent=2)

        business_flows = analysis.get('business_flows', [])
        if business_flows:
            flows_path = output_dir / 'business_flows.json'
            with open(flows_path, 'w', encoding='utf-8') as f:
                json.dump({'business_flows': business_flows}, f, ensure_ascii=False, indent=2)

        return analysis

    def _build_pages_summary(self, pages: Dict[str, str]) -> str:
        lines = []
        for i, (name, path) in enumerate(pages.items()):
            p = Path(path)
            size = f" ({p.stat().st_size/1024:.0f}KB)" if p.exists() else ""
            lines.append(f"{i+1}. {name}{size}")
        return '\n'.join(lines)

    def _build_design_preview(self, pages: Dict[str, str]) -> str:
        """从重建的 HTML 页面中提取设计系统摘要"""
        if not pages:
            return ''

        css_samples = []
        behavior_samples = []
        element_samples = []

        import re as _re

        for name, html_path in list(pages.items())[:3]:  # 最多分析 3 个页面
            p = Path(html_path)
            if not p.exists():
                continue
            html = p.read_text(encoding='utf-8', errors='ignore')

            # 提取 CSS 颜色
            colors = set(_re.findall(r'(?:color|background|border-color|fill)[:\s]+(#[0-9a-fA-F]{3,8})', html))
            if colors:
                css_samples.append(f'  {name}: colors={list(colors)[:10]}')

            # 提取字体
            fonts = set(_re.findall(r'font-family:\s*([^;]+)', html))
            if fonts:
                css_samples.append(f'  {name}: fonts={list(fonts)[:5]}')

            # 提取字号
            sizes = set(_re.findall(r'font-size:\s*(\d+px)', html))
            if sizes:
                css_samples.append(f'  {name}: font-sizes={sorted(sizes, key=lambda x: int(x.replace("px","")), reverse=True)[:5]}')

            # 提取 UI 框架特征类名
            frameworks = []
            if 'el-button' in html or 'el-input' in html:
                frameworks.append('Element UI')
            if 'swiper-container' in html or 'swiper-slide' in html:
                frameworks.append('Swiper')
            if 'vjs-' in html:
                frameworks.append('Video.js')
            if 'el-message' in html:
                frameworks.append('Element UI (Toast/Message)')
            if frameworks:
                element_samples.append(f'  {name}: frameworks={frameworks}')

            # 提取行为注释
            behaviors = _re.findall(r'\[([a-z_]+)\] → (.+)$', html, _re.MULTILINE)
            if behaviors:
                behavior_samples.append(f'  {name}: behaviors={[[b[0], b[1][:60]] for b in behaviors[:5]]}')

            # 提取 media query 断点
            breakpoints = set(_re.findall(r'@media[^{]*max-width:\s*(\d+px)', html))
            if breakpoints:
                css_samples.append(f'  {name}: breakpoints={sorted(breakpoints)}')

        parts = []
        if css_samples:
            parts.append('## CSS 设计系统摘要\n' + '\n'.join(css_samples))
        if element_samples:
            parts.append('## 组件框架检测\n' + '\n'.join(element_samples))
        if behavior_samples:
            parts.append('## 交互行为摘要\n' + '\n'.join(behavior_samples))

        return '\n\n'.join(parts) if parts else ''

    def _format_causal_chain(self, causal_graph: Dict) -> str:
        lines = []

        navigations = causal_graph.get('navigations', [])
        if navigations:
            lines.append('## 页面导航')
            for nav in navigations:
                lines.append(f"- {nav['from']} -> {nav['to']} (触发: {nav['trigger']})")
            lines.append('')

        actions = causal_graph.get('actions', [])
        if actions:
            lines.append('## 用户操作序列')
            for i, action in enumerate(actions):
                desc = action.get('action', '')
                lines.append(f"\n{i+1}. [{action.get('type', '')}] {desc}")
                lines.append(f"   页面: {action.get('url', '')}")

                api_calls = action.get('api_calls', [])
                if api_calls:
                    lines.append(f"   调用的 API:")
                    for api in api_calls:
                        lines.append(f"     - {api.get('method', 'GET')} {api.get('full_url', api.get('url', ''))}")
                        resp = api.get('response', '')
                        if resp:
                            lines.append(f"       响应: {resp}")

        return '\n'.join(lines)
