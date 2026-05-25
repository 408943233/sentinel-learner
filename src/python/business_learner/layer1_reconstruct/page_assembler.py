"""
Layer 1: 页面组装器

将 rrweb 反序列化后的 HTML 与 CSS 文件、图片资源组装成完整可渲染页面。
不需要 LLM，纯程序化处理。
"""

import json
import logging
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Set
from urllib.parse import urlparse

from .rrweb_deserializer import RrwebDeserializer
from .behavior_extractor import BehaviorExtractor

logger = logging.getLogger(__name__)

# 确保日志可见（learn.py 未配置全局 logging，此处兜底）
if not logger.handlers and not logging.root.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter('[%(name)s] %(levelname)s: %(message)s'))
    logger.addHandler(_handler)
    logger.setLevel(logging.DEBUG)


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

        # 内嵌 iframe 内容（CDP 捕获的跨域 iframe DOM）
        full_html = self._embed_iframe_content(snapshot_path, full_html)

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

        # 提取原始 <html> 标签上的属性
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

        # 提取原始 <body> 标签上的属性（class, style 等布局关键属性）
        body_attrs = ''
        body_tag_match = re.search(r'<body\b([^>]*)>', body, re.IGNORECASE)
        if body_tag_match:
            raw_body_attrs = body_tag_match.group(1).strip()
            body_attr_parts = re.findall(r'(\S+)\s*=\s*["\']([^"\']*)["\']', raw_body_attrs)
            body_preserved = []
            for attr_name, attr_val in body_attr_parts:
                lower = attr_name.lower()
                body_preserved.append(f'{attr_name}="{attr_val}"')
            if body_preserved:
                body_attrs = ' ' + ' '.join(body_preserved)

        inline_styles = []
        def _extract_style(match):
            tag = match.group(0)
            content = re.sub(r'^<style[^>]*>', '', tag)
            content = re.sub(r'</style>$', '', content, flags=re.IGNORECASE)
            inline_styles.append(content.strip())
            return ''

        body = re.sub(r'<style[^>]*>.*?</style>', _extract_style, body, flags=re.DOTALL)
        body = re.sub(r'<link[^>]*rel=["\']stylesheet["\'][^>]*/?>', '', body, flags=re.IGNORECASE)

        if inline_styles:
            extracted = '\n'.join(s.strip() for s in inline_styles)
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

        # 修复 SPA 反闪屏：移除 body{display:none}
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
<body{body_attrs}>
{body_content}
</body>
</html>'''

    def _embed_iframe_content(self, snapshot_path: Path, html: str) -> str:
        """将录制时通过 CDP 捕获的跨域 iframe 内容内嵌到 HTML 中。

        录制阶段（sentinel-browser）通过 CDP Page.getFrameTree + Runtime.evaluate
        突破了同源策略限制，捕获了跨域 iframe 内部的完整 outerHTML，
        保存在快照文件的 iframeCaptures 字段中。
        此方法读取这些捕获内容，用静态 HTML 替换 <iframe> 标签，
        避免重建页面时依赖临时令牌导致 iframe 无法加载。
        """
        try:
            with open(snapshot_path, 'r', encoding='utf-8') as f:
                snapshot = json.load(f)

            iframe_captures = snapshot.get('iframeCaptures', [])
            if not iframe_captures:
                logger.info(f"[iframe-embed] No iframeCaptures in {snapshot_path.name}, skipping")
                return html

            logger.info(f"[iframe-embed] Found {len(iframe_captures)} iframe capture(s) in {snapshot_path.name}")
            _before_count = len(re.findall(r'<iframe\b', html))
            logger.info(f"[iframe-embed] Original HTML size: {len(html)} chars, "
                        f"iframe tags before: {_before_count}")

            for i, capture in enumerate(iframe_captures):
                src = capture.get('src', '')
                outer_html = capture.get('outerHTML', '')
                title = capture.get('title', '')
                name = capture.get('name', '')

                # 原始捕获内容统计
                outer_size = len(outer_html)
                outer_lines = outer_html.count('\n') + 1 if outer_html else 0
                logger.info(
                    f"[iframe-embed] ===== Capture #{i} ===== "
                    f"src={src[:120]}, name={name}, title={title[:60]}, "
                    f"raw_size={outer_size} chars, raw_lines={outer_lines}"
                )

                if outer_html:
                    # 打印 outerHTML 的开头和结尾片段用于验证
                    head_snippet = outer_html[:300].replace('\n', '\\n')
                    tail_snippet = outer_html[-200:].replace('\n', '\\n') if outer_size > 200 else ''
                    logger.debug(f"[iframe-embed]   head_snippet (first 300 chars): {head_snippet}")
                    if tail_snippet:
                        logger.debug(f"[iframe-embed]   tail_snippet (last 200 chars): {tail_snippet}")

                    # 检查常见 HTML 元素
                    tag_counts = {}
                    for tag in ['html', 'head', 'body', 'form', 'input', 'button', 'div', 'script', 'style', 'img']:
                        cnt = len(re.findall(rf'<\s*{tag}\b', outer_html, re.IGNORECASE))
                        if cnt:
                            tag_counts[tag] = cnt
                    if tag_counts:
                        logger.debug(f"[iframe-embed]   tag_counts: {tag_counts}")

                if not outer_html:
                    logger.warning(f"[iframe-embed] Capture #{i} has empty outerHTML, skipping src={src[:100]}")
                    continue

                # 跳过 about:blank（无实际内容）
                if src == 'about:blank' and outer_size < 100:
                    logger.info(f"[iframe-embed] Skipping about:blank (size={outer_size})")
                    continue

                # 在重建 HTML 中查找所有 iframe 标签，使用 re.finditer 获取位置
                # 1. name 属性匹配（iframe name 通常是唯一的）
                # 2. src 后缀匹配（CDP 捕获绝对 URL，HTML 中可能是相对路径）
                # 3. src 精确匹配（回退）
                #
                # 使用带位置信息的匹配，后续需要定位 </iframe> 闭合标签
                all_iframes = list(re.finditer(r'<iframe\b[^>]*>', html, re.IGNORECASE))
                matched_pos = None
                matched_tag = None
                matched_reason = None

                if name:
                    escaped_name = re.escape(name)
                    for m in all_iframes:
                        if re.search(r'\bname\s*=\s*["\']' + escaped_name + r'["\']', m.group()):
                            matched_pos = m.start()
                            matched_tag = m.group()
                            matched_reason = f"name={name}"
                            break

                if not matched_tag and src:
                    url_basename = src.split('?')[0].rsplit('/', 1)[-1] if '/' in src else src
                    if url_basename:
                        escaped_bn = re.escape(url_basename)
                        for m in all_iframes:
                            if re.search(r'src\s*=\s*["\'][^"\']*' + escaped_bn + r'[^"\']*["\']', m.group()):
                                matched_pos = m.start()
                                matched_tag = m.group()
                                matched_reason = f"src_basename={url_basename}"
                                break

                if not matched_tag and src:
                    escaped_src = re.escape(src)
                    for m in all_iframes:
                        if re.search(r'src\s*=\s*["\']' + escaped_src + r'["\']', m.group()):
                            matched_pos = m.start()
                            matched_tag = m.group()
                            matched_reason = f"src_exact={src[:60]}"
                            break

                if not matched_tag:
                    logger.warning(
                        f"[iframe-embed] No matching <iframe> for capture #{i} "
                        f"src={src[:100]} name={name}"
                    )
                    for m in all_iframes:
                        sm = re.search(r'src="([^"]*)"', m.group())
                        nm = re.search(r'name="([^"]*)"', m.group())
                        logger.warning(
                            f"[iframe-embed]   src={sm.group(1)[:80] if sm else '?'} "
                            f"name={nm.group(1) if nm else '?'}"
                        )
                    continue

                logger.info(
                    f"[iframe-embed] Matched by {matched_reason} at pos {matched_pos}: "
                    f"{matched_tag[:200]}"
                )

                # 定位 </iframe> 闭合标签，替换完整的 <iframe>...</iframe> 块
                close_tag_pos = html.find('</iframe>', matched_pos)
                if close_tag_pos < 0:
                    logger.warning(
                        f"[iframe-embed] No </iframe> found after matched tag at pos {matched_pos}"
                    )
                    continue
                close_end = close_tag_pos + len('</iframe>')
                logger.debug(
                    f"[iframe-embed]   </iframe> at pos {close_tag_pos}, "
                    f"block length={close_end - matched_pos}"
                )

                # 从 outerHTML 中提取 <body> 内容
                # outerHTML 是完整 HTML 文档，内嵌时需要去除外层结构避免嵌套 <html><head><body>
                body_match = re.search(r'<body[^>]*>(.*)</body>', outer_html, re.DOTALL | re.IGNORECASE)
                embed_content = body_match.group(1).strip() if body_match else outer_html

                # 计算 iframe 的基 URL，用于将相对路径转换为绝对路径
                # src 形如 https://iam.chinastock.com.cn/authn/login.html?...
                from urllib.parse import urlparse, urljoin
                iframe_base = src.split('?')[0] if src else ''
                # 确保 base 以 / 结尾（目录级）
                if '/' in iframe_base:
                    dir_part = iframe_base.rsplit('/', 1)[0]
                    iframe_base = dir_part + '/'
                logger.debug(f"[iframe-embed]   iframe base URL: {iframe_base}")

                def _make_absolute(url):
                    """将相对路径转为基于 iframe base 的绝对 URL"""
                    if not url or url.startswith(('http://', 'https://', 'data:', '//')):
                        return url
                    return urljoin(iframe_base, url)

                # 提取 <head> 中的资源用于内联
                head_resources = ''
                head_match = re.search(r'<head[^>]*>(.*)</head>', outer_html, re.DOTALL | re.IGNORECASE)
                if head_match:
                    head_content = head_match.group(1)
                    parts = []

                    # <style> 标签
                    for m in re.finditer(r'<style\b[^>]*>.*?</style>', head_content, re.DOTALL | re.IGNORECASE):
                        parts.append(m.group())

                    # <link> 标签，重写 href 为绝对路径
                    for m in re.finditer(r'<link\b[^>]*?>', head_content, re.IGNORECASE):
                        tag = m.group()
                        href_m = re.search(r'href="([^"]*)"', tag)
                        if href_m:
                            abs_href = _make_absolute(href_m.group(1))
                            tag = tag[:href_m.start(1)] + abs_href + tag[href_m.end(1):]
                        parts.append(tag)

                    # <script> 标签，重写 src 为绝对路径
                    for m in re.finditer(r'<script\b[^>]*>.*?</script>|<script\b[^>]*/>', head_content, re.DOTALL | re.IGNORECASE):
                        tag = m.group()
                        src_m = re.search(r'src="([^"]*)"', tag)
                        if src_m:
                            abs_src = _make_absolute(src_m.group(1))
                            tag = tag[:src_m.start(1)] + abs_src + tag[src_m.end(1):]
                        parts.append(tag)

                    head_resources = '\n'.join(parts) if parts else ''
                    if head_resources:
                        style_count = len(re.findall(r'<style|<link', head_resources))
                        script_count = len(re.findall(r'<script', head_resources))
                        logger.debug(
                            f"[iframe-embed]   extracted from <head>: "
                            f"{style_count} style/link, {script_count} script tag(s)"
                        )

                # 重写 embed_content 中的资源路径为绝对路径
                # 包括: <img src>, <script src>, <link href>
                def _rewrite_attr(tag, attr):
                    m = re.search(rf'{attr}="([^"]*)"', tag)
                    if m:
                        abs_val = _make_absolute(m.group(1))
                        return tag[:m.start(1)] + abs_val + tag[m.end(1):]
                    return tag

                embed_content = re.sub(
                    r'<img\b[^>]*>',
                    lambda m: _rewrite_attr(m.group(), 'src'),
                    embed_content,
                    flags=re.IGNORECASE
                )
                embed_content = re.sub(
                    r'<source\b[^>]*>',
                    lambda m: _rewrite_attr(m.group(), 'src'),
                    embed_content,
                    flags=re.IGNORECASE
                )
                # body 中的 <script src="..."> 也需要重写
                embed_content = re.sub(
                    r'<script\b[^>]*src="[^"]*"[^>]*>.*?</script>|<script\b[^>]*src="[^"]*"[^>]*/>',
                    lambda m: _rewrite_attr(m.group(), 'src'),
                    embed_content,
                    flags=re.DOTALL | re.IGNORECASE
                )
                # <link> 标签（如 favicon）
                embed_content = re.sub(
                    r'<link\b[^>]*>',
                    lambda m: _rewrite_attr(m.group(), 'href'),
                    embed_content,
                    flags=re.IGNORECASE
                )

                replacement = (
                    f'<!-- [EMBEDDED IFRAME] src={src} title={title} -->\n'
                    f'{head_resources}\n'
                    f'{embed_content}\n'
                    f'<!-- [/EMBEDDED IFRAME] -->'
                )

                # 替换整个 <iframe ...> ... </iframe> 块
                old_block = html[matched_pos:close_end]
                new_html = html[:matched_pos] + replacement + html[close_end:]
                if new_html != html:
                    delta = len(new_html) - len(html)
                    logger.info(f"[iframe-embed] SUCCESS: replaced by {matched_reason}")
                    logger.info(
                        f"[iframe-embed]   HTML size change: {len(html)} -> {len(new_html)} "
                        f"chars (delta={delta:+d})"
                    )
                    logger.info(
                        f"[iframe-embed]   Embedded: body={len(embed_content)} chars, "
                        f"head_resources={len(head_resources)} chars"
                    )
                    html = new_html
                else:
                    logger.warning(f"[iframe-embed] Replace by {matched_reason} had no effect")

            total_iframe_tags = len(re.findall(r'<iframe\b', html))
            logger.info(
                f"[iframe-embed] ===== Done: {len(iframe_captures)} captures processed, "
                f"{total_iframe_tags} <iframe> tags remain, "
                f"final HTML size: {len(html)} chars ====="
            )
            return html

        except FileNotFoundError:
            logger.error(f"[iframe-embed] Snapshot file not found: {snapshot_path}")
            return html
        except json.JSONDecodeError as e:
            logger.error(f"[iframe-embed] Invalid JSON in snapshot {snapshot_path}: {e}")
            return html
        except Exception as e:
            logger.error(f"[iframe-embed] Failed to embed iframe content: {e}", exc_info=True)
            return html
