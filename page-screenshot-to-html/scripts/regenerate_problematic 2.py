#!/usr/bin/env python3
"""
重新生成有问题的HTML页面
Usage: python regenerate_problematic.py [--debug]
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from screenshot_to_html import ScreenshotToHTML

# 检查是否启用debug模式
debug_mode = '--debug' in sys.argv

# 有问题的文件列表（用户指定的7个页面）
problematic_files = [
    "AI-ETF退签页二次确认弹框.PNG",
    "日内交易分享按钮点击弹框.PNG",
    "签约策略修改收费方式页.PNG",
    "智能看图形分享按钮点击弹框.PNG",
    "财富星AI投顾收费方式确认书页.PNG",
    "AI-ETF首页（未签约状态）.JPG",
    "智能看图形页面（已签约）.JPG"
]

input_dir = "/Users/gaoyiwei/Downloads/财富星AI-ETF所有截图"
output_dir = "/Users/gaoyiwei/Documents/trae_projects/openclaw/page-screenshot-to-html/output"

print(f"将重新生成 {len(problematic_files)} 个有问题的页面")
print(f"输入目录: {input_dir}")
print(f"输出目录: {output_dir}")
print(f"Debug模式: {'启用' if debug_mode else '禁用'}")
print()

success_count = 0
failed_files = []

for i, filename in enumerate(problematic_files, 1):
    print(f"\n{'='*60}")
    print(f"[{i}/{len(problematic_files)}] 重新生成: {filename}")
    print(f"{'='*60}")
    
    input_path = os.path.join(input_dir, filename)
    
    if not os.path.exists(input_path):
        print(f"❌ 文件不存在: {input_path}")
        failed_files.append(filename)
        continue
    
    try:
        converter = ScreenshotToHTML(
            image_path=input_path,
            output_dir=output_dir,
            use_kimi=True,
            debug=debug_mode  # 传递debug参数
        )
        converter.run()
        success_count += 1
        print(f"✅ 成功: {filename}")
    except Exception as e:
        print(f"❌ 失败: {e}")
        failed_files.append(filename)

print(f"\n{'='*60}")
print("重新生成完成")
print(f"{'='*60}")
print(f"✅ 成功: {success_count}/{len(problematic_files)}")
print(f"❌ 失败: {len(failed_files)}/{len(problematic_files)}")

if failed_files:
    print("\n失败的文件:")
    for f in failed_files:
        print(f"  - {f}")
