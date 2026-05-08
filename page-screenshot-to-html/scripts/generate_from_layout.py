#!/usr/bin/env python3
"""
直接从结构化布局JSON生成HTML文件
不依赖page-screenshot-to-html工具
"""

import json

def generate_html_from_layout(json_path, output_path):
    """从结构化布局JSON生成HTML"""
    
    with open(json_path, 'r', encoding='utf-8') as f:
        layout = json.load(f)
    
    page_width = layout['page_width']
    page_height = layout['page_height']
    
    html_parts = []
    
    # HTML头部
    html_parts.append(f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>股票行情页</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
            background-color: #f0f0f0;
            display: flex;
            justify-content: center;
            align-items: flex-start;
            min-height: 100vh;
            padding: 20px 0;
        }}
        
        .page-container {{
            position: relative;
            width: {page_width}px;
            height: {page_height}px;
            overflow: hidden;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        
        .section {{
            position: absolute;
            left: 0;
            right: 0;
        }}
        
        .text-element {{
            position: absolute;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            display: flex;
            align-items: center;
        }}
        
        .ui-element {{
            position: absolute;
            border: 1px dashed rgba(255,0,0,0.15);
            border-radius: 2px;
        }}
    </style>
</head>
<body>
    <div class="page-container" style="width: {page_width}px; height: {page_height}px;">''')
    
    # 遍历每个section
    for section in layout['sections']:
        section_top = section['y_start']
        section_height = section['height']
        bg_color = section.get('bg_color', '#ffffff')
        
        html_parts.append(f'''
        <div class="section" style="top: {section_top}px; height: {section_height}px; background-color: {bg_color};">''')
        
        # 渲染UI元素
        for elem in section['elements']:
            x = elem['x']
            y = elem['y']
            w = elem['w']
            h = elem['h']
            elem_type = elem.get('type', 'ui_element')
            html_parts.append(f'''
            <div class="ui-element" style="left: {x}px; top: {y}px; width: {w}px; height: {h}px;">''')
            if elem_type == 'button':
                html_parts.append('</div>')
            else:
                html_parts.append('</div>')
        
        # 渲染文本元素
        for text_obj in section['texts']:
            text = text_obj['text']
            x = text_obj['x']
            y = text_obj['y']
            w = text_obj['w']
            h = text_obj['h']
            
            # 根据文本内容确定样式
            color = '#333333'
            font_size = max(10, int(h * 0.6))
            font_weight = 'normal'
            
            # 价格相关文本特殊处理
            if any(keyword in text for keyword in ['8.04', '8.03', '8.02', '8.09', '7.94', '7.91', '10.02%', '0.01%', '16.66', '15.19', '2.09', '3.82', '-0.92']):
                if any(k in text for k in ['8.02', '-0.92']):
                    color = '#22c55e'  # 绿色
                else:
                    color = '#ff4757'  # 红色
                font_weight = 'bold'
                font_size = max(12, int(h * 0.7))
            
            # 买/卖文本
            if '买' in text:
                color = '#ff4757'
            if '卖' in text:
                color = '#22c55e'
            
            # 标签文本
            if any(keyword in text for keyword in ['要闻', '资金', 'F10', '两融', '揭秘', '诊股', '明细', '队列', '量价', '逐笔', '分时', '日K', '周K', '月K', '其他']):
                if '诊股' in text:
                    color = '#ff4757'
                    font_weight = 'bold'
            
            # 按钮文本
            if any(keyword in text for keyword in ['下单', '条件下单', '盯盘助手', '删自选', '查看策略详情']):
                font_weight = 'bold'
            
            html_parts.append(f'''
            <div class="text-element" style="left: {x}px; top: {y}px; width: {w}px; height: {h}px; font-size: {font_size}px; color: {color}; font-weight: {font_weight};">
                {text}
            </div>''')
        
        html_parts.append('''
        </div>''')
    
    # HTML尾部
    html_parts.append('''
    </div>
</body>
</html>''')
    
    # 写入文件
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(html_parts))
    
    print(f"✅ HTML文件已生成: {output_path}")
    print(f"📊 页面尺寸: {page_width}x{page_height}")
    print(f"🧩 区域数量: {len(layout['sections'])}")
    print(f"📝 文本块数量: {layout['total_text_blocks']}")
    print(f"🔘 UI元素数量: {layout['total_elements']}")


if __name__ == '__main__':
    json_file = '/Users/gaoyiwei/Documents/trae_projects/openclaw/page-screenshot-to-html/output/个股行情页-财富星- AI选股-智能诊股（未签约状态）_structured_layout.json'
    output_file = '/Users/gaoyiwei/Documents/trae_projects/openclaw/page-screenshot-to-html/output/个股行情页-财富星- AI选股-智能诊股（未签约状态）_direct_layout.html'
    
    generate_html_from_layout(json_file, output_file)