#!/usr/bin/env python3
"""
主窗口 - 知识浏览器界面 (简化版本，无Emoji)
"""
import sys
import os
import threading
from datetime import datetime, timedelta
from tkinter import (
    Tk, Frame, Entry, Button, Label, Text, Scrollbar,
    Listbox, messagebox, StringVar, END, N, S, E, W,
    X, Y, BOTH, LEFT, RIGHT, TOP, BOTTOM, CENTER
)
from tkinter import ttk


class MainWindowSimple:
    """知识浏览器主窗口 (简化版本)"""
    
    def __init__(self, browser_engine):
        self.browser_engine = browser_engine
        self.is_recording = False
        self.recording_start_time = None
        
        # 创建主窗口
        self.root = Tk()
        self.root.title("知识浏览器 v1.0")
        self.root.geometry("1200x800")
        self.root.minsize(800, 600)
        
        # 初始化UI
        self._init_ui()
        
    def _init_ui(self):
        """初始化界面"""
        # 主框架
        self.main_frame = Frame(self.root)
        self.main_frame.pack(fill=BOTH, expand=True, padx=10, pady=10)
        
        # ===== 顶部工具栏 =====
        toolbar = Frame(self.main_frame, bg='#e0e0e0', height=60)
        toolbar.pack(fill=X, pady=(0, 10))
        toolbar.pack_propagate(False)
        
        # 启动浏览器按钮
        self.launch_btn = Button(
            toolbar, 
            text="启动浏览器",
            command=self._on_launch,
            bg='#4285f4',
            fg='white',
            font=('Arial', 11, 'bold'),
            padx=20,
            pady=8
        )
        self.launch_btn.pack(side=LEFT, padx=10, pady=10)
        
        # 录制按钮
        self.record_btn = Button(
            toolbar,
            text="开始录制",
            command=self._on_toggle_recording,
            bg='#f44336',
            fg='white',
            font=('Arial', 11, 'bold'),
            padx=20,
            pady=8,
            state='disabled'
        )
        self.record_btn.pack(side=LEFT, padx=10, pady=10)
        
        # 截图按钮
        self.screenshot_btn = Button(
            toolbar,
            text="截图",
            command=self._on_screenshot,
            bg='#4caf50',
            fg='white',
            font=('Arial', 11),
            padx=15,
            pady=8,
            state='disabled'
        )
        self.screenshot_btn.pack(side=LEFT, padx=10, pady=10)
        
        # 获取代码按钮
        self.code_btn = Button(
            toolbar,
            text="获取代码",
            command=self._on_get_code,
            bg='#ff9800',
            fg='white',
            font=('Arial', 11),
            padx=15,
            pady=8,
            state='disabled'
        )
        self.code_btn.pack(side=LEFT, padx=10, pady=10)
        
        # ===== 地址栏区域 =====
        nav_frame = Frame(self.main_frame, bg='white', height=50)
        nav_frame.pack(fill=X, pady=5)
        nav_frame.pack_propagate(False)
        
        # URL输入框
        self.url_var = StringVar(value="https://www.baidu.com")
        self.url_entry = Entry(
            nav_frame,
            textvariable=self.url_var,
            font=('Arial', 12),
            relief='solid',
            bd=2
        )
        self.url_entry.pack(side=LEFT, fill=X, expand=True, padx=5, pady=10)
        self.url_entry.bind('<Return>', lambda e: self._on_navigate())
        
        # 跳转按钮
        self.go_btn = Button(
            nav_frame,
            text="跳转",
            command=self._on_navigate,
            bg='#4285f4',
            fg='white',
            font=('Arial', 10, 'bold'),
            padx=25,
            state='disabled'
        )
        self.go_btn.pack(side=RIGHT, padx=5, pady=10)
        
        # ===== 主要内容区域 =====
        content_frame = Frame(self.main_frame)
        content_frame.pack(fill=BOTH, expand=True)
        
        # 左侧 - 页面结构
        left_frame = Frame(content_frame, width=300, bg='#f5f5f5')
        left_frame.pack(side=LEFT, fill=Y, padx=(0, 5))
        left_frame.pack_propagate(False)
        
        Label(
            left_frame,
            text="页面结构",
            font=('Arial', 12, 'bold'),
            bg='#f5f5f5',
            anchor='w'
        ).pack(fill=X, padx=10, pady=10)
        
        self.structure_text = Text(
            left_frame,
            wrap='word',
            font=('Consolas', 10),
            bg='#f5f5f5',
            relief='flat',
            state='disabled',
            height=20
        )
        self.structure_text.pack(fill=BOTH, expand=True, padx=10, pady=5)
        
        # 中间 - 浏览器视图占位
        center_frame = Frame(content_frame, bg='#e0e0e0')
        center_frame.pack(side=LEFT, fill=BOTH, expand=True)
        
        self.browser_label = Label(
            center_frame,
            text="浏览器视图区域\n\n点击'启动浏览器'按钮开始",
            font=('Arial', 14),
            bg='#e0e0e0',
            fg='#666666'
        )
        self.browser_label.place(relx=0.5, rely=0.5, anchor=CENTER)
        
        # 右侧 - 操作日志
        right_frame = Frame(content_frame, width=350, bg='#f5f5f5')
        right_frame.pack(side=RIGHT, fill=Y, padx=(5, 0))
        right_frame.pack_propagate(False)
        
        Label(
            right_frame,
            text="操作日志",
            font=('Arial', 12, 'bold'),
            bg='#f5f5f5',
            anchor='w'
        ).pack(fill=X, padx=10, pady=10)
        
        # 日志列表框
        log_frame = Frame(right_frame, bg='#f5f5f5')
        log_frame.pack(fill=BOTH, expand=True, padx=10, pady=5)
        
        scrollbar = Scrollbar(log_frame)
        scrollbar.pack(side=RIGHT, fill=Y)
        
        self.log_listbox = Listbox(
            log_frame,
            font=('Consolas', 10),
            bg='#f5f5f5',
            relief='flat',
            yscrollcommand=scrollbar.set,
            height=20
        )
        self.log_listbox.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.config(command=self.log_listbox.yview)
        
        # 状态栏
        self.status_label = Label(
            self.main_frame,
            text="就绪",
            font=('Arial', 10),
            bg='#e0e0e0',
            anchor='w',
            padx=10,
            pady=5
        )
        self.status_label.pack(fill=X, side=BOTTOM, pady=(10, 0))
        
    def _on_launch(self):
        """启动浏览器"""
        def launch():
            try:
                self._log("正在启动浏览器...")
                self.browser_engine.launch(headless=False)
                self._log("浏览器启动成功")
                
                # 更新UI
                self.root.after(0, self._enable_controls)
                self.root.after(0, lambda: self.browser_label.config(
                    text="浏览器已在外部窗口打开\n请在浏览器中操作",
                    fg='#4caf50'
                ))
            except Exception as e:
                self._log(f"启动失败: {e}")
                messagebox.showerror("错误", f"启动浏览器失败:\n{e}")
        
        threading.Thread(target=launch, daemon=True).start()
        
    def _enable_controls(self):
        """启用控制按钮"""
        self.record_btn.config(state='normal')
        self.screenshot_btn.config(state='normal')
        self.code_btn.config(state='normal')
        self.go_btn.config(state='normal')
        self.launch_btn.config(state='disabled', text="浏览器已启动")
        self.status_label.config(text="浏览器运行中")
        
    def _on_toggle_recording(self):
        """切换录制状态"""
        if not self.is_recording:
            # 开始录制
            try:
                self.browser_engine.start_recording()
                self.is_recording = True
                self.recording_start_time = datetime.now()
                self.record_btn.config(text="停止录制", bg='#666666')
                self._log("开始录制用户操作")
                self.status_label.config(text="正在录制...")
            except Exception as e:
                messagebox.showerror("错误", f"开始录制失败:\n{e}")
        else:
            # 停止录制
            try:
                data = self.browser_engine.stop_recording()
                self.is_recording = False
                self.record_btn.config(text="开始录制", bg='#f44336')
                self._log(f"录制完成: {data['actions_count']} 个操作")
                self._log(f"录制时长: {data['duration']:.1f} 秒")
                self.status_label.config(text="录制完成")
                
                # 显示操作统计
                self._show_recording_stats(data)
            except Exception as e:
                messagebox.showerror("错误", f"停止录制失败:\n{e}")
                
    def _show_recording_stats(self, data):
        """显示录制统计"""
        stats_text = f"\n录制统计:\n"
        stats_text += f"  操作数: {data['actions_count']}\n"
        stats_text += f"  时长: {data['duration']:.1f}秒\n"
        stats_text += f"  起始URL: {data['start_url']}\n"
        stats_text += f"  结束URL: {data['end_url']}\n"
        
        # 操作类型统计
        action_types = {}
        for action in data['actions']:
            t = action.get('type', 'unknown')
            action_types[t] = action_types.get(t, 0) + 1
        
        if action_types:
            stats_text += "  操作类型:\n"
            for t, count in action_types.items():
                stats_text += f"    - {t}: {count}\n"
        
        self._log(stats_text)
        
    def _on_screenshot(self):
        """截取屏幕"""
        try:
            filepath = self.browser_engine.take_screenshot()
            self._log(f"截图已保存: {filepath}")
            messagebox.showinfo("成功", f"截图已保存:\n{filepath}")
        except Exception as e:
            messagebox.showerror("错误", f"截图失败:\n{e}")
            
    def _on_get_code(self):
        """获取页面代码"""
        try:
            self._log("正在获取页面代码...")
            
            html = self.browser_engine.get_page_source()
            styles = self.browser_engine.get_page_styles()
            
            # 保存代码
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            html_path = os.path.join(
                self.browser_engine.output_dir, 
                f"page_{timestamp}.html"
            )
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html)
            
            import json
            styles_path = os.path.join(
                self.browser_engine.output_dir,
                f"styles_{timestamp}.json"
            )
            with open(styles_path, 'w', encoding='utf-8') as f:
                json.dump(styles, f, ensure_ascii=False, indent=2)
            
            self._log(f"HTML已保存: {html_path}")
            self._log(f"样式已保存: {styles_path}")
            self._log(f"HTML大小: {len(html)} 字符")
            self._log(f"样式元素: {len(styles)} 个")
            
            # 更新页面结构显示
            self._update_structure(styles)
            
            messagebox.showinfo("成功", f"代码已保存到:\n{html_path}")
        except Exception as e:
            messagebox.showerror("错误", f"获取代码失败:\n{e}")
            
    def _update_structure(self, styles):
        """更新页面结构显示"""
        self.structure_text.config(state='normal')
        self.structure_text.delete('1.0', END)
        
        structure_text = "页面元素结构:\n"
        structure_text += "=" * 40 + "\n\n"
        
        # 按类型分组
        by_type = {}
        for elem in styles:
            t = elem.get('tag', 'unknown')
            if t not in by_type:
                by_type[t] = []
            by_type[t].append(elem)
        
        # 显示统计
        structure_text += f"总元素数: {len(styles)}\n\n"
        
        for tag, elems in sorted(by_type.items(), key=lambda x: -len(x[1])):
            structure_text += f"[{tag}] x {len(elems)}\n"
            for i, elem in enumerate(elems[:5]):  # 只显示前5个
                text = elem.get('text', '')[:30]
                if text:
                    structure_text += f"  - {text}\n"
            if len(elems) > 5:
                structure_text += f"  ... 还有 {len(elems)-5} 个\n"
            structure_text += "\n"
        
        self.structure_text.insert('1.0', structure_text)
        self.structure_text.config(state='disabled')
        
    def _on_navigate(self):
        """导航到URL"""
        url = self.url_var.get().strip()
        if not url:
            return
            
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
            
        def navigate():
            try:
                self._log(f"正在导航到: {url}")
                self.browser_engine.navigate(url)
                self._log(f"页面加载完成: {url}")
            except Exception as e:
                self._log(f"导航失败: {e}")
                messagebox.showerror("错误", f"导航失败:\n{e}")
        
        threading.Thread(target=navigate, daemon=True).start()
        
    def _log(self, message):
        """添加日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_listbox.insert(END, f"[{timestamp}] {message}")
        self.log_listbox.see(END)
        
    def on_close(self):
        """关闭处理"""
        if self.is_recording:
            self.browser_engine.stop_recording()
        self.browser_engine.close()
        self.root.destroy()
        
    def run(self):
        """运行应用"""
        self.root.mainloop()
