80#!/usr/bin/env python3
"""
测试基于代码的局部优化方案
Usage: python test_code_optimize.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from screenshot_to_html import ScreenshotToHTML

# 测试文件
test_file = "智能看图形分享按钮点击弹框.PNG"
input_dir = "/Users/gaoyiwei/Downloads/财富星AI-ETF所有截图"
output_dir = "/Users/gaoyiwei/Documents/trae_projects/openclaw/page-screenshot-to-html/output"

input_path = os.path.join(input_dir, test_file)
output_path = os.path.join(output_dir, test_file.replace('.PNG', '.html').replace('.JPG', '.html'))

if not os.path.exists(input_path):
    print(f"❌ 文件不存在: {input_path}")
    sys.exit(1)

print(f"测试基于代码的局部优化方案")
print(f"输入: {input_path}")
print(f"输出: {output_path}")
print("="*60)

# 创建转换器
converter = ScreenshotToHTML(
    image_path=input_path,
    output_path=output_path,
    use_kimi=True,
    debug=True
)

# 执行转换
converter.run()

print("\n测试完成!")
