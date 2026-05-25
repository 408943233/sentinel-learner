"""
DOM 快照重建器
从 rrweb DOM 快照重建可交互 HTML 页面
支持 Full Snapshot 和 Incremental Snapshot
结合图片、CSS、JS 资源
"""

import json
import re
import base64
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse

from ..core.build_result import BuildResult, DataSource


class DOMReconstructor:
    """DOM 重建器"""
    
    def __init__(self):
        self.inline_styles = {}
        self.external_css = []
        self.scripts = []
        self.images = {}  # 图片资源映射
        # rrweb 节点类型映射
        self.NODE_TYPES = {
            0: 'Document',
            1: 'DocumentType',
            2: 'Element',
            3: 'Text',
            4: 'CDATA',
            5: 'Comment'
        }
        # 节点 ID 到节点的映射
        self.nodes_map = {}
        self.task_path = None
    
    def reconstruct(self, 
                   task_path: str,
                   output_dir: str,
                   target_score: float = 0.95) -> BuildResult:
        """
        从 DOM 快照重建页面
        
        Args:
            task_path: task 目录路径
            output_dir: 输出目录
            target_score: 目标质量分数
            
        Returns:
            构建结果
        """
        task_path = Path(task_path)
        self.task_path = task_path
        task_id = task_path.name
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        start_time = datetime.now()
        
        try:
            # 1. 加载所有快照（包括完整和增量）
            snapshots = self._load_all_snapshots(task_path)
            if not snapshots:
                return BuildResult(
                    task_id=task_id,
                    source=DataSource.FAILED,
                    error_message="未找到有效的 DOM 快照"
                )
            
            print(f"    找到 {len(snapshots)} 个快照")
            
            # 2. 重建完整 DOM 状态
            dom_state = self._rebuild_dom_state(snapshots, task_path)
            if not dom_state:
                return BuildResult(
                    task_id=task_id,
                    source=DataSource.FAILED,
                    error_message="无法重建 DOM 状态"
                )
            
            # 3. 提取资源文件（CSS、JS、图片）
            self._extract_resources(task_path)
            
            # 4. 重建 HTML（结合 DOM + 资源）
            html_content = self._build_html_from_state(dom_state, task_path)
            
            # 5. 保存文件
            output_path = output_dir / f"prototype_dom_{task_id}.html"
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            build_time = (datetime.now() - start_time).total_seconds() * 1000
            
            return BuildResult(
                task_id=task_id,
                source=DataSource.DOM_SNAPSHOT,
                output_path=output_path,
                build_time_ms=build_time,
                source_files=[str(s['file']) for s in snapshots[:5]]
            )
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return BuildResult(
                task_id=task_id,
                source=DataSource.FAILED,
                error_message=f"DOM 重建失败: {str(e)}"
            )
    
    def _load_all_snapshots(self, task_path: Path) -> List[Dict]:
        """加载所有 DOM 快照（完整和增量）"""
        snapshots = []
        dom_dir = task_path / "dom"
        
        if not dom_dir.exists():
            return snapshots
        
        # 加载所有 snapshot 文件
        for snapshot_file in sorted(dom_dir.glob("snapshot_*.json")):
            try:
                with open(snapshot_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                rrweb_event = data.get('rrwebEvent', {})
                event_type = rrweb_event.get('type')
                
                # 支持 Full Snapshot (type=2) 和 Incremental Snapshot (type=3)
                if event_type in [2, 3]:
                    snapshots.append({
                        'file': snapshot_file,
                        'data': data,
                        'timestamp': data.get('timestamp', 0),
                        'event_type': event_type,
                        'url': data.get('url', ''),
                        'title': data.get('title', '')
                    })
            except Exception as e:
                continue
        
        # 按时间戳排序
        snapshots.sort(key=lambda s: s['timestamp'])
        return snapshots
    
    def _rebuild_dom_state(self, snapshots: List[Dict], task_path: Path) -> Optional[Dict]:
        """
        重建 DOM 状态
        从 Full Snapshot 开始，应用所有 Incremental Snapshot
        """
        if not snapshots:
            return None
        
        # 获取当前 URL 的时间戳范围
        first_snapshot = snapshots[0]
        last_snapshot = snapshots[-1]
        first_timestamp = first_snapshot.get('timestamp', 0)
        last_timestamp = last_snapshot.get('timestamp', 0)
        current_url = first_snapshot.get('url', '')
        
        # 【关键修复】从 rrweb_events.json 加载与当前 URL 时间戳最接近的完整快照
        rrweb_events_file = task_path / "dom" / "rrweb_events.json"
        if rrweb_events_file.exists():
            try:
                with open(rrweb_events_file, 'r', encoding='utf-8') as f:
                    rrweb_events = json.load(f)
                
                # 找到所有完整快照 (type=2) 并选择时间戳最接近的
                best_full_snapshot = None
                best_time_diff = float('inf')
                
                for event in rrweb_events:
                    if event.get('type') == 2:  # Full Snapshot
                        event_timestamp = event.get('timestamp', 0)
                        # 计算与当前 URL 时间范围的距离
                        time_diff = abs(event_timestamp - first_timestamp)
                        
                        if time_diff < best_time_diff:
                            best_time_diff = time_diff
                            best_full_snapshot = event
                
                if best_full_snapshot:
                    rrweb_data = best_full_snapshot.get('data', {})
                    root_node = rrweb_data.get('node', {})
                    nodes_array = rrweb_data.get('nodes', [])
                    
                    # 构建节点 ID 到节点的映射
                    self.nodes_map = {}
                    for node in nodes_array:
                        if isinstance(node, dict) and 'id' in node:
                            self.nodes_map[node['id']] = node
                    
                    # 将 ID 引用转换为实际节点引用
                    dom_tree = self._resolve_node_references(root_node)
                    
                    print(f"    使用完整快照: timestamp={best_full_snapshot.get('timestamp')}, 节点数={len(nodes_array)}")
                    
                    return {
                        'dom_tree': dom_tree,
                        'url': current_url,
                        'title': first_snapshot.get('title', ''),
                        'timestamp': first_timestamp
                    }
            except Exception as e:
                print(f"    从 rrweb_events.json 加载失败: {e}")
        
        # 回退到原来的逻辑
        # 找到第一个 Full Snapshot
        full_snapshot = None
        for snapshot in snapshots:
            if snapshot['event_type'] == 2:  # Full Snapshot
                full_snapshot = snapshot
                break
        
        if not full_snapshot:
            # 如果没有 Full Snapshot，使用第一个可用的快照
            full_snapshot = snapshots[0]
        
        # 获取初始 DOM 树
        rrweb_event = full_snapshot['data'].get('rrwebEvent', {})
        rrweb_data = rrweb_event.get('data', {})
        root_node = rrweb_data.get('node', {})
        nodes_array = rrweb_data.get('nodes', [])
        
        # 构建节点 ID 到节点的映射
        self.nodes_map = {}
        for node in nodes_array:
            if isinstance(node, dict) and 'id' in node:
                self.nodes_map[node['id']] = node
        
        # 将 ID 引用转换为实际节点引用
        dom_tree = self._resolve_node_references(root_node)
        
        return {
            'dom_tree': dom_tree,
            'url': full_snapshot.get('url', ''),
            'title': full_snapshot.get('title', ''),
            'timestamp': full_snapshot['timestamp']
        }
    
    def _resolve_node_references(self, node: Dict) -> Dict:
        """将节点中的 ID 引用解析为实际节点"""
        if not isinstance(node, dict):
            return node
        
        result = node.copy()
        
        # 解析 childNodes（从 ID 数组到节点数组）
        if 'childNodes' in result:
            child_ids = result['childNodes']
            resolved_children = []
            for child_id in child_ids:
                if isinstance(child_id, int) and child_id in self.nodes_map:
                    child_node = self.nodes_map[child_id]
                    resolved_child = self._resolve_node_references(child_node)
                    resolved_children.append(resolved_child)
            result['childNodes'] = resolved_children
        
        return result
    
    def _extract_resources(self, task_path: Path):
        """提取资源文件（CSS、JS、图片）"""
        resources_dir = task_path / "network" / "resources"
        
        if not resources_dir.exists():
            return
        
        # 收集 CSS、JS 和图片文件
        for resource_file in resources_dir.iterdir():
            if not resource_file.is_file():
                continue
                
            suffix = resource_file.suffix.lower()
            
            if suffix == '.css':
                self.external_css.append(resource_file)
            elif suffix == '.js':
                self.scripts.append(resource_file)
            elif suffix in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp', '.ico']:
                # 存储图片映射（文件名 -> 路径）
                self.images[resource_file.name] = resource_file
                # 也存储去掉哈希的版本
                clean_name = self._clean_filename(resource_file.name)
                if clean_name and clean_name != resource_file.name:
                    self.images[clean_name] = resource_file
                # 也存储去重后缀的版本（如 .png.png -> .png）
                deduped_name = self._normalize_filename(resource_file.name)
                if deduped_name != resource_file.name and deduped_name not in self.images:
                    self.images[deduped_name] = resource_file
                # 同时存储去重+去哈希的版本
                clean_deduped = self._clean_filename(deduped_name)
                if clean_deduped != deduped_name and clean_deduped not in self.images:
                    self.images[clean_deduped] = resource_file
                # 【新增】存储 @2x/_2x 转换版本（DOM中常用@2x，但文件名用_2x）
                at2x_name = resource_file.name.replace('_2x', '@2x')
                if at2x_name != resource_file.name and at2x_name not in self.images:
                    self.images[at2x_name] = resource_file
                # 【新增】存储 @3x/_3x 转换版本
                at3x_name = resource_file.name.replace('_3x', '@3x')
                if at3x_name != resource_file.name and at3x_name not in self.images:
                    self.images[at3x_name] = resource_file
                # 【关键新增】存储去掉时间戳前缀的版本
                # 例如：1778678926979_banner_company_structure.png -> banner_company_structure.png
                no_timestamp = self._remove_timestamp_prefix(resource_file.name)
                if no_timestamp != resource_file.name and no_timestamp not in self.images:
                    self.images[no_timestamp] = resource_file
                    # 同时存储去掉时间戳+去哈希的版本
                    clean_no_timestamp = self._clean_filename(no_timestamp)
                    if clean_no_timestamp != no_timestamp and clean_no_timestamp not in self.images:
                        self.images[clean_no_timestamp] = resource_file
    
    def _clean_filename(self, filename: str) -> str:
        """清理文件名（去掉哈希）"""
        # 处理带哈希的文件名，如 logo.123456.png -> logo.png
        parts = filename.split('.')
        if len(parts) >= 3:
            # 去掉中间的哈希部分
            return f"{parts[0]}.{parts[-1]}"
        return filename
    
    def _build_html_from_state(self, dom_state: Dict, task_path: Path) -> str:
        """从 DOM 状态构建完整 HTML（结合 CSS、JS、图片、AJAX数据）"""
        url = dom_state.get('url', '')
        title = dom_state.get('title', 'Prototype')
        dom_tree = dom_state.get('dom_tree', {})

        # 【关键修复】分别提取 head 和 body 的内容
        head_content = self._extract_head_content(dom_tree)
        body_content = self._extract_body_content(dom_tree)

        # 收集并内联 CSS
        styles = self._collect_and_inline_css(task_path)

        # 收集并内联 JS
        scripts = self._collect_and_inline_js(task_path)

        # 【新增】加载并注入 AJAX 响应数据拦截脚本
        ajax_interceptor = self._build_ajax_interceptor(task_path)

        # 【新增】构建 <head> 中的全局修复脚本（必须在所有其他 JS 之前执行）
        head_fixes = self._build_head_fixes()

        # 【关键修复】构建 base 标签，解决 file 协议安全限制问题
        base_tag = self._build_base_tag(url)

        # 【关键修复】构建 favicon 标签，防止 404 错误
        favicon_tag = self._build_favicon_tag(task_path)

        # 构建完整 HTML
        html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    {base_tag}
    <title>{title}</title>
    {favicon_tag}
    <style>
{styles}
    </style>
    {head_fixes}
    {head_content}
</head>
<body>
{body_content}
{ajax_interceptor}
{scripts}
</body>
</html>'''

        return html
    
    def _extract_head_content(self, node: Dict) -> str:
        """从 DOM 树中提取 head 标签内的内容"""
        if not isinstance(node, dict):
            return ""
        
        node_type = node.get('type')
        tag = node.get('tagName', '').lower() if node_type == 2 else ''
        
        # 找到 head 标签
        if node_type == 2 and tag == 'head':
            return self._children_to_html(node.get('childNodes', []))
        
        # 递归查找 head
        if node_type in [0, 2]:  # 文档节点或元素节点
            for child in node.get('childNodes', []):
                result = self._extract_head_content(child)
                if result:
                    return result
        
        return ""
    
    def _extract_body_content(self, node: Dict) -> str:
        """从 DOM 树中提取 body 标签内的内容"""
        if not isinstance(node, dict):
            return ""
        
        node_type = node.get('type')
        tag = node.get('tagName', '').lower() if node_type == 2 else ''
        
        # 找到 body 标签
        if node_type == 2 and tag == 'body':
            return self._children_to_html(node.get('childNodes', []))
        
        # 如果是 html 标签，处理其子节点（跳过 head）
        if node_type == 2 and tag == 'html':
            result = []
            for child in node.get('childNodes', []):
                child_tag = child.get('tagName', '').lower() if child.get('type') == 2 else ''
                if child_tag != 'head':
                    result.append(self._node_to_html(child))
            return ''.join(result)
        
        # 递归查找 body
        if node_type == 0:  # 文档节点
            for child in node.get('childNodes', []):
                result = self._extract_body_content(child)
                if result:
                    return result
        
        # 默认处理所有子节点
        return self._children_to_html(node.get('childNodes', []))
    
    def _node_to_html(self, node: Dict) -> str:
        """将 rrweb 节点转换为 HTML 字符串（结合资源）"""
        if not isinstance(node, dict):
            return ""
        
        node_type = node.get('type')
        
        # 文档节点
        if node_type == 0:
            return self._children_to_html(node.get('childNodes', []))
        
        # 文档类型节点
        elif node_type == 1:
            return ""
        
        # 元素节点
        elif node_type == 2:
            return self._element_to_html(node)
        
        # 文本节点
        elif node_type == 3:
            text = node.get('textContent', '')
            return self._escape_html(text)
        
        # CDATA 节点
        elif node_type == 4:
            return node.get('textContent', '')
        
        # 未知类型，尝试处理子节点
        else:
            return self._children_to_html(node.get('childNodes', []))
    
    def _element_to_html(self, node: Dict) -> str:
        """转换元素节点（处理图片资源）"""
        tag = node.get('tagName', 'div').lower()
        attributes = node.get('attributes', {}).copy()
        
        # 跳过 script 和 style 标签（我们单独处理）
        if tag in ['script', 'style']:
            return ""
        
        # 处理 iframe（安全考虑）
        if tag == 'iframe':
            return ""
        
        # 【关键修复】跳过 html, head, body 标签，直接处理其子节点
        # 这些标签已经在 _build_html_from_state 中生成，避免嵌套
        if tag in ['html', 'head', 'body']:
            return self._children_to_html(node.get('childNodes', []))
        
        # 【新增】处理 link 标签（CSS 文件）- 跳过外部 CSS，因为我们会内联所有 CSS
        if tag == 'link':
            rel = attributes.get('rel', '').lower()
            href = attributes.get('href', '')
            # 如果是 CSS 文件链接，跳过（我们会在 head 中内联所有 CSS）
            if rel == 'stylesheet' and href:
                return ""
        
        # 处理图片标签 - 替换 src 为 base64
        if tag == 'img':
            src = attributes.get('src', '')
            if src and not src.startswith('data:'):
                # 【通用修复】处理占位符图片（如 ***）
                # 问题：DOM 快照中可能包含占位符而非真实图片路径
                # 解决：替换为透明的 1x1 像素 base64 图片
                if src in ['***', '###', '...', ''] or len(src) < 5:
                    attributes['src'] = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
                else:
                    # 查找对应的图片资源（包括外部 CDN 图片）
                    img_path = self._find_image_resource(src)
                    if img_path:
                        img_data = self._image_to_base64(img_path)
                        if img_data:
                            attributes['src'] = img_data
        
        # 处理背景图片（在 style 属性中）
        if 'style' in attributes:
            style = attributes['style']
            # 查找 url() 中的图片引用
            style = self._process_style_images(style)
            attributes['style'] = style
        
        # 【修复】处理 data-bg 属性 - 将图片内联到 style 中，但保留 data-bg 属性
        # 这样 JS 可以正常读取 data-bg，不会生成 undefined 路径
        if 'data-bg' in attributes:
            data_bg = attributes['data-bg']
            style = attributes.get('style', '')
            # 如果 style 中还没有内联背景图片，尝试查找并内联
            if not ('background-image' in style and 'data:image' in style):
                # 尝试查找并内联 data-bg 图片
                img_path = self._find_image_resource(data_bg)
                if img_path:
                    img_data = self._image_to_base64(img_path)
                    if img_data:
                        # 将图片内联到 style 中
                        if 'style' in attributes:
                            attributes['style'] += f'; background-image: url({img_data});'
                        else:
                            attributes['style'] = f'background-image: url({img_data});'
                        print(f"    [修复] data-bg 图片已内联: {data_bg}")
                else:
                    # 图片不存在，保留 data-bg 属性，但打印警告
                    print(f"    [警告] data-bg 图片不存在: {data_bg}")
        
        # 构建属性字符串
        attr_str = ""
        for key, value in attributes.items():
            if key and value and not key.startswith('on'):  # 跳过事件属性
                # 处理布尔属性
                if isinstance(value, bool):
                    if value:
                        attr_str += f' {key}'
                else:
                    attr_str += f' {key}="{self._escape_attr(str(value))}"'
        
        # 处理自闭合标签
        self_closing = ['img', 'br', 'hr', 'input', 'meta', 'link', 'area', 'base', 'col', 'embed', 'param', 'source', 'track', 'wbr']
        
        if tag in self_closing:
            return f"<{tag}{attr_str}>"
        
        # 处理子节点
        children = self._children_to_html(node.get('childNodes', []))
        
        return f"<{tag}{attr_str}>{children}</{tag}>"
    
    def _find_image_resource(self, src: str) -> Optional[Path]:
        """查找对应的图片资源"""
        src_name = Path(src).name
        
        # 直接匹配
        if src_name in self.images:
            return self.images[src_name]
        
        # 处理 @2x -> _2x 的转换
        normalized_name = src_name.replace('@2x', '_2x').replace('@3x', '_3x')
        if normalized_name in self.images:
            return self.images[normalized_name]
        
        # 处理重复后缀的情况（如 .png.png -> .png）
        deduped_name = self._normalize_filename(src_name)
        if deduped_name != src_name and deduped_name in self.images:
            return self.images[deduped_name]
        
        # 同时尝试 @2x/_2x + 去重后缀的组合
        deduped_normalized = self._normalize_filename(normalized_name)
        if deduped_normalized in self.images:
            return self.images[deduped_normalized]
        
        # 清理后的文件名匹配
        clean_name = self._clean_filename(src_name)
        if clean_name in self.images:
            return self.images[clean_name]
        
        # 【新增】处理后缀匹配：资源文件有时间戳前缀，但 DOM 中没有
        # 例如：1778678864642_icon_95551_92_2x.44efe523.png -> icon_95551_92_2x.44efe523.png
        for name, path in self.images.items():
            # 去掉资源文件的时间戳前缀进行匹配
            resource_base = self._remove_timestamp_prefix(name)
            if resource_base == src_name or resource_base == normalized_name:
                return path
            if resource_base == deduped_name or resource_base == deduped_normalized:
                return path
            
            # 【关键修复】处理 data-bg 属性匹配
            # DOM 中的文件名可能是 banner_company_structure.png
            # 资源文件名是 1778678926979_banner_company_structure.png
            # 去掉时间戳前缀后，还需要去掉哈希后缀进行匹配
            resource_no_hash = self._remove_hash_suffix(resource_base)
            src_no_hash = self._remove_hash_suffix(src_name)
            if resource_no_hash == src_no_hash:
                return path
            if resource_no_hash == self._remove_hash_suffix(normalized_name):
                return path
            if resource_no_hash == self._remove_hash_suffix(deduped_name):
                return path
            if resource_no_hash == self._remove_hash_suffix(deduped_normalized):
                return path
        
        # 提取核心文件名（去掉哈希和重复后缀）进行模糊匹配
        src_base = self._extract_base_name(src_name)
        for name, path in self.images.items():
            # 检查是否包含相同的核心名称
            if src_base and src_base in name:
                return path
            # 反向检查：资源文件的核心名是否在 src 中
            img_base = self._extract_base_name(name)
            if img_base and img_base in src_name:
                return path
            # 检查去掉重复后缀后的匹配
            normalized_img_name = self._normalize_filename(name)
            if normalized_img_name == src_name or normalized_img_name == deduped_name:
                return path
        
        return None
    
    def _remove_timestamp_prefix(self, filename: str) -> str:
        """去掉文件名的时间戳前缀（如 1778678864642_icon.png -> icon.png）"""
        # 匹配时间戳前缀：13位数字 + 下划线
        import re
        match = re.match(r'^\d{13}_(.+)$', filename)
        if match:
            return match.group(1)
        return filename
    
    def _extract_base_name(self, filename: str) -> str:
        """提取文件名的核心部分（去掉哈希和扩展名）"""
        # 首先去掉重复后缀：icon.png.png -> icon.png
        name = self._normalize_filename(filename)
        
        # 然后去掉扩展名：icon.png -> icon
        stem = Path(name).stem
        
        # 去掉 .hash 部分（如 icon.44efe523 -> icon）
        parts = stem.split('.')
        if len(parts) >= 2:
            # 检查最后一部分是否像哈希（8-10位十六进制）
            last_part = parts[-1]
            if len(last_part) >= 6 and all(c in '0123456789abcdefABCDEF' for c in last_part):
                return '.'.join(parts[:-1])
        
        return stem
    
    def _normalize_filename(self, filename: str) -> str:
        """标准化文件名（处理重复后缀）"""
        # 处理 .png.png -> .png 的情况
        for ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp']:
            double_ext = ext + ext
            if filename.endswith(double_ext):
                filename = filename[:-len(ext)]
        return filename
    
    def _remove_hash_suffix(self, filename: str) -> str:
        """去掉文件名的哈希后缀（如 banner.44efe523.png -> banner.png）"""
        import re
        # 匹配 .hash.extension 模式
        match = re.match(r'^(.+)\.([a-f0-9]{6,10})\.(png|jpg|jpeg|gif|svg|webp)$', filename, re.IGNORECASE)
        if match:
            return f"{match.group(1)}.{match.group(3)}"
        return filename
    
    def _image_to_base64(self, img_path: Path) -> Optional[str]:
        """将图片转换为 base64"""
        try:
            with open(img_path, 'rb') as f:
                img_data = base64.b64encode(f.read()).decode()
            
            ext = img_path.suffix.lower().replace('.', '')
            if ext == 'jpg':
                ext = 'jpeg'
            elif ext == 'svg':
                ext = 'svg+xml'
            
            return f"data:image/{ext};base64,{img_data}"
        except Exception as e:
            print(f"    图片转 base64 失败: {e}")
            return None
    
    def _process_style_images(self, style: str) -> str:
        """处理 style 属性中的图片引用"""
        if not style:
            return style
        
        # 匹配 url() 中的图片引用
        import re
        url_pattern = r'url\s*\(\s*["\']?([^"\')]+\.(?:png|jpg|jpeg|gif|svg|webp))["\']?\s*\)'
        
        def replace_url(match):
            img_ref = match.group(1)
            img_path = self._find_image_resource(img_ref)
            if img_path:
                img_data = self._image_to_base64(img_path)
                if img_data:
                    return f'url("{img_data}")'
            return 'none'
        
        return re.sub(url_pattern, replace_url, style, flags=re.IGNORECASE)
    
    def _children_to_html(self, children: List[Dict]) -> str:
        """转换子节点列表"""
        if not children:
            return ""
        
        html = ""
        for child in children:
            html += self._node_to_html(child)
        return html
    
    def _collect_and_inline_css(self, task_path: Path) -> str:
        """收集并内联所有 CSS"""
        styles = []
        
        # 1. 添加基础重置样式
        styles.append(self._get_reset_css())
        
        # 2. 从资源文件加载 CSS 并处理其中的图片
        resources_dir = task_path / "network" / "resources"
        if resources_dir.exists():
            for css_file in sorted(resources_dir.glob("*.css")):
                try:
                    with open(css_file, 'r', encoding='utf-8', errors='ignore') as f:
                        css_content = f.read()
                    
                    # 处理 CSS 中的图片引用
                    css_content = self._process_css_images(css_content)
                    
                    # 清理 CSS
                    css_content = self._clean_css(css_content)
                    
                    styles.append(css_content)
                except Exception as e:
                    continue
        
        return "\n".join(styles)
    
    def _process_css_images(self, css_content: str) -> str:
        """处理 CSS 中的图片引用"""
        import re
        url_pattern = r'url\s*\(\s*["\']?([^"\')]+\.(?:png|jpg|jpeg|gif|svg|webp))["\']?\s*\)'
        
        def replace_url(match):
            img_ref = match.group(1)
            img_path = self._find_image_resource(img_ref)
            if img_path:
                img_data = self._image_to_base64(img_path)
                if img_data:
                    return f'url("{img_data}")'
            return 'none'
        
        return re.sub(url_pattern, replace_url, css_content, flags=re.IGNORECASE)
    
    def _collect_and_inline_js(self, task_path: Path) -> str:
        """收集并内联所有 JS（按依赖顺序）"""
        scripts = []
        
        resources_dir = task_path / "network" / "resources"
        if not resources_dir.exists():
            return ""
        
        # 获取所有 JS 文件
        js_files = list(resources_dir.glob("*.js"))
        
        # 定义加载优先级（按顺序）
        # 注意：更具体的匹配应该在前，避免 'jquery-migrate' 匹配 'jquery' 但排在主库之前
        priority_order = [
            ('jquery-1', 0),      # jQuery 1.x 主库最先
            ('jquery-2', 0),      # jQuery 2.x 主库最先
            ('jquery-3', 0),      # jQuery 3.x 主库最先
            ('jquery.min', 0),    # jQuery minified 主库
            ('jquery-migrate', 1), # jQuery Migrate 必须在主库之后
            ('bootstrap', 2),     # Bootstrap 依赖 jQuery
            ('polyfill', 3),      # Polyfill
            ('swiper', 4),        # Swiper
            ('video', 5),         # Video.js
        ]
        
        # 按优先级排序
        def get_priority(filepath: Path) -> int:
            name_lower = filepath.name.lower()
            # 先检查特定匹配
            for keyword, priority in priority_order:
                if keyword in name_lower:
                    return priority
            # 检查通用 jQuery（排除 migrate）
            if 'jquery' in name_lower and 'migrate' not in name_lower:
                return 0
            return 100  # 其他文件最后
        
        js_files.sort(key=get_priority)
        
        for js_file in js_files:
            try:
                with open(js_file, 'r', encoding='utf-8', errors='ignore') as f:
                    js_content = f.read()
                
                # 简单的 JS 清理
                js_content = self._clean_js(js_content)
                
                if js_content.strip():
                    scripts.append(f'<script>\n{js_content}\n</script>')
            except Exception as e:
                continue

        return "\n".join(scripts)

    def _build_base_tag(self, url: str) -> str:
        """构建 base 标签，解决 file 协议安全限制问题

        当使用 file 协议打开页面时，浏览器会将每个 file URL 视为独立的安全源。
        这会导致跨 frame 访问、AJAX 请求等问题。添加 base 标签可以模拟一个一致的源。
        """
        if not url:
            return '<base href="./">'

        try:
            parsed = urlparse(url)
            if parsed.scheme in ('http', 'https'):
                # 使用原始 URL 的目录作为 base
                base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path.rsplit('/', 1)[0]}/"
                return f'<base href="{base_url}">'
        except Exception:
            pass

        return '<base href="./">'

    def _build_favicon_tag(self, task_path: Path) -> str:
        """构建 favicon 标签，防止 404 错误

        如果存在 favicon 资源，使用它；否则使用透明像素 base64 数据。
        """
        # 查找 favicon 文件
        resources_dir = task_path / "network" / "resources"
        if resources_dir.exists():
            for favicon_name in ['favicon.ico', 'favicon.png', 'favicon.svg']:
                favicon_file = resources_dir / favicon_name
                if favicon_file.exists():
                    return f'<link rel="icon" type="image/x-icon" href="network/resources/{favicon_name}">'

        # 使用透明像素作为默认 favicon
        transparent_pixel = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=='
        return f'<link rel="icon" type="image/png" href="{transparent_pixel}">'

    def _clean_css(self, css: str) -> str:
        """清理 CSS 内容"""
        # 移除 @import
        css = re.sub(r'@import\s+[^;]+;', '', css)
        return css
    
    def _clean_js(self, js: str) -> str:
        """清理 JS 内容"""
        import re
        
        # 移除 document.write 等危险操作
        js = re.sub(r'document\.write\s*\([^)]+\)', '/* document.write removed */', js)
        
        # 【新增】替换 JS 中的图片路径为 base64
        # 匹配常见的图片路径模式：/path/to/image.png 或 ./image.png
        
        def replace_img_path(match):
            full_match = match.group(0)
            img_path = match.group(1)
            # 跳过 data: 和 http: 开头的路径
            if img_path.startswith(('data:', 'http', '//')):
                return full_match
            # 尝试查找对应的图片资源
            img_file = self._find_image_resource(img_path)
            if img_file:
                img_data = self._image_to_base64(img_file)
                if img_data:
                    # 保留引号，替换路径
                    quote = '"' if '"' in full_match else "'"
                    return full_match.replace(img_path, img_data)
            return full_match
        
        # 匹配字符串中的图片路径
        js = re.sub(
            r'["\']([^"\']+\.(?:png|jpg|jpeg|gif|svg|webp))["\']',
            replace_img_path,
            js,
            flags=re.IGNORECASE
        )
        
        # 【通用修复】修复 webpack 错误的 base64 URL 拼接
        # 问题：__webpack_require__.p + "data:image/..." 会生成 /newsite/data:image/...
        # 解决：移除 __webpack_require__.p + 前缀，直接使用 base64 数据
        js = re.sub(
            r'__webpack_require__\.p\s*\+\s*"(data:image/[^"]+)"',
            r'"\1"',
            js
        )
        
        # 【通用修复】修复多行 base64 数据（移除换行符和空格）
        # 问题：base64 数据被格式化成多行，导致浏览器解析失败
        # 解决：将多行 base64 合并成一行
        def fix_multiline_base64(match):
            prefix = match.group(1)  # "data:image/... 或 url(data:image/...
            base64_data = match.group(2)
            # 移除所有换行符和多余空格
            fixed_data = re.sub(r'\s+', '', base64_data)
            return f'{prefix}{fixed_data}"'
        
        # 修复 JS 字符串中的多行 base64
        js = re.sub(
            r'("data:image/[^"]*\n[^"]*)"',
            fix_multiline_base64,
            js
        )
        
        return js
    
    def _build_head_fixes(self) -> str:
        """构建 <head> 中的全局修复脚本（必须在所有其他 JS 之前执行）"""
        return '''<script>
// 【Sentinel】全局错误捕获和变量预定义（必须在所有其他 JS 之前执行）
(function() {
    'use strict';
    
    // 【关键】全局错误处理器 - 捕获并显示所有未被捕获的错误
    window.addEventListener('error', function(event) {
        console.error('[Sentinel 全局错误捕获]', {
            message: event.message,
            filename: event.filename,
            lineno: event.lineno,
            colno: event.colno,
            error: event.error ? event.error.stack : 'N/A'
        });
        // 不阻止默认行为，让错误继续显示
        return false;
    });
    
    // 【关键】捕获 Promise 未处理的 rejection
    window.addEventListener('unhandledrejection', function(event) {
        console.error('[Sentinel Promise 错误捕获]', {
            reason: event.reason,
            stack: event.reason && event.reason.stack ? event.reason.stack : 'N/A'
        });
        // 不阻止默认行为
        return false;
    });
    
    // 【关键】拦截 console.error 以便记录所有错误
    const originalConsoleError = console.error;
    console.error = function() {
        // 调用原始方法
        originalConsoleError.apply(console, arguments);
        // 同时发送到全局错误收集器（如果有）
        if (window.SentinelErrorCollector) {
            window.SentinelErrorCollector.add('console.error', arguments);
        }
    };
    
    // 【关键】全局错误收集器
    window.SentinelErrorCollector = {
        errors: [],
        add: function(type, details) {
            this.errors.push({
                type: type,
                details: details,
                timestamp: new Date().toISOString()
            });
        },
        getAll: function() {
            return this.errors;
        },
        clear: function() {
            this.errors = [];
        }
    };
    
    // 【修复】神策数据 SDK (sensors)
    if (typeof window.sensors === 'undefined') {
        window.sensors = {
            track: function() { console.log('[Sentinel] sensors.track 被调用'); },
            login: function() {},
            logout: function() {},
            identify: function() {},
            init: function() { console.log('[Sentinel] sensors.init 被调用'); },
            quick: function() { console.log('[Sentinel] sensors.quick 被调用'); },
            registerPage: function() {},
            setProfile: function() {},
            setOnceProfile: function() {}
        };
        console.log('[Sentinel] sensors 已预定义');
    }
    
    // 【修复】神策数据别名 (sa)
    if (typeof window.sa === 'undefined') {
        window.sa = window.sensors;
        console.log('[Sentinel] sa 已预定义');
    }
    
    // 【修复】Newsite 命名空间
    if (typeof window.Newsite === 'undefined') {
        window.Newsite = {};
        console.log('[Sentinel] Newsite 已预定义');
    }
    
    // 【修复】Newsite 常用属性（必须在页面 JS 执行前初始化）
    // 【重要】注意：实际代码使用 Newsite.Config（大写 C），不是 config
    if (!window.Newsite.Config) {
        window.Newsite.Config = {};
        console.log('[Sentinel] Newsite.Config 已预定义');
    }
    // 同时预定义小写版本以兼容
    if (!window.Newsite.config) {
        window.Newsite.config = window.Newsite.Config;
    }
    if (!window.Newsite.Config.history_list) {
        window.Newsite.Config.history_list = [];
        console.log('[Sentinel] Newsite.Config.history_list 已预定义');
    }
    // 同时预定义 Newsite.history_list 以兼容
    if (!window.Newsite.history_list) {
        window.Newsite.history_list = window.Newsite.Config.history_list;
    }
    // 【修复】honor_list 未定义错误
    if (!window.Newsite.Config.honor_list) {
        window.Newsite.Config.honor_list = [];
        console.log('[Sentinel] Newsite.Config.honor_list 已预定义');
    }
    // 【修复】securities_list 未定义错误
    if (!window.Newsite.Config.securities_list) {
        window.Newsite.Config.securities_list = [];
        console.log('[Sentinel] Newsite.Config.securities_list 已预定义');
    }
    if (!window.Newsite.api) {
        window.Newsite.api = {};
    }
    
    // 【修复】SensorsData 命名空间
    if (typeof window.SensorsData === 'undefined') {
        window.SensorsData = {};
        console.log('[Sentinel] SensorsData 已预定义');
    }
    
    // 【修复】Google Tag Manager (dataLayer)
    if (typeof window.dataLayer === 'undefined') {
        window.dataLayer = [];
    }
    
    // 【修复】Google Analytics (gtag)
    if (typeof window.gtag === 'undefined') {
        window.gtag = function() { window.dataLayer.push(arguments); };
    }
    
    // 【修复】百度统计 (_hmt)
    if (typeof window._hmt === 'undefined') {
        window._hmt = [];
    }
    
    // 【修复】微信 JS-SDK (wx)
    if (typeof window.wx === 'undefined') {
        window.wx = {
            ready: function(callback) { if(callback) callback(); },
            config: function() {},
            checkJsApi: function() {},
            onMenuShareTimeline: function() {},
            onMenuShareAppMessage: function() {},
            onMenuShareQQ: function() {},
            onMenuShareWeibo: function() {},
            onMenuShareQZone: function() {},
            updateTimelineShareData: function() {},
            updateAppMessageShareData: function() {},
            // 【新增】微信客户端信息
            Client: {
                isWechat: false,
                isMobile: false,
                isIOS: false,
                isAndroid: false,
                version: '0.0.0'
            }
        };
    }
    
    // 【新增】修复微信分享相关的其他全局变量
    if (typeof window.WeixinJSBridge === 'undefined') {
        window.WeixinJSBridge = {
            invoke: function() {},
            call: function() {},
            on: function() {}
        };
    }
    
    // 【新增】修复 JSSDK 未定义错误（银河证券自定义微信 SDK 封装）
    if (typeof window.JSSDK === 'undefined') {
        window.JSSDK = {
            Client: {
                isWeixin: function() { return false; },
                isWechat: function() { return false; },
                isMobile: function() { return false; },
                isIOS: function() { return false; },
                isAndroid: function() { return false; }
            },
            WxShare: {
                customShare: function() {
                    console.log('[Sentinel] JSSDK.WxShare.customShare 被调用');
                }
            }
        };
    }
    
    console.log('[Sentinel] 全局变量预定义完成');
})();

// 【通用能力】DOM 访问保护（必须在页面 JS 执行前设置）
(function() {
    'use strict';
    
    // 保存原始方法
    const originalGetElementById = document.getElementById;
    const originalQuerySelector = document.querySelector;
    const originalQuerySelectorAll = document.querySelectorAll;
    
    // 创建虚拟元素工厂
    function createDummyElement(type, identifier) {
        const dummy = document.createElement('div');
        if (type === 'id') {
            dummy.id = identifier;
        } else if (type === 'selector') {
            dummy.setAttribute('data-sentinel-dummy', identifier);
        }
        dummy.style.display = 'none';
        dummy.style.position = 'absolute';
        dummy.style.top = '0';
        dummy.style.left = '0';
        dummy.setAttribute('data-sentinel-created', 'true');
        
        // 【关键】将虚拟元素添加到 body，使 jQuery offset() 正常工作
        if (document.body) {
            document.body.appendChild(dummy);
        }
        
        // 虚拟元素支持 innerHTML 操作
        dummy._innerHTML = '';
        Object.defineProperty(dummy, 'innerHTML', {
            get: function() { return this._innerHTML; },
            set: function(value) { 
                this._innerHTML = value; 
                console.log('[Sentinel] 虚拟元素 innerHTML 被设置:', identifier);
            }
        });
        
        // 【新增】支持 jQuery offset() 方法
        dummy.getBoundingClientRect = function() {
            return { top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0 };
        };
        // 使用 Object.defineProperty 定义只读属性
        Object.defineProperty(dummy, 'offsetTop', { get: function() { return 0; }, configurable: true });
        Object.defineProperty(dummy, 'offsetLeft', { get: function() { return 0; }, configurable: true });
        Object.defineProperty(dummy, 'offsetHeight', { get: function() { return 0; }, configurable: true });
        Object.defineProperty(dummy, 'offsetWidth', { get: function() { return 0; }, configurable: true });
        Object.defineProperty(dummy, 'clientTop', { get: function() { return 0; }, configurable: true });
        Object.defineProperty(dummy, 'clientLeft', { get: function() { return 0; }, configurable: true });
        Object.defineProperty(dummy, 'clientHeight', { get: function() { return 0; }, configurable: true });
        Object.defineProperty(dummy, 'clientWidth', { get: function() { return 0; }, configurable: true });
        Object.defineProperty(dummy, 'scrollTop', { get: function() { return 0; }, configurable: true });
        Object.defineProperty(dummy, 'scrollLeft', { get: function() { return 0; }, configurable: true });
        
        // 【新增】支持 classList
        dummy.classList = {
            _classes: [],
            add: function() { console.log('[Sentinel] 虚拟元素 classList.add 被调用'); },
            remove: function() { console.log('[Sentinel] 虚拟元素 classList.remove 被调用'); },
            toggle: function() { return false; },
            contains: function() { return false; }
        };
        
        // 【新增】支持 addEventListener
        dummy.addEventListener = function() { console.log('[Sentinel] 虚拟元素 addEventListener 被调用'); };
        dummy.removeEventListener = function() {};
        
        return dummy;
    }
    
    // 包装 getElementById
    document.getElementById = function(id) {
        const element = originalGetElementById.call(document, id);
        if (!element) {
            console.warn('[Sentinel] getElementById 返回 null，创建虚拟元素:', id);
            return createDummyElement('id', id);
        }
        return element;
    };
    
    // 包装 querySelector
    document.querySelector = function(selector) {
        const element = originalQuerySelector.call(document, selector);
        if (!element) {
            console.warn('[Sentinel] querySelector 返回 null，创建虚拟元素:', selector);
            return createDummyElement('selector', selector);
        }
        return element;
    };
    
    // 包装 querySelectorAll - 返回包含虚拟元素的数组
    document.querySelectorAll = function(selector) {
        const elements = originalQuerySelectorAll.call(document, selector);
        if (!elements || elements.length === 0) {
            console.warn('[Sentinel] querySelectorAll 返回空结果，创建虚拟元素数组:', selector);
            // 返回包含一个虚拟元素的类数组对象
            const dummy = createDummyElement('selector', selector);
            return [dummy];
        }
        return elements;
    };
    
    console.log('[Sentinel] DOM 访问保护已启用');
})();

// 【关键修复】jQuery offset() 保护 - 确保空选择器返回有效 offset 对象
(function() {
    'use strict';
    
    // 等待 jQuery 加载
    function setupJQueryOffsetFix() {
        if (!window.jQuery) {
            return false;
        }
        
        const $ = window.jQuery;
        
        // 保存原始的 offset 方法
        const originalOffset = $.fn.offset;
        
        // 重写 offset 方法
        $.fn.offset = function() {
            // 如果选择器为空（没有匹配元素），返回一个带有默认值的对象
            if (this.length === 0) {
                console.warn('[Sentinel] jQuery offset() 被调用在空选择器上，返回默认值');
                return { top: 0, left: 0 };
            }
            
            // 对于非空选择器，调用原始方法
            // 但如果原始方法返回 undefined 或 null，也返回默认值
            const result = originalOffset.apply(this, arguments);
            if (result === undefined || result === null) {
                console.warn('[Sentinel] jQuery offset() 返回 undefined，使用默认值');
                return { top: 0, left: 0 };
            }
            return result;
        };
        
        console.log('[Sentinel] jQuery offset() 保护已启用');
        return true;
    }
    
    // 立即尝试设置
    if (!setupJQueryOffsetFix()) {
        // 如果 jQuery 还没加载，等待它加载
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', function() {
                setupJQueryOffsetFix();
            });
        } else {
            // DOM 已加载，直接尝试
            setupJQueryOffsetFix();
        }
        
        // 也监听 jQuery 可能稍后加载的情况
        let checkCount = 0;
        const checkInterval = setInterval(function() {
            if (setupJQueryOffsetFix() || checkCount++ > 50) {
                clearInterval(checkInterval);
            }
        }, 100);
    }
})();

// 【关键修复】图片加载拦截器 - 阻止 undefined 或无效路径的图片请求
(function() {
    'use strict';
    
    // 透明 1x1 像素图片
    const TRANSPARENT_PIXEL = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==';
    
    // 检查值是否是无效的图片路径
    function isInvalidImagePath(value) {
        if (!value || value === 'undefined' || value === 'null') {
            return true;
        }
        const strValue = String(value);
        // 检查是否包含 undefined 或 null（包括 url(undefined) 的情况）
        if (strValue.includes('undefined') || strValue.includes('null')) {
            return true;
        }
        return false;
    }
    
    // 拦截 Image 构造函数
    const OriginalImage = window.Image;
    window.Image = function(width, height) {
        const img = new OriginalImage(width, height);
        
        // 拦截 src 属性的设置
        const originalDescriptor = Object.getOwnPropertyDescriptor(HTMLImageElement.prototype, 'src');
        if (originalDescriptor) {
            Object.defineProperty(img, 'src', {
                get: function() {
                    return originalDescriptor.get.call(this);
                },
                set: function(value) {
                    if (isInvalidImagePath(value)) {
                        console.warn('[Sentinel] 拦截无效图片路径 (Image.src):', value);
                        originalDescriptor.set.call(this, TRANSPARENT_PIXEL);
                        return;
                    }
                    originalDescriptor.set.call(this, value);
                }
            });
        }
        
        return img;
    };
    
    // 复制原始 Image 的静态属性和方法
    for (const key in OriginalImage) {
        if (OriginalImage.hasOwnProperty(key)) {
            window.Image[key] = OriginalImage[key];
        }
    }
    
    // 拦截 setAttribute 方法
    const originalSetAttribute = Element.prototype.setAttribute;
    Element.prototype.setAttribute = function(name, value) {
        // 检查是否是图片相关属性
        if (name && (name.toLowerCase() === 'src' || name.toLowerCase() === 'href')) {
            if (isInvalidImagePath(value)) {
                console.warn('[Sentinel] 拦截无效图片路径 (setAttribute):', name, '=', value);
                return originalSetAttribute.call(this, name, TRANSPARENT_PIXEL);
            }
        }
        return originalSetAttribute.call(this, name, value);
    };
    
    // 拦截 CSSStyleDeclaration 的 backgroundImage 属性
    const originalBackgroundImage = Object.getOwnPropertyDescriptor(CSSStyleDeclaration.prototype, 'backgroundImage');
    if (originalBackgroundImage) {
        Object.defineProperty(CSSStyleDeclaration.prototype, 'backgroundImage', {
            get: originalBackgroundImage.get,
            set: function(value) {
                if (isInvalidImagePath(value)) {
                    console.warn('[Sentinel] 拦截无效背景图片:', value);
                    return originalBackgroundImage.set.call(this, 'none');
                }
                return originalBackgroundImage.set.call(this, value);
            }
        });
    }
    
    // 拦截 CSSStyleDeclaration 的 setProperty 方法
    const originalSetProperty = CSSStyleDeclaration.prototype.setProperty;
    CSSStyleDeclaration.prototype.setProperty = function(propertyName, value, priority) {
        if (propertyName && (propertyName.toLowerCase().includes('background') || propertyName.toLowerCase().includes('image'))) {
            if (isInvalidImagePath(value)) {
                console.warn('[Sentinel] 拦截无效 CSS 图片属性:', propertyName, '=', value);
                return originalSetProperty.call(this, propertyName, 'none', priority);
            }
        }
        return originalSetProperty.call(this, propertyName, value, priority);
    };
    
    // 【关键修复】拦截 HTMLElement.style 的访问，包装 CSSStyleDeclaration 以拦截 backgroundImage 设置
    const originalStyleDescriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'style');
    if (originalStyleDescriptor) {
        Object.defineProperty(HTMLElement.prototype, 'style', {
            get: function() {
                const styleObj = originalStyleDescriptor.get.call(this);
                if (!styleObj || styleObj._sentinelWrapped) {
                    return styleObj;
                }
                
                // 标记已包装
                styleObj._sentinelWrapped = true;
                
                // 拦截 backgroundImage 属性的设置
                const originalBgDescriptor = Object.getOwnPropertyDescriptor(styleObj, 'backgroundImage');
                if (originalBgDescriptor && originalBgDescriptor.set) {
                    const originalSetter = originalBgDescriptor.set;
                    Object.defineProperty(styleObj, 'backgroundImage', {
                        get: originalBgDescriptor.get,
                        set: function(value) {
                            if (isInvalidImagePath(value)) {
                                console.warn('[Sentinel] 拦截无效 backgroundImage (HTMLElement.style):', value);
                                return originalSetter.call(this, 'none');
                            }
                            return originalSetter.call(this, value);
                        },
                        configurable: true
                    });
                }
                
                return styleObj;
            },
            set: originalStyleDescriptor.set,
            configurable: true
        });
    }
    
    // 拦截 DOM 中已存在的 img 元素的 src 属性修改
    if (window.MutationObserver) {
        const observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                if (mutation.type === 'attributes' && mutation.attributeName === 'src') {
                    const target = mutation.target;
                    if (target.tagName === 'IMG') {
                        const src = target.getAttribute('src');
                        if (isInvalidImagePath(src)) {
                            console.warn('[Sentinel] 拦截 MutationObserver 检测到的无效图片路径:', src);
                            target.setAttribute('src', TRANSPARENT_PIXEL);
                        }
                    }
                }
            });
        });
        
        // 观察整个文档
        if (document.body) {
            observer.observe(document.body, {
                attributes: true,
                attributeFilter: ['src'],
                subtree: true
            });
        } else {
            // 如果 body 还不存在，等待 DOMContentLoaded
            document.addEventListener('DOMContentLoaded', function() {
                observer.observe(document.body, {
                    attributes: true,
                    attributeFilter: ['src'],
                    subtree: true
                });
            });
        }
    }
    
    console.log('[Sentinel] 图片加载拦截器已启用 (增强版)');
    
    // 【关键修复】页面加载完成后，修复所有无效的 backgroundImage
    function fixInvalidBackgroundImages() {
        const allElements = document.querySelectorAll('*');
        allElements.forEach(function(el) {
            const bgImage = el.style.backgroundImage;
            if (bgImage && isInvalidImagePath(bgImage)) {
                console.warn('[Sentinel] 修复无效的 backgroundImage:', bgImage, el);
                el.style.backgroundImage = 'none';
            }
        });
    }
    
    // 立即执行一次
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', fixInvalidBackgroundImages);
    } else {
        fixInvalidBackgroundImages();
    }
    
    // 定期检查和修复
    setInterval(fixInvalidBackgroundImages, 1000);
})();

// 【关键修复】修复 data[i].picPath 为 undefined 导致的图片加载错误
(function() {
    'use strict';
    
    // 保存原始 JSON.parse
    const originalJSONParse = JSON.parse;
    
    // 拦截 JSON.parse，修复 picPath 为 undefined 的情况
    JSON.parse = function(text, reviver) {
        const result = originalJSONParse.call(this, text, reviver);
        
        // 递归修复对象中的 picPath
        function fixPicPath(obj) {
            if (!obj || typeof obj !== 'object') return obj;
            
            if (Array.isArray(obj)) {
                for (let i = 0; i < obj.length; i++) {
                    obj[i] = fixPicPath(obj[i]);
                }
            } else {
                for (const key in obj) {
                    if (obj.hasOwnProperty(key)) {
                        if (key === 'picPath' && (obj[key] === undefined || obj[key] === null || obj[key] === 'undefined')) {
                            console.warn('[Sentinel] 修复 picPath 为 undefined:', obj);
                            obj[key] = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==';
                        } else if (typeof obj[key] === 'object') {
                            obj[key] = fixPicPath(obj[key]);
                        }
                    }
                }
            }
            return obj;
        }
        
        return fixPicPath(result);
    };
    
    // 拦截 XMLHttpRequest 的 response 属性，确保返回的数据中 picPath 不为 undefined
    const originalXhrOpen = XMLHttpRequest.prototype.open;
    const originalXhrSend = XMLHttpRequest.prototype.send;
    
    XMLHttpRequest.prototype.open = function(method, url, async, user, password) {
        this._sentinelUrl = url;
        return originalXhrOpen.apply(this, arguments);
    };
    
    XMLHttpRequest.prototype.send = function(body) {
        const xhr = this;
        const originalOnLoad = xhr.onload;
        
        xhr.onload = function() {
            // 检查响应内容类型
            const contentType = xhr.getResponseHeader('Content-Type');
            if (contentType && contentType.includes('application/json')) {
                try {
                    const response = JSON.parse(xhr.responseText);
                    // 递归修复 picPath
                    function fixPicPath(obj) {
                        if (!obj || typeof obj !== 'object') return obj;
                        
                        if (Array.isArray(obj)) {
                            for (let i = 0; i < obj.length; i++) {
                                obj[i] = fixPicPath(obj[i]);
                            }
                        } else {
                            for (const key in obj) {
                                if (obj.hasOwnProperty(key)) {
                                    if (key === 'picPath' && (obj[key] === undefined || obj[key] === null || obj[key] === 'undefined')) {
                                        console.warn('[Sentinel] 修复 XHR response 中的 picPath:', obj);
                                        obj[key] = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==';
                                    } else if (typeof obj[key] === 'object') {
                                        obj[key] = fixPicPath(obj[key]);
                                    }
                                }
                            }
                        }
                        return obj;
                    }
                    fixPicPath(response);
                } catch (e) {
                    // 不是有效的 JSON，记录警告
                    console.warn('[Sentinel] XHR response 不是有效的 JSON:', e.message);
                }
            }
            
            if (originalOnLoad) {
                originalOnLoad.apply(this, arguments);
            }
        };
        
        return originalXhrSend.apply(this, arguments);
    };
    
    console.log('[Sentinel] picPath 修复器已启用');
})();

// 【关键修复】拦截 Image 元素加载，阻止 undefined 或无效路径
(function() {
    'use strict';
    
    const TRANSPARENT_PIXEL = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==';
    
    // 检查是否是有效的图片路径
    function isValidImagePath(src) {
        if (!src || src === 'undefined' || src === 'null' || src === '') {
            return false;
        }
        // 检查是否包含 undefined 或 null 字符串（但不是作为 base64 的一部分）
        if (typeof src === 'string' && (src === 'undefined' || src === 'null' || src.includes('/undefined') || src.includes('/null'))) {
            return false;
        }
        return true;
    }
    
    // 拦截 Image 构造函数
    const OriginalImage = window.Image;
    window.Image = function(width, height) {
        const img = new OriginalImage(width, height);
        
        // 拦截 src 属性的设置
        const originalDescriptor = Object.getOwnPropertyDescriptor(HTMLImageElement.prototype, 'src');
        if (originalDescriptor) {
            Object.defineProperty(img, 'src', {
                get: function() {
                    return originalDescriptor.get.call(this);
                },
                set: function(value) {
                    if (!isValidImagePath(value)) {
                        console.warn('[Sentinel] 拦截无效图片路径 (Image.src):', value);
                        originalDescriptor.set.call(this, TRANSPARENT_PIXEL);
                        return;
                    }
                    originalDescriptor.set.call(this, value);
                }
            });
        }
        
        return img;
    };
    
    // 复制原始 Image 的静态属性和方法
    for (const key in OriginalImage) {
        if (OriginalImage.hasOwnProperty(key)) {
            window.Image[key] = OriginalImage[key];
        }
    }
    
    // 【关键修复】拦截 HTMLImageElement.prototype.setAttribute
    const originalSetAttribute = HTMLImageElement.prototype.setAttribute;
    HTMLImageElement.prototype.setAttribute = function(name, value) {
        if (name === 'src' && !isValidImagePath(value)) {
            console.warn('[Sentinel] 拦截无效图片路径 (setAttribute):', name, '=', value);
            return originalSetAttribute.call(this, name, TRANSPARENT_PIXEL);
        }
        return originalSetAttribute.call(this, name, value);
    };
    
    // 【关键修复】拦截 document.createElement('img') 创建的元素的 src 属性
    const originalCreateElement = document.createElement;
    document.createElement = function(tagName) {
        const element = originalCreateElement.call(document, tagName);
        if (tagName.toLowerCase() === 'img') {
            // 拦截 src 属性的设置
            const originalSrcDescriptor = Object.getOwnPropertyDescriptor(HTMLImageElement.prototype, 'src');
            if (originalSrcDescriptor) {
                Object.defineProperty(element, 'src', {
                    get: function() {
                        return originalSrcDescriptor.get.call(this);
                    },
                    set: function(value) {
                        if (!isValidImagePath(value)) {
                            console.warn('[Sentinel] 拦截无效图片路径 (createElement.src):', value);
                            originalSrcDescriptor.set.call(this, TRANSPARENT_PIXEL);
                            return;
                        }
                        originalSrcDescriptor.set.call(this, value);
                    }
                });
            }
        }
        return element;
    };
    
    // 【关键修复】拦截 innerHTML 设置，防止无效图片路径被写入
    const originalInnerHTMLDescriptor = Object.getOwnPropertyDescriptor(Element.prototype, 'innerHTML');
    if (originalInnerHTMLDescriptor) {
        Object.defineProperty(Element.prototype, 'innerHTML', {
            get: function() {
                return originalInnerHTMLDescriptor.get.call(this);
            },
            set: function(value) {
                if (typeof value === 'string') {
                    // 替换 src="undefined" 为 src="透明像素"
                    const originalValue = value;
                    value = value.replace(/src=["']undefined["']/gi, 'src="' + TRANSPARENT_PIXEL + '"');
                    value = value.replace(/src=["']\/newsite\/assets\/images\/undefined["']/gi, 'src="' + TRANSPARENT_PIXEL + '"');
                    if (value !== originalValue) {
                        console.warn('[Sentinel] 拦截 innerHTML 中的无效图片路径');
                    }
                }
                originalInnerHTMLDescriptor.set.call(this, value);
            }
        });
    }
    
    // 【关键修复】拦截 jQuery 的 append/prepend/html 方法
    function setupJQueryImageFix() {
        if (!window.jQuery || !window.jQuery.fn) {
            return false;
        }
        
        // 防止重复设置
        if (window.jQuery._sentinelImageFixApplied) {
            return true;
        }
        window.jQuery._sentinelImageFixApplied = true;
        
        // 修复 HTML 字符串中的无效图片路径
        function fixHtmlString(html) {
            if (typeof html !== 'string') return html;
            const originalValue = html;
            // 匹配 src="undefined" 或 src='undefined'
            html = html.replace(/src\s*=\s*["']undefined["']/gi, 'src="' + TRANSPARENT_PIXEL + '"');
            // 匹配 src="/newsite/assets/images/undefined"
            html = html.replace(/src\s*=\s*["']\/newsite\/assets\/images\/undefined["']/gi, 'src="' + TRANSPARENT_PIXEL + '"');
            // 匹配 src="undefined" 在任何位置
            html = html.replace(/src\s*=\s*["'][^"']*undefined[^"']*["']/gi, 'src="' + TRANSPARENT_PIXEL + '"');
            if (html !== originalValue) {
                console.warn('[Sentinel] 修复 HTML 字符串中的无效图片路径');
            }
            return html;
        }
        
        const originalAppend = window.jQuery.fn.append;
        window.jQuery.fn.append = function() {
            const args = Array.prototype.slice.call(arguments);
            for (let i = 0; i < args.length; i++) {
                args[i] = fixHtmlString(args[i]);
            }
            return originalAppend.apply(this, args);
        };
        
        const originalPrepend = window.jQuery.fn.prepend;
        window.jQuery.fn.prepend = function() {
            const args = Array.prototype.slice.call(arguments);
            for (let i = 0; i < args.length; i++) {
                args[i] = fixHtmlString(args[i]);
            }
            return originalPrepend.apply(this, args);
        };
        
        const originalHtml = window.jQuery.fn.html;
        window.jQuery.fn.html = function() {
            const args = Array.prototype.slice.call(arguments);
            for (let i = 0; i < args.length; i++) {
                args[i] = fixHtmlString(args[i]);
            }
            return originalHtml.apply(this, args);
        };
        
        console.log('[Sentinel] jQuery 图片路径拦截已启用');
        return true;
    }
    
    // 立即尝试设置
    if (!setupJQueryImageFix()) {
        // 如果 jQuery 还没加载，等待它加载
        const checkInterval = setInterval(function() {
            if (setupJQueryImageFix()) {
                clearInterval(checkInterval);
            }
        }, 100);
        
        // 超时清理
        setTimeout(function() {
            clearInterval(checkInterval);
        }, 10000);
        
        // 也监听 jQuery 可能稍后加载的情况
        let checkCount = 0;
        const lateCheck = setInterval(function() {
            if (setupJQueryImageFix() || checkCount++ > 50) {
                clearInterval(lateCheck);
            }
        }, 200);
    }
    
    // 拦截 DOM 中动态创建的 img 元素
    if (window.MutationObserver) {
        const observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                if (mutation.type === 'childList') {
                    mutation.addedNodes.forEach(function(node) {
                        if (node.tagName === 'IMG') {
                            const src = node.getAttribute('src');
                            if (!isValidImagePath(src)) {
                                console.warn('[Sentinel] 拦截动态添加的无效图片:', src);
                                node.setAttribute('src', TRANSPARENT_PIXEL);
                            }
                        }
                        // 检查子节点
                        if (node.querySelectorAll) {
                            const imgs = node.querySelectorAll('img');
                            imgs.forEach(function(img) {
                                const src = img.getAttribute('src');
                                if (!isValidImagePath(src)) {
                                    console.warn('[Sentinel] 拦截子节点中的无效图片:', src);
                                    img.setAttribute('src', TRANSPARENT_PIXEL);
                                }
                            });
                        }
                    });
                }
            });
        });
        
        // 观察整个文档
        if (document.body) {
            observer.observe(document.body, {
                childList: true,
                subtree: true
            });
        } else {
            document.addEventListener('DOMContentLoaded', function() {
                if (document.body) {
                    observer.observe(document.body, {
                        childList: true,
                        subtree: true
                    });
                }
            });
        }
    }
    
    console.log('[Sentinel] Image 加载拦截器已启用');
})();
</script>'''
    
    def _build_ajax_interceptor(self, task_path: Path) -> str:
        """构建 AJAX 拦截脚本，注入保存的 API 响应数据"""
        api_responses_path = task_path / "network" / "api_responses.json"
        
        if not api_responses_path.exists():
            return ""
        
        try:
            with open(api_responses_path, 'r', encoding='utf-8') as f:
                api_data = json.load(f)
            
            if not api_data:
                return ""
            
            # 构建拦截脚本（分离 XMLHttpRequest 和 jQuery 拦截）
            interceptor_script = '''
<script>
// 【Sentinel】AJAX 响应拦截器 - 注入保存的 API 数据
(function() {
    // 保存的 API 响应数据
    const savedResponses = ''' + json.dumps(api_data, ensure_ascii=False) + ''';
    
    // 查找匹配的保存响应
    function findMatchingResponse(url) {
        // 尝试精确匹配
        if (savedResponses[url]) {
            console.log('[Sentinel] 精确匹配: ' + url);
            return savedResponses[url];
        }
        
        // 尝试部分匹配（忽略域名和协议）
        try {
            const urlObj = new URL(url, window.location.href);
            const pathAndQuery = urlObj.pathname + urlObj.search;
            
            for (const [savedUrl, response] of Object.entries(savedResponses)) {
                try {
                    const savedUrlObj = new URL(savedUrl, window.location.href);
                    const savedPathAndQuery = savedUrlObj.pathname + savedUrlObj.search;
                    
                    if (pathAndQuery === savedPathAndQuery) {
                        console.log('[Sentinel] 路径匹配: ' + url + ' -> ' + savedUrl);
                        return response;
                    }
                } catch (e) {
                    // 保存的 URL 可能不是完整 URL，尝试字符串匹配
                    console.log('[Sentinel] URL 解析失败，使用字符串匹配:', savedUrl);
                    if (savedUrl.includes(pathAndQuery) || pathAndQuery.includes(savedUrl)) {
                        console.log('[Sentinel] 字符串匹配: ' + url + ' -> ' + savedUrl);
                        return response;
                    }
                }
            }
        } catch (e) {
            // URL 解析失败，尝试字符串匹配
            console.warn('[Sentinel] URL 解析失败:', url, e.message);
            for (const [savedUrl, response] of Object.entries(savedResponses)) {
                if (savedUrl.includes(url) || url.includes(savedUrl)) {
                    console.log('[Sentinel] 字符串匹配: ' + url + ' -> ' + savedUrl);
                    return response;
                }
            }
        }
        
        console.log('[Sentinel] 未找到匹配: ' + url);
        return null;
    }
    
    // 保存原始 XMLHttpRequest
    const OriginalXMLHttpRequest = window.XMLHttpRequest;
    
    // 创建拦截器
    function InterceptedXMLHttpRequest() {
        const xhr = new OriginalXMLHttpRequest();
        const originalOpen = xhr.open;
        const originalSend = xhr.send;
        
        let requestUrl = '';
        let requestMethod = 'GET';
        
        // 拦截 open 方法
        xhr.open = function(method, url, async, user, password) {
            requestUrl = url;
            requestMethod = method;
            return originalOpen.apply(xhr, arguments);
        };
        
        // 拦截 send 方法
        xhr.send = function(body) {
            // 检查是否有保存的响应
            const savedResponse = findMatchingResponse(requestUrl);
            
            if (savedResponse) {
                // 模拟异步响应
                setTimeout(() => {
                    // 设置响应属性
                    Object.defineProperty(xhr, 'readyState', {
                        get: () => 4  // DONE
                    });
                    Object.defineProperty(xhr, 'status', {
                        get: () => savedResponse.status || 200
                    });
                    Object.defineProperty(xhr, 'statusText', {
                        get: () => 'OK'
                    });
                    Object.defineProperty(xhr, 'responseText', {
                        get: () => JSON.stringify(savedResponse.body)
                    });
                    Object.defineProperty(xhr, 'response', {
                        get: () => JSON.stringify(savedResponse.body)
                    });
                    
                    // 触发 onload 回调
                    if (xhr.onload) {
                        xhr.onload();
                    }
                    // 触发 onreadystatechange 回调
                    if (xhr.onreadystatechange) {
                        xhr.onreadystatechange();
                    }
                }, 10);
                
                return;
            }
            
            // 没有保存的响应，调用原始方法
            return originalSend.apply(xhr, arguments);
        };
        
        return xhr;
    }
    
    // 替换全局 XMLHttpRequest
    window.XMLHttpRequest = InterceptedXMLHttpRequest;
    
    // 立即尝试设置 jQuery 拦截器（如果 jQuery 已存在）
    if (window.jQuery && window.jQuery.ajax) {
        setupJQueryAjaxInterceptor();
    }
    
    // 同时监听 DOMContentLoaded
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', setupJQueryInterceptor);
    } else {
        setupJQueryInterceptor();
    }
    
    function setupJQueryInterceptor() {
        // 检查 jQuery 是否已加载
        if (window.jQuery && window.jQuery.ajax) {
            // 检查是否已设置拦截器
            if (!window.jQuery._sentinelIntercepted) {
                setupJQueryAjaxInterceptor();
            }
        } else {
            // 等待 jQuery 加载
            const checkJQuery = setInterval(() => {
                if (window.jQuery && window.jQuery.ajax) {
                    clearInterval(checkJQuery);
                    if (!window.jQuery._sentinelIntercepted) {
                        setupJQueryAjaxInterceptor();
                    }
                }
            }, 50);
            // 5秒后停止检查
            setTimeout(() => clearInterval(checkJQuery), 5000);
        }
    }
    
    function setupJQueryAjaxInterceptor() {
        // 标记已设置拦截器
        window.jQuery._sentinelIntercepted = true;
        
        const originalAjax = window.jQuery.ajax;
        window.jQuery.ajax = function(options) {
            const url = options.url || '';
            const savedResponse = findMatchingResponse(url);
            
            if (savedResponse) {
                console.log('[Sentinel] 拦截 jQuery.ajax: ' + url);
                
                // 【关键修复】根据 API 类型返回正确的数据结构
                // 对于 queryIndexBanner API，返回 body.data 而不是整个 body
                let responseData = savedResponse.body;
                if (savedResponse.body && savedResponse.body.data !== undefined) {
                    // 检查调用者期望的数据结构
                    // 如果 URL 包含 queryIndexBanner，返回 data 数组
                    if (url.includes('queryIndexBanner')) {
                        responseData = savedResponse.body.data;
                        console.log('[Sentinel] 返回 body.data 而不是整个 body');
                    }
                }
                
                // 创建模拟的 jqXHR 对象
                const deferred = window.jQuery.Deferred();
                const jqXHR = {
                    status: savedResponse.status || 200,
                    statusText: 'OK',
                    responseText: JSON.stringify(savedResponse.body),
                    readyState: 4,
                    getResponseHeader: () => null,
                    getAllResponseHeaders: () => ''
                };
                
                // 模拟异步响应
                setTimeout(() => {
                    if (options.success) {
                        options.success(responseData, 'success', jqXHR);
                    }
                    deferred.resolve(responseData, 'success', jqXHR);
                }, 10);
                
                // 返回增强的 deferred 对象
                return window.jQuery.extend(deferred.promise(), {
                    abort: () => {},
                    setRequestHeader: () => {},
                    getResponseHeader: () => null,
                    getAllResponseHeaders: () => ''
                });
            }
            
            return originalAjax.apply(this, arguments);
        };
        
        console.log('[Sentinel] jQuery.ajax 拦截器已设置');
    }
    
    console.log('[Sentinel] AJAX 拦截器已加载，保存了 ' + Object.keys(savedResponses).length + ' 个 API 响应');
    
    // 【通用能力】JavaScript 错误修复插件系统
    window.SentinelJSErrorFixer = {
        fixes: [],
        
        // 注册错误修复插件
        register: function(config) {
            this.fixes.push(config);
            console.log('[Sentinel] 注册 JS 错误修复:', config.name);
        },
        
        // 应用所有修复
        applyAll: function() {
            const self = this;
            this.fixes.forEach(function(config) {
                try {
                    self.apply(config);
                } catch (e) {
                    console.error('[Sentinel] JS 修复应用失败:', config.name, e);
                    // 将错误也发送到全局错误收集器
                    if (window.SentinelErrorCollector) {
                        window.SentinelErrorCollector.add('JSFixer.apply', {
                            name: config.name,
                            error: e.message,
                            stack: e.stack
                        });
                    }
                }
            });
        },
        
        // 应用单个修复
        apply: function(config) {
            if (config.check && !config.check()) {
                return; // 检查条件不满足，跳过
            }
            config.fix();
            console.log('[Sentinel] JS 错误已修复:', config.name);
        },
        
        // 自动检测并修复常见错误
        autoFix: function() {
            // 修复 1: 未定义的全局变量（增强版）
            this.register({
                name: 'Undefined Global Variables',
                check: function() {
                    return true; // 总是应用
                },
                fix: function() {
                    // 创建通用的命名空间对象
                    if (typeof window.Newsite === 'undefined') {
                        window.Newsite = {};
                    }
                    if (typeof window.SensorsData === 'undefined') {
                        window.SensorsData = {};
                    }
                    // 【新增】修复 sensors 未定义错误（神策数据 SDK）
                    if (typeof window.sensors === 'undefined') {
                        window.sensors = {
                            track: function() { console.log('[Sentinel] sensors.track 被调用'); },
                            login: function() {},
                            logout: function() {},
                            identify: function() {},
                            init: function() { console.log('[Sentinel] sensors.init 被调用'); }
                        };
                    }
                    // 【新增】修复 sa 未定义错误（神策数据别名）
                    if (typeof window.sa === 'undefined') {
                        window.sa = window.sensors;
                    }
                    // 【新增】修复 dataLayer 未定义错误（Google Tag Manager）
                    if (typeof window.dataLayer === 'undefined') {
                        window.dataLayer = [];
                    }
                    // 【新增】修复 gtag 未定义错误（Google Analytics）
                    if (typeof window.gtag === 'undefined') {
                        window.gtag = function() { window.dataLayer.push(arguments); };
                    }
                    // 【新增】修复 _hmt 未定义错误（百度统计）
                    if (typeof window._hmt === 'undefined') {
                        window._hmt = [];
                    }
                    // 【新增】修复 wx 未定义错误（微信 JS-SDK）
                    if (typeof window.wx === 'undefined') {
                        window.wx = {
                            ready: function(callback) { if(callback) callback(); },
                            config: function() {},
                            checkJsApi: function() {},
                            onMenuShareTimeline: function() {},
                            onMenuShareAppMessage: function() {},
                            onMenuShareQQ: function() {},
                            onMenuShareWeibo: function() {},
                            onMenuShareQZone: function() {},
                            updateTimelineShareData: function() {},
                            updateAppMessageShareData: function() {},
                            Client: {
                                isWechat: false,
                                isMobile: false,
                                isIOS: false,
                                isAndroid: false,
                                version: '0.0.0'
                            }
                        };
                    }
                    // 【新增】修复 WeixinJSBridge 未定义错误
                    if (typeof window.WeixinJSBridge === 'undefined') {
                        window.WeixinJSBridge = {
                            invoke: function() {},
                            call: function() {},
                            on: function() {}
                        };
                    }
                    // 【新增】修复 JSSDK 未定义错误（银河证券自定义微信 SDK 封装）
                    if (typeof window.JSSDK === 'undefined') {
                        window.JSSDK = {
                            Client: {
                                isWeixin: function() { return false; },
                                isWechat: function() { return false; },
                                isMobile: function() { return false; },
                                isIOS: function() { return false; },
                                isAndroid: function() { return false; }
                            },
                            WxShare: {
                                customShare: function() {
                                    console.log('[Sentinel] JSSDK.WxShare.customShare 被调用');
                                }
                            }
                        };
                    }
                }
            });
            
            // 修复 2: Newsite 命名空间及历史记录相关错误
            this.register({
                name: 'Newsite Namespace and History API Errors',
                check: function() {
                    return true; // 总是应用
                },
                fix: function() {
                    // 确保 Newsite 命名空间存在（必须在访问其属性前创建）
                    if (typeof window.Newsite === 'undefined') {
                        window.Newsite = {};
                    }
                    // 确保 history_list 存在
                    if (!window.Newsite.history_list) {
                        window.Newsite.history_list = [];
                    }
                    // 【通用能力】确保 Newsite 其他常用属性存在
                    if (!window.Newsite.config) {
                        window.Newsite.config = {};
                    }
                    if (!window.Newsite.api) {
                        window.Newsite.api = {};
                    }
                }
            });
            
            // 修复 3: DOM 元素空引用
            this.register({
                name: 'DOM Null References',
                check: function() {
                    return true; // 总是应用
                },
                fix: function() {
                    // 包装 getElementById 和 querySelector
                    const originalGetElementById = document.getElementById;
                    document.getElementById = function(id) {
                        const element = originalGetElementById.call(document, id);
                        if (!element) {
                            console.warn('[Sentinel] getElementById 返回 null:', id);
                            // 创建一个虚拟元素防止错误
                            const dummy = document.createElement('div');
                            dummy.id = id;
                            dummy.style.display = 'none';
                            if (document.body) {
                                document.body.appendChild(dummy);
                            }
                            return dummy;
                        }
                        return element;
                    };
                    
                    // 【通用能力】包装 querySelector，防止返回 null
                    const originalQuerySelector = document.querySelector;
                    document.querySelector = function(selector) {
                        const element = originalQuerySelector.call(document, selector);
                        if (!element) {
                            console.warn('[Sentinel] querySelector 返回 null:', selector);
                            // 创建一个虚拟元素防止错误
                            const dummy = document.createElement('div');
                            dummy.setAttribute('data-sentinel-dummy', selector);
                            dummy.style.display = 'none';
                            if (document.body) {
                                document.body.appendChild(dummy);
                            }
                            return dummy;
                        }
                        return element;
                    };
                    
                    // 【通用能力】包装 innerHTML 设置，防止 null 错误
                    const originalInnerHTMLDescriptor = Object.getOwnPropertyDescriptor(Element.prototype, 'innerHTML');
                    if (originalInnerHTMLDescriptor && originalInnerHTMLDescriptor.set) {
                        Object.defineProperty(Element.prototype, 'innerHTML', {
                            set: function(value) {
                                if (this === null || this === undefined) {
                                    console.warn('[Sentinel] 尝试在 null/undefined 上设置 innerHTML');
                                    return;
                                }
                                try {
                                    originalInnerHTMLDescriptor.set.call(this, value);
                                } catch (e) {
                                    console.warn('[Sentinel] innerHTML 设置失败:', e.message);
                                }
                            },
                            get: originalInnerHTMLDescriptor.get
                        });
                    }
                }
            });
            
            this.applyAll();
        }
    };
    
    // 页面加载时自动应用修复
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            window.SentinelJSErrorFixer.autoFix();
        });
    } else {
        window.SentinelJSErrorFixer.autoFix();
    }
    
    // 【通用能力】Video.js 兼容性处理
    // 在 videojs 加载前拦截并包装，防止元素不存在错误
    (function() {
        // 保存原始 videojs 引用（如果存在）
        let originalVideojs = window.videojs;
        
        // 创建包装器
        function videojsWrapper(idOrElement, options, ready) {
            // 确保元素存在
            let element = idOrElement;
            if (typeof idOrElement === 'string') {
                element = document.getElementById(idOrElement);
            }
            
            // 如果元素不存在，创建一个虚拟视频元素
            if (!element || element === null) {
                console.warn('[Sentinel] videojs: 元素不存在，创建虚拟元素:', idOrElement);
                const dummyId = typeof idOrElement === 'string' ? idOrElement : 'sentinel-video-dummy';
                element = document.createElement('video');
                element.id = dummyId;
                element.style.display = 'none';
                if (document.body) {
                    document.body.appendChild(element);
                }
            }
            
            // 如果原始 videojs 存在，调用它
            if (originalVideojs && typeof originalVideojs === 'function') {
                try {
                    return originalVideojs(element, options, ready);
                } catch (e) {
                    console.warn('[Sentinel] videojs 调用失败:', e.message);
                }
            }
            
            // 返回一个 mock player 对象
            console.log('[Sentinel] 返回 videojs mock player');
            return {
                play: function() { console.log('[Sentinel] videojs.play() 被调用'); },
                pause: function() { console.log('[Sentinel] videojs.pause() 被调用'); },
                src: function() { console.log('[Sentinel] videojs.src() 被调用'); },
                currentTime: function() { return 0; },
                duration: function() { return 0; },
                volume: function() { return 1; },
                muted: function() { return false; },
                on: function() {},
                off: function() {},
                one: function() {},
                trigger: function() {},
                dispose: function() {},
                ready: function(callback) { if (callback) setTimeout(callback, 0); },
                error: function() { return null; },
                isDisposed: function() { return false; }
            };
        }
        
        // 复制原始 videojs 的静态属性和方法
        if (originalVideojs) {
            for (const key in originalVideojs) {
                if (originalVideojs.hasOwnProperty(key)) {
                    videojsWrapper[key] = originalVideojs[key];
                }
            }
        }
        
        // 添加常用静态方法
        videojsWrapper.getPlayer = function(id) {
            console.log('[Sentinel] videojs.getPlayer() 被调用:', id);
            return null;
        };
        videojsWrapper.getAllPlayers = function() {
            return [];
        };
        videojsWrapper.registerPlugin = function() {
            console.log('[Sentinel] videojs.registerPlugin() 被调用');
        };
        videojsWrapper.addLanguage = function(lang, data) {
            console.log('[Sentinel] videojs.addLanguage() 被调用:', lang);
        };
        videojsWrapper.options = {};
        videojsWrapper.VERSION = '7.0.0';
        
        // 覆盖全局 videojs
        Object.defineProperty(window, 'videojs', {
            get: function() {
                return videojsWrapper;
            },
            set: function(value) {
                originalVideojs = value;
            },
            configurable: true
        });
    })();
    
    // 【通用能力】Swiper 兼容性处理
    // 防止 Swiper 在元素不存在时出错
    (function() {
        // 创建 Swiper 包装器
        function createSwiperWrapper(originalSwiper) {
            function SwiperWrapper(container, options) {
                console.log('[Sentinel] Swiper 被调用:', container);
                
                // 确保容器元素存在
                let element = container;
                if (typeof container === 'string') {
                    element = document.querySelector(container);
                }
                
                // 如果元素不存在，创建一个虚拟容器
                if (!element) {
                    console.warn('[Sentinel] Swiper 容器不存在，创建虚拟容器:', container);
                    element = document.createElement('div');
                    element.className = 'swiper-container sentinel-dummy';
                    element.style.display = 'none';
                    if (document.body) {
                        document.body.appendChild(element);
                    }
                }
                
                // 【关键】如果元素是虚拟创建的（sentinel-dummy），直接返回 mock，不要调用原始 Swiper
                if (element.getAttribute && element.getAttribute('data-sentinel-created') === 'true') {
                    console.log('[Sentinel] 元素是虚拟元素，返回 Swiper mock 实例');
                } else if (originalSwiper && typeof originalSwiper === 'function') {
                    // 如果是真实元素，尝试调用原始 Swiper
                    try {
                        return new originalSwiper(element, options);
                    } catch (e) {
                        console.warn('[Sentinel] Swiper 初始化失败:', e.message);
                    }
                }
                
                // 返回 mock Swiper 实例
                console.log('[Sentinel] 返回 Swiper mock 实例');
                return {
                    slideNext: function() { console.log('[Sentinel] Swiper.slideNext() 被调用'); },
                    slidePrev: function() { console.log('[Sentinel] Swiper.slidePrev() 被调用'); },
                    slideTo: function() { console.log('[Sentinel] Swiper.slideTo() 被调用'); },
                    on: function() { return this; },
                    off: function() { return this; },
                    emit: function() { return this; },
                    update: function() {},
                    destroy: function() {},
                    init: function() { console.log('[Sentinel] Swiper.init() 被调用'); return this; },
                    mount: function() { return this; },
                    autoplay: {
                        start: function() {},
                        stop: function() {},
                        pause: function() {},
                        run: function() {}
                    },
                    params: options || {},
                    el: element,
                    $el: element,
                    slides: [],
                    activeIndex: 0,
                    previousIndex: 0,
                    width: 0,
                    height: 0,
                    clickedSlide: undefined,
                    clickedIndex: undefined,
                    allowClick: true,
                    allowTouchMove: true,
                    isBeginning: true,
                    isEnd: true,
                    progress: 0,
                    touches: { startX: 0, startY: 0, currentX: 0, currentY: 0, diff: 0 }
                };
            }
            
            // 复制原始 Swiper 的静态属性和方法
            if (originalSwiper) {
                for (const key in originalSwiper) {
                    if (originalSwiper.hasOwnProperty(key)) {
                        SwiperWrapper[key] = originalSwiper[key];
                    }
                }
            }
            
            // 添加常用静态方法
            SwiperWrapper.use = function() {
                console.log('[Sentinel] Swiper.use() 被调用');
            };
            SwiperWrapper.extend = function() {
                return SwiperWrapper;
            };
            
            return SwiperWrapper;
        }
        
        // 立即包装当前的 Swiper（如果存在）
        let currentSwiper = window.Swiper;
        if (currentSwiper) {
            window.Swiper = createSwiperWrapper(currentSwiper);
        }
        
        // 使用 Object.defineProperty 拦截后续对 Swiper 的赋值
        Object.defineProperty(window, 'Swiper', {
            get: function() {
                return currentSwiper;
            },
            set: function(value) {
                console.log('[Sentinel] Swiper 被重新赋值，重新包装');
                currentSwiper = createSwiperWrapper(value);
            },
            configurable: true
        });
        
        console.log('[Sentinel] Swiper 兼容性处理已启用');
    })();
    
    // 【通用能力】动态内容注入器
    // 自动将 API 数据注入到对应的 DOM 元素中
    window.SentinelContentInjector = {
        injectors: [],
        
        // 注册内容注入器
        register: function(config) {
            this.injectors.push(config);
            console.log('[Sentinel] 注册内容注入器:', config.name);
        },
        
        // 执行所有注入器
        injectAll: function() {
            this.injectors.forEach(function(config) {
                try {
                    window.SentinelContentInjector.execute(config);
                } catch (e) {
                    console.error('[Sentinel] 注入器执行失败:', config.name, e);
                }
            });
        },
        
        // 执行单个注入器
        execute: function(config) {
            const container = document.querySelector(config.container);
            if (!container) {
                console.log('[Sentinel] 未找到容器:', config.container);
                return;
            }
            
            // 查找匹配的 API 响应
            let data = null;
            for (const [url, response] of Object.entries(savedResponses)) {
                if (url.includes(config.apiPattern)) {
                    data = response.body;
                    break;
                }
            }
            
            if (!data) {
                console.log('[Sentinel] 未找到 API 数据:', config.apiPattern);
                return;
            }
            
            // 生成 HTML 内容
            const html = config.template(data);
            if (html) {
                container.innerHTML = html;
                console.log('[Sentinel] 内容已注入:', config.name);
            }
        }
    };
    
    // 页面加载完成后自动注入内容
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            setTimeout(function() {
                window.SentinelContentInjector.injectAll();
            }, 100);
        });
    } else {
        setTimeout(function() {
            window.SentinelContentInjector.injectAll();
        }, 100);
    }
})();
</script>'''
            
            return interceptor_script
            
        except Exception as e:
            print(f"    加载 API 响应数据失败: {e}")
            return ""
    
    def _get_reset_css(self) -> str:
        """获取基础重置样式"""
        return """
/* Reset and Base Styles */
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    line-height: 1.6;
    color: #333;
    background: #fff;
}

img {
    max-width: 100%;
    height: auto;
}

a {
    color: inherit;
    text-decoration: none;
}

button {
    cursor: pointer;
    border: none;
    background: none;
}

input, textarea {
    font-family: inherit;
}
"""
    
    def _escape_html(self, text: str) -> str:
        """转义 HTML 特殊字符"""
        if not isinstance(text, str):
            text = str(text)
        return (text
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;'))
    
    def _escape_attr(self, text: str) -> str:
        """转义属性值"""
        return (text
                .replace('&', '&amp;')
                .replace('"', '&quot;')
                .replace("'", '&#39;'))
