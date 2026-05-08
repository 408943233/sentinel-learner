#!/usr/bin/env python3
import json
import os

def generate_html_from_layout(layout_file, output_file):
    """从结构化布局JSON生成HTML"""
    
    with open(layout_file, 'r', encoding='utf-8') as f:
        layout = json.load(f)
    
    html_parts = []
    
    html_parts.append('''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>股票行情页</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
            background-color: #333;
            display: flex;
            justify-content: center;
            align-items: flex-start;
            min-height: 100vh;
            padding: 20px 0;
            margin: 0;
        }
        
        .page-container {
            position: relative;
            width: {{page_width}}px;
            height: {{page_height}}px;
            overflow: hidden;
        }
        
        .layout-section {
            position: absolute;
            left: 0;
            right: 0;
            box-sizing: border-box;
        }
        
        .text-element {
            position: absolute;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        
        .ui-element {
            position: absolute;
            border: 1px dashed rgba(0,0,0,0.1);
            box-sizing: border-box;
        }
    </style>
</head>
<body>
    <div class="page-container" style="width: {{page_width}}px; height: {{page_height}}px;">
'''.replace('{{page_width}}', str(layout['page_width']))
   .replace('{{page_height}}', str(layout['page_height'])))
    
    for section in layout['sections']:
        section_style = f'top: {section["y_start"]}px; height: {section["height"]}px; background-color: {section["bg_color"]};'
        html_parts.append(f'        <div class="layout-section" style="{section_style}">')
        
        for text in section['texts']:
            if not text['text'].strip():
                continue
            text_style = f'left: {text["x"]}px; top: {text["y"]}px; width: {text["w"]}px; height: {text["h"]}px; font-size: {max(12, int(text["h"]*0.7))}px; line-height: {text["h"]}px;'
            html_parts.append(f'            <div class="text-element" style="{text_style}">{text["text"]}</div>')
        
        for elem in section['elements']:
            elem_style = f'left: {elem["x"]}px; top: {elem["y"]}px; width: {elem["w"]}px; height: {elem["h"]}px;'
            html_parts.append(f'            <div class="ui-element" style="{elem_style}"></div>')
        
        html_parts.append('        </div>')
    
    html_parts.append('''    </div>
</body>
</html>''')
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(html_parts))
    
    print(f"HTML已生成: {output_file}")

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 3:
        print("用法: python generate_html_from_layout.py <layout_json_file> <output_html_file>")
        sys.exit(1)
    
    layout_file = sys.argv[1]
    output_file = sys.argv[2]
    
    generate_html_from_layout(layout_file, output_file)
