"""
Layer 1: 页面组装器

将 rrweb 反序列化后的 HTML 与 CSS 文件、图片资源组装成完整可渲染页面。
不需要 LLM，纯程序化处理。
"""

import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Set
from urllib.parse import urlparse

from .rrweb_deserializer import RrwebDeserializer
from .behavior_extractor import BehaviorExtractor


class PageAssembler:
    """组装完整页面"""

    def __init__(self, task_path: Path):
        self.task_path = Path(task_path)
        self.dom_dir = self.task_path / 'dom'
        self.resources_dir = self.task_path / 'network' / 'resources'
        self.deserializer = RrwebDeserializer()

    def build_page(self, snapshot_file: str, output_dir: Path,
                   page_event_id: str = None) -> Optional[Path]:
        """
        构建单个页面

        Args:
            snapshot_file: DOM 快照文件名 (如 evt_xxx.json)
            output_dir: 输出目录
            page_event_id: page-load-start 的 eventId（用于行为提取）

        Returns:
            生成的 HTML 文件路径
        """
        snapshot_path = self.dom_dir / snapshot_file
        if not snapshot_path.exists():
            return None

        html_body = self.deserializer.deserialize_file(snapshot_path)
        if not html_body:
            return None

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # 收集页面引用的 CSS 和资源
        css_links = self._extract_css_links(html_body)
        css_content = self._load_css_files(css_links)

        # 构建资源映射
        resource_map = self._build_resource_map()

        # 从 eventId 提取页面时间戳，用于资源匹配优先级
        page_timestamp = 0
        if page_event_id:
            m = re.match(r'evt_(\d{13})_', page_event_id)
            if m:
                page_timestamp = int(m.group(1))

        # 复制图片到输出目录（扫描 HTML 和 CSS）
        images_dir = output_dir / 'images'
        images_dir.mkdir(exist_ok=True)
        self._copy_images(html_body, resource_map, images_dir, page_timestamp)
        self._copy_images(css_content, resource_map, images_dir, page_timestamp)

        # 重写 HTML 和 CSS 中的资源路径
        html_body = self._rewrite_resource_paths(html_body, resource_map, page_timestamp)
        css_content = self._rewrite_resource_paths(css_content, resource_map, page_timestamp)
        html_body = self._remove_script_tags(html_body)

        # 提取 JS 驱动的交互行为，注入注释
        if page_event_id:
            behaviors = BehaviorExtractor.extract_page_behaviors(
                self.task_path, page_event_id, snapshot_file
            )
            behavior_html = BehaviorExtractor.generate_behavior_html(
                behaviors.get('behaviors', []),
                behaviors.get('inline_annotations', {})
            )
            html_body = behavior_html + '\n' + html_body

        full_html = self._assemble_full_html(html_body, css_content)

        output_path = output_dir / 'index.html'
        if output_path.is_dir():
            import shutil
            shutil.rmtree(output_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(full_html)

        return output_path

    def _extract_css_links(self, html: str) -> List[str]:
        """提取 HTML 中的 CSS link"""
        pattern = r'<link[^>]*rel=["\']stylesheet["\'][^>]*href=["\']([^"\']+)["\'][^>]*/?>'
        matches = re.findall(pattern, html, re.IGNORECASE)
        pattern2 = r'<link[^>]*href=["\']([^"\']+)["\'][^>]*rel=["\']stylesheet["\'][^>]*/?>'
        matches2 = re.findall(pattern2, html, re.IGNORECASE)
        return list(set(matches + matches2))

    def _load_css_files(self, css_links: List[str]) -> str:
        """加载 CSS 文件内容"""
        all_css = []
        for link in css_links:
            filename = link.split('/')[-1].split('?')[0]
            for f in (self.resources_dir / filename,
                      self.resources_dir / f'1778981135411_{filename}',
                      self.resources_dir / f'1778981135556_{filename}'):
                pass

            matches = list(self.resources_dir.glob(f'*{filename}'))
            for match in matches:
                try:
                    content = match.read_text(encoding='utf-8', errors='ignore')
                    all_css.append(f'/* {filename} */\n{content}')
                    break
                except Exception:
                    pass

        # 也尝试匹配文件名中的 hash
        for link in css_links:
            base = link.split('/')[-1].split('?')[0]
            for file in self.resources_dir.iterdir():
                if file.is_file() and file.name.endswith('.css') and base in file.name:
                    try:
                        content = file.read_text(encoding='utf-8', errors='ignore')
                        all_css.append(f'/* {file.name} */\n{content}')
                    except Exception:
                        pass

        return '\n'.join(all_css)

    def _build_resource_map(self) -> Dict[str, str]:
        """构建 URL 路径到实际文件名的映射"""
        mapping = {}
        if not self.resources_dir.exists():
            return mapping

        for f in self.resources_dir.iterdir():
            if not f.is_file():
                continue
            name = f.name
            mapping[name] = name
            base_name = name.rsplit('.', 1)[0] if '.' in name else name
            ext = f.suffix
            mapping[f'{base_name}{ext}'] = name

        return mapping

    def _normalize_filename(self, name: str) -> str:
        """规范化文件名用于匹配：@2x → _2x, @3x → _3x"""
        return name.replace('@2x', '_2x').replace('@3x', '_3x').replace('@4x', '_4x')

    def _match_resource(self, src: str, page_timestamp: int = 0) -> Optional[Path]:
        """在 resources 目录中匹配资源文件

        匹配优先级：
        1. 精确后缀：rname 以 filename 结尾 (如 logo.png 匹配 *_logo.png)
           同组内优先选择时间戳最接近 page_timestamp 的文件
        2. 基线后缀：rbase 以 base 结尾
        3. 模糊匹配：base in rname
        """
        if not src or src.startswith(('data:', 'http://', 'https://', '#')):
            return None
        if src == '***':
            return None

        filename = src.split('/')[-1].split('?')[0]
        if not filename or filename == '***':
            return None

        normalized = self._normalize_filename(filename)
        base = filename.rsplit('.', 1)[0] if '.' in filename else filename
        normalized_base = self._normalize_filename(base)

        hashless_base = re.sub(r'\.[a-f0-9]{8,}$', '', base) if base else base
        hashless_filename = re.sub(r'\.[a-f0-9]{8,}\.', '.', filename) if filename else filename

        if not self.resources_dir.exists():
            return None

        def extract_ts(rname):
            m = re.match(r'^(\d{13})_', rname)
            return int(m.group(1)) if m else 0

        # 收集所有资源文件
        candidates_exact = []  # rname ends with filename
        candidates_base = []   # rbase ends with base
        candidates_fuzzy = []  # base in rname or filename in rname

        for res_file in self.resources_dir.iterdir():
            if not res_file.is_file():
                continue
            rname = res_file.name
            rbase = rname.rsplit('.', 1)[0] if '.' in rname else rname

            if rname.endswith(filename) or rname.endswith(normalized):
                candidates_exact.append(res_file)
            elif rname.endswith(hashless_filename):
                candidates_exact.append(res_file)
            elif rbase.endswith(base) or rbase.endswith(normalized_base):
                candidates_base.append(res_file)
            elif rbase.endswith(hashless_base):
                candidates_base.append(res_file)
            elif base in rname or normalized_base in rname:
                candidates_fuzzy.append(res_file)
            elif filename in rname or normalized in rname:
                candidates_fuzzy.append(res_file)
            elif hashless_base in rname or hashless_filename in rname:
                candidates_fuzzy.append(res_file)

        def closest_by_timestamp(candidates):
            if not candidates:
                return None
            best = None
            best_dist = float('inf')
            for f in candidates:
                ts = extract_ts(f.name)
                dist = abs(ts - page_timestamp) if page_timestamp and ts else 0
                if dist < best_dist:
                    best_dist = dist
                    best = f
            return best

        return closest_by_timestamp(candidates_exact) or \
               closest_by_timestamp(candidates_base) or \
               closest_by_timestamp(candidates_fuzzy)

    def _copy_images(self, html: str, resource_map: Dict[str, str], images_dir: Path,
                     page_timestamp: int = 0):
        """复制页面引用的图片到输出目录"""
        img_pattern = r'<img[^>]+src=["\']([^"\']+)["\']'
        src_pattern = r'src=["\']([^"\']+)["\']'
        css_url_pattern = r'url\(["\']?([^"\')\s]+)["\']?\)'

        all_srcs = set()
        for pattern in [img_pattern, src_pattern, css_url_pattern]:
            for match in re.finditer(pattern, html):
                src = match.group(1)
                if src == '***' or not src:
                    continue
                # Skip data: URIs and absolute URLs
                if src.startswith(('data:', 'http://', 'https://')):
                    continue
                all_srcs.add(src)

        for src in all_srcs:
            ext = src.rsplit('.', 1)[-1].lower() if '.' in src else ''
            if ext in ('jsp', 'php', 'aspx', 'asp', 'do', 'action'):
                continue
            matched = self._match_resource(src, page_timestamp)
            if matched:
                dest = images_dir / matched.name
                try:
                    shutil.copy2(matched, dest)
                except shutil.SameFileError:
                    pass

    def _rewrite_resource_paths(self, html: str, resource_map: Dict[str, str],
                                page_timestamp: int = 0) -> str:
        """重写 HTML 和 CSS 中的资源路径"""
        PLACEHOLDER_IMG = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'

        def replace_src(match):
            attr = match.group(1)
            src = match.group(2)
            if src == '***':
                return f'{attr}="{PLACEHOLDER_IMG}"'
            if src.startswith(('data:', 'http://', 'https://', '#')):
                return match.group(0)
            ext = src.rsplit('.', 1)[-1].lower() if '.' in src else ''
            if ext in ('jsp', 'php', 'aspx', 'asp', 'do', 'html', 'htm', 'action', 'shtml'):
                return match.group(0)
            matched = self._match_resource(src, page_timestamp)
            if matched:
                return f'{attr}="images/{matched.name}"'
            return match.group(0)

        # 替换 img src / source src / video src
        html = re.sub(
            r'(src)=["\']([^"\']+)["\']',
            replace_src,
            html
        )
        # 替换 link href
        html = re.sub(
            r'(href)=["\']([^"\']+\.(?:png|jpg|jpeg|svg|ico|woff2?))["\']',
            replace_src,
            html
        )

        # 替换 CSS url() 引用（在 <style> 块中）
        def replace_css_url(match):
            url_path = match.group(1)
            if url_path == '***':
                return f'url({PLACEHOLDER_IMG})'
            if url_path.startswith(('data:', 'http://', 'https://')):
                return match.group(0)
            matched = self._match_resource(url_path, page_timestamp)
            if matched:
                return f'url(images/{matched.name})'
            return match.group(0)

        html = re.sub(
            r'url\(["\']?([^"\')\s]+)["\']?\)',
            replace_css_url,
            html
        )

        return html

    def _remove_script_tags(self, html: str) -> str:
        """移除 script 标签（保留内容作为 HTML 注释供 LLM 理解）"""
        def _wrap_script(match):
            content = match.group(0)
            inner = re.sub(r'^<script[^>]*>', '', content)
            inner = re.sub(r'</script>$', '', inner)
            inner_stripped = inner.strip()
            if not inner_stripped:
                return ''
            short = inner_stripped[:200] + ('...' if len(inner_stripped) > 200 else '')
            return f'\n<!-- [REMOVED SCRIPT] {short} -->\n'

        html = re.sub(r'<script[^>]*>.*?</script>', _wrap_script, html, flags=re.DOTALL)
        html = re.sub(r'<noscript[^>]*>.*?</noscript>', '', html, flags=re.DOTALL)
        return html

    def _assemble_full_html(self, body: str, css: str) -> str:
        """组装完整 HTML"""
        # 移除 html/head/body 标签，因为反序列化出来的可能包含它们
        # 提取 title
        title_match = re.search(r'<title[^>]*>(.*?)</title>', body, re.DOTALL)
        title = title_match.group(1).strip() if title_match else 'Page'

        # 提取原始 <html> 标签上的属性（特别是 style，lang 由模板统一控制）
        html_tag_match = re.search(r'<html\b([^>]*)>', body, re.IGNORECASE)
        html_attrs = ''
        if html_tag_match:
            raw_attrs = html_tag_match.group(1).strip()
            attr_parts = re.findall(r'(\S+)\s*=\s*["\']([^"\']*)["\']', raw_attrs)
            preserved = []
            for attr_name, attr_val in attr_parts:
                lower = attr_name.lower()
                if lower == 'lang':
                    continue
                preserved.append(f'{attr_name}="{attr_val}"')
            if preserved:
                html_attrs = ' ' + ' '.join(preserved)

        inline_styles = []
        def _extract_style(match):
            tag = match.group(0)
            # 提取 style 标签的内容（去掉 <style ...> 和 </style>）
            content = re.sub(r'^<style[^>]*>', '', tag)
            content = re.sub(r'</style>$', '', content, flags=re.IGNORECASE)
            inline_styles.append(content.strip())
            return ''

        body = re.sub(r'<style[^>]*>.*?</style>', _extract_style, body, flags=re.DOTALL)
        body = re.sub(r'<link[^>]*rel=["\']stylesheet["\'][^>]*/?>', '', body, flags=re.IGNORECASE)

        if inline_styles:
            extracted = '\n'.join(s.strip() for s in inline_styles)
            # 避免 CSS 内容中的 </style> 提前关闭 <style> 标签
            extracted = extracted.replace('</style>', '<\\/style>')
            if css:
                css = extracted + '\n' + css
            else:
                css = extracted

        # 尝试提取 body 内容或直接用全部
        body_match = re.search(r'<body[^>]*>(.*)</body>', body, re.DOTALL)
        if body_match:
            body_content = body_match.group(1)
        else:
            body_content = body

        # 修复 SPA 反闪屏：移除 body{display:none}。
        # Vue.js/React SPA 在 body 上设 display:none 防止渲染闪屏，
        # 挂载后由 JS 移除。重建页面不含 JS 运行时，body 会永久隐藏。
        css = re.sub(
            r'body\s*\{[^}]*display\s*:\s*none[^}]*\}',
            'body{display:block}',
            css,
            flags=re.IGNORECASE
        )

        return f'''<!DOCTYPE html>
<html lang="zh-CN"{html_attrs}>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
{css}
</style>
</head>
<body>
{body_content}
</body>
</html>'''
