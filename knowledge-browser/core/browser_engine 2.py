#!/usr/bin/env python3
"""
浏览器引擎 - 基于Playwright (线程安全版本)
支持完整操作录制和多标签页跟踪
"""
import os
import json
import time
import threading
import queue
from datetime import datetime
from typing import Optional, Callable, Dict, List, Any


class BrowserEngine:
    """浏览器引擎 - 封装Playwright功能 (线程安全)"""
    
    def __init__(self, output_dir: str = "output"):
        self.output_dir = output_dir
        
        # 录制状态
        self.is_recording = False
        self.recorded_actions: List[Dict] = []
        self.start_time: Optional[datetime] = None
        
        # 页面跳转历史
        self.navigation_history: List[Dict] = []
        
        # 回调函数
        self.on_navigate: Optional[Callable] = None
        self.on_click: Optional[Callable] = None
        self.on_input: Optional[Callable] = None
        self.on_screenshot: Optional[Callable] = None
        self.on_new_tab: Optional[Callable] = None
        self.on_action: Optional[Callable] = None  # 通用操作回调（用于视频录制触发）
        
        # 实时截图
        self.screenshot_interval = 2
        self.last_screenshot_path: Optional[str] = None
        
        # 线程通信队列
        self._command_queue = queue.Queue()
        self._result_queue = queue.Queue()
        
        # 浏览器线程
        self._browser_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # 浏览器状态
        self._is_running = False
        self._current_url = ""
        
        # 多标签页管理
        self._pages: Dict[str, Any] = {}  # page_id -> page object
        self._current_page_id: Optional[str] = None
        self._page_counter = 0
        
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        
    def launch(self, headless: bool = False):
        """启动浏览器"""
        if self._is_running:
            print("⚠️ 浏览器已在运行")
            return
            
        self._browser_thread = threading.Thread(
            target=self._browser_loop,
            args=(headless,),
            daemon=True
        )
        self._browser_thread.start()
        
        # 等待启动结果
        result = self._result_queue.get(timeout=30)
        if result.get('success'):
            self._is_running = True
            print("✅ 浏览器启动成功")
        else:
            raise RuntimeError(result.get('error', '启动失败'))
            
    def _browser_loop(self, headless: bool):
        """浏览器主循环（在独立线程中运行）"""
        from playwright.sync_api import sync_playwright
        
        try:
            # 获取屏幕尺寸
            import subprocess
            result = subprocess.run(
                ['system_profiler', 'SPDisplaysDataType', '-json'],
                capture_output=True, text=True
            )
            
            # 默认使用屏幕分辨率
            screen_width = 1920
            screen_height = 1080
            
            # 尝试获取实际屏幕分辨率
            try:
                import json
                data = json.loads(result.stdout)
                for display in data.get('SPDisplaysDataType', []):
                    for screen in display.get('spdisplays_ndrvs', []):
                        if '_spdisplays_resolution' in screen:
                            res = screen['_spdisplays_resolution']
                            if 'x' in res:
                                parts = res.split('x')
                                screen_width = int(parts[0].strip())
                                screen_height = int(parts[1].strip().split()[0])
                                break
            except:
                pass
            
            print(f"🖥️ 屏幕分辨率: {screen_width}x{screen_height}")
            
            playwright = sync_playwright().start()
            browser = playwright.chromium.launch(
                headless=headless,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-popup-blocking',
                    f'--window-size={screen_width},{screen_height}'
                ]
            )
            
            # 创建上下文，使用屏幕全尺寸
            context = browser.new_context(
                viewport={'width': screen_width, 'height': screen_height},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            )
            
            # 监听新页面创建（新标签页）
            context.on("page", lambda page: self._on_new_page(page))
            
            # 创建第一个页面
            page = context.new_page()
            self._register_page(page, "main")
            
            # 通知主线程启动成功
            self._result_queue.put({'success': True})
            
            # 主循环
            while not self._stop_event.is_set():
                try:
                    # 非阻塞获取命令
                    cmd = self._command_queue.get(timeout=0.1)
                    self._execute_command(cmd, page, context, browser)
                except queue.Empty:
                    # 检查当前页面是否已关闭，如果是则切换到其他页面
                    if self._current_page_id and self._current_page_id in self._pages:
                        current_page = self._pages[self._current_page_id]
                        try:
                            current_page.is_closed()
                        except:
                            # 页面已关闭，切换到第一个可用页面
                            self._switch_to_available_page()
                    continue
                    
        except Exception as e:
            self._result_queue.put({'success': False, 'error': str(e)})
        finally:
            try:
                if 'context' in locals():
                    context.close()
                if 'browser' in locals():
                    browser.close()
                if 'playwright' in locals():
                    playwright.stop()
            except:
                pass
            self._is_running = False
            
    def _register_page(self, page, page_type="tab"):
        """注册新页面"""
        self._page_counter += 1
        page_id = f"{page_type}_{self._page_counter}"
        self._pages[page_id] = page
        self._current_page_id = page_id
        
        # 设置页面事件监听
        page.on("load", lambda p: self._on_page_load(p, page_id))
        page.on("framenavigated", lambda frame: self._on_frame_navigated(frame, page_id))
        
        # 如果正在录制，在新页面也注入录制脚本
        if self.is_recording:
            try:
                page.wait_for_load_state("domcontentloaded", timeout=5000)
                self._inject_recording_script(page, page_id)
            except:
                pass
        
        return page_id
        
    def _on_new_page(self, page):
        """处理新页面创建（新标签页）"""
        page_id = self._register_page(page, "popup")
        print(f"📄 新标签页打开: {page_id}")
        
        # 记录新标签页事件
        if self.is_recording:
            self._record_action({
                "type": "new_tab",
                "timestamp": datetime.now().isoformat(),
                "page_id": page_id,
                "description": "新标签页打开"
            })
        
        if self.on_new_tab:
            try:
                self.on_new_tab(page_id)
            except:
                pass
                
    def _switch_to_available_page(self):
        """切换到第一个可用的页面"""
        for page_id, page in list(self._pages.items()):
            try:
                if not page.is_closed():
                    self._current_page_id = page_id
                    self._current_url = page.url
                    return
            except:
                del self._pages[page_id]
        
    def _get_current_page(self):
        """获取当前页面"""
        if self._current_page_id and self._current_page_id in self._pages:
            page = self._pages[self._current_page_id]
            try:
                if not page.is_closed():
                    return page
            except Exception as e:
                # 页面已关闭或出现错误
                print(f"🔴 当前页面已关闭: {e}")
                pass
        # 当前页面不可用，切换到其他页面
        self._switch_to_available_page()
        return self._pages.get(self._current_page_id)
        
    def _on_page_load(self, page, page_id):
        """页面加载完成"""
        try:
            # 检查页面是否已关闭
            if page.is_closed():
                print(f"🔴 页面已关闭，跳过加载处理")
                return
                
            url = page.url
            self._current_url = url
            
            # 安全地获取标题
            try:
                title = page.title()
            except:
                title = ""
            
            # 记录导航历史
            nav_record = {
                "timestamp": datetime.now().isoformat(),
                "url": url,
                "page_id": page_id,
                "title": title
            }
            self.navigation_history.append(nav_record)
        except Exception as e:
            print(f"🔴 页面加载处理出错: {e}")
            return
        
        # 如果正在录制，重新注入录制脚本
        if self.is_recording:
            try:
                self._inject_recording_script(page, page_id)
            except:
                pass
        
        if self.on_navigate:
            try:
                self.on_navigate(url)
            except:
                pass
                
    def _on_frame_navigated(self, frame, page_id):
        """框架导航"""
        if frame == frame.page.main_frame:
            url = frame.url
            print(f"🔄 页面跳转: {url}")
            
            # 记录跳转
            if self.is_recording:
                self._record_action({
                    "type": "navigation",
                    "timestamp": datetime.now().isoformat(),
                    "url": url,
                    "page_id": page_id,
                    "description": f"页面跳转到: {url}"
                })
                
    def _record_action(self, action: Dict):
        """记录操作到所有页面的共享存储"""
        print(f"🔴 _record_action 被调用: {action.get('type')}")
        
        # 通过 JavaScript 存储在 window 对象中，所有页面共享
        for page_id, page in list(self._pages.items()):
            try:
                if not page.is_closed():
                    page.evaluate(f"""
                        () => {{
                            if (window.__kb_recording && window.__kb_actions) {{
                                window.__kb_actions.push({json.dumps(action)});
                            }}
                        }}
                    """)
            except:
                pass
        
        # 触发操作回调（用于视频录制截图）
        print(f"🔴 检查 on_action 回调: {self.on_action}")
        if self.on_action:
            try:
                print(f"🔴 调用 on_action 回调")
                self.on_action(action)
                print(f"🔴 on_action 回调完成")
            except Exception as e:
                print(f"🔴 on_action 回调异常: {e}")
                import traceback
                traceback.print_exc()
        else:
            print(f"🔴 on_action 回调未设置")
                
    def _inject_recording_script(self, page, page_id):
        """注入录制脚本到页面"""
        try:
            page.evaluate(f"""
                () => {{
                    // 如果已经初始化过，只恢复录制状态
                    if (window.__kb_initialized) {{
                        window.__kb_recording = true;
                        window.__kb_page_id = "{page_id}";
                        const indicator = document.getElementById('__kb_indicator');
                        if (indicator) indicator.style.display = 'block';
                        console.log('[KB] 录制已恢复在页面:', "{page_id}");
                        return;
                    }}
                    
                    window.__kb_initialized = true;
                    window.__kb_recording = true;
                    window.__kb_page_id = "{page_id}";
                    window.__kb_actions = window.__kb_actions || [];  // 共享操作数组
                    
                    // 添加录制指示器
                    const addIndicator = () => {{
                        if (!document.body) {{
                            setTimeout(addIndicator, 100);
                            return;
                        }}
                        
                        const oldIndicator = document.getElementById('__kb_indicator');
                        if (oldIndicator) oldIndicator.remove();
                        
                        const indicator = document.createElement('div');
                        indicator.id = '__kb_indicator';
                        indicator.style.cssText = `
                            position: fixed;
                            top: 10px;
                            right: 10px;
                            background: #f44336;
                            color: white;
                            padding: 8px 16px;
                            border-radius: 20px;
                            font-family: Arial, sans-serif;
                            font-size: 14px;
                            font-weight: bold;
                            z-index: 999999;
                            box-shadow: 0 2px 8px rgba(0,0,0,0.3);
                        `;
                        indicator.innerHTML = '正在录制';
                        document.body.appendChild(indicator);
                        console.log('[KB] 录制指示器已添加到页面:', "{page_id}");
                    }};
                    addIndicator();
                    
                    // 生成元素选择器
                    const getSelector = (el) => {{
                        const path = [];
                        while (el && el.nodeType === Node.ELEMENT_NODE) {{
                            let selector = el.nodeName.toLowerCase();
                            if (el.id) {{
                                selector += '#' + el.id;
                                path.unshift(selector);
                                break;
                            }} else {{
                                let sibling = el;
                                let nth = 1;
                                while (sibling = sibling.previousElementSibling) {{
                                    if (sibling.nodeName.toLowerCase() === selector) nth++;
                                }}
                                if (nth !== 1) selector += `:nth-of-type(${{nth}})`;
                            }}
                            if (el.className) {{
                                const classes = el.className.split(' ').filter(c => c).slice(0, 2);
                                if (classes.length > 0) selector += '.' + classes.join('.');
                            }}
                            path.unshift(selector);
                            el = el.parentNode;
                        }}
                        return path.join(' > ');
                    }};
                    
                    // 获取元素描述
                    const getElementInfo = (el) => {{
                        return {{
                            tagName: el.tagName,
                            id: el.id,
                            className: el.className,
                            name: el.name,
                            type: el.type,
                            href: el.href,
                            src: el.src,
                            text: el.textContent?.substring(0, 100).trim(),
                            selector: getSelector(el),
                            xpath: getSelector(el)  // 简化版xpath
                        }};
                    }};
                    
                    // 去重辅助函数
                    const isDuplicateAction = (type, target, position) => {{
                        const now = Date.now();
                        const key = `${{type}}_${{target.selector}}_${{position.x}}_${{position.y}}`;
                        
                        // 检查最近100ms内的相同操作
                        if (window.__kb_last_actions) {{
                            const lastAction = window.__kb_last_actions[key];
                            if (lastAction && (now - lastAction.time) < 100) {{
                                return true;
                            }}
                        }} else {{
                            window.__kb_last_actions = {{}};
                        }}
                        
                        window.__kb_last_actions[key] = {{ time: now }};
                        return false;
                    }};
                    
                    // 监听点击
                    document.addEventListener('click', (e) => {{
                        if (!window.__kb_recording) return;
                        
                        const target = e.target;
                        const selector = getSelector(target);
                        
                        // 去重检查
                        if (isDuplicateAction('click', {{ selector }}, {{ x: e.clientX, y: e.clientY }})) {{
                            return;
                        }}
                        
                        const action = {{
                            type: 'click',
                            timestamp: new Date().toISOString(),
                            page_id: window.__kb_page_id,
                            target: getElementInfo(target),
                            position: {{ x: e.clientX, y: e.clientY }},
                            description: `点击: ${{target.textContent?.substring(0, 30).trim() || target.tagName}}`
                        }};
                        
                        window.__kb_actions.push(action);
                        console.log('[KB] 点击记录:', action.description);
                    }}, true);
                    
                    // 监听双击
                    document.addEventListener('dblclick', (e) => {{
                        if (!window.__kb_recording) return;
                        
                        const target = e.target;
                        const selector = getSelector(target);
                        
                        // 去重检查
                        if (isDuplicateAction('dblclick', {{ selector }}, {{ x: e.clientX, y: e.clientY }})) {{
                            return;
                        }}
                        
                        const action = {{
                            type: 'dblclick',
                            timestamp: new Date().toISOString(),
                            page_id: window.__kb_page_id,
                            target: getElementInfo(target),
                            position: {{ x: e.clientX, y: e.clientY }},
                            description: `双击: ${{target.textContent?.substring(0, 30).trim() || target.tagName}}`
                        }};
                        
                        window.__kb_actions.push(action);
                        console.log('[KB] 双击记录:', action.description);
                    }}, true);
                    
                    // 监听输入
                    document.addEventListener('input', (e) => {{
                        if (!window.__kb_recording) return;
                        
                        const target = e.target;
                        // 防抖，避免每个字符都记录
                        clearTimeout(target.__kb_input_timeout);
                        target.__kb_input_timeout = setTimeout(() => {{
                            const action = {{
                                type: 'input',
                                timestamp: new Date().toISOString(),
                                page_id: window.__kb_page_id,
                                target: getElementInfo(target),
                                value: target.type === 'password' ? '********' : target.value?.substring(0, 200),
                                description: `输入: ${{target.name || target.id || target.placeholder || '文本'}}`
                            }};
                            
                            window.__kb_actions.push(action);
                            console.log('[KB] 输入记录:', action.description);
                        }}, 500);
                    }}, true);
                    
                    // 监听键盘
                    document.addEventListener('keydown', (e) => {{
                        if (!window.__kb_recording) return;
                        
                        // 只记录特殊按键
                        if (['Enter', 'Escape', 'Tab', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key)) {{
                            const action = {{
                                type: 'keydown',
                                timestamp: new Date().toISOString(),
                                page_id: window.__kb_page_id,
                                key: e.key,
                                target: getElementInfo(e.target),
                                description: `按键: ${{e.key}}`
                            }};
                            
                            window.__kb_actions.push(action);
                            console.log('[KB] 按键记录:', e.key);
                        }}
                    }}, true);
                    
                    // 监听表单提交
                    document.addEventListener('submit', (e) => {{
                        if (!window.__kb_recording) return;
                        
                        const action = {{
                            type: 'submit',
                            timestamp: new Date().toISOString(),
                            page_id: window.__kb_page_id,
                            target: getElementInfo(e.target),
                            description: `表单提交: ${{e.target.action || '未知'}}`
                        }};
                        
                        window.__kb_actions.push(action);
                        console.log('[KB] 表单提交记录');
                    }}, true);
                    
                    // 监听文件选择
                    document.addEventListener('change', (e) => {{
                        if (!window.__kb_recording) return;
                        
                        const target = e.target;
                        if (target.type === 'file' && target.files.length > 0) {{
                            const action = {{
                                type: 'file_upload',
                                timestamp: new Date().toISOString(),
                                page_id: window.__kb_page_id,
                                target: getElementInfo(target),
                                files: Array.from(target.files).map(f => ({{
                                    name: f.name,
                                    size: f.size,
                                    type: f.type
                                }})),
                                description: `上传文件: ${{target.files.length}} 个文件`
                            }};
                            
                            window.__kb_actions.push(action);
                            console.log('[KB] 文件上传记录:', target.files.length, '个文件');
                        }}
                    }}, true);
                    
                    // 监听滚动
                    let scrollTimeout;
                    window.addEventListener('scroll', () => {{
                        if (!window.__kb_recording) return;
                        
                        clearTimeout(scrollTimeout);
                        scrollTimeout = setTimeout(() => {{
                            const action = {{
                                type: 'scroll',
                                timestamp: new Date().toISOString(),
                                page_id: window.__kb_page_id,
                                position: {{ x: window.scrollX, y: window.scrollY }},
                                description: `滚动到: (${{Math.round(window.scrollX)}}, ${{Math.round(window.scrollY)}})`
                            }};
                            
                            window.__kb_actions.push(action);
                            console.log('[KB] 滚动记录:', action.description);
                        }}, 1000);
                    }}, true);
                    
                    // 监听鼠标移动（只记录重要位置）
                    let lastMousePos = {{ x: 0, y: 0 }};
                    document.addEventListener('mousemove', (e) => {{
                        if (!window.__kb_recording) return;
                        
                        const dx = Math.abs(e.clientX - lastMousePos.x);
                        const dy = Math.abs(e.clientY - lastMousePos.y);
                        
                        // 只记录移动超过100像素的位置
                        if (dx > 100 || dy > 100) {{
                            lastMousePos = {{ x: e.clientX, y: e.clientY }};
                            // 不记录到actions，避免数据过大
                        }}
                    }}, true);
                    
                    console.log('[KB] 录制系统已初始化在页面:', "{page_id}");
                }}
            """)
        except Exception as e:
            print(f"⚠️ 注入录制脚本失败: {e}")
            
    def _execute_command(self, cmd: Dict, page, context, browser):
        """执行命令"""
        cmd_type = cmd.get('type')
        
        try:
            if cmd_type == 'navigate':
                url = cmd.get('url')
                current_page = self._get_current_page()
                if current_page:
                    current_page.goto(url, wait_until="networkidle")
                    self._current_url = current_page.url
                self._result_queue.put({'success': True})
                
            elif cmd_type == 'get_source':
                current_page = self._get_current_page()
                html = current_page.content() if current_page else ""
                self._result_queue.put({'success': True, 'data': html})
                
            elif cmd_type == 'get_full_page':
                # 获取完整的页面，包括内联所有CSS
                current_page = self._get_current_page()
                if not current_page:
                    self._result_queue.put({'success': False, 'error': '没有可用页面'})
                    return
                    
                html = current_page.evaluate("""
                    () => {
                        // 克隆整个文档
                        const clone = document.documentElement.cloneNode(true);
                        const doc = document.implementation.createHTMLDocument();
                        doc.documentElement.innerHTML = clone.innerHTML;
                        
                        // 获取所有样式表并内联
                        const styles = [];
                        for (const sheet of document.styleSheets) {
                            try {
                                const rules = sheet.cssRules || sheet.rules;
                                if (rules) {
                                    let cssText = '';
                                    for (const rule of rules) {
                                        cssText += rule.cssText + '\\n';
                                    }
                                    styles.push(cssText);
                                }
                            } catch (e) {
                                // 跨域样式表无法访问，跳过
                            }
                        }
                        
                        // 创建内联样式标签
                        if (styles.length > 0) {
                            const styleEl = doc.createElement('style');
                            styleEl.textContent = styles.join('\\n');
                            doc.head.insertBefore(styleEl, doc.head.firstChild);
                        }
                        
                        // 将所有相对URL转换为绝对URL
                        const baseUrl = window.location.href;
                        const elements = doc.querySelectorAll('[src], [href]');
                        elements.forEach(el => {
                            if (el.src) {
                                try {
                                    el.src = new URL(el.src, baseUrl).href;
                                } catch (e) {}
                            }
                            if (el.href && el.tagName !== 'LINK') {
                                try {
                                    el.href = new URL(el.href, baseUrl).href;
                                } catch (e) {}
                            }
                        });
                        
                        // 处理link标签的href
                        const links = doc.querySelectorAll('link[rel="stylesheet"]');
                        links.forEach(link => {
                            if (link.href) {
                                try {
                                    link.href = new URL(link.href, baseUrl).href;
                                } catch (e) {}
                            }
                        });
                        
                        return '<!DOCTYPE html>\\n' + doc.documentElement.outerHTML;
                    }
                """)
                self._result_queue.put({'success': True, 'data': html})
                
            elif cmd_type == 'get_styles':
                current_page = self._get_current_page()
                if not current_page:
                    self._result_queue.put({'success': True, 'data': []})
                    return
                    
                styles = current_page.evaluate("""
                    () => {
                        const styles = [];
                        const elements = document.querySelectorAll('*');
                        elements.forEach((el, index) => {
                            if (index < 100) {
                                const computed = window.getComputedStyle(el);
                                const rect = el.getBoundingClientRect();
                                styles.push({
                                    tag: el.tagName,
                                    id: el.id,
                                    className: el.className,
                                    text: el.textContent?.substring(0, 50),
                                    rect: {
                                        x: rect.x,
                                        y: rect.y,
                                        width: rect.width,
                                        height: rect.height
                                    }
                                });
                            }
                        });
                        return styles;
                    }
                """)
                self._result_queue.put({'success': True, 'data': styles})
                
            elif cmd_type == 'screenshot':
                current_page = self._get_current_page()
                if not current_page:
                    self._result_queue.put({'success': False, 'error': '没有可用页面'})
                    return
                    
                import tempfile
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
                    temp_path = f.name
                current_page.screenshot(path=temp_path, full_page=True)
                self._result_queue.put({'success': True, 'data': temp_path})
                
            elif cmd_type == 'screenshot_sync':
                current_page = self._get_current_page()
                if not current_page or current_page.is_closed():
                    self._result_queue.put({'success': False, 'error': '页面已关闭'})
                    return
                    
                try:
                    import tempfile
                    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
                        temp_path = f.name
                    
                    # 使用CDP协议进行后台截图，完全不干扰页面
                    try:
                        # 尝试使用CDP协议截图（Chromium only）
                        context = current_page.context
                        browser = context.browser
                        if hasattr(browser, 'new_cdp_session'):
                            cdp_session = browser.new_cdp_session(current_page)
                            result = cdp_session.send('Page.captureScreenshot', {
                                'format': 'png',
                                'fromSurface': True
                            })
                            import base64
                            img_data = base64.b64decode(result['data'])
                            with open(temp_path, 'wb') as f:
                                f.write(img_data)
                        else:
                            # 回退到普通截图
                            current_page.screenshot(path=temp_path, full_page=False)
                    except:
                        # 如果CDP失败，使用普通截图
                        current_page.screenshot(path=temp_path, full_page=False)
                    
                    if self.on_screenshot:
                        self.on_screenshot(temp_path)
                    self._result_queue.put({'success': True, 'data': temp_path})
                except Exception as e:
                    self._result_queue.put({'success': False, 'error': str(e)})
                    
            elif cmd_type == 'start_recording':
                # 为所有页面注入录制脚本
                for page_id, page in list(self._pages.items()):
                    try:
                        if not page.is_closed():
                            self._inject_recording_script(page, page_id)
                    except:
                        pass
                self._result_queue.put({'success': True})
                
            elif cmd_type == 'stop_recording':
                # 从所有页面收集操作
                all_actions = []
                for page_id, page in list(self._pages.items()):
                    try:
                        if not page.is_closed():
                            result = page.evaluate("""
                                () => {
                                    window.__kb_recording = false;
                                    const indicator = document.getElementById('__kb_indicator');
                                    if (indicator) indicator.style.display = 'none';
                                    return {
                                        actions: window.__kb_actions || [],
                                        count: window.__kb_actions?.length || 0
                                    };
                                }
                            """)
                            if result and 'actions' in result:
                                all_actions.extend(result['actions'])
                    except:
                        pass
                
                # 按时间排序
                all_actions.sort(key=lambda x: x.get('timestamp', ''))
                
                duration = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0
                
                data = {
                    "start_time": self.start_time.isoformat() if self.start_time else None,
                    "duration": duration,
                    "actions_count": len(all_actions),
                    "actions": all_actions,
                    "navigation_history": self.navigation_history,
                    "pages": list(self._pages.keys())
                }
                
                self._result_queue.put({'success': True, 'data': data})
                
            elif cmd_type == 'close':
                self._stop_event.set()
                self._result_queue.put({'success': True})
                
            elif cmd_type == 'is_alive':
                current_page = self._get_current_page()
                is_alive = current_page is not None and not current_page.is_closed()
                self._result_queue.put({'success': True, 'data': is_alive})
                
            elif cmd_type == 'get_current_url':
                current_page = self._get_current_page()
                if current_page and not current_page.is_closed():
                    url = current_page.url
                    self._result_queue.put({'success': True, 'data': url})
                else:
                    self._result_queue.put({'success': False, 'error': 'No active page'})
                
        except Exception as e:
            self._result_queue.put({'success': False, 'error': str(e)})
            
    def _send_command(self, cmd: Dict, timeout: float = 30):
        """发送命令并等待结果"""
        self._command_queue.put(cmd)
        result = self._result_queue.get(timeout=timeout)
        if not result.get('success'):
            raise RuntimeError(result.get('error', 'Unknown error'))
        return result.get('data')
        
    def navigate(self, url: str):
        """导航到指定URL"""
        print(f"🌐 导航到: {url}")
        self._send_command({'type': 'navigate', 'url': url})
        
    def get_page_source(self) -> str:
        """获取页面源代码"""
        return self._send_command({'type': 'get_source'})
        
    def get_full_page(self) -> str:
        """获取完整页面（包含内联CSS和绝对路径）"""
        return self._send_command({'type': 'get_full_page'})
        
    def get_page_styles(self) -> List[Dict]:
        """获取页面样式信息"""
        return self._send_command({'type': 'get_styles'})
        
    def take_screenshot(self, name: Optional[str] = None) -> str:
        """截取屏幕"""
        temp_path = self._send_command({'type': 'screenshot'})
        
        # 复制到输出目录
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{name or 'screenshot'}_{timestamp}.png"
        filepath = os.path.join(self.output_dir, filename)
        
        import shutil
        shutil.copy(temp_path, filepath)
        os.remove(temp_path)
        
        print(f"📸 截图已保存: {filepath}")
        return filepath
        
    def take_screenshot_sync(self) -> Optional[str]:
        """同步截图（用于实时预览）"""
        try:
            return self._send_command({'type': 'screenshot_sync'}, timeout=5)
        except:
            return None
            
    def start_screenshot_loop(self):
        """开始定时截图循环"""
        def loop():
            while self._is_running and not self._stop_event.is_set():
                self.take_screenshot_sync()
                time.sleep(self.screenshot_interval)
                
        thread = threading.Thread(target=loop, daemon=True)
        thread.start()
        print(f"📸 实时截图已启动（每{self.screenshot_interval}秒）")
        
    def start_recording(self):
        """开始录制"""
        print("🔴 开始录制...")
        self._send_command({'type': 'start_recording'})
        self.is_recording = True
        self.start_time = datetime.now()
        self.navigation_history = []
        
    def stop_recording(self) -> Dict:
        """停止录制"""
        data = self._send_command({'type': 'stop_recording'})
        self.is_recording = False
        
        # 保存录制数据
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(self.output_dir, f"recording_{timestamp}.json")
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"✅ 录制完成: {data['actions_count']} 个操作")
        print(f"📝 录制文件: {filepath}")
        
        # 打印操作摘要
        if data['actions']:
            print("\n📋 操作摘要:")
            for i, action in enumerate(data['actions'][:10], 1):
                desc = action.get('description', action.get('type', '未知'))
                print(f"   {i}. {desc}")
            if len(data['actions']) > 10:
                print(f"   ... 还有 {len(data['actions']) - 10} 个操作")
        
        return data
        
    def is_browser_alive(self) -> bool:
        """检查浏览器是否还活着"""
        # 首先检查线程是否还在运行
        if not self._is_running or not self._browser_thread or not self._browser_thread.is_alive():
            return False
            
        try:
            # 检查浏览器进程是否还在
            is_alive = self._send_command({'type': 'is_alive'}, timeout=2)
            if not is_alive:
                print(f"🔴 浏览器页面已关闭")
                return False
                
            return True
        except Exception as e:
            print(f"🔴 浏览器状态检测异常: {e}")
            return False
        
    def close(self):
        """关闭浏览器"""
        print("🔒 关闭浏览器...")
        try:
            self._send_command({'type': 'close'}, timeout=10)
        except:
            pass
        self._is_running = False
        if self._browser_thread and self._browser_thread.is_alive():
            self._browser_thread.join(timeout=5)
        print("✅ 浏览器已关闭")
