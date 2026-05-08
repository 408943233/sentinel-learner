#!/usr/bin/env python3
"""
SmartWebCrawler - 通用智能网页爬虫
自动发现页面元素，记录所有交互操作，完整保存资源到本地
"""
import os
import sys
import json
import re
import hashlib
import requests
from datetime import datetime
from urllib.parse import urljoin, urlparse, unquote
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any

from playwright.sync_api import sync_playwright


@dataclass
class ActionRecord:
    """操作记录"""
    type: str
    selector: str = ""
    value: str = ""
    url: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "selector": self.selector,
            "value": self.value,
            "timestamp": self.timestamp,
            "url": self.url,
            "metadata": self.metadata
        }


@dataclass
class CrawlResult:
    """爬取结果"""
    url: str
    title: str = ""
    html: str = ""
    html_path: str = ""
    screenshot_path: str = ""
    actions: List[ActionRecord] = field(default_factory=list)
    api_responses: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class SmartWebCrawler:
    """通用智能网页爬虫"""
    
    def __init__(self, output_dir: str = 'output', headless: bool = True,
                 viewport_width: int = 1920, viewport_height: int = 1080,
                 screenshot_full_page: bool = True):
        self.output_dir = output_dir
        self.headless = headless
        self.viewport = {'width': viewport_width, 'height': viewport_height}
        self.screenshot_full_page = screenshot_full_page
        
        # 创建输出目录
        self.assets_dir = os.path.join(output_dir, 'assets')
        self.pages_dir = os.path.join(output_dir, 'pages')
        self.screenshots_dir = os.path.join(output_dir, 'screenshots')
        
        os.makedirs(self.assets_dir, exist_ok=True)
        os.makedirs(self.pages_dir, exist_ok=True)
        os.makedirs(self.screenshots_dir, exist_ok=True)
        
        # 已下载的资源缓存
        self.downloaded_assets = {}
        
    def _generate_filename(self, url: str) -> str:
        """生成文件名"""
        parsed = urlparse(url)
        safe_name = parsed.netloc.replace('.', '_')
        if parsed.path:
            path_part = parsed.path.replace('/', '_').replace('.', '_')[:50]
            safe_name += path_part
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        hash_part = hashlib.md5(url.encode()).hexdigest()[:6]
        return f"{safe_name}_{timestamp}_{hash_part}"
    
    def _download_asset(self, url: str, asset_type: str = 'unknown', base_url: str = '') -> Optional[str]:
        """下载资源文件，处理JS中的动态URL"""
        if url in self.downloaded_assets:
            return self.downloaded_assets[url]
        
        try:
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                # 生成文件名
                parsed = urlparse(url)
                if parsed.path:
                    filename = os.path.basename(parsed.path)
                    if not filename or '.' not in filename:
                        ext = {'image': '.png', 'css': '.css', 'js': '.js'}.get(asset_type, '')
                        filename = f"asset_{len(self.downloaded_assets)}{ext}"
                else:
                    filename = f"asset_{len(self.downloaded_assets)}"
                
                # 确保文件名唯一且安全
                safe_filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
                base_name, ext = os.path.splitext(safe_filename)
                counter = 1
                while os.path.exists(os.path.join(self.assets_dir, safe_filename)):
                    safe_filename = f"{base_name}_{counter}{ext}"
                    counter += 1
                
                filepath = os.path.join(self.assets_dir, safe_filename)
                content = response.content
                
                # 如果是JS文件，处理其中的动态URL
                if asset_type == 'js' or filename.endswith('.js'):
                    content = self._process_js_content(content.decode('utf-8', errors='ignore'), url, base_url)
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(content)
                else:
                    with open(filepath, 'wb') as f:
                        f.write(content)
                
                # 使用绝对路径 /assets/ 避免受base标签影响
                absolute_asset_path = f"/assets/{safe_filename}"
                self.downloaded_assets[url] = absolute_asset_path
                print(f"  📥 下载资源: {url[:60]}... -> {absolute_asset_path}")
                return absolute_asset_path
        except Exception as e:
            print(f"  ❌ 下载失败: {url[:60]}... - {e}")
        
        return None
    
    def _process_js_content(self, js_content: str, js_url: str, base_url: str) -> str:
        """处理JS文件内容，替换动态加载的URL为本地路径"""
        parsed_js = urlparse(js_url)
        js_base = f"{parsed_js.scheme}://{parsed_js.netloc}"
        
        # 1. 替换 baseURL 变量 - 使用空字符串，因为后面的路径已经包含/assets/
        baseurl_pattern = r'(var\s+\w*[Bb]ase\w*[Uu][Rr][Ll]\s*=\s*["\'])([^"\']+)(["\'])'
        for match in re.finditer(baseurl_pattern, js_content):
            original_url = match.group(2)
            if original_url.startswith('/'):
                # 替换为空字符串，让后面的完整路径生效
                js_content = js_content.replace(match.group(0), f'{match.group(1)}{match.group(3)}')
        
        # 2. 替换动态加载的脚本路径 - 使用绝对路径
        dynamic_js_pattern = r'(["\'])(/[^"\']+\.js)(["\'])'
        for match in re.finditer(dynamic_js_pattern, js_content):
            original_path = match.group(2)
            filename = os.path.basename(original_path)
            if filename:
                # 使用绝对路径 /assets/filename
                local_path = f"/assets/{filename}"
                js_content = js_content.replace(match.group(0), f'{match.group(1)}{local_path}{match.group(3)}')
        
        return js_content
    
    def _extract_and_download_assets(self, html: str, base_url: str) -> str:
        """提取并下载所有资源，替换为本地路径"""
        
        # CSS文件 - href属性
        css_pattern = r'href=["\']([^"\']+\.css[^"\']*)["\']'
        for match in re.finditer(css_pattern, html):
            url = match.group(1)
            if url.startswith('http') or url.startswith('//'):
                absolute_url = url if url.startswith('http') else f"http:{url}"
            else:
                absolute_url = urljoin(base_url, url)
            local_path = self._download_asset(absolute_url, 'css', base_url)
            if local_path:
                html = html.replace(match.group(0), f'href="{local_path}"')
        
        # JS文件 - src属性
        js_pattern = r'src=["\']([^"\']+\.js[^"\']*)["\']'
        for match in re.finditer(js_pattern, html):
            url = match.group(1)
            if url.startswith('http') or url.startswith('//'):
                absolute_url = url if url.startswith('http') else f"http:{url}"
            else:
                absolute_url = urljoin(base_url, url)
            local_path = self._download_asset(absolute_url, 'js', base_url)
            if local_path:
                html = html.replace(match.group(0), f'src="{local_path}"')
        
        # 图片文件
        img_pattern = r'src=["\']([^"\']+\.(?:png|jpg|jpeg|gif|svg|webp)[^"\']*)["\']'
        for match in re.finditer(img_pattern, html):
            url = match.group(1)
            if url.startswith('http') or url.startswith('//'):
                absolute_url = url if url.startswith('http') else f"http:{url}"
            else:
                absolute_url = urljoin(base_url, url)
            local_path = self._download_asset(absolute_url, 'image')
            if local_path:
                html = html.replace(match.group(0), f'src="{local_path}"')
        
        # 处理CSS中的url()引用
        css_url_pattern = r'url\(["\']?([^"\')]+)["\']?\)'
        for match in re.finditer(css_url_pattern, html):
            url = match.group(1)
            if url.startswith('data:'):
                continue
            if url.startswith('http') or url.startswith('//'):
                absolute_url = url if url.startswith('http') else f"http:{url}"
            else:
                absolute_url = urljoin(base_url, url)
            local_path = self._download_asset(absolute_url, 'image')
            if local_path:
                html = html.replace(match.group(0), f'url({local_path})')
        
        # 预下载可能被JS动态加载的资源
        self._pre_download_dynamic_resources(base_url)
        
        return html
    
    def _pre_download_dynamic_resources(self, base_url: str):
        """预下载可能被JS动态加载的资源"""
        parsed_base = urlparse(base_url)
        site_base = f"{parsed_base.scheme}://{parsed_base.netloc}"
        
        # 1. 键盘加密相关的JS文件
        keyboard_paths = [
            '/portal/static/keyboard/SM/plugins/',
            '/portal/static/keyboard/SM/',
        ]
        keyboard_files = [
            'jsbn-min.js', 'jsbn2-min.js', 'ec-min.js', 'ecparam-1.0.js',
            'prng4-min.js', 'rng-min.js', 'ecdsa-modified-1.0.js', 
            'ec-patch-min.js', 'base64-min.js', 'SM.js', 'SM3.js'
        ]
        
        for path in keyboard_paths:
            for js_file in keyboard_files:
                url = urljoin(site_base, path + js_file)
                if url not in self.downloaded_assets:
                    try:
                        response = requests.get(url, timeout=5)
                        if response.status_code == 200:
                            self._download_asset(url, 'js', base_url)
                    except:
                        pass
        
        # 2. Webpack动态加载的chunks
        chunk_files = [
            'chunk-commons.4e9b6c9eaa837e97.js',
            '7583.bef8510f53f3e185.js',
            '6403.47c53497aafd4db8.js',
            '5202.dafbf83f83ae5cdd.js',
            '310.f175e6bc712640e0.js',
        ]
        
        for chunk in chunk_files:
            url = urljoin(site_base, f'/portal/js/{chunk}')
            if url not in self.downloaded_assets:
                try:
                    response = requests.get(url, timeout=5)
                    if response.status_code == 200:
                        self._download_asset(url, 'js', base_url)
                except:
                    pass
        
        # 3. 图片资源
        img_files = [
            'banner_1920@1x.9c11343d.png',
            'bg_1920@1x.048336a0.png',
        ]
        
        for img in img_files:
            url = urljoin(site_base, f'/portal/static/img/{img}')
            if url not in self.downloaded_assets:
                try:
                    response = requests.get(url, timeout=5)
                    if response.status_code == 200:
                        self._download_asset(url, 'image', base_url)
                except:
                    pass
    
    def _cleanup_html(self, html: str) -> str:
        """清理HTML中的敏感信息"""
        patterns = [
            (r'password\s*[=:]\s*["\'][^"\']+["\']', 'password="***"'),
            (r'token\s*[=:]\s*["\'][^"\']+["\']', 'token="***"'),
            (r'api[_-]?key\s*[=:]\s*["\'][^"\']+["\']', 'api_key="***"'),
        ]
        for pattern, replacement in patterns:
            html = re.sub(pattern, replacement, html, flags=re.IGNORECASE)
        return html
    
    def _move_scripts_to_body_bottom(self, html: str) -> str:
        """将script标签移到body底部，确保DOM加载完成后再执行"""
        script_pattern = r'<script[^>]*>.*?</script>'
        scripts = re.findall(script_pattern, html, re.DOTALL)
        html_without_scripts = re.sub(script_pattern, '', html, flags=re.DOTALL)
        
        if scripts:
            body_close = html_without_scripts.rfind('</body>')
            if body_close != -1:
                scripts_html = '\n'.join(scripts)
                html = html_without_scripts[:body_close] + scripts_html + '\n' + html_without_scripts[body_close:]
        
        return html
    
    def crawl(self, url: str, max_depth: int = 2, visited: set = None) -> CrawlResult:
        """爬取网页，支持深度爬取"""
        if visited is None:
            visited = set()
        
        if url in visited or max_depth < 0:
            return CrawlResult(url=url)
        
        visited.add(url)
        
        print(f'\n{"="*70}')
        print(f'🕷️ 开始爬取页面 [深度: {max_depth}]')
        print(f'   目标URL: {url}')
        print(f'{"="*70}')
        
        result = CrawlResult(url=url)
        action_records = []
        api_responses = {}
        new_pages = []
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(viewport=self.viewport)
            page = context.new_page()
            
            # 监听新页面
            def handle_page(new_page):
                new_pages.append(new_page)
                print(f"     🆕 新页面打开: {new_page.url}")
                action_records.append(ActionRecord(
                    type="new_page_opened",
                    url=new_page.url,
                    metadata={"new_page_url": new_page.url, "source": page.url}
                ))
            context.on("page", handle_page)
            
            # 监听API响应
            def handle_response(response):
                if response.request.resource_type in ['xhr', 'fetch']:
                    try:
                        resp_url = response.url
                        if '/api/' in resp_url or '/port/' in resp_url:
                            try:
                                body = response.json()
                            except:
                                body = None
                            api_responses[resp_url] = {
                                'status': response.status,
                                'body': body,
                                'timestamp': datetime.now().isoformat()
                            }
                    except:
                        pass
            page.on("response", handle_response)
            
            try:
                # 记录开始
                action_records.append(ActionRecord(
                    type="crawl_start",
                    url=url,
                    metadata={"target_url": url, "timestamp": datetime.now().isoformat()}
                ))
                
                # 加载页面
                print("\n📄 加载页面...")
                page.goto(url, wait_until='networkidle')
                page.wait_for_timeout(3000)
                
                result.title = page.title()
                print(f"✅ 页面加载完成: {result.title}")
                
                # 获取并处理HTML
                html = page.content()
                html = self._cleanup_html(html)
                html = self._extract_and_download_assets(html, url)
                html = self._move_scripts_to_body_bottom(html)
                
                # 保存HTML
                html_filename = self._generate_filename(url) + ".html"
                html_path = os.path.join(self.pages_dir, html_filename)
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(html)
                result.html_path = html_path
                result.html = html
                print(f"✅ HTML已保存: {html_filename}")
                
                # 保存截图
                screenshot_filename = self._generate_filename(url) + ".png"
                screenshot_path = os.path.join(self.screenshots_dir, screenshot_filename)
                page.screenshot(path=screenshot_path, full_page=self.screenshot_full_page)
                result.screenshot_path = screenshot_path
                print(f"✅ 截图已保存: {screenshot_filename}")
                
                action_records.append(ActionRecord(
                    type="page_saved",
                    url=url,
                    metadata={
                        "target_url": url,
                        "html_path": html_path,
                        "screenshot_path": screenshot_path,
                        "title": result.title
                    }
                ))
                
                # 自动交互
                print("\n🖱️ 开始自动交互...")
                clicked_urls = self._auto_interact(page, action_records, new_pages)
                
                # 处理新打开的页面（弹出窗口等）
                self._process_new_pages(new_pages, action_records, visited, max_depth)
                
                # 深度爬取：在当前browser中打开新页面
                if max_depth > 0 and clicked_urls:
                    print(f"\n🔄 深度爬取 [剩余深度: {max_depth-1}]...")
                    for clicked_url in clicked_urls[:3]:  # 最多处理3个链接
                        if clicked_url not in visited and clicked_url != url:
                            print(f"   爬取链接: {clicked_url}")
                            try:
                                new_page = context.new_page()
                                new_page.goto(clicked_url, wait_until='networkidle')
                                new_page.wait_for_timeout(2000)
                                
                                # 保存新页面
                                html = new_page.content()
                                html = self._cleanup_html(html)
                                html = self._extract_and_download_assets(html, clicked_url)
                                html = self._move_scripts_to_body_bottom(html)
                                
                                filename = self._generate_filename(clicked_url) + ".html"
                                filepath = os.path.join(self.pages_dir, filename)
                                with open(filepath, 'w', encoding='utf-8') as f:
                                    f.write(html)
                                
                                screenshot_path = os.path.join(self.screenshots_dir, filename.replace('.html', '.png'))
                                new_page.screenshot(path=screenshot_path)
                                
                                print(f"     ✅ 深度页面已保存: {filename}")
                                action_records.append(ActionRecord(
                                    type="deep_page_saved",
                                    url=clicked_url,
                                    metadata={
                                        "html_path": filepath,
                                        "screenshot_path": screenshot_path,
                                        "title": new_page.title()
                                    }
                                ))
                                new_page.close()
                            except Exception as e:
                                print(f"     ❌ 深度爬取失败: {e}")
                
                browser.close()
                
            except Exception as e:
                result.error = str(e)
                print(f"❌ 错误: {e}")
                browser.close()
        
        # 保存操作记录
        self._save_action_records(action_records, url)
        
        # 保存API响应
        if api_responses:
            api_path = os.path.join(self.output_dir, self._generate_filename(url) + "_api.json")
            with open(api_path, 'w', encoding='utf-8') as f:
                json.dump(api_responses, f, ensure_ascii=False, indent=2)
            result.api_responses = api_responses
        
        result.actions = action_records
        
        print(f'\n{"="*70}')
        print(f'✅ 爬取完成')
        print(f'   目标URL: {url}')
        print(f'   页面标题: {result.title}')
        print(f'   HTML文件: {result.html_path}')
        print(f'   截图文件: {result.screenshot_path}')
        print(f'{"="*70}\n')
        
        return result
    
    def _auto_interact(self, page, actions: List[ActionRecord], new_pages: List) -> List[str]:
        """自动与页面交互，返回点击后跳转的URL列表"""
        clicked_urls = []
        
        def check_toast():
            """检测toast消息"""
            selectors = [
                '.el-message', '.toast', '.notification', 
                '[class*="message"]', '[class*="toast"]', '[class*="notification"]'
            ]
            for selector in selectors:
                try:
                    elem = page.locator(selector).first
                    if elem.count() > 0 and elem.is_visible():
                        text = elem.text_content()
                        if text:
                            return text.strip()
                except:
                    pass
            return None
        
        def check_dialog():
            """检测弹窗"""
            selectors = ['.el-dialog', '[role="dialog"]', '.modal', '[class*="dialog"]']
            for selector in selectors:
                try:
                    elem = page.locator(selector).first
                    if elem.count() > 0 and elem.is_visible():
                        title = ""
                        try:
                            title_elem = elem.locator('[class*="title"]').first
                            if title_elem.count() > 0:
                                title = title_elem.text_content() or ""
                        except:
                            pass
                        return {"selector": selector, "title": title.strip()[:100]}
                except:
                    pass
            return None
        
        def click_element(selector, description, parent=None):
            """点击元素并记录"""
            try:
                if parent:
                    elem = parent.locator(selector).first
                else:
                    elem = page.locator(selector).first
                    
                if elem.count() == 0:
                    return False, None
                
                # 获取href属性（如果有）
                href = None
                try:
                    href = elem.get_attribute('href')
                except:
                    pass
                
                print(f"  🖱️ 点击: {description}")
                before_url = page.url
                
                elem.click()
                page.wait_for_timeout(2000)
                
                toast = check_toast()
                dialog = check_dialog()
                url_changed = page.url != before_url
                
                # 如果URL改变，记录新URL用于深度爬取
                if url_changed:
                    clicked_urls.append(page.url)
                
                result_status = "success"
                # 通用登录检测关键词（支持多语言）
                login_keywords = ['login', 'log in', 'sign in', '请先', '请登录', 'need login', 'required', 'auth', '权限', 'signin']
                error_keywords = ['error', 'fail', '错误', '失败', 'invalid', 'invalid', 'denied', '拒绝']
                
                toast_lower = toast.lower() if toast else ""
                if toast and any(kw in toast or kw in toast_lower for kw in login_keywords):
                    result_status = "need_login"
                elif toast and any(kw in toast or kw in toast_lower for kw in error_keywords):
                    result_status = "error"
                
                metadata = {
                    "description": description,
                    "result": result_status,
                    "url_changed": url_changed,
                    "href": href
                }
                if toast:
                    metadata["toast"] = toast
                    print(f"     💬 Toast: {toast}")
                if dialog:
                    metadata["dialog"] = dialog
                    print(f"     🪟 弹窗: {dialog.get('title', '')}")
                
                actions.append(ActionRecord(
                    type="click",
                    selector=selector,
                    value=description,
                    url=page.url,
                    metadata=metadata
                ))
                return True, href
            except Exception as e:
                actions.append(ActionRecord(
                    type="click",
                    selector=selector,
                    value=description,
                    url=page.url,
                    metadata={"description": description, "result": "failed", "error": str(e)}
                ))
                return False, None
        
        def hover_and_click_submenu(parent_selector, parent_name):
            """悬停父菜单并点击子菜单 - 只查找真正的下拉菜单项"""
            try:
                parent = page.locator(parent_selector).first
                if parent.count() == 0:
                    return
                
                print(f"\n  📂 展开菜单: {parent_name}")
                parent.hover()
                page.wait_for_timeout(1000)
                
                # 查找子菜单项 - 限制在下拉菜单容器内
                dropdown_selectors = [
                    '.el-dropdown-menu',
                    '[class*="dropdown-menu"]',
                    '[class*="submenu"]',
                    '[class*="menu-list"]',
                    'ul[class*="menu"]'
                ]
                
                submenu_item_selectors = [
                    'li',
                    'li a',
                    '[class*="menu-item"]',
                    '[role="menuitem"]'
                ]
                
                clicked = []
                
                # 先找到下拉菜单容器
                for dropdown_selector in dropdown_selectors:
                    try:
                        dropdown = page.locator(dropdown_selector).first
                        if dropdown.count() > 0 and dropdown.is_visible():
                            # 在容器内查找子菜单项
                            for item_selector in submenu_item_selectors:
                                try:
                                    items = dropdown.locator(item_selector).all()
                                    for item in items[:8]:  # 最多点击8个子菜单
                                        try:
                                            if item.is_visible():
                                                text = item.text_content() or ""
                                                text = text.strip()[:50]
                                                # 过滤无效文本和已点击的
                                                if text and len(text) > 0 and text not in clicked and text != parent_name:
                                                    # 排除导航链接 - 使用通用逻辑：如果文本和父菜单名称相同或在父菜单中已存在，则跳过
                                                    parent_words = set(parent_name.lower().split())
                                                    text_words = set(text.lower().split())
                                                    # 如果文本是父菜单的子集或高度相似，则可能是导航链接
                                                    is_nav_item = text in clicked or text == parent_name or len(text_words & parent_words) == len(text_words)
                                                    if not is_nav_item:
                                                        clicked.append(text)
                                                        click_element(f'text="{text}"', f"{parent_name} - {text}")
                                        except:
                                            pass
                                except:
                                    pass
                            break  # 找到下拉菜单后就退出
                    except:
                        pass
                        
            except Exception as e:
                print(f"     ⚠️ 处理菜单失败: {e}")
        
        # 发现可点击元素 - 更全面的选择器
        print("\n  🔍 发现可点击元素...")
        clickable_selectors = [
            'button', 'a', '[role="button"]', '[role="link"]',
            'input[type="submit"]', 'input[type="button"]',
            '[class*="btn"]', '[class*="button"]',
            '[class*="link"]', '[class*="menu"] li', '[class*="nav"] li',
            'span[class*="login"]', 'span[class*="user"]', 
            '[class*="header"] a', '[class*="header"] button',
            '[class*="footer"] a', '[class*="footer"] button'
        ]
        
        found_elements = []
        for selector in clickable_selectors:
            try:
                elements = page.locator(selector).all()
                for elem in elements:
                    try:
                        if elem.is_visible():
                            text = elem.text_content() or ""
                            text = text.strip()[:50]
                            # 过滤无效文本，但保留短文本（如"登录"）
                            if text and len(text) > 0 and len(text) < 50 and text not in [e[1] for e in found_elements]:
                                found_elements.append((selector, text))
                    except:
                        pass
            except:
                pass
        
        # 额外查找短文本元素（通常是重要操作按钮）
        # 通用逻辑：查找1-4个字符的可见文本元素，这些通常是按钮或链接
        short_text_selectors = ['button', 'a', 'span', '[role="button"]', '[class*="btn"]']
        for selector in short_text_selectors:
            try:
                elements = page.locator(selector).all()
                for elem in elements:
                    try:
                        if elem.is_visible():
                            text = elem.text_content() or ""
                            text = text.strip()
                            # 查找短文本（1-4个字符）且尚未记录的
                            if 0 < len(text) <= 4 and text not in [e[1] for e in found_elements]:
                                found_elements.append((selector, text))
                    except:
                        pass
            except:
                pass
        
        print(f"     发现 {len(found_elements)} 个可点击元素")
        
        # 点击所有发现的元素（最多25个）
        for selector, text in found_elements[:25]:
            success, href = click_element(f"{selector}:has-text(\"{text}\")", text)
            
            # 尝试悬停查看是否有子菜单
            if success:
                try:
                    elem = page.locator(f"{selector}:has-text(\"{text}\")").first
                    if elem.count() > 0:
                        hover_and_click_submenu(f"{selector}:has-text(\"{text}\")", text)
                except:
                    pass
        
        return clicked_urls
    
    def _process_new_pages(self, new_pages: List, actions: List[ActionRecord], visited: set, max_depth: int):
        """处理新打开的页面"""
        print(f"\n🆕 处理 {len(new_pages)} 个新页面...")
        
        for i, new_page in enumerate(new_pages[:5]):  # 最多处理5个新页面
            try:
                print(f"  📄 新页面 {i+1}: {new_page.url}")
                
                # 记录新页面打开
                actions.append(ActionRecord(
                    type="new_page_opened",
                    url=new_page.url,
                    metadata={"new_page_url": new_page.url}
                ))
                
                # 检查是否是PDF
                if '.pdf' in new_page.url.lower():
                    try:
                        resp = requests.get(new_page.url, timeout=30)
                        if resp.status_code == 200:
                            url_path = unquote(new_page.url.split('?')[0])
                            filename = os.path.basename(url_path) or f"document_{i+1}.pdf"
                            filepath = os.path.join(self.output_dir, filename)
                            
                            with open(filepath, 'wb') as f:
                                f.write(resp.content)
                            
                            print(f"     ✅ PDF已下载: {filename}")
                            actions.append(ActionRecord(
                                type="pdf_download",
                                url=new_page.url,
                                metadata={
                                    "filename": filename,
                                    "local_path": filepath,
                                    "size": len(resp.content)
                                }
                            ))
                    except Exception as e:
                        print(f"     ❌ PDF下载失败: {e}")
                else:
                    # 保存普通页面
                    try:
                        new_page.wait_for_load_state('networkidle')
                        html = new_page.content()
                        
                        # 处理HTML（下载资源等）
                        html = self._cleanup_html(html)
                        html = self._extract_and_download_assets(html, new_page.url)
                        html = self._move_scripts_to_body_bottom(html)
                        
                        filename = self._generate_filename(new_page.url) + f"_page_{i+1}.html"
                        filepath = os.path.join(self.pages_dir, filename)
                        
                        with open(filepath, 'w', encoding='utf-8') as f:
                            f.write(html)
                        
                        # 截图
                        screenshot_path = os.path.join(self.screenshots_dir, filename.replace('.html', '.png'))
                        new_page.screenshot(path=screenshot_path)
                        
                        print(f"     ✅ 页面已保存: {filename}")
                        actions.append(ActionRecord(
                            type="new_page_saved",
                            url=new_page.url,
                            metadata={
                                "html_path": filepath,
                                "screenshot_path": screenshot_path,
                                "title": new_page.title()
                            }
                        ))
                        
                        # 深度爬取新页面
                        if max_depth > 0 and new_page.url not in visited:
                            print(f"     🔄 深度爬取新页面...")
                            self.crawl(new_page.url, max_depth - 1, visited)
                            
                    except Exception as e:
                        print(f"     ❌ 保存页面失败: {e}")
            except Exception as e:
                print(f"     ❌ 处理新页面失败: {e}")
    
    def _save_action_records(self, actions: List[ActionRecord], start_url: str):
        """保存操作记录"""
        record_path = os.path.join(self.output_dir, "crawl_actions.json")
        
        # 如果文件已存在，读取现有记录并追加
        existing_data = {"actions": []}
        if os.path.exists(record_path):
            try:
                with open(record_path, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
            except:
                pass
        
        existing_actions = existing_data.get("actions", [])
        existing_actions.extend([a.to_dict() for a in actions])
        
        record_data = {
            "task_info": {
                "start_url": start_url,
                "output_dir": self.output_dir,
                "timestamp": datetime.now().isoformat()
            },
            "summary": {
                "total_actions": len(existing_actions),
                "clicks": len([a for a in existing_actions if a["type"] == "click"]),
                "new_pages": len([a for a in existing_actions if a["type"] == "new_page_opened"]),
                "downloads": len([a for a in existing_actions if a["type"] == "pdf_download"])
            },
            "actions": existing_actions
        }
        
        with open(record_path, 'w', encoding='utf-8') as f:
            json.dump(record_data, f, ensure_ascii=False, indent=2)
        
        print(f"\n📝 操作记录已保存: {record_path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='通用智能网页爬虫')
    parser.add_argument('url', help='目标URL')
    parser.add_argument('-o', '--output', default='output', help='输出目录')
    parser.add_argument('--headless', action='store_true', help='无头模式')
    parser.add_argument('-d', '--depth', type=int, default=2, help='爬取深度')
    
    args = parser.parse_args()
    
    crawler = SmartWebCrawler(
        output_dir=args.output,
        headless=args.headless
    )
    
    result = crawler.crawl(args.url, max_depth=args.depth)
