#!/usr/bin/env python3
"""
主窗口 - 知识浏览器界面
"""
import sys
import os
from datetime import datetime, timedelta
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel, QStatusBar,
    QToolBar, QDockWidget, QTextEdit, QListWidget,
    QListWidgetItem, QMessageBox, QApplication
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt6.QtGui import QIcon, QAction, QKeySequence


class BrowserThread(QThread):
    """浏览器后台线程"""
    page_loaded = pyqtSignal(str)
    action_recorded = pyqtSignal(dict)
    
    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self.running = True
        
    def run(self):
        """运行浏览器循环"""
        # Playwright在主线程运行，这里只做状态检查
        timer = QTimer()
        timer.timeout.connect(self.check_status)
        timer.start(1000)
        
    def check_status(self):
        """检查浏览器状态"""
        if not self.running:
            self.quit()


class MainWindow(QMainWindow):
    """知识浏览器主窗口"""
    
    def __init__(self, browser_engine):
        super().__init__()
        self.browser_engine = browser_engine
        self.is_recording = False
        self.recording_start_time = None
        
        # 设置窗口
        self.setWindowTitle("🌐 知识浏览器 v1.0")
        self.setGeometry(100, 100, 1400, 900)
        
        # 初始化UI
        self._init_ui()
        self._init_toolbar()
        self._init_sidebar()
        self._init_statusbar()
        
        # 定时器（用于更新录制时间）
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_recording_time)
        
    def _init_ui(self):
        """初始化主界面"""
        # 中央部件 - 浏览器视图占位
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        layout = QVBoxLayout(self.central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 地址栏区域
        nav_layout = QHBoxLayout()
        nav_layout.setContentsMargins(10, 10, 10, 10)
        nav_layout.setSpacing(10)
        
        # 地址输入框
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("输入网址...")
        self.url_input.setStyleSheet("""
            QLineEdit {
                padding: 8px 12px;
                border: 2px solid #e0e0e0;
                border-radius: 20px;
                font-size: 14px;
                background: #f8f9fa;
            }
            QLineEdit:focus {
                border-color: #4285f4;
                background: white;
            }
        """)
        self.url_input.returnPressed.connect(self._on_navigate)
        nav_layout.addWidget(self.url_input, stretch=1)
        
        # 跳转按钮
        self.go_btn = QPushButton("跳转")
        self.go_btn.setStyleSheet("""
            QPushButton {
                padding: 8px 20px;
                background: #4285f4;
                color: white;
                border: none;
                border-radius: 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #3367d6;
            }
        """)
        self.go_btn.clicked.connect(self._on_navigate)
        nav_layout.addWidget(self.go_btn)
        
        layout.addLayout(nav_layout)
        
        # 浏览器视图占位（实际浏览器窗口会浮在上面）
        self.browser_placeholder = QLabel("浏览器视图区域\n\n点击'启动浏览器'开始")
        self.browser_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.browser_placeholder.setStyleSheet("""
            QLabel {
                background: #f0f0f0;
                border: 2px dashed #ccc;
                color: #666;
                font-size: 16px;
            }
        """)
        layout.addWidget(self.browser_placeholder, stretch=1)
        
    def _init_toolbar(self):
        """初始化工具栏"""
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setStyleSheet("""
            QToolBar {
                background: #ffffff;
                border-bottom: 1px solid #e0e0e0;
                padding: 5px;
            }
        """)
        self.addToolBar(toolbar)
        
        # 启动浏览器按钮
        self.launch_btn = QAction("🚀 启动浏览器", self)
        self.launch_btn.triggered.connect(self._on_launch)
        toolbar.addAction(self.launch_btn)
        
        toolbar.addSeparator()
        
        # 录制按钮
        self.record_btn = QAction("🔴 开始录制", self)
        self.record_btn.triggered.connect(self._on_toggle_recording)
        toolbar.addAction(self.record_btn)
        
        # 截图按钮
        self.screenshot_btn = QAction("📸 截图", self)
        self.screenshot_btn.triggered.connect(self._on_screenshot)
        toolbar.addAction(self.screenshot_btn)
        
        toolbar.addSeparator()
        
        # 获取代码按钮
        self.code_btn = QAction("📄 获取代码", self)
        self.code_btn.triggered.connect(self._on_get_code)
        toolbar.addAction(self.code_btn)
        
    def _init_sidebar(self):
        """初始化侧边栏"""
        # 右侧边栏 - 操作日志
        self.log_dock = QDockWidget("📋 操作日志", self)
        self.log_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
        
        self.log_widget = QListWidget()
        self.log_widget.setStyleSheet("""
            QListWidget {
                border: none;
                background: #fafafa;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #eee;
            }
            QListWidget::item:hover {
                background: #e3f2fd;
            }
        """)
        self.log_dock.setWidget(self.log_widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.log_dock)
        
        # 左侧边栏 - 页面结构
        self.structure_dock = QDockWidget("📁 页面结构", self)
        self.structure_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea)
        
        self.structure_widget = QTextEdit()
        self.structure_widget.setReadOnly(True)
        self.structure_widget.setPlaceholderText("页面加载后显示DOM结构...")
        self.structure_widget.setStyleSheet("""
            QTextEdit {
                border: none;
                background: #fafafa;
                font-family: monospace;
                font-size: 12px;
            }
        """)
        self.structure_dock.setWidget(self.structure_widget)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.structure_dock)
        
    def _init_statusbar(self):
        """初始化状态栏"""
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        
        # 状态标签
        self.status_label = QLabel("就绪")
        self.statusbar.addWidget(self.status_label)
        
        self.statusbar.addStretch()
        
        # 录制时间标签
        self.recording_label = QLabel("")
        self.recording_label.setStyleSheet("color: #d32f2f; font-weight: bold;")
        self.statusbar.addWidget(self.recording_label)
        
        self.statusbar.addSeparator()
        
        # 统计信息
        self.stats_label = QLabel("页面: 0 | 操作: 0")
        self.statusbar.addWidget(self.stats_label)
        
    def _on_launch(self):
        """启动浏览器"""
        try:
            self.status_label.setText("正在启动浏览器...")
            
            # 启动浏览器引擎
            self.browser_engine.launch(headless=False)
            
            # 设置回调
            self.browser_engine.on_navigate = self._on_page_navigated
            
            # 更新UI
            self.browser_placeholder.setText("浏览器已在外部窗口打开\n\n请在浏览器窗口中操作")
            self.launch_btn.setText("✅ 浏览器运行中")
            self.launch_btn.setEnabled(False)
            
            self.status_label.setText("浏览器运行中")
            self._add_log("✅ 浏览器启动成功", "success")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"启动浏览器失败: {e}")
            self.status_label.setText("启动失败")
            
    def _on_navigate(self):
        """导航到指定URL"""
        url = self.url_input.text().strip()
        if not url:
            return
            
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
            
        try:
            self.status_label.setText(f"正在加载: {url}...")
            self.browser_engine.navigate(url)
            self._add_log(f"🌐 导航到: {url}", "navigate")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导航失败: {e}")
            
    def _on_page_navigated(self, url: str):
        """页面导航回调"""
        self.url_input.setText(url)
        self.status_label.setText(f"当前页面: {url}")
        self._add_log(f"📄 页面加载完成: {url}", "page")
        
        # 更新页面结构
        self._update_page_structure()
        
    def _on_toggle_recording(self):
        """切换录制状态"""
        if not self.is_recording:
            # 开始录制
            try:
                self.browser_engine.start_recording()
                self.is_recording = True
                self.recording_start_time = datetime.now()
                
                self.record_btn.setText("⏹️ 停止录制")
                self.status_label.setText("🔴 录制中...")
                self.timer.start(1000)  # 每秒更新一次
                
                self._add_log("🔴 开始录制用户操作", "record")
                
            except Exception as e:
                QMessageBox.critical(self, "错误", f"开始录制失败: {e}")
        else:
            # 停止录制
            try:
                recording_data = self.browser_engine.stop_recording()
                self.is_recording = False
                self.recording_start_time = None
                
                self.record_btn.setText("🔴 开始录制")
                self.status_label.setText("录制完成")
                self.timer.stop()
                self.recording_label.setText("")
                
                # 显示录制统计
                actions_count = recording_data.get('actions_count', 0)
                duration = recording_data.get('duration', 0)
                self._add_log(f"✅ 录制完成: {actions_count}个操作, {duration:.1f}秒", "success")
                
                QMessageBox.information(
                    self, 
                    "录制完成", 
                    f"录制数据已保存\n\n操作数: {actions_count}\n时长: {duration:.1f}秒"
                )
                
            except Exception as e:
                QMessageBox.critical(self, "错误", f"停止录制失败: {e}")
                
    def _on_screenshot(self):
        """截图"""
        try:
            filepath = self.browser_engine.take_screenshot()
            self._add_log(f"📸 截图已保存: {os.path.basename(filepath)}", "screenshot")
            self.status_label.setText(f"截图已保存: {filepath}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"截图失败: {e}")
            
    def _on_get_code(self):
        """获取页面代码"""
        try:
            # 获取HTML
            html = self.browser_engine.get_page_source()
            
            # 保存到文件
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = os.path.join(self.browser_engine.output_dir, f"page_source_{timestamp}.html")
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html)
            
            self._add_log(f"📄 页面代码已保存: {os.path.basename(filepath)}", "code")
            self.status_label.setText(f"代码已保存: {filepath}")
            
            # 显示代码预览
            preview = html[:1000] + "..." if len(html) > 1000 else html
            self.structure_widget.setText(f"<!-- HTML源码 -->\n{preview}")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"获取代码失败: {e}")
            
    def _update_page_structure(self):
        """更新页面结构显示"""
        try:
            styles = self.browser_engine.get_page_styles()
            
            # 构建结构文本
            structure_text = "/* 页面样式概览 */\n\n"
            for selector, style in list(styles.items())[:20]:  # 只显示前20个
                structure_text += f"{selector} {{\n"
                for prop, value in style.items():
                    structure_text += f"  {prop}: {value};\n"
                structure_text += "}\n\n"
            
            self.structure_widget.setText(structure_text)
            
        except Exception as e:
            self.structure_widget.setText(f"获取页面结构失败: {e}")
            
    def _update_recording_time(self):
        """更新录制时间显示"""
        if self.recording_start_time:
            elapsed = datetime.now() - self.recording_start_time
            elapsed_str = str(elapsed).split('.')[0]  # 去掉微秒
            self.recording_label.setText(f"🔴 录制中 {elapsed_str}")
            
    def _add_log(self, message: str, log_type: str = "info"):
        """添加日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        item_text = f"[{timestamp}] {message}"
        
        item = QListWidgetItem(item_text)
        
        # 根据类型设置颜色
        if log_type == "success":
            item.setForeground(Qt.GlobalColor.darkGreen)
        elif log_type == "error":
            item.setForeground(Qt.GlobalColor.red)
        elif log_type == "record":
            item.setForeground(Qt.GlobalColor.darkRed)
        elif log_type == "navigate":
            item.setForeground(Qt.GlobalColor.blue)
            
        self.log_widget.addItem(item)
        self.log_widget.scrollToBottom()
        
        # 更新统计
        self._update_stats()
        
    def _update_stats(self):
        """更新统计信息"""
        # 这里可以添加更复杂的统计逻辑
        log_count = self.log_widget.count()
        self.stats_label.setText(f"日志: {log_count}")
        
    def closeEvent(self, event):
        """关闭事件"""
        # 停止录制
        if self.is_recording:
            self.browser_engine.stop_recording()
            
        # 关闭浏览器
        self.browser_engine.close()
        
        event.accept()


def main():
    """主函数"""
    from core.browser_engine import BrowserEngine
    
    app = QApplication(sys.argv)
    
    # 创建浏览器引擎
    engine = BrowserEngine(output_dir="output")
    
    # 创建主窗口
    window = MainWindow(engine)
    window.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
