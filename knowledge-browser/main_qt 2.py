#!/usr/bin/env python3
"""
知识浏览器 - PyQt5版本
集成无监督学习和视频录制功能
"""
import sys
import os
import threading
import json
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QLabel, QTextEdit, QListWidget,
    QSplitter, QFrame, QMessageBox, QStatusBar, QFileDialog,
    QGroupBox, QGridLayout, QTabWidget
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QPixmap

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.browser_engine import BrowserEngine
from core.unsupervised_learning import UnsupervisedLearning
from core.video_recorder import VideoRecorder, ScreenshotCapture
from core.crawlee_crawler import CrawleeWebsiteCrawler
from core.screen_recorder import ScreenRecorder


class MainWindow(QMainWindow):
    """知识浏览器主窗口"""
    
    log_signal = pyqtSignal(str)
    browser_started_signal = pyqtSignal()
    screenshot_signal = pyqtSignal(str)
    
    def __init__(self, browser_engine):
        super().__init__()
        self.browser_engine = browser_engine
        self.is_recording = False
        self.is_video_recording = False
        
        # 初始化无监督学习模块
        self.learning_engine = UnsupervisedLearning(output_dir="output/knowledge")
        
        # 初始化屏幕录制模块（MSS方案，30fps流畅录制）
        self.screen_recorder = ScreenRecorder(output_dir="output/videos")
        self.screen_recorder.on_recording_started = self._on_screen_recording_started
        self.screen_recorder.on_recording_stopped = self._on_screen_recording_stopped
        
        # 初始化网站爬虫模块（使用 Crawlee）
        self.website_crawler = CrawleeWebsiteCrawler(output_dir="output")
        self.website_crawler.on_page_crawled = self._on_page_crawled
        self.website_crawler.on_crawl_complete = self._on_crawl_complete
        self.website_crawler.on_progress = self._on_crawl_progress
        self.website_crawler.on_log = self._on_crawl_log
        
        self.setWindowTitle("知识浏览器 v2.0 - 智能学习版")
        self.setGeometry(100, 100, 1600, 1000)
        
        self._init_ui()
        
        self.log_signal.connect(self._add_log)
        self.browser_started_signal.connect(self._on_browser_started)
        self.screenshot_signal.connect(self._update_screenshot)
        
        # 设置截图回调
        self.browser_engine.on_screenshot = self._on_screenshot_callback
        
        # 设置操作回调（用于视频录制触发截图）
        self.browser_engine.on_action = self._on_action_callback
        
        # 浏览器状态检测定时器
        self.browser_check_timer = QTimer()
        self.browser_check_timer.timeout.connect(self._check_browser_status)
        self.browser_check_timer.start(1000)  # 每1秒检测一次
        
        # 浏览器运行标志
        self._browser_running = False
        
        # 加载已有知识库
        self._load_knowledge()
        
    def _init_ui(self):
        """初始化界面"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # 工具栏
        toolbar = QHBoxLayout()
        
        self.launch_btn = QPushButton("🚀 启动浏览器")
        self.launch_btn.setStyleSheet("background-color: #4285f4; color: white; padding: 10px; font-size: 14px;")
        self.launch_btn.clicked.connect(self._on_launch)
        toolbar.addWidget(self.launch_btn)
        
        self.record_btn = QPushButton("🔴 开始录制操作")
        self.record_btn.setStyleSheet("background-color: #f44336; color: white; padding: 10px; font-size: 14px;")
        self.record_btn.clicked.connect(self._on_toggle_recording)
        self.record_btn.setEnabled(False)
        toolbar.addWidget(self.record_btn)
        
        self.video_btn = QPushButton("🎥 开始视频录制")
        self.video_btn.setStyleSheet("background-color: #9c27b0; color: white; padding: 10px; font-size: 14px;")
        self.video_btn.clicked.connect(self._on_toggle_video_recording)
        self.video_btn.setEnabled(False)
        toolbar.addWidget(self.video_btn)
        
        self.screenshot_btn = QPushButton("📸 截图")
        self.screenshot_btn.setStyleSheet("background-color: #4caf50; color: white; padding: 10px; font-size: 14px;")
        self.screenshot_btn.clicked.connect(self._on_screenshot)
        self.screenshot_btn.setEnabled(False)
        toolbar.addWidget(self.screenshot_btn)
        
        self.code_btn = QPushButton("📄 获取代码")
        self.code_btn.setStyleSheet("background-color: #ff9800; color: white; padding: 10px; font-size: 14px;")
        self.code_btn.clicked.connect(self._on_get_code)
        self.code_btn.setEnabled(False)
        toolbar.addWidget(self.code_btn)
        
        self.knowledge_btn = QPushButton("🧠 查看知识库")
        self.knowledge_btn.setStyleSheet("background-color: #00bcd4; color: white; padding: 10px; font-size: 14px;")
        self.knowledge_btn.clicked.connect(self._on_view_knowledge)
        toolbar.addWidget(self.knowledge_btn)
        
        self.crawl_btn = QPushButton("🕷️ 爬取网站")
        self.crawl_btn.setStyleSheet("background-color: #795548; color: white; padding: 10px; font-size: 14px;")
        self.crawl_btn.clicked.connect(self._on_crawl_website)
        self.crawl_btn.setEnabled(False)
        toolbar.addWidget(self.crawl_btn)
        
        toolbar.addStretch()
        main_layout.addLayout(toolbar)
        
        # 地址栏
        nav_layout = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setText("https://www.baidu.com")
        self.url_input.setStyleSheet("padding: 8px; font-size: 14px;")
        nav_layout.addWidget(self.url_input)
        
        self.go_btn = QPushButton("跳转")
        self.go_btn.setStyleSheet("padding: 8px 20px;")
        self.go_btn.clicked.connect(self._on_navigate)
        self.go_btn.setEnabled(False)
        nav_layout.addWidget(self.go_btn)
        
        main_layout.addLayout(nav_layout)
        
        # 内容区域
        splitter = QSplitter(Qt.Horizontal)
        
        # 左侧 - 页面结构和知识库
        left_tabs = QTabWidget()
        
        # 页面结构标签
        structure_widget = QWidget()
        structure_layout = QVBoxLayout(structure_widget)
        structure_layout.addWidget(QLabel("页面结构分析"))
        self.structure_text = QTextEdit()
        self.structure_text.setReadOnly(True)
        structure_layout.addWidget(self.structure_text)
        left_tabs.addTab(structure_widget, "页面结构")
        
        # 知识库标签
        knowledge_widget = QWidget()
        knowledge_layout = QVBoxLayout(knowledge_widget)
        
        knowledge_control = QHBoxLayout()
        self.analyze_btn = QPushButton("分析当前录制")
        self.analyze_btn.clicked.connect(self._on_analyze_recording)
        self.analyze_btn.setEnabled(False)
        knowledge_control.addWidget(self.analyze_btn)
        
        self.save_knowledge_btn = QPushButton("保存知识库")
        self.save_knowledge_btn.clicked.connect(self._on_save_knowledge)
        knowledge_control.addWidget(self.save_knowledge_btn)
        
        self.load_knowledge_btn = QPushButton("加载知识库")
        self.load_knowledge_btn.clicked.connect(self._on_load_knowledge)
        knowledge_control.addWidget(self.load_knowledge_btn)
        
        knowledge_control.addStretch()
        knowledge_layout.addLayout(knowledge_control)
        
        self.knowledge_text = QTextEdit()
        self.knowledge_text.setReadOnly(True)
        knowledge_layout.addWidget(self.knowledge_text)
        
        left_tabs.addTab(knowledge_widget, "知识库")
        
        splitter.addWidget(left_tabs)
        
        # 中间 - 浏览器视图（实时截图）
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.addWidget(QLabel("实时预览（每2秒更新）"))
        
        self.browser_label = QLabel("点击'启动浏览器'按钮开始")
        self.browser_label.setAlignment(Qt.AlignCenter)
        self.browser_label.setMinimumSize(800, 600)
        self.browser_label.setStyleSheet("background-color: #e0e0e0; border: 2px dashed #999;")
        center_layout.addWidget(self.browser_label)
        
        # 截图控制按钮
        screenshot_control = QHBoxLayout()
        self.preview_btn = QPushButton("开始实时预览")
        self.preview_btn.setCheckable(True)
        self.preview_btn.clicked.connect(self._on_toggle_preview)
        self.preview_btn.setEnabled(False)
        screenshot_control.addWidget(self.preview_btn)
        
        self.video_status_label = QLabel("视频录制: 未开始")
        screenshot_control.addWidget(self.video_status_label)
        
        screenshot_control.addStretch()
        center_layout.addLayout(screenshot_control)
        
        splitter.addWidget(center_widget)
        
        # 右侧 - 日志和录制信息
        right_tabs = QTabWidget()
        
        # 日志标签
        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)
        log_layout.addWidget(QLabel("操作日志"))
        self.log_list = QListWidget()
        log_layout.addWidget(self.log_list)
        right_tabs.addTab(log_widget, "日志")
        
        # 录制信息标签
        recording_widget = QWidget()
        recording_layout = QVBoxLayout(recording_widget)
        recording_layout.addWidget(QLabel("录制信息"))
        self.recording_info_text = QTextEdit()
        self.recording_info_text.setReadOnly(True)
        recording_layout.addWidget(self.recording_info_text)
        right_tabs.addTab(recording_widget, "录制信息")
        
        splitter.addWidget(right_tabs)
        
        splitter.setSizes([400, 900, 400])
        main_layout.addWidget(splitter)
        
        # 状态栏
        self.status_bar = QStatusBar()
        self.status_bar.showMessage("就绪 - 请启动浏览器开始")
        self.setStatusBar(self.status_bar)
        
    def _load_knowledge(self):
        """加载已有知识库"""
        knowledge_path = "output/knowledge/knowledge_base.json"
        if os.path.exists(knowledge_path):
            self.learning_engine.load_knowledge(knowledge_path)
            self.log_signal.emit("已加载已有知识库")
        
    def _on_launch(self):
        """启动浏览器"""
        def launch():
            try:
                self.log_signal.emit("正在启动浏览器...")
                self.browser_engine.launch(headless=False)
                self.log_signal.emit("浏览器启动成功")
                self.browser_started_signal.emit()
            except Exception as e:
                self.log_signal.emit(f"启动失败: {e}")
        
        threading.Thread(target=launch, daemon=True).start()
        
    def _on_browser_started(self):
        """浏览器启动后的UI更新"""
        self._browser_running = True
        self.record_btn.setEnabled(True)
        self.video_btn.setEnabled(True)
        self.screenshot_btn.setEnabled(True)
        self.code_btn.setEnabled(True)
        self.go_btn.setEnabled(True)
        self.preview_btn.setEnabled(True)
        self.analyze_btn.setEnabled(True)
        self.crawl_btn.setEnabled(True)
        self.launch_btn.setEnabled(False)
        self.launch_btn.setText("浏览器已启动")
        self.browser_label.setText("等待截图...")
        self.status_bar.showMessage("浏览器运行中 - 自动开始屏幕录制")
        
        # 自动开始屏幕录制
        self._auto_start_screen_recording()
        
    def _on_toggle_preview(self):
        """切换实时预览"""
        if self.preview_btn.isChecked():
            self.browser_engine.start_screenshot_loop()
            self.log_signal.emit("实时预览已启动")
        else:
            self.log_signal.emit("实时预览已停止（将在下次截图后停止）")
            
    def _on_screenshot_callback(self, path):
        """截图回调（在后台线程中调用）"""
        self.screenshot_signal.emit(path)
        
    def _on_action_callback(self, action):
        """操作回调（在后台线程中调用）- 触发视频录制截图"""
        # 当用户操作发生时，触发截图
        if self.is_video_recording and self.screenshot_capture:
            self.screenshot_capture.capture_on_action()
    
    def _auto_start_screen_recording(self):
        """自动开始屏幕录制"""
        try:
            # 延迟2秒等待浏览器窗口完全打开
            def start_recording():
                import time
                time.sleep(2)
                
                # 获取屏幕尺寸
                import subprocess
                import json
                
                screen_width = 1920
                screen_height = 1080
                
                try:
                    result = subprocess.run(
                        ['system_profiler', 'SPDisplaysDataType', '-json'],
                        capture_output=True, text=True
                    )
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
                
                # 开始录制浏览器窗口（跟踪窗口位置）
                video_path = self.screen_recorder.start_recording(
                    custom_name="auto_recording",
                    window_title="Chromium"  # 跟踪Chromium窗口
                )
                
                self.is_video_recording = True
                self.log_signal.emit(f"🎥 自动开始屏幕录制: {video_path}")
                self.log_signal.emit(f"   模式: 跟踪浏览器窗口, 帧率: 30fps")
            
            threading.Thread(target=start_recording, daemon=True).start()
            
        except Exception as e:
            self.log_signal.emit(f"⚠️ 自动开始录制失败: {e}")
    
    def _on_screen_recording_started(self, video_path):
        """屏幕录制开始回调"""
        self.log_signal.emit(f"🎥 屏幕录制已开始: {video_path}")
    
    def _on_screen_recording_stopped(self, result):
        """屏幕录制停止回调"""
        self.log_signal.emit(f"✅ 屏幕录制完成: {result['frame_count']}帧, {result['duration']:.1f}秒")
        
    def _update_screenshot(self, path):
        """更新截图显示（在主线程中执行）"""
        try:
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                # 缩放以适应显示区域
                scaled = pixmap.scaled(
                    self.browser_label.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self.browser_label.setPixmap(scaled)
                self.browser_label.setText("")
        except Exception as e:
            print(f"更新截图失败: {e}")
            
    def _check_browser_status(self):
        """检查浏览器状态"""
        if not self._browser_running:
            return
            
        try:
            is_alive = self.browser_engine.is_browser_alive()
        except Exception as e:
            is_alive = False
            
        if not is_alive:
            print(f"🔴 检测到浏览器已关闭")
            self._browser_running = False
            self.log_signal.emit("警告: 浏览器已关闭或失去响应")
            self.status_bar.showMessage("浏览器已断开")
            
            # 停止屏幕录制
            if self.is_video_recording:
                try:
                    print(f"🔴 正在停止屏幕录制...")
                    result = self.screen_recorder.stop_recording()
                    self.is_video_recording = False
                    self.log_signal.emit(f"✅ 屏幕录制已自动停止: {result['frame_count']}帧")
                    print(f"🔴 屏幕录制已停止: {result}")
                except Exception as e:
                    self.log_signal.emit(f"⚠️ 停止屏幕录制失败: {e}")
                    print(f"🔴 停止屏幕录制失败: {e}")
                    import traceback
                    traceback.print_exc()
            
            # 重置UI状态
            self.launch_btn.setEnabled(True)
            self.launch_btn.setText("启动浏览器")
            self.record_btn.setEnabled(False)
            self.video_btn.setEnabled(False)
            self.screenshot_btn.setEnabled(False)
            self.code_btn.setEnabled(False)
            self.go_btn.setEnabled(False)
            self.preview_btn.setEnabled(False)
            self.analyze_btn.setEnabled(False)
            self.browser_label.setText("浏览器已关闭，请重新启动")
            self.browser_label.setPixmap(QPixmap())
        
    def _on_toggle_recording(self):
        """切换操作录制状态"""
        if not self.is_recording:
            try:
                self.browser_engine.start_recording()
                self.is_recording = True
                self.record_btn.setText("停止录制操作")
                self.log_signal.emit("开始录制用户操作")
                self.status_bar.showMessage("正在录制操作...")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"开始录制失败: {e}")
        else:
            try:
                data = self.browser_engine.stop_recording()
                self.is_recording = False
                self.record_btn.setText("开始录制操作")
                self.log_signal.emit(f"录制完成: {data['actions_count']} 个操作")
                self.status_bar.showMessage("录制完成")
                
                # 显示录制信息
                self._update_recording_info(data)
                
                # 自动分析
                self._auto_analyze(data)
                
            except Exception as e:
                QMessageBox.critical(self, "错误", f"停止录制失败: {e}")
                
    def _on_toggle_video_recording(self):
        """切换视频录制状态"""
        if not self.is_video_recording:
            try:
                # 开始视频录制
                video_path = self.video_recorder.start_recording()
                
                # 开始截图捕获（用于视频录制）
                self.screenshot_capture.start_capture(
                    lambda: self.browser_engine.take_screenshot_sync()
                )
                
                # 同时启动操作录制（用于触发截图）
                if not self.is_recording:
                    self.browser_engine.start_recording()
                    self.is_recording = True
                    self.record_btn.setText("停止录制操作")
                    self.log_signal.emit("操作录制已自动启动（用于视频录制）")
                
                self.is_video_recording = True
                self.video_btn.setText("停止视频录制")
                self.video_status_label.setText("视频录制: 进行中")
                self.video_status_label.setStyleSheet("color: red; font-weight: bold;")
                self.log_signal.emit(f"开始视频录制: {video_path}")
                self.status_bar.showMessage("正在录制视频...")
                
            except Exception as e:
                QMessageBox.critical(self, "错误", f"开始视频录制失败: {e}")
        else:
            try:
                # 停止定时截图
                self.screenshot_capture.stop_capture()
                
                # 停止视频录制
                result = self.video_recorder.stop_recording()
                
                self.is_video_recording = False
                self.video_btn.setText("开始视频录制")
                self.video_status_label.setText("视频录制: 未开始")
                self.video_status_label.setStyleSheet("")
                self.log_signal.emit(f"视频录制完成: {result['frame_count']} 帧, {result['duration']:.1f}秒")
                self.status_bar.showMessage(f"视频已保存: {result['video_path']}")
                
                # 显示视频信息
                QMessageBox.information(self, "视频录制完成", 
                    f"视频已保存: {result['video_path']}\n"
                    f"帧数: {result['frame_count']}\n"
                    f"时长: {result['duration']:.1f}秒\n"
                    f"分辨率: {result['resolution']}")
                
            except Exception as e:
                QMessageBox.critical(self, "错误", f"停止视频录制失败: {e}")
                
    def _update_recording_info(self, data: dict):
        """更新录制信息显示"""
        info_text = f"录制时间: {data.get('start_time', 'N/A')}\n"
        info_text += f"录制时长: {data.get('duration', 0):.1f}秒\n"
        info_text += f"操作数量: {data.get('actions_count', 0)}\n"
        info_text += f"页面数量: {len(data.get('pages', []))}\n\n"
        
        if data.get('actions'):
            info_text += "操作列表:\n"
            for i, action in enumerate(data['actions'][:20], 1):
                desc = action.get('description', action.get('type', '未知'))
                info_text += f"{i}. {desc}\n"
            if len(data['actions']) > 20:
                info_text += f"... 还有 {len(data['actions']) - 20} 个操作\n"
                
        self.recording_info_text.setText(info_text)
        
    def _auto_analyze(self, data: dict):
        """自动分析录制数据"""
        self.log_signal.emit("正在分析录制数据...")
        
        # 学习行为模式
        result = self.learning_engine.learn_from_actions(
            data.get('actions', []),
            data.get('navigation_history', [])
        )
        
        self.log_signal.emit(f"分析完成: 发现 {result['patterns_found']} 个新模式")
        
        if result['new_patterns']:
            self.log_signal.emit(f"新发现 {len(result['new_patterns'])} 个行为模式")
            
    def _on_analyze_recording(self):
        """手动分析录制"""
        # 这里可以加载历史录制文件进行分析
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择录制文件", "output", "JSON Files (*.json)"
        )
        
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                self._auto_analyze(data)
                self._update_recording_info(data)
                QMessageBox.information(self, "分析完成", f"已分析录制文件: {file_path}")
                
            except Exception as e:
                QMessageBox.critical(self, "错误", f"分析失败: {e}")
                
    def _on_view_knowledge(self):
        """查看知识库"""
        report = self.learning_engine.generate_knowledge_report()
        
        # 格式化显示
        text = "=== 知识库报告 ===\n\n"
        text += f"页面模式数量: {report['summary']['total_page_patterns']}\n"
        text += f"行为模式数量: {report['summary']['total_behavior_patterns']}\n\n"
        
        text += "=== 洞察 ===\n"
        for insight in report['insights']:
            text += f"• {insight}\n"
            
        text += "\n=== 行为模式 ===\n"
        for pattern in report['behavior_patterns']:
            text += f"\n[{pattern['pattern_id']}]\n"
            text += f"  类型: {pattern['context']}\n"
            text += f"  频率: {pattern['frequency']}\n"
            text += f"  成功率: {pattern['success_rate']:.2f}\n"
            
        self.knowledge_text.setText(text)
        
    def _on_save_knowledge(self):
        """保存知识库"""
        filepath = "output/knowledge/knowledge_base.json"
        self.learning_engine.save_knowledge(filepath)
        self.log_signal.emit(f"知识库已保存: {filepath}")
        QMessageBox.information(self, "保存成功", f"知识库已保存到:\n{filepath}")
        
    def _on_load_knowledge(self):
        """加载知识库"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择知识库文件", "output/knowledge", "JSON Files (*.json)"
        )
        
        if file_path:
            if self.learning_engine.load_knowledge(file_path):
                self.log_signal.emit(f"知识库已加载: {file_path}")
                QMessageBox.information(self, "加载成功", f"知识库已加载")
            else:
                QMessageBox.critical(self, "错误", "加载知识库失败")
                
    def _on_screenshot(self):
        """截取屏幕"""
        try:
            filepath = self.browser_engine.take_screenshot()
            self.log_signal.emit(f"截图已保存: {filepath}")
            QMessageBox.information(self, "成功", f"截图已保存: {filepath}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"截图失败: {e}")
            
    def _on_get_code(self):
        """获取页面代码"""
        try:
            self.log_signal.emit("正在获取完整页面代码（包含CSS）...")
            
            html = self.browser_engine.get_full_page()
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            html_path = os.path.join(self.browser_engine.output_dir, f"page_{timestamp}.html")
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html)
            
            self.log_signal.emit(f"完整HTML已保存: {html_path}")
            self.log_signal.emit(f"HTML大小: {len(html)} 字符")
            
            # 分析页面结构
            self._analyze_page_structure(html_path, html)
            
            QMessageBox.information(self, "成功", f"完整页面已保存到:\n{html_path}\n\n可以直接用浏览器打开查看")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"获取代码失败: {e}")
            
    def _analyze_page_structure(self, url: str, html: str):
        """分析页面结构"""
        # 获取样式信息
        styles = self.browser_engine.get_page_styles()
        
        # 分析页面
        result = self.learning_engine.analyze_page_structure(url, html, styles)
        
        # 显示分析结果
        structure_text = f"页面指纹: {result['pattern_id']}\n"
        structure_text += f"是否新页面: {result['is_new_pattern']}\n"
        structure_text += f"出现次数: {result['occurrences']}\n\n"
        
        features = result['features']
        structure_text += f"交互元素: {features.get('interactive_elements', 0)}\n"
        structure_text += f"表单元素: {features.get('form_elements', 0)}\n"
        structure_text += f"链接数量: {features.get('link_count', 0)}\n"
        structure_text += f"图片数量: {features.get('image_count', 0)}\n\n"
        
        structure_text += "元素类型分布:\n"
        for tag, count in sorted(features.get('element_types', {}).items(), key=lambda x: x[1], reverse=True)[:10]:
            structure_text += f"  {tag}: {count}\n"
            
        self.structure_text.setText(structure_text)
        
    def _on_navigate(self):
        """导航到URL"""
        url = self.url_input.text().strip()
        if not url:
            return
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
            
        def navigate():
            try:
                self.log_signal.emit(f"正在导航到: {url}")
                self.browser_engine.navigate(url)
                self.log_signal.emit(f"页面加载完成: {url}")
            except Exception as e:
                self.log_signal.emit(f"导航失败: {e}")
        
        threading.Thread(target=navigate, daemon=True).start()
        
    def _on_crawl_website(self):
        """爬取网站"""
        self.log_signal.emit("点击了爬取网站按钮")
        
        try:
            url = self.url_input.text().strip()
            if not url:
                QMessageBox.warning(self, "警告", "请先输入要爬取的网址")
                return
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
                
            self.log_signal.emit(f"准备爬取: {url}")
            
            # 使用默认参数，简化流程
            depth = 2
            max_pages = 50
                
            # 开始爬取
            self.crawl_btn.setEnabled(False)
            self.crawl_btn.setText("🕷️ 爬取中...")
            self.status_bar.showMessage(f"正在爬取 {url}...")
            self.log_signal.emit(f"开始爬取: {url}, 深度={depth}, 页面数={max_pages}")
            
            # 在后台线程中启动爬取（Crawlee 使用异步 API）
            import threading
            import asyncio
            
            def do_crawl():
                try:
                    # 创建新的事件循环
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    # 运行异步爬虫
                    result = loop.run_until_complete(
                        self.website_crawler.start_crawl(url, max_depth=depth, max_pages=max_pages)
                    )
                    self.log_signal.emit(result)
                except Exception as e:
                    self.log_signal.emit(f"爬取异常: {e}")
                    import traceback
                    traceback.print_exc()
                finally:
                    # 恢复按钮状态
                    self.crawl_btn.setEnabled(True)
                    self.crawl_btn.setText("🕷️ 爬取网站")
            
            threading.Thread(target=do_crawl, daemon=True).start()
        except Exception as e:
            self.log_signal.emit(f"启动爬取失败: {e}")
            QMessageBox.critical(self, "错误", f"启动爬取失败: {e}")
        
    def _on_page_crawled(self, result):
        """页面爬取完成回调"""
        self.log_signal.emit(f"爬取完成: {result.url} - {result.title}")
        
        # 更新状态
        self.status_bar.showMessage(
            f"已爬取 {len(self.website_crawler.results)}/{self.website_crawler.max_pages} 页"
        )
        
    def _on_crawl_complete(self, results):
        """爬取完成回调"""
        self.crawl_btn.setEnabled(True)
        self.crawl_btn.setText("🕷️ 爬取网站")
        
        self.log_signal.emit(f"爬取完成! 共 {len(results)} 个页面")
        self.status_bar.showMessage(f"爬取完成: {len(results)} 个页面")
        
        # 显示结果
        QMessageBox.information(
            self, "爬取完成",
            f"爬取完成!\n\n"
            f"总页面数: {len(results)}\n"
            f"报告已保存到: output/crawl/"
        )
        
    def _on_crawl_progress(self, progress):
        """爬取进度回调"""
        self.status_bar.showMessage(
            f"正在爬取: {progress['current']}/{progress['total']} - {progress['current_url']}"
        )
        
    def _on_crawl_log(self, message):
        """爬取日志回调"""
        self.log_signal.emit(message)
        
    def _add_log(self, message):
        """添加日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_list.addItem(f"[{timestamp}] {message}")
        self.log_list.scrollToBottom()
        
    def closeEvent(self, event):
        """关闭事件处理"""
        if self.is_recording:
            self.browser_engine.stop_recording()
        if self.is_video_recording:
            self.screen_recorder.stop_recording()
        self.browser_engine.close()
        event.accept()


def main():
    """主函数"""
    app = QApplication(sys.argv)
    
    # 创建输出目录
    output_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(os.path.join(output_dir, "knowledge"), exist_ok=True)
    os.makedirs(os.path.join(output_dir, "videos"), exist_ok=True)
    os.makedirs(os.path.join(output_dir, "crawl"), exist_ok=True)
    
    # 创建浏览器引擎
    engine = BrowserEngine(output_dir=output_dir)
    
    # 创建主窗口
    window = MainWindow(engine)
    window.show()
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
