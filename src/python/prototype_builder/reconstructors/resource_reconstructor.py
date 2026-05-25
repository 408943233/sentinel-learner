"""
资源文件重建器
从静态资源文件（HTML/CSS/JS）重建页面
支持图片 base64 嵌入，保留完整内容
"""

import json
import re
import base64
from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime

from ..core.build_result import BuildResult, DataSource


class ResourceReconstructor:
    """资源文件重建器"""
    
    def __init__(self):
        self.resources = {
            'html': [],
            'css': [],
            'js': [],
            'images': [],
            'fonts': []
        }
        self.resources_dir = None
    
    def reconstruct(self,
                   task_path: str,
                   output_dir: str,
                   target_score: float = 0.95) -> BuildResult:
        """
        从资源文件重建页面
        
        Args:
            task_path: task 目录路径
            output_dir: 输出目录
            target_score: 目标质量分数
            
        Returns:
            构建结果
        """
        task_path = Path(task_path)
        task_id = task_path.name
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        self.resources_dir = task_path / "network" / "resources"
        
        start_time = datetime.now()
        
        try:
            # 1. 扫描资源文件
            self._scan_resources(task_path)
            
            if not self.resources['html']:
                return BuildResult(
                    task_id=task_id,
                    source=DataSource.FAILED,
                    error_message="未找到 HTML 资源文件"
                )
            
            # 2. 选择主 HTML 文件
            main_html = self._select_main_html()
            
            # 3. 重建页面（使用正则替换，保留原始格式）
            html_content = self._rebuild_page_preserve_format(main_html, task_path)
            
            # 4. 保存文件
            output_path = output_dir / f"prototype_resource_{task_id}.html"
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            build_time = (datetime.now() - start_time).total_seconds() * 1000
            
            return BuildResult(
                task_id=task_id,
                source=DataSource.RESOURCE_FILES,
                output_path=output_path,
                build_time_ms=build_time,
                source_files=[str(f) for f in self.resources['html'][:3]]
            )
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return BuildResult(
                task_id=task_id,
                source=DataSource.FAILED,
                error_message=f"资源重建失败: {str(e)}"
            )
    
    def _scan_resources(self, task_path: Path):
        """扫描资源文件"""
        resources_dir = task_path / "network" / "resources"
        
        if not resources_dir.exists():
            return
        
        for file in resources_dir.iterdir():
            if file.is_file():
                suffix = file.suffix.lower()
                
                if suffix == '.html' or file.name.endswith('.html'):
                    self.resources['html'].append(file)
                elif suffix == '.css':
                    self.resources['css'].append(file)
                elif suffix == '.js':
                    self.resources['js'].append(file)
                elif suffix in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp', '.ico']:
                    self.resources['images'].append(file)
                elif suffix in ['.woff', '.woff2', '.ttf', '.otf', '.eot']:
                    self.resources['fonts'].append(file)
    
    def _select_main_html(self) -> Path:
        """选择主 HTML 文件"""
        if not self.resources['html']:
            raise ValueError("没有 HTML 文件")
        
        # 优先选择 index.html 或包含 index 的文件
        for html_file in self.resources['html']:
            if 'index' in html_file.name.lower():
                return html_file
        
        # 选择最大的 HTML 文件（通常是最完整的）
        return max(self.resources['html'], key=lambda f: f.stat().st_size)
    
    def _rebuild_page_preserve_format(self, main_html: Path, task_path: Path) -> str:
        """重建页面，保留原始格式和内容"""
        # 读取主 HTML
        with open(main_html, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        resources_dir = task_path / "network" / "resources"
        
        # 1. 处理 CSS 链接（内联并处理图片）
        content = self._inline_css_links(content, resources_dir)
        
        # 2. 处理 HTML 中的图片
        content = self._process_html_images(content, resources_dir)
        
        # 3. 处理 JS 引用
        content = self._inline_js_scripts(content, resources_dir)
        
        # 4. 移除外部资源引用
        content = self._remove_external_resources(content)
        
        return content
    
    def _inline_css_links(self, html_content: str, resources_dir: Path) -> str:
        """内联 CSS 链接并处理其中的图片"""
        # 匹配 link 标签
        link_pattern = r'<link[^>]*rel=["\']stylesheet["\'][^>]*href=["\']([^"\']+)["\'][^>]*>'
        
        def replace_link(match):
            full_tag = match.group(0)
            href = match.group(1)
            
            # 跳过外部链接
            if href.startswith(('http', '//')):
                return ''  # 移除外部 CSS
            
            # 提取 CSS 文件名
            css_name = Path(href).name
            
            # 查找对应的 CSS 文件
            for css_file in self.resources['css']:
                if css_name in css_file.name or css_file.name.endswith(css_name):
                    try:
                        with open(css_file, 'r', encoding='utf-8', errors='ignore') as f:
                            css_content = f.read()
                        
                        # 处理 CSS 中的图片
                        css_content = self._process_css_images(css_content, resources_dir)
                        
                        # 返回 style 标签
                        return f'<style>\n{css_content}\n</style>'
                    except Exception as e:
                        print(f"    处理 CSS 失败 {css_name}: {e}")
                        return ''
            
            # 找不到 CSS 文件，移除链接
            return ''
        
        return re.sub(link_pattern, replace_link, html_content, flags=re.IGNORECASE)
    
    def _process_css_images(self, css_content: str, resources_dir: Path) -> str:
        """处理 CSS 中的图片引用"""
        # 匹配 url() 中的图片引用
        url_pattern = r'url\s*\(\s*["\']?([^"\')]+\.(?:png|jpg|jpeg|gif|svg|webp|bmp|ico))["\']?\s*\)'
        
        def replace_url(match):
            img_ref = match.group(1)
            img_name = Path(img_ref).name
            
            # 查找对应的图片文件
            for img_file in self.resources['images']:
                if img_name in img_file.name or self._match_image_name(img_name, img_file.name):
                    # 转换为 base64
                    img_data = self._image_to_base64(img_file)
                    if img_data:
                        return f'url("{img_data}")'
            
            # 找不到图片，返回 none
            return 'none'
        
        return re.sub(url_pattern, replace_url, css_content, flags=re.IGNORECASE)
    
    def _process_html_images(self, html_content: str, resources_dir: Path) -> str:
        """处理 HTML 中的图片"""
        # 匹配 img 标签的 src
        img_pattern = r'<img([^>]*)src=["\']([^"\']+)["\']([^>]*)>'
        
        def replace_img(match):
            prefix = match.group(1)
            src = match.group(2)
            suffix = match.group(3)
            
            # 跳过外部链接和 data URI
            if src.startswith(('http', '//', 'data:')):
                return match.group(0)
            
            img_name = Path(src).name
            
            # 查找对应的图片文件
            for img_file in self.resources['images']:
                if img_name in img_file.name or self._match_image_name(img_name, img_file.name):
                    img_data = self._image_to_base64(img_file)
                    if img_data:
                        return f'<img{prefix}src="{img_data}"{suffix}>'
            
            # 找不到图片，保留原样（可能显示破损图标）
            return match.group(0)
        
        return re.sub(img_pattern, replace_img, html_content, flags=re.IGNORECASE)
    
    def _inline_js_scripts(self, html_content: str, resources_dir: Path) -> str:
        """内联 JS 脚本"""
        script_pattern = r'<script([^>]*)src=["\']([^"\']+)["\']([^>]*)></script>'
        
        def replace_script(match):
            prefix = match.group(1)
            src = match.group(2)
            suffix = match.group(3)
            
            # 跳过外部链接
            if src.startswith(('http', '//')):
                return ''  # 移除外部 JS
            
            js_name = Path(src).name
            
            # 查找对应的 JS 文件
            for js_file in self.resources['js']:
                if js_name in js_file.name:
                    try:
                        with open(js_file, 'r', encoding='utf-8', errors='ignore') as f:
                            js_content = f.read()
                        return f'<script{prefix}{suffix}>\n{js_content}\n</script>'
                    except:
                        return ''
            
            # 找不到 JS 文件，移除脚本
            return ''
        
        return re.sub(script_pattern, replace_script, html_content, flags=re.IGNORECASE)
    
    def _remove_external_resources(self, html_content: str) -> str:
        """移除外部资源引用"""
        # 移除外部脚本（保留内联脚本）
        external_script_pattern = r'<script[^>]*src=["\'](?:https?://|//)[^"\']*["\'][^>]*></script>'
        html_content = re.sub(external_script_pattern, '', html_content, flags=re.IGNORECASE)
        
        # 移除外部链接（如 CDN）
        external_link_pattern = r'<link[^>]*href=["\'](?:https?://|//)[^"\']*["\'][^>]*>'
        html_content = re.sub(external_link_pattern, '', html_content, flags=re.IGNORECASE)
        
        return html_content
    
    def _match_image_name(self, ref_name: str, file_name: str) -> bool:
        """匹配图片文件名（处理哈希后缀）"""
        ref_base = Path(ref_name).stem
        file_base = Path(file_name).stem
        
        # 检查是否匹配
        if ref_base in file_base or file_base in ref_base:
            return True
        
        # 检查去掉哈希后的匹配
        ref_clean = ref_base.split('.')[0] if '.' in ref_base else ref_base
        file_clean = file_base.split('.')[0] if '.' in file_base else file_base
        
        return ref_clean == file_clean
    
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
