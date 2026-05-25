"""
Layer 1 完整性验证器

验证维度：
1. DOM 结构一致性 (tag/class/id/层级对比)
2. CSS 资源完整性 (是否所有 link 都有对应 CSS)
3. 图片资源完整性 (img src 是否指向真实文件)
4. 字体资源完整性 (font 引用是否都有对应文件)
5. 文本内容覆盖率
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Set
from html.parser import HTMLParser


class HTMLResourceParser(HTMLParser):
    """解析 HTML，提取所有资源引用和结构"""

    def __init__(self):
        super().__init__()
        self.elements = []
        self.texts = []
        self.css_links = []
        self.img_srcs = []
        self.font_refs = []
        self.script_srcs = []
        self.video_sources = []
        self._id_counter = 1
        self._stack = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        tag_lower = tag.lower()
        el = {'id': self._id_counter, 'tag': tag_lower, 'attrs': attrs_dict}
        if self._stack:
            el['parent_id'] = self._stack[-1]
        self._stack.append(self._id_counter)
        self._id_counter += 1
        self.elements.append(el)

        # CSS
        if tag_lower == 'link' and attrs_dict.get('rel', '') == 'stylesheet':
            self.css_links.append(attrs_dict.get('href', ''))
        # Images
        if tag_lower == 'img':
            self.img_srcs.append(attrs_dict.get('src', ''))
        # Fonts
        if tag_lower == 'link' and 'font' in (attrs_dict.get('as', '') + attrs_dict.get('rel', '')):
            self.font_refs.append(attrs_dict.get('href', ''))
        # Scripts
        if tag_lower == 'script' and attrs_dict.get('src'):
            self.script_srcs.append(attrs_dict.get('src', ''))
        # Video
        if tag_lower == 'source' and attrs_dict.get('src'):
            self.video_sources.append(attrs_dict.get('src', ''))

    def handle_endtag(self, tag):
        if self._stack:
            self._stack.pop()

    def handle_data(self, data):
        text = data.strip()
        if text:
            self.texts.append(text)


class Layer1Validator:
    """Layer 1 完整性验证器"""

    def __init__(self, task_path: Path):
        self.task_path = Path(task_path)

    def validate_page(self, snapshot_file: str, html_path: Path) -> Dict:
        """完整验证单个页面"""

        result = {
            'snapshot': snapshot_file,
            'html': str(html_path),
            'passed': False,
            'checks': {}
        }

        dom_path = self.task_path / 'dom' / snapshot_file
        if not dom_path.exists():
            result['errors'] = ['Snapshot file not found']
            return result

        with open(dom_path, 'r') as f:
            dom_data = json.load(f)

        rrweb = dom_data.get('rrwebEvent', {})
        if rrweb.get('type') != 2:
            result['errors'] = [f'Not a FullSnapshot (type={rrweb.get("type")})']
            return result

        original_nodes = rrweb['data'].get('nodes', [])

        if not html_path.exists():
            result['errors'] = ['HTML file not found']
            return result

        with open(html_path, 'r') as f:
            html_content = f.read()

        parser = HTMLResourceParser()
        try:
            parser.feed(html_content)
        except Exception as e:
            result['errors'] = [f'HTML parse error: {e}']
            return result

        images_dir = html_path.parent / 'images'

        # ===== Check 1: DOM 结构 =====
        original_elements = [n for n in original_nodes if n.get('type') == 2]

        orig_sigs = set()
        for node in original_elements:
            tag = node.get('tagName', '')
            attrs = node.get('attributes', {})
            sig = f"{tag}|{attrs.get('id','')}|{attrs.get('class','')}"
            orig_sigs.add(sig)

        parsed_sigs = set()
        for el in parser.elements:
            attrs = el['attrs']
            sig = f"{el['tag']}|{attrs.get('id','')}|{attrs.get('class','')}"
            parsed_sigs.add(sig)

        missing = orig_sigs - parsed_sigs
        extra = parsed_sigs - orig_sigs

        # Collect original text content
        orig_texts = []
        for node in original_nodes:
            if node.get('type') == 3 and node.get('textContent', '').strip():
                orig_texts.append(node['textContent'].strip())

        result['checks']['dom_structure'] = {
            'original_elements': len(original_elements),
            'parsed_elements': len(parser.elements),
            'element_match_pct': round(100 * min(len(original_elements), len(parser.elements)) / max(len(original_elements), len(parser.elements), 1), 1),
            'signature_match_pct': round(100 * len(orig_sigs & parsed_sigs) / max(len(orig_sigs), 1), 1),
            'missing_signatures': list(missing)[:10],
            'extra_signatures': list(extra)[:10],
            'text_chars_original': sum(len(t) for t in orig_texts),
            'text_chars_parsed': sum(len(t) for t in parser.texts),
            'text_segments_original': len(orig_texts),
            'text_segments_parsed': len(parser.texts),
        }

        # ===== Check 2: CSS 资源完整性 =====
        # Extract original CSS links from rrweb nodes
        orig_css_links = []
        for node in original_elements:
            if node.get('tagName', '').lower() == 'link':
                attrs = node.get('attributes', {})
                if attrs.get('rel', '') == 'stylesheet':
                    orig_css_links.append(attrs.get('href', ''))

        # Check if CSS from original DOM is embedded in rebuilt HTML
        css_embedded = len(re.findall(r'<style[^>]*>', html_content)) > 0

        # Check CSS url() references — are they rewritten correctly?
        # Skip commented-out CSS rules (/* ... */)
        uncommented_html = re.sub(r'/\*.*?\*/', '', html_content, flags=re.DOTALL)
        css_url_refs = re.findall(r'url\(["\']?([^"\')\s]+)["\']?\)', uncommented_html)
        css_url_unresolved = []
        css_url_resolved = 0
        for ref in css_url_refs:
            if ref.startswith(('data:', 'http://', 'https://')):
                css_url_resolved += 1
                continue
            if ref.startswith('images/'):
                # Local path rewritten — check file exists
                filename = ref.split('/')[-1].split('?')[0]
                found = any(
                    f.name == filename for d in [images_dir, self.task_path / 'network' / 'resources']
                    if d.exists() for f in d.iterdir() if f.is_file()
                )
                if found:
                    css_url_resolved += 1
                else:
                    css_url_unresolved.append(ref)
            else:
                # Still has old path (../images/ or /newsite/images/)
                css_url_unresolved.append(ref)

        result['checks']['css'] = {
            'original_css_links': len(orig_css_links),
            'css_embedded_in_style': css_embedded,
            'css_url_total': len(css_url_refs),
            'css_url_resolved': css_url_resolved,
            'css_url_unresolved': len(css_url_unresolved),
            'css_url_unresolved_examples': css_url_unresolved[:10],
            'css_file_links_remaining': len(parser.css_links),
        }

        # ===== Check 3: 图片资源完整性 =====
        img_hits = 0
        img_misses = []
        for src in parser.img_srcs:
            if not src or src.startswith(('data:', 'http://', 'https://')):
                img_hits += 1  # data URLs and external URLs are fine
                continue
            filename = src.split('/')[-1].split('?')[0]
            found = False
            for check_dir in [images_dir, self.task_path / 'network' / 'resources']:
                if check_dir.exists():
                    for f in check_dir.iterdir():
                        if f.is_file() and (f.name == filename or
                                            filename in f.name or
                                            f.name.endswith(filename)):
                            found = True
                            break
                if found:
                    break
            if found:
                img_hits += 1
            else:
                img_misses.append(src)

        result['checks']['images'] = {
            'total_img_refs': len(parser.img_srcs),
            'resolved': img_hits,
            'unresolved': len(img_misses),
            'resolution_pct': round(100 * img_hits / max(len(parser.img_srcs), 1), 1),
            'unresolved_examples': img_misses[:10],
        }

        # ===== Check 4: 字体资源完整性 =====
        font_refs = []
        # Extract font-face references from CSS in style blocks
        font_face_matches = re.findall(r"url\(['\"]?([^'\")\s]+)['\"]?\)", html_content)
        font_refs.extend(font_face_matches)

        # Also check woff2 font files
        all_font_refs = set(font_refs + parser.font_refs)
        font_hits = 0
        font_misses = []
        for ref in all_font_refs:
            if ref.startswith(('data:', 'http://', 'https://')):
                font_hits += 1
                continue
            filename = ref.split('/')[-1].split('?')[0]
            found = False
            for check_dir in [images_dir, self.task_path / 'network' / 'resources']:
                if check_dir.exists():
                    for f in check_dir.iterdir():
                        if f.is_file() and (f.name == filename or f.name.endswith(filename)):
                            found = True
                            break
                if found:
                    break
            if found:
                font_hits += 1
            else:
                font_misses.append(ref)

        result['checks']['fonts'] = {
            'total_font_refs': len(all_font_refs),
            'resolved': font_hits,
            'unresolved': len(font_misses),
            'unresolved_examples': font_misses[:5],
        }

        # ===== Check 5: 整体评分 =====
        scores = []
        scores.append(result['checks']['dom_structure']['signature_match_pct'] / 100)
        scores.append(result['checks']['images']['resolution_pct'] / 100 if result['checks']['images']['total_img_refs'] > 0 else 1.0)
        scores.append(1.0 if css_embedded else 0.0)
        # CSS url() resolution
        css_total = result['checks']['css']['css_url_total']
        if css_total > 0:
            scores.append(result['checks']['css']['css_url_resolved'] / css_total)

        result['overall_score'] = round(100 * sum(scores) / len(scores), 1)
        result['passed'] = result['overall_score'] >= 70

        return result
