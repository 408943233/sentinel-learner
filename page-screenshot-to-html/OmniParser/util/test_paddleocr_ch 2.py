#!/usr/bin/env python3
"""测试优化后的 PaddleOCR 中文识别效果"""

from utils import check_ocr_box, postprocess_ocr_result
from PIL import Image
import numpy as np

# 测试识别
image_path = '/Users/gaoyiwei/Downloads/财富星AI投顾-AI选股/个股行情页-财富星- AI选股-智能诊股（未签约状态）.jpg'

print('='*60)
print('测试优化后的 PaddleOCR 中文识别')
print('='*60)

# 使用 OmniParser 的 check_ocr_box 函数
result, _ = check_ocr_box(
    image_source=image_path,
    display_img=False,
    output_bb_format='xywh',
    use_paddleocr=True
)

text_list, coord_list = result

print(f'\n检测到 {len(text_list)} 个文本区域（后处理后）')
print('\n前50个结果：')
for i, (text, coord) in enumerate(zip(text_list[:50], coord_list[:50])):
    print(f'{i}: "{text}" @ ({coord[0]}, {coord[1]})')

print('\n' + '='*60)
print('检查关键文本是否正确拆分：')
print('='*60)

# 检查是否成功拆分
key_patterns = ['8.09', '成交量', '7.94', '最高', '最低', '成交额', '白银有色', '601212']
for pattern in key_patterns:
    found = [t for t in text_list if pattern in t]
    if found:
        print(f'✅ 找到 "{pattern}": {found[:3]}')
    else:
        print(f'❌ 未找到 "{pattern}"')
