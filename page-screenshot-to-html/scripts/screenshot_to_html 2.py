#!/usr/bin/env python3
import argparse
import os
import sys
import base64
import time
import glob
from PIL import Image
import pytesseract
import cv2
import json
import numpy as np
from datetime import datetime
from openai import OpenAI
from skimage.metrics import structural_similarity as ssim
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# 全局变量
def get_default_output_dir():
    """获取默认输出目录 - 使用项目目录下的output文件夹"""
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(script_dir, 'output')


class HTMLPostProcessor:
    """HTML后处理器 - 检测问题并生成修复建议，不直接修改HTML"""
    
    @staticmethod
    def detect_issues(html):
        """检测HTML中的问题，返回问题列表"""
        import re
        issues = []
        
        # 1. 检测emoji（包括Unicode emoji和HTML实体emoji）
        emoji_pattern = re.compile("["
            u"\U0001F600-\U0001F64F"
            u"\U0001F300-\U0001F5FF"
            u"\U0001F680-\U0001F6FF"
            u"\U0001F1E0-\U0001F1FF"
            "\u2764\uFE0F"  # ❤️
            "\u2728"  # ✨
            "\u2B50"  # ⭐
            "]+", flags=re.UNICODE)
        if emoji_pattern.search(html):
            issues.append("检测到emoji字符，请移除所有emoji（包括📈💰📊等），使用SVG或CSS替代")
        
        # 1.1 检测HTML实体emoji（如&#128200;）
        if re.search(r'&#\d{5,6};', html):
            issues.append("检测到HTML实体emoji（如&#128200;），请移除并用SVG替代")
        
        # 2. 检测动画和滑动效果（黑名单）
        if re.search(r'transition:|animation:|@keyframes', html, re.IGNORECASE):
            issues.append("检测到动画效果（transition/animation），请移除")
        
        # 2.1 检测滑动/滚动效果（黑名单）
        scroll_patterns = [
            r'overflow-y:\s*auto',
            r'overflow-y:\s*scroll', 
            r'overflow:\s*auto',
            r'overflow:\s*scroll',
            r'\.scroll',
            r'\.content-scroll',
            r'scrollbar-width',
            r'-ms-overflow-style',
            r'::-webkit-scrollbar'
        ]
        for pattern in scroll_patterns:
            if re.search(pattern, html, re.IGNORECASE):
                issues.append("检测到滑动/滚动效果（overflow-y: auto/scroll等），请移除，所有内容必须平铺展示")
                break
        
        # 3. 检测hover效果
        if re.search(r':hover', html, re.IGNORECASE):
            issues.append("检测到hover效果，请移除")
        
        # 4. 检测JavaScript
        if re.search(r'<script|on\w+=', html, re.IGNORECASE):
            issues.append("检测到JavaScript代码，请移除")
        
        # 5. 检测fixed定位（可能导致重叠）
        if re.search(r'position:\s*fixed', html, re.IGNORECASE):
            issues.append("检测到fixed定位，请改为absolute定位")
        
        # 6. 检测是否创造了过多箭头（可能是幻觉）
        arrow_classes = re.findall(r'class="[^"]*arrow[^"]*"', html, re.IGNORECASE)
        if len(arrow_classes) > 10:
            issues.append(f"检测到{len(arrow_classes)}个箭头元素，可能存在幻觉。请只保留原图中确实存在的箭头，移除其他装饰性箭头")
        
        return issues
    
    @staticmethod
    def generate_fix_prompt(html, issues):
        """生成修复提示词 - 包含具体的问题代码片段"""
        if not issues:
            return None
        
        import re
        
        fix_prompt = """【HTML修复任务】

请修复以下HTML代码中的问题。我会告诉你具体哪些代码有问题，你只需要修改这些特定部分：

"""
        for i, issue in enumerate(issues, 1):
            fix_prompt += f"\n## 问题 {i}: {issue}\n"
            
            # 根据问题类型，提取具体的代码片段
            if "滑动/滚动" in issue:
                # 提取overflow相关的CSS
                overflow_matches = re.findall(r'[^}]*overflow[^;]*;[^}]*', html, re.IGNORECASE)
                if overflow_matches:
                    fix_prompt += "**需要修改的代码（移除这些overflow属性）：**\n```css\n"
                    for match in overflow_matches[:5]:
                        fix_prompt += f"{match}\n"
                    fix_prompt += "```\n"
                    fix_prompt += "**修复方法**：删除overflow-y: auto/scroll，改为overflow: visible或删除该属性\n"
            
            elif "动画" in issue:
                # 提取动画相关的CSS
                anim_matches = re.findall(r'[^}]*(?:transition|animation|@keyframes)[^{]*\{[^}]*\}', html, re.IGNORECASE | re.DOTALL)
                if anim_matches:
                    fix_prompt += "**需要修改的代码（移除这些动画）：**\n```css\n"
                    for match in anim_matches[:3]:
                        fix_prompt += f"{match}\n"
                    fix_prompt += "```\n"
                    fix_prompt += "**修复方法**：删除transition、animation、@keyframes相关代码\n"
            
            elif "emoji" in issue:
                # 提取emoji
                emoji_pattern = re.compile("["
                    u"\U0001F600-\U0001F64F"
                    u"\U0001F300-\U0001F5FF"
                    u"\U0001F680-\U0001F6FF"
                    u"\U0001F1E0-\U0001F1FF"
                    "\u2764\uFE0F\u2728\u2B50"
                    "]+", flags=re.UNICODE)
                emojis = emoji_pattern.findall(html)
                if emojis:
                    fix_prompt += f"**需要移除的emoji：** {', '.join(set(emojis))}\n"
                    fix_prompt += "**修复方法**：将这些emoji替换为SVG图标或删除\n"
                
                # 提取HTML实体emoji
                entity_emojis = re.findall(r'&#\d{5,6};', html)
                if entity_emojis:
                    fix_prompt += f"**需要移除的HTML实体emoji：** {', '.join(set(entity_emojis))}\n"
                    fix_prompt += "**修复方法**：将这些HTML实体替换为SVG图标或删除\n"
            
            elif "箭头" in issue and "幻觉" in issue:
                # 提取箭头相关的class
                arrow_matches = re.findall(r'<[^>]*class="[^"]*arrow[^"]*"[^>]*>', html, re.IGNORECASE)
                if arrow_matches:
                    fix_prompt += f"**检测到{len(arrow_matches)}个箭头元素，请检查并只保留原图确实存在的：**\n"
                    fix_prompt += "**修复方法**：删除装饰性箭头，只保留功能必需的箭头\n"
        
        fix_prompt += f"""

【当前完整HTML代码】
```html
{html}
```

【修复要求】
1. **只修改上述指出的问题代码**，其他代码完全不要动
2. **保持HTML结构完整**，不要重新生成整个页面
3. **保持文字内容不变**
4. **返回完整的修复后HTML代码**
5. **不要添加任何解释**，只返回HTML代码

【重要】
- 只修复我告诉你的具体问题
- 不要改变页面布局
- 不要改变元素位置
- 不要改变颜色
- 只删除/修改有问题的代码片段
"""
        return fix_prompt
    
    @staticmethod
    def process(html, extracted_colors=None, logical_height=844):
        """检测问题并返回修复建议（自动修复可正则处理的问题）"""
        print("开始HTML问题检测...")
        
        issues = HTMLPostProcessor.detect_issues(html)
        
        auto_fixable = []
        need_api_fix = []
        
        for issue in issues:
            if any(kw in issue for kw in ["JavaScript", "hover效果", "fixed定位"]):
                auto_fixable.append(issue)
            else:
                need_api_fix.append(issue)
        
        if auto_fixable:
            print(f"  🔧 自动修复 {len(auto_fixable)} 个问题（无需调用API）:")
            for issue in auto_fixable:
                print(f"    - {issue}")
            
            import re
            
            for issue in auto_fixable:
                if "JavaScript" in issue:
                    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
                    html = re.sub(r'\s*on\w+\s*=\s*["\'][^"\']*["\']', '', html, flags=re.IGNORECASE)
                    print(f"    ✅ 已自动移除JavaScript代码")
                
                if "hover效果" in issue:
                    html = re.sub(r'[^}]*:hover\s*\{[^}]*\}', '', html, flags=re.DOTALL | re.IGNORECASE)
                    print(f"    ✅ 已自动移除hover效果")
                
                if "fixed定位" in issue:
                    html = re.sub(r'position:\s*fixed', 'position: absolute', html, flags=re.IGNORECASE)
                    print(f"    ✅ 已将fixed定位改为absolute定位")
            
            remaining_issues = HTMLPostProcessor.detect_issues(html)
            need_api_fix = [i for i in remaining_issues if i not in auto_fixable]
        
        if need_api_fix:
            print(f"  ⚠️ 仍有 {len(need_api_fix)} 个问题需要API修复:")
            for issue in need_api_fix:
                print(f"    - {issue}")
            
            fix_prompt = HTMLPostProcessor.generate_fix_prompt(html, need_api_fix)
            return html, need_api_fix, fix_prompt
        else:
            if auto_fixable:
                print("  ✓ 所有问题已自动修复")
            else:
                print("  ✓ 未检测到问题")
            return html, [], None

class ScreenshotToHTML:
    def __init__(self, image_path, output_path=None, output_dir=None, use_kimi=True, accuracy="medium", debug=False, timeout=120):
        self.image_path = image_path
        self.output_path = output_path
        self.output_dir = output_dir or get_default_output_dir()
        self.use_kimi = use_kimi  # 默认使用Kimi
        self.debug = debug  # Debug模式开关
        self.accuracy = accuracy
        self.timeout = timeout  # API调用超时时间（秒）
        
        # 获取Kimi Coding API配置
        self.kimi_api_key = os.environ.get('KIMI_CODING_API_KEY') or os.environ.get('KIMI_API_KEY', '')
        # Kimi Coding使用Anthropic API格式，baseUrl以/coding/结尾
        self.kimi_base_url = os.environ.get('KIMI_CODING_BASE_URL', 'https://api.kimi.com/coding/')
        # 使用k2p5模型（Kimi for Coding）
        self.kimi_model = os.environ.get('KIMI_CODING_MODEL', 'k2p5')
        
        # 确定最终输出路径和图标目录
        if not self.output_path:
            # 如果没有指定输出路径，使用默认目录
            base_name = os.path.splitext(os.path.basename(self.image_path))[0]
            self.output_path = os.path.join(self.output_dir, f"{base_name}.html")
            # 创建输出目录
            os.makedirs(self.output_dir, exist_ok=True)
            # 创建图标目录
            self.icons_dir = os.path.join(self.output_dir, 'icons')
            os.makedirs(self.icons_dir, exist_ok=True)
        else:
            # 如果指定了输出路径，在输出路径所在目录创建图标目录
            output_dir = os.path.dirname(self.output_path)
            os.makedirs(output_dir, exist_ok=True)
            self.icons_dir = os.path.join(output_dir, 'icons')
            os.makedirs(self.icons_dir, exist_ok=True)
        
        # 获取原图尺寸
        image = Image.open(self.image_path)
        self.original_width, self.original_height = image.size
        print(f"原图分辨率: {self.original_width}x{self.original_height}")
    
    def preprocess_image(self):
        """预处理图像 - 保持原始尺寸"""
        try:
            # 打开图像
            image = Image.open(self.image_path)
            
            # 不再调整大小，保持原始尺寸以确保准确性
            # 原始尺寸对于正确还原页面至关重要
            
            # 转换为灰度图用于OCR
            gray_image = image.convert('L')
            
            return image, gray_image
        except Exception as e:
            print(f"图像处理失败: {e}")
            sys.exit(1)
    
    def extract_text(self, gray_image):
        """提取文本 - 优化配置以识别更多文字"""
        try:
            config = '--psm 6 -c preserve_interword_spaces=1'
            text = pytesseract.image_to_string(gray_image, lang='chi_sim+eng', config=config)
            return text
        except Exception as e:
            print(f"文本提取失败: {e}")
            return ""
    
    def extract_text_with_positions(self, image):
        """提取带位置信息的OCR文本 - 使用PaddleOCR"""
        try:
            from paddleocr import PaddleOCR
            import sys
            import os
            
            # 添加OmniParser路径以导入后处理函数
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            omniparser_path = os.path.join(base_dir, 'OmniParser')
            if omniparser_path not in sys.path:
                sys.path.insert(0, omniparser_path)
            
            # 初始化PaddleOCR（与OmniParser使用相同的配置）
            paddle_ocr = PaddleOCR(
                lang='ch',
                use_angle_cls=False,
                use_gpu=False,
                show_log=False,
                max_batch_size=1024,
                use_dilation=True,
                det_db_score_mode='slow',
                rec_batch_num=1024,
                det_db_thresh=0.1,
                det_db_box_thresh=0.3,
                drop_score=0.2,
                det_db_unclip_ratio=1.5,
                max_text_length=25,
                rec_algorithm='SVTR_LCNet',
            )
            
            # 转换图像为numpy数组
            image_np = np.array(image)
            h, w = image_np.shape[:2]
            
            # 使用PaddleOCR识别
            result = paddle_ocr.ocr(image_np, cls=False)[0]
            
            if not result:
                print("PaddleOCR未识别到文本")
                return []
            
            text_blocks = []
            for item in result:
                if item[1][1] > 0.2:  # 置信度阈值
                    coord = item[0]
                    text = item[1][0]
                    
                    # 后处理：拆分合并的文本
                    split_results = self._split_text_by_patterns(text, coord)
                    
                    for split_text, split_coord in split_results:
                        # 从四个角点计算xywh
                        x = min(split_coord[0][0], split_coord[3][0])
                        y = min(split_coord[0][1], split_coord[1][1])
                        box_w = max(split_coord[1][0], split_coord[2][0]) - x
                        box_h = max(split_coord[2][1], split_coord[3][1]) - y
                        
                        text_blocks.append({
                            'text': split_text,
                            'x': int(x),
                            'y': int(y),
                            'w': int(box_w),
                            'h': int(box_h)
                        })
            
            print(f"PaddleOCR位置提取完成: {len(text_blocks)} 个文本块")
            return text_blocks
        except Exception as e:
            print(f"PaddleOCR位置提取失败: {e}")
            import traceback
            traceback.print_exc()
            # 降级到Tesseract OCR
            return self._extract_text_with_tesseract(image)
    
    def _extract_text_with_tesseract(self, image):
        """使用Tesseract OCR作为后备方案"""
        try:
            import cv2
            img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            data = pytesseract.image_to_data(gray, lang='chi_sim+eng', output_type=pytesseract.Output.DICT)
            
            text_blocks = []
            current_block = ""
            block_x, block_y, block_w, block_h = 0, 0, 0, 0
            
            n_boxes = len(data['text'])
            for i in range(n_boxes):
                text = data['text'][i].strip()
                conf = int(data['conf'][i])
                x, y, w, h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
                
                if conf < 30 or not text:
                    if current_block:
                        text_blocks.append({
                            'text': current_block,
                            'x': block_x,
                            'y': block_y,
                            'w': block_w,
                            'h': block_h
                        })
                        current_block = ""
                    continue
                
                if current_block:
                    if abs(y - block_y) < 15:
                        current_block += text
                        block_w = (x + w) - block_x
                        block_h = max(block_h, h)
                    else:
                        text_blocks.append({
                            'text': current_block,
                            'x': block_x,
                            'y': block_y,
                            'w': block_w,
                            'h': block_h
                        })
                        current_block = text
                        block_x, block_y, block_w, block_h = x, y, w, h
                else:
                    current_block = text
                    block_x, block_y, block_w, block_h = x, y, w, h
            
            if current_block:
                text_blocks.append({
                    'text': current_block,
                    'x': block_x,
                    'y': block_y,
                    'w': block_w,
                    'h': block_h
                })
            
            print(f"Tesseract OCR位置提取完成: {len(text_blocks)} 个文本块")
            return text_blocks
        except Exception as e:
            print(f"Tesseract OCR位置提取失败: {e}")
            return []
    
    def _split_text_by_patterns(self, text, coord):
        """
        根据多种模式拆分合并的文本
        返回 [(text_part, coord_part), ...]
        """
        import re
        
        if not isinstance(coord, (list, tuple)) or len(coord) != 4:
            return [(text, coord)]
        
        # 从四个角点计算 xywh
        x = min(coord[0][0], coord[3][0])
        y = min(coord[0][1], coord[1][1])
        w = max(coord[1][0], coord[2][0]) - x
        h = max(coord[2][1], coord[3][1]) - y
        
        parts = []
        
        # 模式1：数值 + 中文标签 (如 "8.09成交量", "1.04%最低", "7.94最高")
        pattern1 = r'^([\d\.]+%?)([\u4e00-\u9fa5]+)$'
        match1 = re.match(pattern1, text)
        
        # 模式2：股票名称 + 代码 (如 "白银有色601212")
        pattern2 = r'^([\u4e00-\u9fa5]+)(\d{6,})$'
        match2 = re.match(pattern2, text)
        
        # 模式3：数值 + 单位 + 中文 (如 "6.15亿换手")
        pattern3 = r'^([\d\.]+[万亿]?)([\u4e00-\u9fa5]+)$'
        match3 = re.match(pattern3, text)
        
        # 模式4：多个数值+中文混合 (如 "8.09成交量76.92万")
        pattern4 = r'([\d\.]+%?)([\u4e00-\u9fa5]+)'
        matches4 = list(re.finditer(pattern4, text))
        
        # 模式5：中文 + 数值 + 百分号 (如 "领涨焦作万方10.02%")
        pattern5 = r'^([\u4e00-\u9fa5]+)([\d\.]+%)$'
        match5 = re.match(pattern5, text)
        
        if match1 and len(matches4) <= 2:
            # 简单的数值+中文，直接拆分
            part1, part2 = match1.groups()
            total_len = len(part1) + len(part2)
            ratio = len(part1) / total_len if total_len > 0 else 0.5
            split_x = int(x + w * ratio)
            
            parts.append((part1, [[x, y], [split_x, y], [split_x, y+h], [x, y+h]]))
            parts.append((part2, [[split_x, y], [x+w, y], [x+w, y+h], [split_x, y+h]]))
            
        elif match2:
            # 股票名称+代码
            part1, part2 = match2.groups()
            total_len = len(part1) + len(part2)
            ratio = len(part1) / total_len if total_len > 0 else 0.5
            split_x = int(x + w * ratio)
            
            parts.append((part1, [[x, y], [split_x, y], [split_x, y+h], [x, y+h]]))
            parts.append((part2, [[split_x, y], [x+w, y], [x+w, y+h], [split_x, y+h]]))
            
        elif match5:
            # 中文+百分比
            part1, part2 = match5.groups()
            total_len = len(part1) + len(part2)
            ratio = len(part1) / total_len if total_len > 0 else 0.5
            split_x = int(x + w * ratio)
            
            parts.append((part1, [[x, y], [split_x, y], [split_x, y+h], [x, y+h]]))
            parts.append((part2, [[split_x, y], [x+w, y], [x+w, y+h], [split_x, y+h]]))
            
        elif len(matches4) >= 2:
            # 多个数值+中文混合，按每个匹配拆分
            total_text_len = len(text)
            for i, match in enumerate(matches4):
                match_text = match.group(0)
                num_part = match.group(1)
                chn_part = match.group(2)
                
                # 计算相对位置
                start_ratio = match.start() / total_text_len
                end_ratio = match.end() / total_text_len
                
                part_x = int(x + w * start_ratio)
                part_w = int(w * (end_ratio - start_ratio))
                
                parts.append((num_part, [[part_x, y], [part_x + part_w//2, y], [part_x + part_w//2, y+h], [part_x, y+h]]))
                parts.append((chn_part, [[part_x + part_w//2, y], [part_x + part_w, y], [part_x + part_w, y+h], [part_x + part_w//2, y+h]]))
        else:
            # 无法拆分，保留原样
            parts.append((text, coord))
        
        return parts
    
    def extract_colors(self, image, n_colors=5):
        """使用K-means聚类提取主要颜色"""
        try:
            # 将图像转换为扁平化的像素数组
            pixels = np.array(image).reshape(-1, 3)
            
            # 使用K-means聚类
            from sklearn.cluster import KMeans
            kmeans = KMeans(n_clusters=n_colors, random_state=42)
            kmeans.fit(pixels)
            
            # 获取聚类中心（主要颜色）
            colors = kmeans.cluster_centers_.astype(int)
            
            # 转换为十六进制颜色代码
            hex_colors = ['#%02x%02x%02x' % (r, g, b) for r, g, b in colors]
            
            return hex_colors
        except Exception as e:
            print(f"颜色提取失败: {e}")
            return ['#FFFFFF', '#000000', '#4CAF50', '#2196F3', '#FF9800']
    
    def _ensure_omniparser_model(self):
        """确保OmniParser V2模型文件存在且完整，如果不存在则下载"""
        import os
        import subprocess
        
        # 设置OmniParser V2模型路径（相对于scripts目录）
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        weights_dir = os.path.join(base_dir, 'OmniParser', 'weights')
        
        # 检查必要的文件是否存在
        required_files = {
            'icon_detect': ['train_args.yaml', 'model.pt', 'model.yaml'],
            'icon_caption_florence': ['config.json', 'generation_config.json', 'model.safetensors']
        }
        
        all_exist = True
        for folder, files in required_files.items():
            folder_path = os.path.join(weights_dir, folder)
            for file in files:
                file_path = os.path.join(folder_path, file)
                if not os.path.exists(file_path):
                    all_exist = False
                    print(f"缺少模型文件: {file_path}")
                    break
            if not all_exist:
                break
        
        if all_exist:
            print(f"✅ OmniParser V2模型已存在: {weights_dir}")
            return weights_dir
        
        # 需要下载模型
        print("📥 需要下载OmniParser V2模型...")
        print("请手动下载模型到 OmniParser/weights 目录:")
        print("1. 克隆仓库: git clone https://github.com/microsoft/OmniParser.git")
        print("2. 下载模型权重:")
        print("   cd OmniParser")
        print("   for f in icon_detect/{train_args.yaml,model.pt,model.yaml} icon_caption/{config.json,generation_config.json,model.safetensors}; do huggingface-cli download microsoft/OmniParser-v2.0 \"$f\" --local-dir weights; done")
        print("   mv weights/icon_caption weights/icon_caption_florence")
        print("3. 或使用 ModelScope:")
        print("   cd OmniParser/weights")
        print("   git clone https://www.modelscope.cn/models/microsoft/OmniParser-v2.0.git")
        return None
    
    def _detect_elements_fallback(self, image_path):
        """当YOLO不可用时使用的备用检测方法"""
        try:
            from PIL import Image
            
            image = Image.open(image_path)
            width, height = image.size
            print(f"使用备用方法检测元素，原图尺寸: {width}x{height}")
            
            elements = []
            
            # 1. 检测文本区域
            text_elements = self.detect_text_areas(image)
            elements.extend(text_elements)
            
            # 2. 检测UI元素
            ui_elements = self.detect_ui_elements(image)
            elements.extend(ui_elements)
            
            # 3. 检测小图标
            icon_elements = self.detect_icons(image)
            elements.extend(icon_elements)
            
            # 去重
            elements = self.filter_elements(elements)
            
            print(f"备用方法检测到 {len(elements)} 个元素")
            return elements
            
        except Exception as e:
            print(f"备用检测失败: {e}")
            return []
    
    def detect_elements(self, image_path):
        """使用OmniParser V2识别UI元素"""
        print("\n" + "="*60)
        print("元素检测 - OmniParser V2")
        print("="*60)
        
        try:
            from PIL import Image
            import numpy as np
            import os
            
            # 检查OmniParser V2模型是否存在
            print("🔍 检查OmniParser V2模型...")
            weights_dir = self._ensure_omniparser_model()
            if not weights_dir:
                print("❌ OmniParser V2模型不可用")
                print("🔄 切换到备用检测方法 (OpenCV)")
                print("="*60)
                return self._detect_elements_fallback(image_path)
            
            print("✅ OmniParser V2模型已找到")
            
            # 打开图像
            image = Image.open(image_path)
            width, height = image.size
            print(f"📐 原图尺寸: {width}x{height}")
            
            # 使用OmniParser V2进行元素检测
            print("🚀 启动OmniParser V2检测...")
            elements = self._detect_with_omniparser(image_path)
            
            # 去重和过滤
            elements = self.filter_elements(elements)
            
            if len(elements) == 0:
                print("⚠️ OmniParser V2检测到 0 个元素，可能检测失败")
                print("🔄 切换到备用检测方法 (OpenCV)")
                print("="*60)
                return self._detect_elements_fallback(image_path)
            else:
                print(f"✅ OmniParser V2检测完成，共 {len(elements)} 个元素")
                print("="*60)
                return elements
            
        except Exception as e:
            print(f"❌ OmniParser V2检测失败: {e}")
            print("🔄 切换到备用检测方法 (OpenCV)")
            print("="*60)
            import traceback
            traceback.print_exc()
            return self._detect_elements_fallback(image_path)
    
    def _detect_with_omniparser(self, image_path):
        """使用OmniParser V2检测UI元素"""
        elements = []
        
        try:
            import torch
            from PIL import Image
            import numpy as np
            
            # 设置OmniParser V2模型路径
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            weights_dir = os.path.join(base_dir, 'OmniParser', 'weights')
            
            # 导入OmniParser V2工具函数
            try:
                import sys
                omniparser_path = os.path.join(base_dir, 'OmniParser')
                if omniparser_path not in sys.path:
                    sys.path.insert(0, omniparser_path)
                
                from util.utils import check_ocr_box, get_yolo_model, get_caption_model_processor, get_som_labeled_img
            except ImportError as e:
                print(f"⚠️ 无法导入OmniParser V2工具函数: {e}")
                print("请确保OmniParser仓库已克隆到正确位置")
                return elements
            
            # 设置设备（CPU优先）
            device = 'cpu'
            print(f"🔄 使用设备: {device}")
            
            # 初始化OmniParser V2模型（懒加载，只在首次调用时初始化）
            if not hasattr(self, '_omniparser_models'):
                print("🔄 初始化OmniParser V2模型...")
                self._omniparser_models = {}
                
                # 加载YOLOv8图标检测模型
                som_model_path = os.path.join(weights_dir, 'icon_detect', 'model.pt')
                if os.path.exists(som_model_path):
                    som_model = get_yolo_model(model_path=som_model_path)
                    som_model.to(device)
                    self._omniparser_models['som_model'] = som_model
                    print(f"✅ 加载图标检测模型: {som_model_path}")
                else:
                    print(f"⚠️ 图标检测模型不存在: {som_model_path}")
                
                # 加载Florence2图标描述模型
                caption_model_path = os.path.join(weights_dir, 'icon_caption_florence')
                if os.path.exists(caption_model_path):
                    caption_model_processor = get_caption_model_processor(
                        model_name="florence2",
                        model_name_or_path=caption_model_path,
                        device=device
                    )
                    self._omniparser_models['caption_model_processor'] = caption_model_processor
                    print(f"✅ 加载图标描述模型: {caption_model_path}")
                else:
                    print(f"⚠️ 图标描述模型不存在: {caption_model_path}")
                
                print("✅ OmniParser V2模型初始化完成")
            
            # 检查模型是否加载成功
            if 'som_model' not in self._omniparser_models:
                print("❌ 图标检测模型未加载，无法进行元素检测")
                return elements
            
            # 读取图像
            image = Image.open(image_path)
            width, height = image.size
            
            # 配置边界框绘制参数
            box_overlay_ratio = max(image.size) / 3200
            draw_bbox_config = {
                'text_scale': 0.8 * box_overlay_ratio,
                'text_thickness': max(int(2 * box_overlay_ratio), 1),
                'text_padding': max(int(3 * box_overlay_ratio), 1),
                'thickness': max(int(3 * box_overlay_ratio), 1),
            }
            
            # OCR配置（使用PaddleOCR提升中文识别）
            print("🔄 执行OCR文本检测...")
            try:
                ocr_bbox_rslt, is_goal_filtered = check_ocr_box(
                    image_path,
                    display_img=False,
                    output_bb_format='xyxy',
                    goal_filtering=None,
                    easyocr_args={'paragraph': False, 'text_threshold': 0.9},
                    use_paddleocr=True
                )
                text, ocr_bbox = ocr_bbox_rslt
                print(f"✅ OCR检测完成，发现 {len(ocr_bbox)} 个文本区域")
            except Exception as e:
                print(f"⚠️ OCR检测失败: {e}")
                text = ""
                ocr_bbox = []
            
            # 执行OmniParser V2元素检测
            print("🔄 执行OmniParser V2图标检测...")
            BOX_TRESHOLD = 0.05  # 检测阈值
            
            try:
                dino_labled_img, label_coordinates, parsed_content_list = get_som_labeled_img(
                    image_path,
                    self._omniparser_models['som_model'],
                    BOX_TRESHOLD=BOX_TRESHOLD,
                    output_coord_in_ratio=False,
                    ocr_bbox=ocr_bbox,
                    draw_bbox_config=draw_bbox_config,
                    caption_model_processor=self._omniparser_models.get('caption_model_processor'),
                    ocr_text=text,
                    use_local_semantics=True,
                    iou_threshold=0.1,
                    batch_size=64  # CPU环境下减小批大小
                )
                print(f"✅ OmniParser V2检测完成，发现 {len(parsed_content_list)} 个元素")
            except Exception as e:
                print(f"⚠️ OmniParser V2检测失败: {e}")
                import traceback
                traceback.print_exc()
                parsed_content_list = []
            
            # 解析OmniParser V2结果，转换为统一的元素格式
            print("🔄 解析OmniParser V2结果...")
            
            for i, content in enumerate(parsed_content_list):
                try:
                    # 确保content是字符串
                    if isinstance(content, dict):
                        # 如果content是字典，尝试提取文本
                        content = str(content.get('content', content.get('text', str(content))))
                    
                    # 解析content字符串，格式如："Text Box ID 0: Task Manager" 或 "Icon ID 5: Google Chrome浏览器图标"
                    if ':' in content:
                        prefix, description = content.split(':', 1)
                        prefix = prefix.strip()
                        description = description.strip()
                    else:
                        prefix = content.strip() if isinstance(content, str) else str(content)
                        description = ""
                    
                    # 判断元素类型
                    elem_type = "unknown"
                    if "Text Box" in prefix or "text" in prefix.lower():
                        elem_type = "text"
                    elif "Icon" in prefix:
                        elem_type = "icon"
                    elif "button" in prefix.lower() or "按钮" in description:
                        elem_type = "button"
                    elif "input" in prefix.lower() or "输入" in description:
                        elem_type = "input"
                    else:
                        elem_type = "ui_element"
                    
                    # 尝试从label_coordinates获取坐标
                    bbox = None
                    if 'label_coordinates' in dir() and i in label_coordinates:
                        coords = label_coordinates[i]
                        if isinstance(coords, (list, tuple)) and len(coords) >= 4:
                            bbox = [float(coords[0]), float(coords[1]), float(coords[2]), float(coords[3])]
                    
                    # 如果无法获取坐标，使用占位符
                    if bbox is None:
                        # 根据元素索引估算位置（这只是占位符）
                        bbox = [50, 50 + i * 60, 200, 100 + i * 60]
                    
                    # 添加到元素列表
                    elements.append({
                        'type': elem_type,
                        'bbox': bbox,
                        'confidence': 0.85,  # OmniParser V2默认置信度
                        'description': description,
                        'raw_content': content
                    })
                    
                except Exception as e:
                    print(f"  解析元素 {i} 失败: {e}")
                    continue
            
            print(f"✅ 成功解析 {len(elements)} 个OmniParser V2元素")
            
            # 保存OmniParser V2原始输出用于调试
            self._save_omniparser_debug_output(image_path, elements, parsed_content_list, ocr_bbox, text)
            
        except Exception as e:
            print(f"⚠️ OmniParser V2处理失败: {e}")
            import traceback
            traceback.print_exc()
        
        return elements
    
    def _save_omniparser_debug_output(self, image_path, elements, parsed_content_list, ocr_bbox, ocr_text):
        """保存OmniParser V2的调试输出"""
        try:
            import json
            import os
            from datetime import datetime
            
            # 生成输出文件名
            base_name = os.path.splitext(os.path.basename(image_path))[0]
            output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
            os.makedirs(output_dir, exist_ok=True)
            
            debug_data = {
                'timestamp': datetime.now().isoformat(),
                'image_path': image_path,
                'total_elements': len(elements),
                'elements': elements,
                'parsed_content_list': parsed_content_list if isinstance(parsed_content_list, list) else list(parsed_content_list) if parsed_content_list is not None else [],
                'ocr_bbox_count': len(ocr_bbox) if ocr_bbox else 0,
                'ocr_bbox': ocr_bbox.tolist() if hasattr(ocr_bbox, 'tolist') else ocr_bbox if ocr_bbox else [],
                'ocr_text_count': len(ocr_text) if ocr_text else 0,
                'ocr_text': ocr_text if isinstance(ocr_text, list) else list(ocr_text) if ocr_text is not None else []
            }
            
            debug_file = os.path.join(output_dir, f'{base_name}_omniparser_debug.json')
            with open(debug_file, 'w', encoding='utf-8') as f:
                json.dump(debug_data, f, ensure_ascii=False, indent=2)
            
            print(f"💾 OmniParser V2调试数据已保存: {debug_file}")
            
            # 同时保存一个可读的文本版本
            text_file = os.path.join(output_dir, f'{base_name}_omniparser_elements.txt')
            with open(text_file, 'w', encoding='utf-8') as f:
                f.write(f"OmniParser V2 检测结果\n")
                f.write(f"{'='*60}\n")
                f.write(f"图像: {image_path}\n")
                f.write(f"时间: {datetime.now().isoformat()}\n")
                f.write(f"总元素数: {len(elements)}\n")
                f.write(f"OCR文本区域: {len(ocr_bbox) if ocr_bbox else 0}\n")
                f.write(f"{'='*60}\n\n")
                
                f.write(f"【OCR文本内容】\n")
                if ocr_text:
                    for i, txt in enumerate(ocr_text[:20]):  # 只显示前20个
                        f.write(f"  {i}: {txt}\n")
                f.write(f"\n{'='*60}\n\n")
                
                f.write(f"【检测到的元素】\n")
                for i, elem in enumerate(elements):
                    f.write(f"\n元素 {i}:\n")
                    f.write(f"  类型: {elem.get('type', 'unknown')}\n")
                    f.write(f"  位置: {elem.get('bbox', [])}\n")
                    f.write(f"  置信度: {elem.get('confidence', 0)}\n")
                    f.write(f"  描述: {elem.get('description', 'N/A')}\n")
                    f.write(f"  原始内容: {elem.get('raw_content', 'N/A')}\n")
            
            print(f"💾 元素列表已保存: {text_file}")
            
        except Exception as e:
            print(f"⚠️ 保存调试数据失败: {e}")
    
    def detect_with_yolo(self, model, image, width, height):
        """使用YOLOv5检测通用对象"""
        elements = []
        
        # 对于长图像，使用不同的策略
        if height > 1000:
            # 计算需要分割的块数
            block_height = 800
            num_blocks = (height + block_height - 1) // block_height
            
            for i in range(num_blocks):
                # 计算当前块的位置
                start_y = i * block_height
                end_y = min((i + 1) * block_height, height)
                
                # 提取当前块
                block = image.crop((0, start_y, width, end_y))
                
                # RGBA图像需要转换为RGB才能保存为JPG
                if block.mode == 'RGBA':
                    block = block.convert('RGB')
                
                # 保存临时块图像
                temp_block_path = f"/tmp/temp_block_{i}.jpg"
                block.save(temp_block_path)
                
                # 执行检测
                results = model(temp_block_path, verbose=False)
                
                # 处理检测结果
                for result in results:
                    for box in result.boxes:
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        confidence = box.conf[0].item()
                        class_id = box.cls[0].item()
                        class_name = model.names[class_id]
                        
                        # 只保留高置信度的检测结果
                        if confidence > 0.5:
                            # 调整坐标到原始图像
                            adjusted_y1 = y1 + start_y
                            adjusted_y2 = y2 + start_y
                            elements.append({
                                'type': class_name,
                                'bbox': [x1, adjusted_y1, x2, adjusted_y2],
                                'confidence': confidence
                            })
                
                # 清理临时文件
                if os.path.exists(temp_block_path):
                    os.remove(temp_block_path)
        else:
            # 对于普通尺寸的图像，直接检测
            results = model(image, verbose=False)
            
            # 处理检测结果
            for result in results:
                for box in result.boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    confidence = box.conf[0].item()
                    class_id = box.cls[0].item()
                    class_name = model.names[class_id]
                    
                    # 只保留高置信度的检测结果
                    if confidence > 0.5:
                        elements.append({
                            'type': class_name,
                            'bbox': [x1, y1, x2, y2],
                            'confidence': confidence
                        })
        
        return elements
    
    def detect_text_areas(self, image):
        """检测文本区域"""
        try:
            import cv2
            import numpy as np
            
            # 转换为OpenCV格式
            img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # 使用自适应阈值
            thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2)
            
            # 查找轮廓
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # 过滤文本区域
            text_areas = []
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                
                # 过滤掉太小或太大的区域
                if 50 < w < 1000 and 10 < h < 100:
                    # 计算宽高比，文本通常是水平的
                    aspect_ratio = w / h
                    if aspect_ratio > 1.5:
                        text_areas.append({
                            'type': 'text',
                            'bbox': [x, y, x + w, y + h],
                            'confidence': 0.8
                        })
            
            return text_areas
        except Exception as e:
            print(f"文本区域检测失败: {e}")
            return []
    
    def detect_ui_elements(self, image):
        """检测UI元素（按钮、输入框等）"""
        try:
            import cv2
            import numpy as np
            
            # 转换为OpenCV格式
            img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # 边缘检测
            edges = cv2.Canny(gray, 50, 150)
            
            # 查找轮廓
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # 过滤UI元素
            ui_elements = []
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                
                # 降低过滤条件，允许更小的元素
                if 10 < w < 500 and 10 < h < 200:
                    # 计算面积和周长，用于识别按钮等元素
                    area = cv2.contourArea(contour)
                    perimeter = cv2.arcLength(contour, True)
                    
                    # 计算形状因子
                    if perimeter > 0:
                        circularity = 4 * np.pi * area / (perimeter ** 2)
                        
                        # 圆形或矩形元素可能是按钮
                        if 0.5 < circularity < 1.5:
                            ui_elements.append({
                                'type': 'button',
                                'bbox': [x, y, x + w, y + h],
                                'confidence': 0.7
                            })
                        else:
                            # 矩形元素可能是输入框或其他UI元素
                            ui_elements.append({
                                'type': 'ui_element',
                                'bbox': [x, y, x + w, y + h],
                                'confidence': 0.6
                            })
            
            return ui_elements
        except Exception as e:
            print(f"UI元素检测失败: {e}")
            return []
    
    def detect_icons(self, image):
        """检测小图标（包括箭头、展开/收起图标等）"""
        try:
            import cv2
            import numpy as np
            
            # 转换为OpenCV格式
            img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # 使用多种方法检测小图标
            icon_elements = []
            
            # 方法1：使用自适应阈值检测小图标
            thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2)
            
            # 查找轮廓
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # 过滤小图标
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                area = cv2.contourArea(contour)
                
                # 小图标通常是小的，面积在50-2000之间
                if 50 < area < 2000 and 5 < w < 100 and 5 < h < 100:
                    # 分析形状，判断是否是箭头
                    arrow_type = self.classify_arrow_shape(contour, x, y, w, h)
                    
                    if arrow_type:
                        icon_elements.append({
                            'type': f'arrow_{arrow_type}',
                            'bbox': [x, y, x + w, y + h],
                            'confidence': 0.8
                        })
                    else:
                        # 其他小图标
                        icon_elements.append({
                            'type': 'icon',
                            'bbox': [x, y, x + w, y + h],
                            'confidence': 0.7
                        })
            
            # 方法2：使用边缘检测检测小图标
            edges = cv2.Canny(gray, 100, 200)
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                area = cv2.contourArea(contour)
                
                # 小图标
                if 50 < area < 2000 and 5 < w < 100 and 5 < h < 100:
                    # 检查是否已经检测到
                    already_detected = False
                    for existing in icon_elements:
                        iou = self.calculate_iou([x, y, x + w, y + h], existing['bbox'])
                        if iou > 0.3:
                            already_detected = True
                            break
                    
                    if not already_detected:
                        # 分析形状
                        arrow_type = self.classify_arrow_shape(contour, x, y, w, h)
                        
                        if arrow_type:
                            icon_elements.append({
                                'type': f'arrow_{arrow_type}',
                                'bbox': [x, y, x + w, y + h],
                                'confidence': 0.8
                            })
                        else:
                            icon_elements.append({
                                'type': 'icon',
                                'bbox': [x, y, x + w, y + h],
                                'confidence': 0.7
                            })
            
            return icon_elements
        except Exception as e:
            print(f"图标检测失败: {e}")
            return []
    
    def classify_arrow_shape(self, contour, x, y, w, h):
        """分类箭头形状"""
        try:
            import cv2
            import numpy as np
            
            # 计算矩
            M = cv2.moments(contour)
            if M['m00'] == 0:
                return None
            
            # 计算质心
            cx = int(M['m10'] / M['m00'])
            cy = int(M['m01'] / M['m00'])
            
            # 计算边界框的中心
            bbox_center_x = x + w // 2
            bbox_center_y = y + h // 2
            
            # 根据质心相对于边界框中心的位置判断箭头方向
            dx = cx - bbox_center_x
            dy = cy - bbox_center_y
            
            # 判断箭头方向
            if abs(dx) > abs(dy):
                # 水平箭头
                if dx > 0:
                    return 'right'
                else:
                    return 'left'
            else:
                # 垂直箭头
                if dy > 0:
                    return 'down'
                else:
                    return 'up'
        except Exception as e:
            return None
    
    def filter_elements(self, elements):
        """去重和过滤元素"""
        if not elements:
            return []
        
        # 按置信度排序
        elements.sort(key=lambda x: x['confidence'], reverse=True)
        
        # 去重
        filtered_elements = []
        for element in elements:
            # 检查是否与已添加的元素重叠
            overlap = False
            for existing in filtered_elements:
                # 计算重叠率
                iou = self.calculate_iou(element['bbox'], existing['bbox'])
                if iou > 0.5:
                    overlap = True
                    break
            
            if not overlap:
                filtered_elements.append(element)
        
        return filtered_elements
    
    def calculate_iou(self, bbox1, bbox2):
        """计算两个边界框的IoU"""
        x1 = max(bbox1[0], bbox2[0])
        y1 = max(bbox1[1], bbox2[1])
        x2 = min(bbox1[2], bbox2[2])
        y2 = min(bbox1[3], bbox2[3])
        
        # 计算交集面积
        intersection = max(0, x2 - x1) * max(0, y2 - y1)
        
        # 计算两个边界框的面积
        area1 = (bbox1[2] - bbox1[0]) * (bbox1[3] - bbox1[1])
        area2 = (bbox2[2] - bbox2[0]) * (bbox2[3] - bbox2[1])
        
        # 计算并集面积
        union = area1 + area2 - intersection
        
        # 计算IoU
        if union > 0:
            return intersection / union
        else:
            return 0
    
    def extract_icons(self, image_path):
        """从原图中提取图标并记录位置"""
        try:
            from PIL import Image
            import cv2
            
            # 打开图像
            image = Image.open(image_path)
            img_array = np.array(image)
            
            # 转换为灰度图
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            
            # 使用Canny边缘检测
            edges = cv2.Canny(gray, 50, 150)
            
            # 查找轮廓
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            icons = []
            icon_count = 0
            
            # 遍历轮廓
            for contour in contours:
                # 计算轮廓面积
                area = cv2.contourArea(contour)
                
                # 过滤掉太小或太大的轮廓
                if 500 < area < 10000:
                    # 计算边界框
                    x, y, w, h = cv2.boundingRect(contour)
                    
                    # 确保边界框在图像范围内
                    if x > 0 and y > 0 and x + w < img_array.shape[1] and y + h < img_array.shape[0]:
                        # 提取图标
                        icon = image.crop((x, y, x + w, y + h))
                        
                        # 保存图标
                        icon_path = os.path.join(self.icons_dir, f"icon_{icon_count}.png")
                        icon.save(icon_path)
                        
                        # 保存图标的相对路径和位置信息
                        relative_icon_path = f"icons/icon_{icon_count}.png"
                        icons.append({
                            'id': icon_count,
                            'path': relative_icon_path,
                            'bbox': [x, y, w, h],
                            'area': area,
                            'center': [x + w/2, y + h/2],
                            'position': {
                                'top': y,
                                'bottom': y + h,
                                'left': x,
                                'right': x + w,
                                'width': w,
                                'height': h
                            }
                        })
                        
                        icon_count += 1
            
            # 按照位置排序图标（从上到下，从左到右）
            icons.sort(key=lambda icon: (icon['position']['top'], icon['position']['left']))
            
            print(f"提取到 {len(icons)} 个图标")
            return icons
        except Exception as e:
            print(f"图标提取失败: {e}")
            return []
    
    def analyze_layout(self, image):
        """分析页面布局"""
        try:
            # 转换为OpenCV格式
            img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # 边缘检测
            edges = cv2.Canny(gray, 100, 200)
            
            # 查找轮廓
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # 过滤掉小轮廓
            large_contours = [c for c in contours if cv2.contourArea(c) > 1000]
            
            # 检测水平线和垂直线
            horizontal_lines = self.detect_horizontal_lines(gray)
            vertical_lines = self.detect_vertical_lines(gray)
            
            # 分析布局结构
            layout = {
                "total_contours": len(large_contours),
                "contours": [],
                "horizontal_lines": horizontal_lines,
                "vertical_lines": vertical_lines,
                "grid": self.analyze_grid(horizontal_lines, vertical_lines),
                "elements": []
            }
            
            # 分析每个轮廓的位置和关系
            for i, contour in enumerate(large_contours):
                x, y, w, h = cv2.boundingRect(contour)
                
                # 分析元素的对齐方式
                alignment = self.analyze_alignment(x, y, w, h, horizontal_lines, vertical_lines)
                
                layout["contours"].append({
                    "id": i,
                    "x": x,
                    "y": y,
                    "width": w,
                    "height": h,
                    "alignment": alignment
                })
            
            # 分析元素之间的关系
            layout["elements"] = self.analyze_element_relationships(layout["contours"])
            
            return layout
        except Exception as e:
            print(f"布局分析失败: {e}")
            return {"total_contours": 0, "contours": [], "horizontal_lines": [], "vertical_lines": [], "grid": [], "elements": []}
    
    def detect_horizontal_lines(self, gray):
        """检测水平线"""
        # 使用形态学操作检测水平线
        horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (50, 1))
        detected_lines = cv2.morphologyEx(gray, cv2.MORPH_OPEN, horizontal_kernel, iterations=2)
        
        # 查找轮廓
        contours, _ = cv2.findContours(detected_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # 提取水平线的y坐标
        lines = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if w > 100 and h < 10:
                lines.append(y)
        
        # 去重并排序
        lines = sorted(list(set(lines)))
        return lines
    
    def detect_vertical_lines(self, gray):
        """检测垂直线"""
        # 使用形态学操作检测垂直线
        vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 50))
        detected_lines = cv2.morphologyEx(gray, cv2.MORPH_OPEN, vertical_kernel, iterations=2)
        
        # 查找轮廓
        contours, _ = cv2.findContours(detected_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # 提取垂直线的x坐标
        lines = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if h > 100 and w < 10:
                lines.append(x)
        
        # 去重并排序
        lines = sorted(list(set(lines)))
        return lines
    
    def analyze_grid(self, horizontal_lines, vertical_lines):
        """分析网格布局"""
        grid = {
            "rows": len(horizontal_lines),
            "cols": len(vertical_lines),
            "cells": []
        }
        
        # 生成网格单元格
        for i in range(len(horizontal_lines) - 1):
            for j in range(len(vertical_lines) - 1):
                grid["cells"].append({
                    "row": i,
                    "col": j,
                    "top": horizontal_lines[i],
                    "bottom": horizontal_lines[i + 1],
                    "left": vertical_lines[j],
                    "right": vertical_lines[j + 1]
                })
        
        return grid
    
    def analyze_alignment(self, x, y, w, h, horizontal_lines, vertical_lines):
        """分析元素的对齐方式"""
        alignment = {
            "horizontal": "left",
            "vertical": "top",
            "center_x": x + w / 2,
            "center_y": y + h / 2
        }
        
        # 分析水平对齐
        for line in vertical_lines:
            if abs((x + w / 2) - line) < 10:
                alignment["horizontal"] = "center"
                break
            elif abs((x + w) - line) < 10:
                alignment["horizontal"] = "right"
                break
        
        # 分析垂直对齐
        for line in horizontal_lines:
            if abs((y + h / 2) - line) < 10:
                alignment["vertical"] = "center"
                break
            elif abs((y + h) - line) < 10:
                alignment["vertical"] = "bottom"
                break
        
        return alignment
    
    def analyze_element_relationships(self, contours):
        """分析元素之间的关系"""
        elements = []
        
        for i, contour in enumerate(contours):
            element = {
                "id": contour["id"],
                "x": contour["x"],
                "y": contour["y"],
                "width": contour["width"],
                "height": contour["height"],
                "alignment": contour["alignment"],
                "relationships": []
            }
            
            # 分析与其他元素的关系
            for j, other_contour in enumerate(contours):
                if i != j:
                    # 检查是否是相邻元素
                    if abs(contour["y"] - other_contour["y"]) < 10 and abs((contour["x"] + contour["width"]) - other_contour["x"]) < 10:
                        element["relationships"].append({
                            "type": "right_of",
                            "target_id": other_contour["id"]
                        })
                    elif abs(contour["x"] - other_contour["x"]) < 10 and abs((contour["y"] + contour["height"]) - other_contour["y"]) < 10:
                        element["relationships"].append({
                            "type": "below",
                            "target_id": other_contour["id"]
                        })
            
            elements.append(element)
        
        return elements
    
    def build_structured_layout(self, image, elements, text_blocks):
        """构建结构化布局信息：将页面分段，每段关联元素和文本"""
        try:
            img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            img_h, img_w = gray.shape[:2]
            
            if self.original_width >= 1000:
                dpr = 3
            elif self.original_width >= 700:
                dpr = 2
            else:
                dpr = 1
            
            logical_h = img_h // dpr
            
            split_points = self._find_section_boundaries(gray, text_blocks, elements, dpr)
            
            sections = []
            for i in range(len(split_points) - 1):
                top_px = split_points[i]
                bottom_px = split_points[i + 1]
                section_height = bottom_px - top_px
                if section_height < 15:
                    continue
                
                logical_top = top_px // dpr
                logical_bottom = bottom_px // dpr
                logical_height = section_height // dpr
                
                section_elements = []
                for elem in elements:
                    x1, y1, x2, y2 = elem['bbox']
                    elem_center_y = (y1 + y2) / 2
                    if top_px <= elem_center_y < bottom_px:
                        section_elements.append({
                            'type': elem['type'],
                            'x': round(x1 / dpr),
                            'y': round(y1 / dpr),
                            'w': round((x2 - x1) / dpr),
                            'h': round((y2 - y1) / dpr),
                            'confidence': round(elem['confidence'], 2)
                        })
                
                section_texts = []
                for tb in text_blocks:
                    tb_center_y = tb['y'] + tb['h'] / 2
                    if top_px <= tb_center_y < bottom_px:
                        section_texts.append({
                            'text': tb['text'],
                            'x': round(tb['x'] / dpr),
                            'y': round(tb['y'] / dpr),
                            'w': round(tb['w'] / dpr),
                            'h': round(tb['h'] / dpr)
                        })
                
                bg_region = gray[top_px:bottom_px, 0:img_w]
                if bg_region.size > 0:
                    mean_val = int(np.mean(bg_region))
                    bg_color = f"#{mean_val:02x}{mean_val:02x}{mean_val:02x}"
                else:
                    bg_color = "#ffffff"
                
                section_type = "content"
                logical_top_val = top_px // dpr
                if logical_top_val < 24:
                    section_type = "status_bar"
                elif logical_top_val < 68:
                    section_type = "nav_bar"
                elif logical_top_val > (logical_h - 50):
                    section_type = "bottom_bar"
                
                section = {
                    'index': len(sections),
                    'type': section_type,
                    'y_start': logical_top,
                    'y_end': logical_bottom,
                    'height': logical_height,
                    'bg_color': bg_color,
                    'elements': section_elements,
                    'texts': section_texts,
                    'element_count': len(section_elements),
                    'text_count': len(section_texts)
                }
                sections.append(section)
            
            horizontal_lines = self.detect_horizontal_lines(gray)
            vertical_lines = self.detect_vertical_lines(gray)
            
            result = {
                'page_width': self.original_width // dpr,
                'page_height': logical_h,
                'dpr': dpr,
                'horizontal_lines': [l // dpr for l in horizontal_lines],
                'vertical_lines': [l // dpr for l in vertical_lines],
                'sections': sections,
                'total_sections': len(sections),
                'total_elements': len(elements),
                'total_text_blocks': len(text_blocks)
            }
            
            print(f"结构化布局分析完成: {len(sections)} 个区域, {len(elements)} 个元素, {len(text_blocks)} 个文本块")
            return result
        except Exception as e:
            print(f"结构化布局分析失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _find_section_boundaries(self, gray, text_blocks, elements, dpr):
        """智能寻找区域边界：结合背景色变化、文本间隙、元素分布"""
        img_h, img_w = gray.shape[:2]
        
        candidates = set()
        candidates.add(0)
        candidates.add(img_h)
        
        row_means = []
        for y in range(img_h):
            row_mean = int(np.mean(gray[y, :]))
            row_means.append(row_mean)
        
        window = max(5, img_h // 200)
        smoothed = []
        for i in range(len(row_means)):
            start = max(0, i - window)
            end = min(len(row_means), i + window + 1)
            smoothed.append(int(np.mean(row_means[start:end])))
        
        color_change_threshold = 25
        for i in range(1, len(smoothed)):
            if abs(smoothed[i] - smoothed[i - 1]) > color_change_threshold:
                candidates.add(i)
                candidates.add(max(0, i - 3))
                candidates.add(min(img_h - 1, i + 3))
        
        if text_blocks:
            sorted_texts = sorted(text_blocks, key=lambda t: t['y'])
            for i in range(len(sorted_texts) - 1):
                curr_bottom = sorted_texts[i]['y'] + sorted_texts[i]['h']
                next_top = sorted_texts[i + 1]['y']
                gap = next_top - curr_bottom
                if gap > 20:
                    mid_y = (curr_bottom + next_top) // 2
                    candidates.add(mid_y)
        
        if elements:
            elem_tops = []
            for elem in elements:
                x1, y1, x2, y2 = elem['bbox']
                elem_tops.append(y1)
            elem_tops.sort()
            
            for i in range(1, len(elem_tops)):
                gap = elem_tops[i] - elem_tops[i - 1]
                if gap > 60:
                    candidates.add(elem_tops[i] - 10)
        
        min_section_height = 30
        sorted_candidates = sorted(candidates)
        filtered = [sorted_candidates[0]]
        for pt in sorted_candidates[1:]:
            if pt - filtered[-1] >= min_section_height:
                filtered.append(pt)
        
        if len(filtered) < 3:
            filtered = [0]
            num_auto = max(3, img_h // (200 * dpr))
            step = img_h // num_auto
            for i in range(1, num_auto):
                filtered.append(i * step)
            filtered.append(img_h)
        
        return filtered
    
    def format_structured_layout(self, structured_layout):
        """将结构化布局格式化为LLM可读的文本"""
        if not structured_layout:
            return "布局分析失败，请主要依据截图视觉理解来还原页面。"
        
        lines = []
        lines.append(f"页面尺寸: {structured_layout['page_width']}x{structured_layout['page_height']}px (逻辑像素)")
        lines.append(f"设备像素比: {structured_layout['dpr']}x")
        lines.append(f"水平分割线(y坐标): {structured_layout['horizontal_lines']}")
        lines.append(f"垂直分割线(x坐标): {structured_layout['vertical_lines']}")
        lines.append(f"共 {structured_layout['total_sections']} 个布局区域")
        lines.append("")
        lines.append("=" * 60)
        lines.append("【页面布局详情（从上到下）】")
        lines.append("=" * 60)
        
        for section in structured_layout['sections']:
            lines.append("")
            lines.append(f"--- 区域 {section['index']} [{section['type']}] ---")
            lines.append(f"  位置: y={section['y_start']}~{section['y_end']}, 高度={section['height']}px, 背景色≈{section['bg_color']}")
            lines.append(f"  包含: {section['element_count']}个检测元素, {section['text_count']}个文本块")
            
            if section['texts']:
                lines.append(f"  文本内容:")
                for t in section['texts'][:30]:
                    lines.append(f"    \"{t['text']}\" @({t['x']},{t['y']}) {t['w']}x{t['h']}")
                if len(section['texts']) > 30:
                    lines.append(f"    ... 还有 {len(section['texts']) - 30} 个文本块")
            
            if section['elements']:
                lines.append(f"  检测元素:")
                for e in section['elements'][:20]:
                    lines.append(f"    {e['type']} @({e['x']},{e['y']}) {e['w']}x{e['h']} conf={e['confidence']}")
                if len(section['elements']) > 20:
                    lines.append(f"    ... 还有 {len(section['elements']) - 20} 个元素")
        
        return "\n".join(lines)
    
    def save_structured_layout(self, image_path, structured_layout):
        """保存结构化布局分析结果到文件"""
        try:
            import json
            import os
            from datetime import datetime
            
            base_name = os.path.splitext(os.path.basename(image_path))[0]
            output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
            os.makedirs(output_dir, exist_ok=True)
            
            # 保存JSON格式
            layout_file = os.path.join(output_dir, f'{base_name}_structured_layout.json')
            with open(layout_file, 'w', encoding='utf-8') as f:
                json.dump(structured_layout, f, ensure_ascii=False, indent=2)
            print(f"💾 结构化布局JSON已保存: {layout_file}")
            
            # 保存文本格式
            text_file = os.path.join(output_dir, f'{base_name}_structured_layout.txt')
            with open(text_file, 'w', encoding='utf-8') as f:
                f.write(f"结构化布局分析结果\n")
                f.write(f"{'='*60}\n")
                f.write(f"图像: {image_path}\n")
                f.write(f"时间: {datetime.now().isoformat()}\n")
                f.write(f"{'='*60}\n\n")
                f.write(self.format_structured_layout(structured_layout))
            print(f"💾 结构化布局文本已保存: {text_file}")
            
        except Exception as e:
            print(f"⚠️ 保存结构化布局失败: {e}")
    
    def encode_image_to_base64(self, image_path):
        """将图像编码为base64格式"""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    
    def calculate_ssim(self, image1_path, image2_path):
        """计算两张图像的SSIM相似度 - 严肃像素级比对"""
        try:
            # 读取图像
            img1 = cv2.imread(image1_path)
            img2 = cv2.imread(image2_path)
            
            if img1 is None or img2 is None:
                print("❌ 无法读取图像进行SSIM计算")
                return 0.0
            
            # 确保尺寸完全一致
            if img1.shape != img2.shape:
                img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))
            
            # 方法1: 原始SSIM（灰度）
            gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
            gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
            ssim_score, ssim_map = ssim(gray1, gray2, full=True)
            
            # 方法2: 像素级差异率（更严格）
            diff = cv2.absdiff(img1, img2)
            diff_gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
            # 计算像素差异率（差异像素占比）
            threshold = 10  # 像素差异阈值
            diff_pixels = np.sum(diff_gray > threshold)
            total_pixels = diff_gray.size
            pixel_diff_rate = diff_pixels / total_pixels
            
            # 方法3: 结构相似度（边缘检测）
            edges1 = cv2.Canny(gray1, 50, 150)
            edges2 = cv2.Canny(gray2, 50, 150)
            edge_score, _ = ssim(edges1, edges2, full=True)
            
            # 综合评分（加权平均）
            # SSIM: 40%, 像素差异: 40% (1-差异率), 边缘相似: 20%
            pixel_similarity = 1 - pixel_diff_rate
            combined_score = 0.4 * ssim_score + 0.4 * pixel_similarity + 0.2 * edge_score
            
            print(f"  SSIM评分详情:")
            print(f"    - 结构相似度(SSIM): {ssim_score:.4f}")
            print(f"    - 像素相似度: {pixel_similarity:.4f} (差异像素: {pixel_diff_rate*100:.1f}%)")
            print(f"    - 边缘相似度: {edge_score:.4f}")
            print(f"    - 综合评分: {combined_score:.4f}")
            
            return combined_score
        except Exception as e:
            print(f"❌ SSIM计算失败: {e}")
            return 0.0
    
    def calculate_ssim_by_blocks(self, image1_path, image2_path, num_blocks=4, elements=None):
        """分区块计算SSIM，定位得分最低的区域（考虑语义边界）"""
        try:
            # 读取图像
            img1 = cv2.imread(image1_path)
            img2 = cv2.imread(image2_path)
            
            if img1 is None or img2 is None:
                print("无法读取图像进行区块SSIM计算")
                return None, 0.0
            
            # 调整大小以匹配
            img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))
            
            # 转换为灰度图
            gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
            gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
            
            height, width = gray1.shape
            
            # 使用四叉树分割算法，考虑语义边界
            if elements:
                blocks = self._quadtree_ssim(gray1, gray2, elements, width, height)
            else:
                blocks = self._uniform_block_ssim(gray1, gray2, num_blocks)
            
            if blocks:
                blocks.sort(key=lambda x: x['ssim'])
                min_ssim = blocks[0]['ssim']
            else:
                min_ssim = 1.0
            
            return blocks, min_ssim
        except Exception as e:
            print(f"区块SSIM计算失败: {e}")
            return None, 0.0
    
    def _uniform_block_ssim(self, gray1, gray2, num_blocks):
        """均匀区块SSIM计算"""
        height, width = gray1.shape
        block_height = height // num_blocks
        block_width = width // num_blocks
        
        blocks = []
        
        # 计算每个区块的SSIM
        for i in range(num_blocks):
            for j in range(num_blocks):
                # 计算区块坐标
                y1 = i * block_height
                y2 = min((i + 1) * block_height, height)
                x1 = j * block_width
                x2 = min((j + 1) * block_width, width)
                
                # 提取区块
                block1 = gray1[y1:y2, x1:x2]
                block2 = gray2[y1:y2, x1:x2]
                
                # 计算区块SSIM
                if block1.size > 0 and block2.size > 0:
                    block_ssim, _ = ssim(block1, block2, full=True)
                    
                    blocks.append({
                        'row': i,
                        'col': j,
                        'x': x1,
                        'y': y1,
                        'width': x2 - x1,
                        'height': y2 - y1,
                        'ssim': block_ssim
                    })
        
        return blocks
    
    def _quadtree_ssim(self, gray1, gray2, elements, width, height, 
                       x=0, y=0, level=0, max_level=4, min_size=100):
        """
        四叉树分割算法计算SSIM
        根据内容复杂度自适应分割，同时保护语义边界
        """
        blocks = []
        
        # 当前区域尺寸
        region_width = width // (2 ** level)
        region_height = height // (2 ** level)
        
        # 如果区域太小，停止分割
        if region_width < min_size or region_height < min_size or level >= max_level:
            # 计算当前区域的SSIM
            x2 = min(x + region_width, width)
            y2 = min(y + region_height, height)
            
            block1 = gray1[y:y2, x:x2]
            block2 = gray2[y:y2, x:x2]
            
            if block1.size > 0 and block2.size > 0:
                block_ssim, _ = ssim(block1, block2, full=True)
                
                blocks.append({
                    'x': x,
                    'y': y,
                    'width': x2 - x,
                    'height': y2 - y,
                    'ssim': block_ssim,
                    'level': level,
                    'is_leaf': True
                })
            return blocks
        
        # 分析当前区域内的元素
        region_elements = self._get_elements_in_region(elements, x, y, region_width, region_height)
        
        # 检查是否需要继续分割
        should_split = self._should_split_region(region_elements, region_width, region_height, level)
        
        if should_split:
            # 找到最佳分割点（考虑语义边界）
            split_x, split_y = self._find_semantic_split_point(region_elements, x, y, region_width, region_height)
            
            # 四叉树分割
            half_width = (split_x - x) if split_x else region_width // 2
            half_height = (split_y - y) if split_y else region_height // 2
            
            # 递归处理四个子区域
            # 左上
            blocks.extend(self._quadtree_ssim(gray1, gray2, elements, width, height,
                                            x, y, level + 1, max_level, min_size))
            # 右上
            blocks.extend(self._quadtree_ssim(gray1, gray2, elements, width, height,
                                            x + half_width, y, level + 1, max_level, min_size))
            # 左下
            blocks.extend(self._quadtree_ssim(gray1, gray2, elements, width, height,
                                            x, y + half_height, level + 1, max_level, min_size))
            # 右下
            blocks.extend(self._quadtree_ssim(gray1, gray2, elements, width, height,
                                            x + half_width, y + half_height, level + 1, max_level, min_size))
        else:
            # 不分割，计算当前区域的SSIM
            x2 = min(x + region_width, width)
            y2 = min(y + region_height, height)
            
            block1 = gray1[y:y2, x:x2]
            block2 = gray2[y:y2, x:x2]
            
            if block1.size > 0 and block2.size > 0:
                block_ssim, _ = ssim(block1, block2, full=True)
                
                blocks.append({
                    'x': x,
                    'y': y,
                    'width': x2 - x,
                    'height': y2 - y,
                    'ssim': block_ssim,
                    'level': level,
                    'is_leaf': True,
                    'element_count': len(region_elements)
                })
        
        return blocks
    
    def _get_elements_in_region(self, elements, x, y, width, height):
        """获取区域内的元素"""
        region_elements = []
        for element in elements:
            ex1, ey1, ex2, ey2 = element['bbox']
            # 检查元素是否与区域重叠
            overlap_x = max(0, min(ex2, x + width) - max(ex1, x))
            overlap_y = max(0, min(ey2, y + height) - max(ey1, y))
            
            if overlap_x > 0 and overlap_y > 0:
                region_elements.append(element)
        
        return region_elements
    
    def _should_split_region(self, elements, width, height, level):
        """
        判断是否应该继续分割区域
        基于内容复杂度和区域大小
        """
        if len(elements) == 0:
            return False
        
        # 计算内容密度
        total_element_area = sum(
            (e['bbox'][2] - e['bbox'][0]) * (e['bbox'][3] - e['bbox'][1])
            for e in elements
        )
        region_area = width * height
        density = total_element_area / region_area if region_area > 0 else 0
        
        # 如果内容密度高且元素数量多，继续分割
        if density > 0.3 and len(elements) > 2:
            return True
        
        # 如果元素类型多样，继续分割
        element_types = set(e['type'] for e in elements)
        if len(element_types) > 2:
            return True
        
        return False
    
    def _find_semantic_split_point(self, elements, x, y, width, height):
        """
        找到最佳语义分割点
        在元素间隙处分割，避免切割完整内容
        """
        if not elements:
            return None, None
        
        # 收集所有元素的边界
        x_boundaries = []
        y_boundaries = []
        
        for element in elements:
            ex1, ey1, ex2, ey2 = element['bbox']
            # 相对于区域的位置
            rel_x1 = max(0, ex1 - x)
            rel_x2 = min(width, ex2 - x)
            rel_y1 = max(0, ey1 - y)
            rel_y2 = min(height, ey2 - y)
            
            x_boundaries.extend([rel_x1, rel_x2])
            y_boundaries.extend([rel_y1, rel_y2])
        
        # 找到元素之间的最大间隙
        x_boundaries = sorted(set(x_boundaries))
        y_boundaries = sorted(set(y_boundaries))
        
        best_split_x = None
        best_gap_x = 0
        
        for i in range(len(x_boundaries) - 1):
            gap = x_boundaries[i + 1] - x_boundaries[i]
            if gap > best_gap_x and gap > width * 0.1:  # 至少10%的宽度
                best_gap_x = gap
                best_split_x = x_boundaries[i] + gap // 2
        
        best_split_y = None
        best_gap_y = 0
        
        for i in range(len(y_boundaries) - 1):
            gap = y_boundaries[i + 1] - y_boundaries[i]
            if gap > best_gap_y and gap > height * 0.1:  # 至少10%的高度
                best_gap_y = gap
                best_split_y = y_boundaries[i] + gap // 2
        
        # 如果找不到合适的分割点，使用中间位置
        if best_split_x is None:
            best_split_x = width // 2
        if best_split_y is None:
            best_split_y = height // 2
        
        return best_split_x, best_split_y
    
    def find_low_ssim_regions(self, image1_path, image2_path, elements=None, threshold=0.95):
        """
        找出SSIM低于阈值的区域
        使用四叉树分割算法，考虑语义边界
        """
        try:
            # 使用四叉树分割算法计算区块SSIM
            blocks, _ = self.calculate_ssim_by_blocks(image1_path, image2_path, elements=elements)
            
            if not blocks:
                return []
            
            # 找出低于阈值的区块
            low_regions = [b for b in blocks if b['ssim'] < threshold]
            
            # 按SSIM分数排序
            low_regions.sort(key=lambda x: x['ssim'])
            
            # 合并相邻的低SSIM区域（考虑整体性）
            merged_regions = self._merge_adjacent_regions(low_regions)
            
            # 确保区域不重叠（保留最低SSIM的区域）
            unique_regions = self._remove_overlapping_regions(merged_regions)
            
            print(f"四叉树分割生成 {len(blocks)} 个区块，发现 {len(low_regions)} 个低SSIM区域，合并后 {len(unique_regions)} 个")
            
            return unique_regions[:5]  # 返回前5个最低的区域
        except Exception as e:
            print(f"查找低SSIM区域失败: {e}")
            return []
    
    def _merge_adjacent_regions(self, regions, max_gap=50):
        """
        合并相邻的低SSIM区域
        保持页面整体性，避免过度分割
        """
        if not regions:
            return []
        
        merged = []
        used = set()
        
        for i, region in enumerate(regions):
            if i in used:
                continue
            
            # 当前区域
            current = region.copy()
            used.add(i)
            
            # 查找可以合并的相邻区域
            for j, other in enumerate(regions[i+1:], start=i+1):
                if j in used:
                    continue
                
                # 检查是否相邻（考虑间隙）
                x_gap = abs(current['x'] + current['width'] - other['x'])
                y_gap = abs(current['y'] + current['height'] - other['y'])
                
                # 水平相邻
                horizontal_adjacent = (
                    abs(current['y'] - other['y']) < max_gap and
                    abs(current['height'] - other['height']) < max_gap and
                    x_gap < max_gap
                )
                
                # 垂直相邻
                vertical_adjacent = (
                    abs(current['x'] - other['x']) < max_gap and
                    abs(current['width'] - other['width']) < max_gap and
                    y_gap < max_gap
                )
                
                if horizontal_adjacent or vertical_adjacent:
                    # 合并区域
                    new_x = min(current['x'], other['x'])
                    new_y = min(current['y'], other['y'])
                    new_x2 = max(current['x'] + current['width'], other['x'] + other['width'])
                    new_y2 = max(current['y'] + current['height'], other['y'] + other['height'])
                    
                    current['x'] = new_x
                    current['y'] = new_y
                    current['width'] = new_x2 - new_x
                    current['height'] = new_y2 - new_y
                    current['ssim'] = min(current['ssim'], other['ssim'])  # 取最低SSIM
                    current['merged'] = True
                    
                    used.add(j)
            
            merged.append(current)
        
        return merged
    
    def _remove_overlapping_regions(self, regions, overlap_threshold=0.3):
        """
        移除重叠的区域，保留SSIM最低的区域
        """
        if not regions:
            return []
        
        # 按SSIM排序（低到高）
        sorted_regions = sorted(regions, key=lambda x: x['ssim'])
        
        unique_regions = []
        
        for region in sorted_regions:
            overlap = False
            for existing in unique_regions:
                # 计算重叠率
                x1 = max(region['x'], existing['x'])
                y1 = max(region['y'], existing['y'])
                x2 = min(region['x'] + region['width'], existing['x'] + existing['width'])
                y2 = min(region['y'] + region['height'], existing['y'] + existing['height'])
                
                if x2 > x1 and y2 > y1:
                    overlap_area = (x2 - x1) * (y2 - y1)
                    region_area = region['width'] * region['height']
                    if overlap_area / region_area > overlap_threshold:
                        overlap = True
                        break
            
            if not overlap:
                unique_regions.append(region)
        
        return unique_regions
    
    def check_and_setup_chromedriver(self):
        """检查并设置ChromeDriver，包括环境检测和自动修复"""
        chromedriver_path = os.path.join(os.path.dirname(__file__), 'chromedriver')
        
        print("\n" + "="*60)
        print("ChromeDriver 环境检测")
        print("="*60)
        
        # 1. 检查ChromeDriver是否存在
        if not os.path.exists(chromedriver_path):
            print("❌ ChromeDriver未找到")
            print(f"   期望路径: {chromedriver_path}")
            print("\n正在尝试自动下载ChromeDriver...")
            return self._download_chromedriver()
        
        print(f"✅ ChromeDriver存在: {chromedriver_path}")
        
        # 2. 检查文件权限
        if not os.access(chromedriver_path, os.X_OK):
            print("⚠️ ChromeDriver没有执行权限，正在修复...")
            try:
                os.chmod(chromedriver_path, 0o755)
                print("✅ 权限修复完成")
            except Exception as e:
                print(f"❌ 权限修复失败: {e}")
                return None
        
        # 3. 检查架构是否匹配
        try:
            import subprocess
            result = subprocess.run(['file', chromedriver_path], 
                                  capture_output=True, text=True)
            file_info = result.stdout
            print(f"   文件信息: {file_info.strip()}")
            
            # 检查当前系统架构
            import platform
            machine = platform.machine()
            print(f"   系统架构: {machine}")
            
            # 检查是否匹配
            if 'x86-64' in file_info or 'x86_64' in file_info:
                if machine in ['x86_64', 'AMD64']:
                    print("✅ 架构匹配: x86_64")
                else:
                    print("⚠️ 架构不匹配! ChromeDriver是x86_64，但系统不是")
                    print("正在尝试重新下载匹配版本的ChromeDriver...")
                    return self._download_chromedriver()
            elif 'aarch64' in file_info or 'arm64' in file_info:
                if machine in ['aarch64', 'arm64']:
                    print("✅ 架构匹配: ARM64")
                else:
                    print("⚠️ 架构不匹配! ChromeDriver是ARM64，但系统不是")
                    print("正在尝试重新下载匹配版本的ChromeDriver...")
                    return self._download_chromedriver()
            
        except Exception as e:
            print(f"⚠️ 架构检查失败: {e}")
            print("继续使用现有的ChromeDriver...")
        
        # 4. 检查ChromeDriver版本是否与Chrome浏览器版本匹配
        try:
            print("\n检查ChromeDriver版本兼容性...")
            
            # 获取Chrome浏览器版本
            chrome_version, chrome_major = self._get_chrome_version()
            if chrome_version and chrome_major:
                print(f"   Chrome浏览器版本: {chrome_version}")
                
                # 获取ChromeDriver版本
                result = subprocess.run([chromedriver_path, '--version'], 
                                      capture_output=True, text=True)
                chromedriver_version_line = result.stdout.strip()
                # 格式通常是 "ChromeDriver 120.0.6099.109"
                if 'ChromeDriver' in chromedriver_version_line:
                    chromedriver_version = chromedriver_version_line.split()[1]
                    chromedriver_major = chromedriver_version.split('.')[0]
                    print(f"   ChromeDriver版本: {chromedriver_version}")
                    
                    # 比较主版本号
                    if chrome_major == chromedriver_major:
                        print(f"✅ 版本匹配: {chrome_major}")
                    else:
                        print(f"⚠️ 版本不匹配!")
                        print(f"   Chrome浏览器: {chrome_major}")
                        print(f"   ChromeDriver: {chromedriver_major}")
                        print("\n正在删除旧版本ChromeDriver并重新下载...")
                        try:
                            os.remove(chromedriver_path)
                            print("✅ 旧版本已删除")
                            return self._download_chromedriver()
                        except Exception as e:
                            print(f"❌ 删除失败: {e}")
                            return None
            else:
                print("⚠️ 无法检测Chrome版本，跳过版本检查")
                
        except Exception as e:
            print(f"⚠️ 版本检查失败: {e}")
            print("继续使用现有的ChromeDriver...")
        
        print("="*60 + "\n")
        return chromedriver_path
    
    def _get_chrome_version(self):
        """获取当前安装的Chrome浏览器版本"""
        try:
            import subprocess
            result = subprocess.run(['google-chrome', '--version'], 
                                  capture_output=True, text=True)
            version_line = result.stdout.strip()
            # 解析版本号，格式通常是 "Google Chrome 146.0.7680.177"
            if 'Google Chrome' in version_line:
                version = version_line.split()[-1]
                # 获取主版本号（如 146）
                major_version = version.split('.')[0]
                return version, major_version
            return None, None
        except Exception as e:
            print(f"⚠️ 获取Chrome版本失败: {e}")
            return None, None
    
    def _download_chromedriver(self):
        """下载匹配当前系统的ChromeDriver"""
        import platform
        import urllib.request
        import zipfile
        
        chromedriver_path = os.path.join(os.path.dirname(__file__), 'chromedriver')
        
        # 获取Chrome版本
        chrome_version, chrome_major = self._get_chrome_version()
        
        print(f"\n{'='*60}")
        print("ChromeDriver 自动下载")
        print("="*60)
        
        if chrome_version:
            print(f"检测到Chrome版本: {chrome_version}")
            print(f"主版本号: {chrome_major}")
        else:
            print("⚠️ 无法检测Chrome版本，将使用默认版本 120")
            chrome_major = "120"
        
        # 确定系统架构
        machine = platform.machine()
        system = platform.system().lower()
        
        print(f"\n系统信息: {system} {machine}")
        
        # 尝试下载匹配Chrome版本的ChromeDriver
        # ChromeDriver版本通常与Chrome主版本号对应
        # 例如 Chrome 146 需要 ChromeDriver 146.x.x.x
        
        # 构建版本URL
        # 使用Chrome for Testing的最新稳定版本
        # 参考: https://googlechromelabs.github.io/chrome-for-testing/
        
        base_url = "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing"
        
        # 尝试下载匹配Chrome版本的driver
        # 先尝试完全匹配的版本
        driver_versions_to_try = []
        
        if chrome_major and chrome_major.isdigit():
            # 构建可能的版本号
            major = int(chrome_major)
            # 尝试最新的patch版本（使用0.0.0作为占位符，ChromeDriver会找到最新版本）
            driver_versions_to_try.append(f"{major}.0.7680.0")
            driver_versions_to_try.append(f"{major}.0.0.0")
        
        # 如果特定版本失败，使用已知稳定的版本
        driver_versions_to_try.extend([
            "146.0.7680.0",  # Chrome 146
            "145.0.7668.0",  # Chrome 145
            "144.0.7655.0",  # Chrome 144
            "120.0.6099.109",  # 默认版本
        ])
        
        # 确定平台路径
        if system == 'linux':
            if machine in ['x86_64', 'AMD64']:
                platform_path = "linux64"
                chromedriver_name = "chromedriver-linux64"
            else:
                print(f"❌ 不支持的架构: {machine}")
                return None
        elif system == 'darwin':  # macOS
            if machine in ['x86_64', 'AMD64']:
                platform_path = "mac-x64"
                chromedriver_name = "chromedriver-mac-x64"
            else:
                platform_path = "mac-arm64"
                chromedriver_name = "chromedriver-mac-arm64"
            print("❌ macOS暂不支持自动下载，请手动安装ChromeDriver")
            return None
        else:
            print(f"❌ 不支持的操作系统: {system}")
            return None
        
        # 尝试下载每个版本
        for version in driver_versions_to_try:
            url = f"{base_url}/{version}/{platform_path}/{chromedriver_name}.zip"
            
            print(f"\n尝试下载版本 {version}...")
            print(f"URL: {url}")
            
            try:
                zip_file = os.path.join(os.path.dirname(__file__), f"{chromedriver_name}.zip")
                
                # 下载
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=30) as response:
                    with open(zip_file, 'wb') as f:
                        f.write(response.read())
                
                print(f"✅ 下载完成")
                
                # 解压
                print("正在解压...")
                with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                    zip_ref.extractall(os.path.dirname(__file__))
                print("✅ 解压完成")
                
                # 移动chromedriver到正确位置
                extracted_driver = os.path.join(os.path.dirname(__file__), chromedriver_name, 'chromedriver')
                if os.path.exists(extracted_driver):
                    if os.path.exists(chromedriver_path):
                        os.remove(chromedriver_path)
                    os.rename(extracted_driver, chromedriver_path)
                    os.chmod(chromedriver_path, 0o755)
                    print(f"✅ ChromeDriver {version} 已安装")
                    
                    # 清理临时文件
                    if os.path.exists(zip_file):
                        os.remove(zip_file)
                    extract_dir_path = os.path.join(os.path.dirname(__file__), chromedriver_name)
                    if os.path.exists(extract_dir_path):
                        import shutil
                        shutil.rmtree(extract_dir_path)
                    
                    return chromedriver_path
                else:
                    print(f"❌ 解压后未找到ChromeDriver")
                    
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    print(f"⚠️ 版本 {version} 不存在，尝试下一个版本...")
                else:
                    print(f"❌ HTTP错误 {e.code}: {e.reason}")
            except Exception as e:
                print(f"❌ 下载失败: {e}")
                import traceback
                traceback.print_exc()
        
        print("\n❌ 所有版本都下载失败")
        return None
        
        try:
            print(f"正在下载ChromeDriver...")
            print(f"URL: {url}")
            
            # 下载
            zip_file = os.path.join(os.path.dirname(__file__), zip_path)
            urllib.request.urlretrieve(url, zip_file)
            print(f"✅ 下载完成: {zip_file}")
            
            # 解压
            print("正在解压...")
            with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                zip_ref.extractall(os.path.dirname(__file__))
            print("✅ 解压完成")
            
            # 移动chromedriver到正确位置
            extracted_driver = os.path.join(os.path.dirname(__file__), extract_dir, 'chromedriver')
            if os.path.exists(extracted_driver):
                if os.path.exists(chromedriver_path):
                    os.remove(chromedriver_path)
                os.rename(extracted_driver, chromedriver_path)
                os.chmod(chromedriver_path, 0o755)
                print(f"✅ ChromeDriver已安装: {chromedriver_path}")
            
            # 清理临时文件
            if os.path.exists(zip_file):
                os.remove(zip_file)
            extract_dir_path = os.path.join(os.path.dirname(__file__), extract_dir)
            if os.path.exists(extract_dir_path):
                import shutil
                shutil.rmtree(extract_dir_path)
            
            return chromedriver_path
            
        except Exception as e:
            print(f"❌ 下载失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def render_html_and_capture(self, html_path, output_image_path, window_size):
        """使用Selenium渲染HTML并截图"""
        try:
            # 确保输出目录存在
            output_dir = os.path.dirname(output_image_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
            
            # 检查并设置ChromeDriver
            chromedriver_path = self.check_and_setup_chromedriver()
            if not chromedriver_path:
                print("❌ ChromeDriver设置失败，跳过SSIM计算")
                return False
            
            # 设置Chrome选项
            options = webdriver.ChromeOptions()
            options.add_argument('--headless=new')
            options.add_argument('--disable-gpu')
            options.add_argument(f'--window-size={window_size[0]},{window_size[1]}')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-setuid-sandbox')
            options.add_argument('--disable-web-security')
            options.add_argument('--disable-features=IsolateOrigins,site-per-process')
            options.add_argument('--disable-extensions')
            options.add_argument('--disable-default-apps')
            options.add_argument('--mute-audio')
            options.add_argument('--hide-scrollbars')
            options.add_argument('--force-device-scale-factor=1')
            
            # 使用项目目录下的ChromeDriver
            service = Service(chromedriver_path)
            print(f"使用ChromeDriver: {chromedriver_path}")
            
            # 初始化驱动
            driver = webdriver.Chrome(service=service, options=options)
            
            # 加载HTML文件
            driver.get(f'file://{os.path.abspath(html_path)}')
            
            # 等待页面加载
            time.sleep(1.5)
            
            # 截图
            driver.save_screenshot(output_image_path)
            
            # 关闭驱动
            driver.quit()
            
            return True
        except Exception as e:
            print(f"HTML渲染失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def analyze_with_kimi(self, image_path, text_content, elements, element_info, layout_info, alignment_info, colors):
        """使用Kimi Coding API分析截图，支持多级备用方案"""
        # 将图像编码为base64
        base64_image = self.encode_image_to_base64(image_path)
        
        # 构造提示词
        aspect_ratio = self.original_width / self.original_height
        
        # 计算DPR（设备像素比）- 关键！统一参照系
        # iPhone 14: 1170px物理宽度 / 390px逻辑宽度 = 3x
        # 根据图片宽度推断DPR
        if self.original_width >= 1000:
            dpr = 3  # 3x设备（iPhone 14等）
            logical_width = self.original_width // 3
            logical_height = self.original_height // 3
        elif self.original_width >= 700:
            dpr = 2  # 2x设备
            logical_width = self.original_width // 2
            logical_height = self.original_height // 2
        else:
            dpr = 1  # 1x设备
            logical_width = self.original_width
            logical_height = self.original_height
        
        prompt = f"""分析网页截图，生成高保真HTML代码。

【关键：统一参照系】
- 原图物理像素：{self.original_width}x{self.original_height}px
- 设备像素比(DPR)：{dpr}x
- 逻辑像素：{logical_width}x{logical_height}px（CSS中使用的尺寸）
- 比例：{aspect_ratio:.4f}

【重要规则】
1. CSS中所有尺寸（width/height/font-size/padding/margin）必须使用逻辑像素值
2. 物理像素值 = 逻辑像素值 × DPR({dpr})
3. 例如：截图中文字看起来是48px高 → 实际CSS font-size应该是 48/{dpr}=16px
4. 所有坐标位置也要按DPR缩放

颜色：{colors}

【必须严格遵守的布局规范 - 结构化布局信息】
{layout_info}

【重要】以上结构化布局信息将页面划分为多个区域（如status_bar、nav_bar、content等），每个区域包含：
- 区域类型（type）：status_bar、nav_bar、content、bottom_bar
- 区域位置（y_start~y_end）：该区域在页面中的垂直范围
- 背景色（bg_color）：该区域的背景颜色
- 文本内容（texts）：该区域包含的所有文本及其精确坐标
- 检测元素（elements）：该区域包含的UI元素

【强制要求】
1. HTML结构必须严格按照上述区域划分来构建
2. 每个区域必须使用对应的CSS类名：status-bar、nav-bar、content-section、bottom-bar
3. 每个区域的背景色必须与结构化布局中的bg_color一致
4. 每个区域的高度必须与其在结构化布局中的高度一致
5. 文本必须放置在结构化布局指定的坐标位置（考虑DPR缩放）
6. 禁止随意更改区域顺序或合并区域

检测到的元素（原始列表，已整合到上方结构化布局中）：
{element_info}

OCR文本内容（必须在HTML中完整显示，不能遗漏任何文字）：
{text_content}

## 要求（必须严格遵守）

### 0 布局结构要求（最重要！）
- **必须严格按照结构化布局信息中的区域划分来构建HTML**
- **每个区域的高度必须与其在结构化布局中的y_start~y_end范围一致**
- **文本必须按照结构化布局中指定的坐标位置放置**
- **status-bar、nav-bar、bottom-bar必须使用固定高度和指定的class名**

#### 0.1 核心原则：100%还原原图
- 你必须仔细学习原图截图、布局分析提供的所有知识
- 你的目标是尽可能100%按照原图实现HTML，而不是创造或美化
- 原图有什么就还原什么，原图没有的绝对不能添加
- 每一个颜色、间距、字体大小、元素位置都应以原图为准
- 如果你对某个细节不确定，请仔细观察截图再决定，不要凭想象添加

#### 0.2 布局方式
- 你应该仔细观察截图，布局分析可能有错误或者遗漏，根据你自己对页面布局的理解来安排元素位置
- 可以使用 flex、grid、absolute 等任何你认为合适的 CSS 布局方式
- 检测到的元素坐标仅供参考，帮助你理解页面有哪些元素以及大致位置
- 最终布局应以你的视觉判断为准，确保还原截图的视觉效果

#### 0.3 布局参考信息
- 检测到的元素类型和位置可以帮助你了解页面结构
- 但你不需要严格使用检测到的坐标值
- 检测到的区块高度是正确的，你必须严格遵守
- 重点是还原截图的视觉效果、元素位置

#### 0.4 布局建议
- 优先保证页面整体视觉效果与截图一致
- **bottom-bar 布局规则（重要）**：
  - bottom-bar 必须放在 page-container 的最后，在所有内容之后
  - 如果使用 absolute 定位 bottom: 0，必须确保 main-content 的高度不会超过 page-container 的高度
  - 或者使用 flex 布局：page-container 使用 display: flex; flex-direction: column;，main-content 使用 flex: 1;
  - 绝对不能让 bottom-bar 被其他内容覆盖，也不能让 bottom-bar 覆盖其他内容
  - bottom-bar 必须在页面最底部，清晰可见
- 元素之间的相对位置关系（上下、左右、嵌套）比绝对坐标更重要
- 合理使用 CSS 布局（flex/grid/absolute）来实现最佳还原效果
- 注意元素的对齐、间距、大小比例等视觉细节

#### 0.5 页面结构（从上到下固定顺序）
```
status-bar（高度严格24px）→ nav-bar（高度严格44px）→ 内容区 → bottom-bar（高度严格50px，如有）
```

#### 0.6 status-bar（状态栏）规范
- 高度：严格24px逻辑像素
- class名：必须是"status-bar"，禁止使用其他名称
- 内容：显示时间/信号/电量图标
- 背景色：与nav-bar保持一致（同色）
- z-index：最高（100）

#### 0.7 nav-bar（导航栏/菜单栏）规范
- 高度：严格44px逻辑像素
- class名：必须是"nav-bar"，禁止使用其他名称
- 内容：标题居中，返回按钮左侧
- 背景色：从截图中提取（通常为主题色）
- z-index：次高（99）

#### 0.8 bottom-bar（底部导航栏）规范
- **重要：只有截图中明确存在底部导航栏时才添加，截图中没有则不要添加**
- **禁止自行编造底部导航栏的图标和文字，必须以原图为准**
- 高度：严格50px逻辑像素（仅当存在时）
- class名：必须是"bottom-bar"，禁止使用其他名称
- 内容：底部导航图标和文字（必须与原图一致，不可自创）
- 背景色：白色(#ffffff)，顶部0.5px边线
- z-index：98

#### 0.9 禁止事项
- 禁止状态栏和导航栏重叠
- 禁止按钮悬浮在内容中间
- 禁止使用tab-bar、footer等命名，必须使用bottom-bar

#### 0.10 禁止事项（绝对禁止）
- **禁止任何动画**：transition、animation、@keyframes全部禁止
- **禁止任何交互**：hover效果、click事件、JavaScript全部禁止
- **禁止emoji**：使用SVG图标代替
- **禁止滚动**：overflow: hidden，所有内容必须平铺展示
- **禁止装饰元素**：不要添加原图不存在的圆角、阴影、边框等装饰
- **禁止杂波**：不要渲染检测到的噪声元素（小三角形、随机形状）
- **禁止添加**：不要添加任何原图不存在的元素
- **禁止自创颜色**：颜色必须从截图中提取，禁止LLM自行创造颜色

### 1 文字内容要求（最重要！）
- **上面的OCR文本已经识别了图片中的所有文字（共{len(text_content)}个字符）**
- **你必须将这些文字完整准确地显示在HTML中，不能遗漏任何文字**
- **标题、正文、按钮文字、标签文字、底部风险提示等所有文字都必须与OCR文本一致**
- **禁止自己编造或修改文字内容**
- **禁止截断文字，即使文字很长也要完整显示**
- **如果OCR文本中有空格分隔（如"财 富 星"），请合并为正常中文（"财富星"）**
- **特别注意：页面底部的风险提示、免责声明等长文本必须完整显示**

### 2. 尺寸和缩放（关键）
- 容器尺寸（逻辑像素）：width:{logical_width}px; height:{logical_height}px
- **重要：截图包含完整页面内容（包括需要滚动的部分），HTML必须生成完整页面，不能只有首屏**
- **禁止设置overflow: hidden或overflow-y: auto截断内容**
- **所有内容必须平铺展示，页面高度严格等于{logical_height}px**
- **浏览器显示缩放（重要）**：
  - 使用 transform: scale(0.5) 让页面在浏览器中显示更合适（不要用 scale(3)）
  - 如果页面特别长（高度>2000px），可以使用 scale(0.4) 或 scale(0.3)
  - 重点是让页面在浏览器窗口中能够完整显示，方便查看
- 使用纯CSS实现缩放，禁止使用JavaScript计算scale值
- 禁止添加任何检测到的杂波元素
- **浏览器显示适配**：
  - body添加：display: flex; justify-content: center; align-items: flex-start; min-height: 100vh; padding: 20px 0;
  - 不要固定body的width或height，让它自适应浏览器窗口
  - 这样页面在浏览器中会居中显示，适合查看

### 3. CSS设计系统（必须严格遵守，不可自行发挥）
**以下规则是强制性的，必须原样遵守，禁止自行修改颜色值或尺寸：**

#### 3.1 固定CSS变量（必须在:root中定义，值不可更改）
```css
:root {{
    --color-bg: #333333;
    --status-bar-height: 24px;
    --nav-bar-height: 44px;
    --bottom-bar-height: 50px;
}}
```
- **--color-bg: #333333** 是页面背景色，必须使用此值，禁止使用其他颜色
- 其他颜色变量（如--color-primary等）根据截图内容提取，但--color-bg固定为#333333

#### 3.2 固定组件命名（必须使用以下class名，禁止更改）
- 顶部状态栏：`class="status-bar"`（高度严格24px）
- 导航栏/菜单栏：`class="nav-bar"`（高度严格44px）
- 底部导航栏：`class="bottom-bar"`（高度严格50px）

#### 3.3 固定body样式
```css
body {{
    margin-top: 0px;
    margin-right: auto;
    margin-bottom: 0px;
    margin-left: auto;
}}
```

#### 3.4 固定page-container样式    
截图内容必须使用 `<div class="page-container">` 作为容器，样式固定如下：
```css
.page-container {{
    margin-top: 0px;
    margin-right: auto;
    margin-bottom: 0px;
    margin-left: auto;
    position: relative;
    width: {logical_width}px;
    height: {logical_height}px;
}}
```
- 容器class名必须是"page-container"，禁止使用其他名称（如page-wrapper、main-container等）
- margin必须严格为：0 auto 0 auto（水平居中，上下无间距）

#### 3.5 字体和间距（基于逻辑像素）
- 字体层级：--text-xs({12*dpr}px)到--text-2xl({24*dpr}px)
- 间距系统：--space-1({4*dpr}px)到--space-8({32*dpr}px)
- 所有尺寸按DPR={dpr}缩放

### 4. 代码规范
- BEM命名：.block__element--modifier
- 语义化标签：header/main/section/footer
- 代码分块注释
- **绝对禁止emoji**：不能用📈💰📊等任何emoji字符，也不能用&#128200;等HTML实体emoji
- 图标使用SVG或CSS绘制，不能用emoji

### 5. 内容完整性（关键）
- 所有检测到的有效元素必须出现在HTML中
- OCR文本必须全部显示，不能截断
- **箭头处理**：如果原图有箭头才显示，不要自己创造箭头元素
- 底部免责声明文字必须完整显示，不能截断或省略
- 页面高度必须严格等于{logical_height}px（逻辑像素），不能截断
- 从上到下完整还原整个页面，不能遗漏任何部分
- **重要：不要渲染任何杂波图形（如随机三角形、不完整形状、噪声元素）**
- **不要添加装饰性元素**：不要添加原图不存在的箭头、图标、装饰线等

### 6. 输出要求
- 直接返回完整的HTML代码
- 确保HTML代码完整，包含结束标签
- 不要截断任何内容
- 不要解释"""

        # 尝试方案1: Kimi Coding API (Anthropic格式)
        # 详细的API配置诊断日志
        print("\n" + "="*60)
        print("Kimi API 配置诊断")
        print("="*60)
        print(f"API Key 是否存在: {'是' if self.kimi_api_key else '否'}")
        if self.kimi_api_key:
            masked_key = self.kimi_api_key[:8] + "..." + self.kimi_api_key[-4:] if len(self.kimi_api_key) > 12 else "***"
            print(f"API Key: {masked_key}")
        print(f"Base URL: {self.kimi_base_url}")
        print(f"Model: {self.kimi_model}")
        print(f"Timeout: {self.timeout}秒")
        print("="*60 + "\n")
        
        if not self.kimi_api_key:
            print("❌ 错误: 未设置 Kimi API Key")
            print("请设置环境变量: export KIMI_CODING_API_KEY='your-api-key'")
            print("或: export KIMI_API_KEY='your-api-key'")
            return None
        
        if self.kimi_api_key:
            try:
                print("尝试使用 Kimi Coding API...")
                try:
                    from anthropic import Anthropic
                except ImportError:
                    print("⚠️ anthropic库未安装，尝试安装...")
                    import subprocess
                    subprocess.check_call([sys.executable, "-m", "pip", "install", "anthropic", "-q"])
                    from anthropic import Anthropic
                    print("✅ anthropic库安装成功")
                
                client = Anthropic(
                    api_key=self.kimi_api_key,
                    base_url=self.kimi_base_url,
                    timeout=self.timeout  # 添加超时设置
                )
                
                # 使用streaming模式处理长请求
                print(f"使用streaming模式调用Kimi API (超时: {self.timeout}秒)...")
                
                # 添加信号处理，防止无限等待
                import signal
                
                def timeout_handler(signum, frame):
                    raise TimeoutError(f"Kimi API调用超时 (>{self.timeout}秒)")
                
                max_retries = 5
                for retry in range(max_retries):
                    try:
                        signal.signal(signal.SIGALRM, timeout_handler)
                        signal.alarm(self.timeout)
                    except (AttributeError, ValueError):
                        pass
                    
                    try:
                        with client.messages.stream(
                            model="k2p5",
                            max_tokens=32768,
                            messages=[{
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": prompt},
                                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64_image}}
                                ]
                            }]
                        ) as stream:
                            html_content = ""
                            chunk_count = 0
                            last_update = time.time()
                            
                            for text in stream.text_stream:
                                html_content += text
                                chunk_count += 1
                                
                                if time.time() - last_update > 10:
                                    print(f"  已接收 {chunk_count} 个数据块，内容长度: {len(html_content)} 字符")
                                    last_update = time.time()
                                
                                if hasattr(signal, 'SIGALRM'):
                                    remaining = signal.alarm(0)
                                    if remaining <= 0:
                                        raise TimeoutError("Kimi API调用超时")
                                    signal.alarm(remaining)
                        
                        try:
                            signal.alarm(0)
                        except:
                            pass
                        
                        html_content = self._clean_html_response(html_content)
                        print(f"✅ Kimi Coding API 调用成功 (接收 {chunk_count} 个数据块，共 {len(html_content)} 字符)")
                        return html_content
                        
                    except (TimeoutError, Exception) as e:
                        try:
                            signal.alarm(0)
                        except:
                            pass
                        error_str = str(e)
                        is_rate_limit = '429' in error_str or 'rate_limit' in error_str
                        is_timeout = isinstance(e, TimeoutError) or '超时' in error_str
                        
                        if is_rate_limit or is_timeout:
                            wait_time = 60 * (retry + 1)
                            if retry < max_retries - 1:
                                reason = "限流(429)" if is_rate_limit else "超时"
                                print(f"⚠️ Kimi API{reason}，第{retry+1}/{max_retries}次重试，等待{wait_time}秒...")
                                time.sleep(wait_time)
                                continue
                            else:
                                reason = "限流(429)" if is_rate_limit else "超时"
                                print(f"⚠️ Kimi API{reason}，已重试{max_retries}次，放弃")
                        else:
                            print(f"⚠️ Kimi Coding API 失败: {e}")
                            import traceback
                            traceback.print_exc()
                            break
            except Exception as e:
                print(f"⚠️ Kimi Coding API 初始化失败: {e}")
        
        # 尝试方案2: OpenClaw API转发
        openclaw_api_key = os.environ.get('OPENCLAW_API_KEY')
        if openclaw_api_key:
            try:
                print("尝试使用 OpenClaw API转发...")
                html_content = self._call_openclaw_api(base64_image, prompt)
                if html_content:
                    print("✅ OpenClaw API 调用成功")
                    return html_content
            except Exception as e:
                print(f"⚠️ OpenClaw API 失败: {e}")
        
        # 尝试方案3: Moonshot通用API (OpenAI格式)
        moonshot_key = os.environ.get('MOONSHOT_API_KEY')
        if moonshot_key:
            try:
                print("尝试使用 Moonshot API...")
                try:
                    from openai import OpenAI
                except ImportError:
                    print("⚠️ openai库未安装，尝试安装...")
                    import subprocess
                    subprocess.check_call([sys.executable, "-m", "pip", "install", "openai", "-q"])
                    from openai import OpenAI
                    print("✅ openai库安装成功")
                
                client = OpenAI(api_key=moonshot_key, base_url="https://api.moonshot.cn/v1")
                
                response = client.chat.completions.create(
                    model="kimi-k2.5",
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                        ]
                    }],
                    temperature=1,
                    max_tokens=32768
                )
                
                html_content = response.choices[0].message.content
                html_content = self._clean_html_response(html_content)
                print("✅ Moonshot API 调用成功")
                return html_content
                
            except Exception as e:
                print(f"⚠️ Moonshot API 失败: {e}")
        
        # 所有方案都失败
        print("❌ 所有API方案都失败，使用基础分析")
        return None
    
    def _call_openclaw_api(self, base64_image, prompt):
        """调用OpenClaw API转发请求"""
        try:
            import requests
            
            openclaw_api_key = os.environ.get('OPENCLAW_API_KEY')
            openclaw_base_url = os.environ.get('OPENCLAW_BASE_URL', 'https://api.openclaw.dev/v1')
            
            headers = {
                'Authorization': f'Bearer {openclaw_api_key}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'model': 'kimi-k2.5',
                'messages': [{
                    'role': 'user',
                    'content': [
                        {'type': 'text', 'text': prompt},
                        {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{base64_image}'}}
                    ]
                }],
                'max_tokens': 32768
            }
            
            response = requests.post(
                f'{openclaw_base_url}/chat/completions',
                headers=headers,
                json=payload,
                timeout=300
            )
            
            if response.status_code == 200:
                result = response.json()
                html_content = result['choices'][0]['message']['content']
                return self._clean_html_response(html_content)
            else:
                print(f"OpenClaw API 错误: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"OpenClaw API 调用异常: {e}")
            return None
    
    def _clean_html_response(self, html_content):
        """清理HTML响应"""
        html_content = html_content.replace('```html', '').replace('```', '').strip()
        if '<!DOCTYPE html>' in html_content:
            html_content = html_content[html_content.find('<!DOCTYPE html>'):]
        elif '<html' in html_content:
            html_content = html_content[html_content.find('<html'):]
        return html_content
    
    def fix_html_with_kimi(self, html_content, fix_prompt, colors):
        """使用Kimi修复HTML中的问题"""
        try:
            if not self.kimi_api_key:
                print("⚠️ 没有Kimi API密钥，无法修复")
                return None
            
            from anthropic import Anthropic
            
            client = Anthropic(
                api_key=self.kimi_api_key,
                base_url=self.kimi_base_url
            )
            
            # 构造修复提示词
            full_prompt = f"""{fix_prompt}

【颜色参考】
{colors}

【重要提醒】
- 只修复上述问题，不要修改其他内容
- 保持HTML结构完整
- 保持文字内容不变
- 返回完整的修复后HTML代码
- 不要添加任何解释
"""
            
            print("  使用streaming模式调用Kimi API进行修复...")
            
            with client.messages.stream(
                model=self.kimi_model,
                max_tokens=32768,
                messages=[{
                    "role": "user",
                    "content": full_prompt
                }]
            ) as stream:
                fixed_html = ""
                for text in stream.text_stream:
                    fixed_html += text
            
            fixed_html = self._clean_html_response(fixed_html)
            print("  ✅ Kimi修复调用成功")
            return fixed_html
            
        except Exception as e:
            print(f"  ⚠️ Kimi修复失败: {e}")
            return None
    
    def optimize_html(self, html, layout, elements, low_ssim_regions=None):
        """优化HTML代码，针对SSIM低的区域进行改进"""
        try:
            if not low_ssim_regions:
                print("没有低SSIM区域需要优化")
                return html
            
            print(f"发现 {len(low_ssim_regions)} 个低SSIM区域，开始针对性优化...")
            
            # 分析低SSIM区域的问题
            for i, region in enumerate(low_ssim_regions):
                print(f"区域 {i+1}: 位置=({region['x']}, {region['y']}), 大小={region['width']}x{region['height']}, SSIM={region['ssim']:.4f}")
            
            # 针对低SSIM区域进行优化（传入原图路径）
            optimized_html = self.optimize_regions(html, low_ssim_regions, layout, elements, self.image_path)
            
            return optimized_html
        except Exception as e:
            print(f"HTML优化失败: {e}")
            return html
    
    def optimize_regions(self, html, low_ssim_regions, layout, elements, image_path):
        """针对低SSIM区域进行精确优化
        
        策略：
        1. 只修改低SSIM区域的CSS，不改动HTML结构
        2. 基于原图截图和位置信息精确定位
        3. 严格约束：只调整样式属性，不增删元素
        """
        try:
            import base64
            
            # 只处理最低的一个区域（避免过度修改）
            if not low_ssim_regions:
                return html
            
            target_region = low_ssim_regions[0]  # 只处理SSIM最低的区域
            
            # 找出该区域内的元素
            region_elements = []
            for element in elements:
                x1, y1, x2, y2 = element['bbox']
                # 检查元素是否与区域有重叠
                if (x1 < target_region['x'] + target_region['width'] and
                    x2 > target_region['x'] and
                    y1 < target_region['y'] + target_region['height'] and
                    y2 > target_region['y']):
                    region_elements.append(element)
            
            # 提取区域相关的CSS（简化版，实际应该解析CSS）
            # 这里我们让Kimi基于位置和原图来识别需要修改的样式
            
            # 读取原图并裁剪出低SSIM区域
            with open(image_path, 'rb') as f:
                image_data = f.read()
                base64_image = base64.b64encode(image_data).decode('utf-8')
            
            # 构造精确的优化提示词
            optimize_prompt = f"""【局部CSS优化任务】

请针对以下特定区域进行CSS样式微调。

【目标区域信息】
- 位置：({target_region['x']}, {target_region['y']})
- 大小：{target_region['width']}x{target_region['height']}像素
- 当前SSIM：{target_region['ssim']:.4f}
- 区域内检测到的元素：{len(region_elements)}个
{chr(10).join([f"  - {e.get('type', 'unknown')}: ({e['bbox'][0]},{e['bbox'][1]})-{e['bbox'][2]}x{e['bbox'][3]}" for e in region_elements[:5]])}

【优化要求】
1. 针对低SSIM区域进行精确调整
2. 可以修改CSS样式、调整元素位置、增删元素以匹配原图
3. 确保调整后的区域与原图一致
4. 保持整体页面结构稳定
5. 禁止添加动画或交互效果

【当前HTML代码】（完整代码）
{html}

【优化目标】
基于提供的原图截图，调整目标区域的CSS样式，使其与原图更一致。

请返回完整的HTML代码，只修改必要的CSS样式。"""
            
            # 调用Kimi进行优化 - 使用与analyze_with_kimi相同的配置
            if self.kimi_api_key and region_elements:
                try:
                    from anthropic import Anthropic
                    
                    client = Anthropic(
                        api_key=self.kimi_api_key,
                        base_url=self.kimi_base_url
                    )
                    
                    response = client.messages.create(
                        model="k2p5",
                        max_tokens=16384,
                        messages=[
                            {
                                "role": "user",
                                "content": optimize_prompt
                            }
                        ]
                    )
                    optimized_html = response.content[0].text
                except Exception as e:
                    print(f"Anthropic API调用失败，尝试OpenAI格式: {e}")
                    # 回退到OpenAI格式
                    client = OpenAI(
                        api_key=self.kimi_api_key,
                        base_url=self.kimi_base_url
                    )
                    
                    response = client.chat.completions.create(
                        model="kimi-k2.5",
                        messages=[
                            {
                                "role": "user",
                                "content": optimize_prompt
                            }
                        ],
                        temperature=0.1,
                        max_tokens=16384,
                        stream=False
                    )
                    optimized_html = response.choices[0].message.content
                
                # 清理可能的markdown代码块标记和分析文本
                optimized_html = optimized_html.replace('```html', '').replace('```', '').strip()
                
                # 提取HTML代码（去除前面的分析文本）
                if '<!DOCTYPE html>' in optimized_html:
                    optimized_html = optimized_html[optimized_html.find('<!DOCTYPE html>'):]
                elif '<html' in optimized_html:
                    optimized_html = optimized_html[optimized_html.find('<html'):]
                
                print(f"已针对目标区域进行CSS优化")
                return optimized_html
            
            return html
        except Exception as e:
            print(f"区域优化失败: {e}")
            return html
    
    def optimize_by_code(self, html, low_ssim_regions, elements, image_path):
        """
        基于代码的局部优化 - 新方案
        1. 找出低SSIM区域对应的HTML元素
        2. 提取这些元素的代码片段
        3. 让Kimi优化这些具体代码
        4. 替换回原HTML
        """
        try:
            if not low_ssim_regions or not elements:
                return html
            
            print(f"\n🔧 开始基于代码的局部优化...")
            
            # 为每个低SSIM区域找到对应的元素
            region_code_map = []
            
            for region in low_ssim_regions[:3]:  # 只处理前3个区域
                # 找到区域内的元素
                region_elements = []
                for elem in elements:
                    x1, y1, x2, y2 = elem['bbox']
                    # 检查元素是否在区域内
                    if (x1 >= region['x'] - 20 and 
                        y1 >= region['y'] - 20 and
                        x2 <= region['x'] + region['width'] + 20 and
                        y2 <= region['y'] + region['height'] + 20):
                        region_elements.append(elem)
                
                if region_elements:
                    region_code_map.append({
                        'region': region,
                        'elements': region_elements,
                        'ssim': region['ssim']
                    })
            
            if not region_code_map:
                print("  未找到需要优化的代码区域")
                return html
            
            print(f"  找到 {len(region_code_map)} 个需要优化的代码区域")
            
            # 提取这些区域相关的CSS代码
            css_blocks = self._extract_css_for_regions(html, region_code_map)
            
            if not css_blocks:
                print("  未提取到可优化的CSS代码")
                return html
            
            # 生成优化提示词
            optimize_prompt = self._generate_code_optimize_prompt(html, css_blocks, region_code_map, image_path)
            
            # 调用Kimi进行优化
            print("  调用Kimi优化代码...")
            optimized_css = self._call_kimi_for_css_optimize(optimize_prompt)
            
            if optimized_css:
                # 替换原HTML中的CSS
                new_html = self._replace_css_in_html(html, css_blocks, optimized_css)
                print("  ✅ 代码优化完成")
                return new_html
            else:
                print("  ⚠️ 代码优化失败，使用原版本")
                return html
                
        except Exception as e:
            print(f"  基于代码的优化失败: {e}")
            return html
    
    def _extract_css_for_regions(self, html, region_code_map):
        """提取与区域相关的CSS代码块"""
        import re
        
        css_blocks = []
        
        # 提取所有CSS规则
        style_matches = re.findall(r'<style[^>]*>(.*?)</style>', html, re.DOTALL | re.IGNORECASE)
        
        for style_content in style_matches:
            # 提取CSS规则（简化处理）
            rules = re.findall(r'([^{]+)\{([^}]+)\}', style_content)
            for selector, properties in rules:
                selector = selector.strip()
                # 检查是否与区域元素相关（通过类名或ID）
                for region_data in region_code_map:
                    for elem in region_data['elements']:
                        elem_type = elem['type'].lower()
                        # 简单的匹配逻辑
                        if any(keyword in selector.lower() for keyword in 
                               [elem_type, 'button', 'card', 'modal', 'dialog', 'popup', 'share']):
                            css_blocks.append({
                                'selector': selector,
                                'properties': properties.strip(),
                                'full_rule': f"{selector} {{{properties}}}"
                            })
                            break
        
        # 去重
        seen = set()
        unique_blocks = []
        for block in css_blocks:
            if block['selector'] not in seen:
                seen.add(block['selector'])
                unique_blocks.append(block)
        
        return unique_blocks[:10]  # 最多10个CSS块
    
    def _generate_code_optimize_prompt(self, html, css_blocks, region_code_map, image_path):
        """生成代码优化提示词"""
        
        prompt = f"""【CSS代码优化任务】

原图路径: {image_path}

以下CSS代码区域的还原度较低（SSIM分数低），请优化这些CSS代码以提高还原度：

"""
        
        # 添加区域信息
        for i, region_data in enumerate(region_code_map, 1):
            region = region_data['region']
            prompt += f"\n## 低SSIM区域 {i}:\n"
            prompt += f"- 位置: ({region['x']}, {region['y']})\n"
            prompt += f"- 大小: {region['width']}x{region['height']}\n"
            prompt += f"- SSIM分数: {region['ssim']:.4f}\n"
            prompt += f"- 包含元素: {', '.join(set(e['type'] for e in region_data['elements'][:5]))}\n"
        
        prompt += "\n## 需要优化的CSS代码:\n\n```css\n"
        for block in css_blocks:
            prompt += f"{block['full_rule']}\n\n"
        prompt += "```\n"
        
        prompt += f"""
## 优化要求:
1. **只修改CSS属性值**，不要修改选择器
2. **不要添加新的CSS规则**
3. **不要删除现有属性**，只调整值
4. **重点调整**: 颜色、尺寸、位置、间距、边框等
5. **参考原图**: 根据截图调整样式使其更匹配

## 当前完整HTML:
```html
{html[:5000]}...
```

## 返回格式:
请返回优化后的CSS代码，格式如下:
```css
selector1 {{
    property1: value1;
    property2: value2;
}}

selector2 {{
    property1: value1;
    property2: value2;
}}
```

只返回CSS代码，不要其他解释。
"""
        return prompt
    
    def _call_kimi_for_css_optimize(self, prompt):
        """调用Kimi优化CSS"""
        try:
            import re
            from anthropic import Anthropic
            
            client = Anthropic(
                api_key=self.kimi_api_key,
                base_url=self.kimi_base_url
            )
            
            print("    使用streaming模式调用Kimi API...")
            
            with client.messages.stream(
                model=self.kimi_model,
                max_tokens=16384,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            ) as stream:
                response_text = ""
                for text in stream.text_stream:
                    response_text += text
            
            # 提取CSS代码
            css_match = re.search(r'```css(.*?)```', response_text, re.DOTALL)
            if css_match:
                return css_match.group(1).strip()
            
            # 如果没有代码块标记，尝试直接返回
            return response_text.strip()
            
        except Exception as e:
            print(f"    Kimi CSS优化调用失败: {e}")
            return None
    
    def _replace_css_in_html(self, html, old_css_blocks, new_css):
        """将优化后的CSS替换回原HTML"""
        import re
        
        new_html = html
        
        # 解析新的CSS
        new_rules = re.findall(r'([^{]+)\{([^}]+)\}', new_css)
        
        for selector, new_properties in new_rules:
            selector = selector.strip()
            # 在HTML中查找并替换对应的CSS规则
            pattern = rf'({re.escape(selector)}\s*\{{)[^}}]*(\}})'
            replacement = rf'\1{new_properties}\2'
            new_html = re.sub(pattern, replacement, new_html, flags=re.IGNORECASE)
        
        return new_html
    
    def generate_html(self, text, layout):
        """生成HTML代码"""
        # 基本HTML结构
        html_template = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>页面截图转换结果</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 0;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }}
        h1 {{
            color: #333;
            font-size: 24px;
            margin-bottom: 20px;
        }}
        .button {{
            background-color: #4CAF50;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
        }}
        .input {{
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
            width: 100%;
            margin-bottom: 10px;
        }}
        .text-content {{
            background-color: white;
            padding: 20px;
            border-radius: 4px;
            margin-bottom: 20px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>页面截图转换结果</h1>
        <div class="text-content">
            <pre>{text}</pre>
        </div>
        <form>
            <input type="text" class="input" placeholder="请输入内容">
            <button type="submit" class="button">提交</button>
        </form>
    </div>
</body>
</html>
"""
        
        return html_template
    
    def save_html(self, html_content):
        """保存HTML文件，并自动调整缩放比例以适合浏览器显示"""
        try:
            # 1. 将 scale(3) 替换为 scale(0.5)，让页面在浏览器中显示更合适
            html_content = html_content.replace('transform: scale(3)', 'transform: scale(0.5)')
            
            # 2. 添加响应式媒体查询，让页面在不同屏幕尺寸下都能正常显示
            # 找到 .page-container 的样式结束位置
            page_container_pattern = r'(\.page-container\s*\{[^}]*\})'
            import re
            
            # 定义要添加的响应式媒体查询
            responsive_css = '''
        
        /* 响应式适配 - 让页面在浏览器中更合适地显示 */
        @media (max-width: 800px) {
            .page-container {
                transform: scale(0.4);
            }
        }

        @media (max-width: 600px) {
            .page-container {
                transform: scale(0.3);
            }
        }'''
            
            # 在 .page-container 样式后添加响应式CSS
            def add_responsive_css(match):
                return match.group(1) + responsive_css
            
            html_content = re.sub(page_container_pattern, add_responsive_css, html_content)
            
            with open(self.output_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            print(f"HTML文件已保存到: {self.output_path}")
        except Exception as e:
            print(f"保存HTML文件失败: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    
    def run(self):
        """执行转换过程"""
        print(f"开始处理图像: {self.image_path}")
        
        # 预处理图像
        image, gray_image = self.preprocess_image()
        
        # 获取图像尺寸
        image_size = (image.width, image.height)
        print(f"图像尺寸: {image_size[0]}x{image_size[1]}")
        
        # 并行执行文本提取、颜色提取和元素检测
        from concurrent.futures import ThreadPoolExecutor
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            text_future = executor.submit(self.extract_text, gray_image)
            colors_future = executor.submit(self.extract_colors, image)
            elements_future = executor.submit(self.detect_elements, self.image_path)
            
            text = text_future.result()
            colors = colors_future.result()
            elements = elements_future.result()
        
        print(f"文本提取完成（长度: {len(text)} 字符），颜色提取完成，检测到 {len(elements)} 个元素")
        
        text_blocks = self.extract_text_with_positions(image)
        
        icons = []
        
        filtered_elements = []
        for elem in elements:
            x1, y1, x2, y2 = elem['bbox']
            width = x2 - x1
            height = y2 - y1
            
            if elem['confidence'] < 0.3:
                continue
            if width < 10 or height < 10:
                continue
            if width > self.original_width * 0.9 or height > self.original_height * 0.9:
                continue
            
            elem_type = elem['type'].lower()
            is_valid_type = any(t in elem_type for t in [
                'button', 'text', 'input', 'icon', 'arrow', 'checkbox', 'radio',
                'switch', 'card', 'modal', 'dialog', 'menu', 'tab', 'badge',
                'tag', 'image', 'container', 'box', 'header', 'footer', 'nav',
                'div', 'span', 'p', 'label', 'link', 'list', 'item', 'cell',
                'row', 'col', 'grid', 'section', 'article', 'aside', 'main',
                'ul', 'ol', 'li', 'table', 'tr', 'td', 'th', 'form', 'field'
            ])
            
            if not is_valid_type and elem['confidence'] < 0.5:
                continue
            
            filtered_elements.append(elem)
        
        print(f"过滤后剩余 {len(filtered_elements)} 个有效元素")
        
        structured_layout = self.build_structured_layout(image, filtered_elements, text_blocks)
        
        # 保存结构化布局分析结果
        self.save_structured_layout(self.image_path, structured_layout)
        
        structured_layout_text = self.format_structured_layout(structured_layout)
        
        element_info = ""
        sorted_elements = sorted(filtered_elements, key=lambda x: x['confidence'], reverse=True)[:2000]
        
        for i, element in enumerate(sorted_elements):
            x1, y1, x2, y2 = element['bbox']
            element_type = element['type']
            element_info += f"\n元素{i}:类型={element_type},位置=({x1:.0f},{y1:.0f},{x2:.0f},{y2:.0f}),置信度={element['confidence']:.2f}"
        
        element_info += f"\n\n【注意】以上元素信息已整合到下方结构化布局中，请优先参考结构化布局信息。"
        
        layout_info = structured_layout_text
        
        alignment_info = ""
        
        if self.original_width >= 1000:
            logical_height = self.original_height // 3
        elif self.original_width >= 700:
            logical_height = self.original_height // 2
        else:
            logical_height = self.original_height
        
        # 如果使用Kimi K2.5多模态模型
        html_content = None
        if self.use_kimi:
            print("使用Kimi K2.5多模态模型进行分析...")
            try:
                html_content = self.analyze_with_kimi(self.image_path, text, elements, element_info, layout_info, alignment_info, colors)
                
                if html_content:
                    print("✅ Kimi分析完成")
                else:
                    print("⚠️ Kimi返回空内容，将回退到基础分析")
                    html_content = None
            except Exception as e:
                print(f"⚠️ Kimi API调用失败: {e}")
                print("将回退到基础分析模式...")
                html_content = None
        
        # 如果没有使用Kimi或Kimi失败，报错终止（不自动回退到基础分析）
        if html_content is None:
            error_msg = "Kimi API调用失败，无法生成HTML。请检查:\n"
            error_msg += "1. API Key是否设置正确 (KIMI_CODING_API_KEY 或 KIMI_API_KEY)\n"
            error_msg += "2. 网络连接是否正常\n"
            error_msg += "3. API服务是否可用\n"
            error_msg += "\n如需使用基础分析模式，请添加 --no-kimi 参数"
            print(f"❌ {error_msg}")
            raise Exception("Kimi API调用失败，无法生成HTML")
        
        # Kimi 成功，继续处理
        # 【Debug】保存Kimi原始输出
        if self.debug:
            debug_raw_path = self.output_path.replace('.html', '_debug_1_kimi_raw.html')
            with open(debug_raw_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            print(f"  [Debug] Kimi原始输出已保存: {debug_raw_path}")
        
        # 后处理：检测问题（不直接修改HTML）
        html_content, issues, fix_prompt = HTMLPostProcessor.process(html_content, colors, logical_height)
        
        # 【Debug】保存后处理后输出
        if self.debug:
            debug_post_path = self.output_path.replace('.html', '_debug_2_after_post.html')
            with open(debug_post_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            print(f"  [Debug] 后处理后输出已保存: {debug_post_path}")
        
        # 如果检测到问题，让Kimi重新生成
        if issues and fix_prompt:
            print(f"\n⚠️ 检测到 {len(issues)} 个问题，需要重新生成...")
            for i, issue in enumerate(issues, 1):
                print(f"  {i}. {issue}")
            
            # 使用修复提示词重新调用Kimi
            print("\n调用Kimi修复问题...")
            original_html = html_content
            html_content = self.fix_html_with_kimi(html_content, fix_prompt, colors)
            
            if html_content:
                print("✅ 修复完成")
                # 再次检测
                html_content, issues, _ = HTMLPostProcessor.process(html_content, colors, logical_height)
                if issues:
                    print(f"  ⚠️ 修复后仍有问题: {issues}")
                else:
                    print("  ✓ 问题已解决")
            else:
                print("❌ 修复失败，使用原版本")
                html_content = original_html
        
        # 保存HTML
        self.save_html(html_content)
        
        # 渲染HTML并截图
        rendered_image_path = os.path.join(self.output_dir, "rendered.png")
        print("渲染HTML并截图...")
        if self.render_html_and_capture(self.output_path, rendered_image_path, image_size):
            # 计算整体SSIM
            ssim_score = self.calculate_ssim(self.image_path, rendered_image_path)
            print(f"整体SSIM得分: {ssim_score:.4f}")
            
            # 检查SSIM是否达标
            if ssim_score >= 0.95:
                print("✅ SSIM得分≥0.95，处理完成!")
            else:
                print(f"⚠️ SSIM得分{ssim_score:.4f}<0.95，处理完成")
                print("处理完成，建议手动调整HTML以提高相似度")
        else:
            print("❌ HTML渲染失败，无法计算SSIM")
        
        print("处理完成!")

def process_single_image(image_path, output_dir, use_kimi=True, accuracy="medium", timeout=120):
    """处理单张图片"""
    try:
        print(f"\n{'='*60}")
        print(f"处理图片: {image_path}")
        print(f"模式: {'Kimi AI' if use_kimi else '基础分析'}")
        print(f"超时: {timeout}秒")
        print(f"{'='*60}")
        
        # 创建实例并运行
        converter = ScreenshotToHTML(
            image_path=image_path,
            output_dir=output_dir,
            use_kimi=use_kimi,
            accuracy=accuracy,
            timeout=timeout
        )
        
        converter.run()
        return True
    except KeyboardInterrupt:
        print(f"\n⚠️ 用户中断处理: {image_path}")
        return False
    except Exception as e:
        print(f"❌ 处理失败 {image_path}: {e}")
        import traceback
        traceback.print_exc()
        return False

def batch_process(input_dir, output_dir, use_kimi=True, accuracy="medium", timeout=120):
    """批量处理目录中的所有图片"""
    valid_extensions = ['.png', '.jpg', '.jpeg', '.webp']
    
    # 获取所有图片文件
    image_files = []
    for ext in valid_extensions:
        image_files.extend(glob.glob(os.path.join(input_dir, f"*{ext}")))
        image_files.extend(glob.glob(os.path.join(input_dir, f"*{ext.upper()}")))
    
    if not image_files:
        print(f"错误: 在目录 {input_dir} 中没有找到图片文件")
        return
    
    print(f"找到 {len(image_files)} 个图片文件")
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 批量处理
    success_count = 0
    fail_count = 0
    
    for i, image_path in enumerate(image_files, 1):
        print(f"\n[{i}/{len(image_files)}] 处理中...")
        if process_single_image(image_path, output_dir, use_kimi, accuracy, timeout):
            success_count += 1
        else:
            fail_count += 1
    
    print(f"\n{'='*60}")
    print(f"批量处理完成!")
    print(f"成功: {success_count}/{len(image_files)}")
    print(f"失败: {fail_count}/{len(image_files)}")
    print(f"输出目录: {output_dir}")
    print(f"{'='*60}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="将页面截图转换为HTML代码")
    parser.add_argument("--image", help="截图文件路径")
    parser.add_argument("--input-dir", help="批量处理：输入目录路径")
    parser.add_argument("--output", help="输出HTML文件路径（单文件模式）")
    parser.add_argument("--output-dir", help="输出目录")
    parser.add_argument("--no-kimi", action="store_true", help="禁用Kimi模型，使用基础分析（默认启用Kimi）")
    parser.add_argument("--accuracy", choices=["low", "medium", "high"], default="medium", help="识别精度")
    parser.add_argument("--ssim-threshold", type=float, default=0.95, help="SSIM阈值，默认0.95")
    parser.add_argument("--timeout", type=int, default=120, help="API调用超时时间（秒），默认120秒")
    
    args = parser.parse_args()
    
    # 批量处理模式
    if args.input_dir:
        if not os.path.isdir(args.input_dir):
            print(f"错误: 输入目录不存在: {args.input_dir}")
            sys.exit(1)
        
        output_dir = args.output_dir or os.path.join(args.input_dir, "output")
        batch_process(args.input_dir, output_dir, not args.no_kimi, args.accuracy, args.timeout)
        sys.exit(0)
    
    # 单文件处理模式
    if not args.image:
        print("错误: 请指定 --image 或 --input-dir 参数")
        parser.print_help()
        sys.exit(1)
    
    # 检查图像文件是否存在
    if not os.path.exists(args.image):
        print(f"错误: 图像文件不存在: {args.image}")
        sys.exit(1)
    
    # 检查图像文件格式
    valid_extensions = ['.png', '.jpg', '.jpeg', '.webp']
    ext = os.path.splitext(args.image)[1].lower()
    if ext not in valid_extensions:
        print(f"错误: 不支持的图像格式: {ext}")
        print(f"支持的格式: {', '.join(valid_extensions)}")
        sys.exit(1)
    
    # 创建实例并运行
    converter = ScreenshotToHTML(
        image_path=args.image,
        output_path=args.output,
        output_dir=args.output_dir,
        use_kimi=not args.no_kimi,  # 默认启用Kimi，使用--no-kimi禁用
        accuracy=args.accuracy,
        timeout=args.timeout
    )
    
    converter.run()
