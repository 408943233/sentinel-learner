#!/usr/bin/env python3
"""
主窗口 - 知识浏览器界面 (Tkinter版本)
"""
import sys
import os
import threading
from datetime import datetime, timedelta
from tkinter import (
    Tk, Frame, Entry, Button, Label, Text, Scrollbar,
    Listbox, Menu, messagebox, StringVar, END, N, S, E, W,
    X, Y, BOTH, LEFT, RIGHT, TOP, BOTTOM, CENTER
)
from tkinter import ttk


class MainWindowTk:
    """知识浏览器主窗口 (Tkinter版本)"""
    
    def __init__(self, browser_engine):
        self.browser_engine = browser_engine
        self.is_recording = False
        self.recording_start_time = None
        
        # 创建主窗口
        self.root = Tk()
        self.root.title("知识浏览器 v1.0")
        self.root.geometry("1400x900")
        self.root.minsize(1000, 600)
        
        # 初始化UI
        self._init_ui()
        
        # 定时更新
        self._schedule_update()
        
    def _init_ui(self):
        """初始化界面"""
        # 主框架
        self.main_frame = Frame(self.root)
        self.main_frame.pack(fill=BOTH, expand=True, padx=5, pady=5)
        
        # ===== 顶部工具栏 =====
        toolbar = Frame(self.main_frame, bg='#f0f0f0', height=50)
        toolbar.pack(fill=X, pady=(0, 5))
        toolbar.pack_propagate(False)
        
        # 启动浏览器按钮
        self.launch_btn = Button(
            toolbar, 
            text="🚀 启动浏览器",
            command=self._on_launch,
            bg='#4285f4',
            fg='white',
            font=('Arial', 10, 'bold'),
            padx=15,
            pady=5
        )
        self.launch_btn.pack(side=LEFT, padx=5, pady=5)
        
        # 分隔线
        ttk.Separator(toolbar, orient='vertical').pack(side=LEFT, fill=Y, padx=10, pady=5)
        
        # 录制按钮
        self.record_btn = Button(
            toolbar,
            text="🔴 开始录制",
            command=self._on_toggle_recording,
            bg='#f44336',
            fg='white',
            font=('Arial', 10, 'bold'),
            padx=15,
            pady=5,
            state='disabled'
        )
        self.record_btn.pack(side=LEFT, padx=5, pady=5)
        
        # 截图按钮
        self.screenshot_btn = Button(
            toolbar,
            text="📸 截图",
            command=self._on_screenshot,
            bg='#4caf50',
            fg='white',
            font=('Arial', 10),
            padx=10,
            pady=5,
            state='disabled'
        )
        self.screenshot_btn.pack(side=LEFT, padx=5, pady=5)
        
        # 获取代码按钮
        self.code_btn = Button(
            toolbar,
            text="📄 获取代码",
            command=self._on_get_code,
            bg='#ff9800',
            fg='white',
            font=('Arial', 10),
            padx=10,
            pady=5,
            state='disabled'
        )
        self.code_btn.pack(side=LEFT, padx=5, pady=5)
        
        # ===== 地址栏区域 =====
        nav_frame = Frame(self.main_frame, bg='white', height=50)
        nav_frame.pack(fill=X, pady=5)
        nav_frame.pack_propagate(False)
        
        # URL输入框
        self.url_var = StringVar()
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
            padx=20,
            state='disabled'
        )
        self.go_btn.pack(side=RIGHT, padx=5, pady=10)
        
        # ===== 主要内容区域 =====
        content_frame = Frame(self.main_frame)
        content_frame.pack(fill=BOTH, expand=True)
        
        # 左侧 - 页面结构
        left_frame = Frame(content_frame, width=250, bg='#fafafa')
        left_frame.pack(side=LEFT, fill=Y, padx=(0, 5))
        left_frame.pack_propagate(False)
        
        Label(
            left_frame,
            text="📁 页面结构",
            font=('Arial', 11, 'bold'),
            bg='#fafafa',
            anchor='w'
        ).pack(fill=X, padx=5, pady=5)
        
        self.structure_text = Text(
            left_frame,
            wrap='word',
            font=('Consolas', 10),
            bg='#fafafa',
            relief='flat',
            state='disabled'
        )
        self.structure_text.pack(fill=BOTH, expand=True, padx=5, pady=5)
        
        # 中间 - 浏览器视图占位
        center_frame = Frame(content_frame, bg='#f0f0f0')
        center_frame.pack(side=LEFT, fill=BOTH, expand=True)
        
        self.browser_label = Label(
            center_frame,
            text="浏览器视图区域\n\n点击'启动浏览器'按钮开始",
            font=('Arial', 14),
            bg='#f0f0f0',
            fg='#666666'
        )
        self.browser_label.place(relx=0.5, rely=0.5, anchor=CENTER)
        
        # 右侧 - 操作日志
        right_frame = Frame(content_frame, width=300, bg='#fafafa')
        right_frame.pack(side=RIGHT, fill=Y, padx=(5, 0))
        right_frame.pack_propagate(False)
        
        Label(
            right_frame,
            text="📋 操作日志",
            font=('Arial', 11, 'bold'),
            bg='#fafafa',
            anchor='w'
        ).pack(fill=X, padx=5, pady=5)
        
        # 日志列表框
        log_frame = Frame(right_frame, bg='#fafafa')
        log_frame.pack(fill=BOTH, expand=True, padx=5, pady=5)
        
        scrollbar = Scrollbar(log_frame)
        scrollbar.pack(side=RIGHT, fill=Y)
        
        self.log_listbox = Listbox(
            log_frame,
            font=('Consolas', 10),
            bg='#fafafa',
            relief='flat',
            yscrollcommand=scrollbar.set
        )
        self.log_listbox.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.config(command=self.log_listbox.yview)
        
        # ===== 底部状态栏 =====
        status_frame = Frame(self.main_frame, bg='#e0e0e0', height=30)
        status_frame.pack(fill=X, side=BOTTOM, pady=(5, 0))
        status_frame.pack_propagate(False)
        
        self.status_label = Label(
            status_frame,
            text="就绪",
            font=('Arial', 10),
            bg='#e0e0e0',
            anchor='w'
        )
        self.status_label.pack(side=LEFT, padx=10, pady=5)
        
        self.recording_label = Label(
            status_frame,
            text="",
            font=('Arial', 10, 'bold'),
            bg='#e0e0e0',
            fg='#d32f2f'
        )
        self.recording_label.pack(side=RIGHT, padx=10, pady=5)
        
        self.stats_label = Label(
            status_frame,
            text="日志: 0",
            font=('Arial', 10),
            bg='#e0e0e0'
        )
        self.stats_label.pack(side=RIGHT, padx=10, pady=5)
        
    def _on_launch(self):
        """启动浏览器"""
        try:
            self.status_label.config(text="正在启动浏览器...")
            self.root.update()
            
            # 在新线程中启动浏览器
            thread = threading.Thread(target=self._launch_browser)
            thread.daemon = True
            thread.start()
            
        except Exception as e:
            messagebox.showerror("错误", f"启动浏览器失败: {e}")
            self.status_label.config(text="启动失败")
            
    def _launch_browser(self):
        """在后台线程启动浏览器"""
        try:
            self.browser_engine.launch(headless=False)
            
            # 设置回调
            self.browser_engine.on_navigate = lambda url: self.root.after(0, lambda: self._on_page_navigated(url))
            
            # 更新UI
            self.root.after(0, self._on_browser_launched)
            
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("错误", f"启动浏览器失败: {e}"))
            
    def _on_browser_launched(self):
        """浏览器启动完成回调"""
        self.browser_label.config(text="浏览器已在外部窗口打开\n\n请在浏览器窗口中操作")
        self.launch_btn.config(text="✅ 浏览器运行中", state='disabled')
        
        # 启用其他按钮
        self.record_btn.config(state='normal')
        self.screenshot_btn.config(state='normal')
        self.code_btn.config(state='normal')
        self.go_btn.config(state='normal')
        
        self.status_label.config(text="浏览器运行中")
        self._add_log("✅ 浏览器启动成功")
        
    def _on_navigate(self):
        """导航到指定URL"""
        url = self.url_var.get().strip()
        if not url:
            return
            
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
            self.url_var.set(url)
            
        try:
            self.status_label.config(text=f"正在加载: {url}...")
            self.root.update()
            
            # 在新线程中导航
            thread = threading.Thread(target=lambda: self.browser_engine.navigate(url))
            thread.daemon = True
            thread.start()
            
            self._add_log(f"🌐 导航到: {url}")
        except Exception as e:
            messagebox.showerror("错误", f"导航失败: {e}")
            
    def _on_page_navigated(self, url: str):
        """页面导航回调"""
        self.url_var.set(url)
        self.status_label.config(text=f"当前页面: {url}")
        self._add_log(f"📄 页面加载完成: {url}")
        
    def _on_toggle_recording(self):
        """切换录制状态"""
        if not self.is_recording:
            # 开始录制
            try:
                self.browser_engine.start_recording()
                self.is_recording = True
                self.recording_start_time = datetime.now()
                
                self.record_btn.config(text="⏹️ 停止录制", bg='#d32f2f')
                self.status_label.config(text="🔴 录制中...")
                
                self._add_log("🔴 开始录制用户操作")
                
            except Exception as e:
                messagebox.showerror("错误", f"开始录制失败: {e}")
        else:
            # 停止录制
            try:
                recording_data = self.browser_engine.stop_recording()
                self.is_recording = False
                self.recording_start_time = None
                
                self.record_btn.config(text="🔴 开始录制", bg='#f44336')
                self.status_label.config(text="录制完成")
                self.recording_label.config(text="")
                
                actions_count = recording_data.get('actions_count', 0)
                duration = recording_data.get('duration', 0)
                self._add_log(f"✅ 录制完成: {actions_count}个操作, {duration:.1f}秒")
                
                messagebox.showinfo(
                    "录制完成",
                    f"录制数据已保存\n\n操作数: {actions_count}\n时长: {duration:.1f}秒"
                )
                
            except Exception as e:
                messagebox.showerror("错误", f"停止录制失败: {e}")
                
    def _on_screenshot(self):
        """截图"""
        try:
            filepath = self.browser_engine.take_screenshot()
            self._add_log(f"📸 截图已保存: {os.path.basename(filepath)}")
            self.status_label.config(text=f"截图已保存")
        except Exception as e:
            messagebox.showerror("错误", f"截图失败: {e}")
            
    def _on_get_code(self):
        """获取页面代码"""
        try:
            html = self.browser_engine.get_page_source()
            
            # 保存到文件
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = os.path.join(self.browser_engine.output_dir, f"page_source_{timestamp}.html")
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html)
            
            self._add_log(f"📄 页面代码已保存: {os.path.basename(filepath)}")
            self.status_label.config(text=f"代码已保存")
            
            # 显示代码预览
            preview = html[:2000] + "..." if len(html) > 2000 else html
            self.structure_text.config(state='normal')
            self.structure_text.delete('1.0', END)
            self.structure_text.insert('1.0', f"<!-- HTML源码 -->\n{preview}")
            self.structure_text.config(state='disabled')
            
        except Exception as e:
            messagebox.showerror("错误", f"获取代码失败: {e}")
            
    def _add_log(self, message: str):
        """添加日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_text = f"[{timestamp}] {message}"
        
        self.log_listbox.insert(END, log_text)
        self.log_listbox.see(END)
        
        # 更新统计
        self.stats_label.config(text=f"日志: {self.log_listbox.size()}")
        
    def _schedule_update(self):
        """定时更新"""
        self._update_recording_time()
        self.root.after(1000, self._schedule_update)
        
    def _update_recording_time(self):
        """更新录制时间显示"""
        if self.is_recording and self.recording_start_time:
            elapsed = datetime.now() - self.recording_start_time
            elapsed_str = str(elapsed).split('.')[0]
            self.recording_label.config(text=f"🔴 录制中 {elapsed_str}")
            
    def run(self):
        """运行应用"""
        self.root.mainloop()
        
    def on_close(self):
        """关闭处理"""
        if self.is_recording:
            self.browser_engine.stop_recording()
        self.browser_engine.close()
        self.root.destroy()


def main():
    """主函数"""
    from core.browser_engine import BrowserEngine
    
    # 创建浏览器引擎
    engine = BrowserEngine(output_dir="output")
    
    # 创建主窗口
    app = MainWindowTk(engine)
    
    # 设置关闭处理
    app.root.protocol("WM_DELETE_WINDOW", app.on_close)
    
    # 运行
    app.run()


if __name__ == '__main__':
    main()
