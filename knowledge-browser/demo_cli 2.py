#!/usr/bin/env python3
"""
知识浏览器 - 命令行演示版
展示核心功能，无需GUI
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.browser_engine import BrowserEngine


def demo():
    """演示知识浏览器功能"""
    print("=" * 70)
    print("🌐 知识浏览器 - 命令行演示")
    print("=" * 70)
    print()
    
    # 创建浏览器引擎
    print("1️⃣  初始化浏览器引擎...")
    engine = BrowserEngine(output_dir="output")
    
    # 启动浏览器
    print("2️⃣  启动浏览器（非无头模式）...")
    print("   浏览器窗口即将打开，请在浏览器中操作")
    print()
    
    try:
        engine.launch(headless=False)
        
        # 导航到示例页面
        print("3️⃣  导航到示例页面...")
        engine.navigate("https://www.baidu.com")
        
        print()
        print("=" * 70)
        print("📋 可用操作:")
        print("=" * 70)
        print("   1. 在浏览器窗口中正常操作（点击、输入等）")
        print("   2. 按 Enter 开始录制操作")
        print("   3. 录制完成后按 Enter 停止")
        print("   4. 输入 'screenshot' 截取屏幕")
        print("   5. 输入 'code' 获取页面代码")
        print("   6. 输入 'quit' 退出")
        print("=" * 70)
        print()
        
        while True:
            try:
                command = input("🔘 输入命令: ").strip().lower()
                
                if command == '':
                    if not engine.is_recording:
                        print("🔴 开始录制...")
                        engine.start_recording()
                    else:
                        print("⏹️  停止录制...")
                        data = engine.stop_recording()
                        print(f"   ✅ 录制完成: {data['actions_count']} 个操作")
                        
                elif command == 'screenshot':
                    print("📸 截取屏幕...")
                    filepath = engine.take_screenshot()
                    print(f"   ✅ 截图已保存: {filepath}")
                    
                elif command == 'code':
                    print("📄 获取页面代码...")
                    html = engine.get_page_source()
                    styles = engine.get_page_styles()
                    
                    # 保存代码
                    import json
                    from datetime import datetime
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    
                    html_path = f"output/page_{timestamp}.html"
                    with open(html_path, 'w', encoding='utf-8') as f:
                        f.write(html)
                    
                    styles_path = f"output/styles_{timestamp}.json"
                    with open(styles_path, 'w', encoding='utf-8') as f:
                        json.dump(styles, f, ensure_ascii=False, indent=2)
                    
                    print(f"   ✅ HTML已保存: {html_path}")
                    print(f"   ✅ 样式已保存: {styles_path}")
                    print(f"   📊 HTML大小: {len(html)} 字符")
                    print(f"   📊 样式元素: {len(styles)} 个")
                    
                elif command == 'quit':
                    print("👋 退出程序...")
                    break
                    
                elif command.startswith('goto '):
                    url = command[5:].strip()
                    if not url.startswith(('http://', 'https://')):
                        url = 'https://' + url
                    print(f"🌐 导航到: {url}")
                    engine.navigate(url)
                    
                else:
                    print("❓ 未知命令")
                    print("   可用: <Enter> (录制), screenshot, code, goto <url>, quit")
                    
            except KeyboardInterrupt:
                print("\n👋 退出程序...")
                break
            except Exception as e:
                print(f"❌ 错误: {e}")
                
    finally:
        # 清理
        if engine.is_recording:
            engine.stop_recording()
        engine.close()
        
    print()
    print("=" * 70)
    print("✅ 演示结束")
    print("=" * 70)


if __name__ == '__main__':
    demo()
