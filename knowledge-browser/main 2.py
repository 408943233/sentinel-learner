#!/usr/bin/env python3
"""
知识浏览器 - 主入口
基于Playwright + Tkinter的专用浏览器
"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.browser_engine import BrowserEngine
from ui.main_window_simple import MainWindowSimple


def main():
    """主函数"""
    print("=" * 60)
    print("知识浏览器 v1.0")
    print("=" * 60)
    print()
    
    # 创建输出目录
    output_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)
    
    # 创建浏览器引擎
    print("初始化浏览器引擎...")
    engine = BrowserEngine(output_dir=output_dir)
    
    # 创建主窗口
    print("创建用户界面...")
    app = MainWindowSimple(engine)
    
    # 设置关闭处理
    app.root.protocol("WM_DELETE_WINDOW", app.on_close)
    
    print()
    print("知识浏览器已启动")
    print("   点击'启动浏览器'按钮开始使用")
    print()
    
    # 运行应用
    app.run()


if __name__ == '__main__':
    main()
