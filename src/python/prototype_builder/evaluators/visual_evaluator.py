"""
视觉质量评估器
对比原始页面和重建页面的视觉相似度
"""

import numpy as np
from typing import Dict, List, Tuple, Optional
from pathlib import Path
from dataclasses import dataclass

from ..core.build_result import QualityMetrics


@dataclass
class ElementInfo:
    """元素信息"""
    tag: str
    x: float
    y: float
    width: float
    height: float
    text: str = ""
    class_name: str = ""


class VisualEvaluator:
    """视觉评估器"""
    
    def __init__(self):
        self.ssim_threshold = 0.95
        self.layout_weight = 0.30
        self.element_weight = 0.30
        self.style_weight = 0.15
        self.ssim_weight = 0.25
    
    def evaluate(self, 
                 original_screenshot: Path,
                 prototype_html: Path) -> QualityMetrics:
        """
        评估原型质量
        
        Args:
            original_screenshot: 原始页面截图
            prototype_html: 原型 HTML 文件
            
        Returns:
            质量指标
        """
        metrics = QualityMetrics()
        
        # 1. 生成原型截图
        prototype_screenshot = self._generate_screenshot(prototype_html)
        if not prototype_screenshot:
            return metrics
        
        # 2. 计算 SSIM
        metrics.ssim_score = self._calculate_ssim(
            original_screenshot, 
            prototype_screenshot
        )
        
        # 3. 提取并对比元素
        original_elements = self._extract_elements(original_screenshot)
        prototype_elements = self._extract_elements(prototype_screenshot)
        
        # 4. 计算布局相似度
        metrics.layout_score = self._compare_layout(
            original_elements, 
            prototype_elements
        )
        
        # 5. 计算元素完整性
        metrics.element_score = self._compare_elements(
            original_elements, 
            prototype_elements
        )
        
        # 6. 计算样式一致性
        metrics.style_score = self._compare_styles(
            original_screenshot,
            prototype_screenshot
        )
        
        # 7. 综合评分
        metrics.overall_score = (
            metrics.ssim_score * self.ssim_weight +
            metrics.layout_score * self.layout_weight +
            metrics.element_score * self.element_weight +
            metrics.style_score * self.style_weight
        )
        
        return metrics
    
    def _generate_screenshot(self, html_path: Path) -> Optional[Path]:
        """生成 HTML 的截图"""
        try:
            from playwright.sync_api import sync_playwright
            
            output_path = html_path.parent / f"{html_path.stem}_screenshot.png"
            
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={'width': 1920, 'height': 1080})
                page.goto(f"file://{html_path.absolute()}")
                page.wait_for_load_state('networkidle')
                page.screenshot(path=str(output_path), full_page=True)
                browser.close()
            
            return output_path
        except Exception as e:
            print(f"[VisualEvaluator] 生成截图失败: {e}")
            return None
    
    def _calculate_ssim(self, 
                       image1_path: Path, 
                       image2_path: Path) -> float:
        """
        计算 SSIM（结构相似度）
        
        Returns:
            相似度分数 (0-1)
        """
        try:
            from skimage.metrics import structural_similarity as ssim
            from PIL import Image
            
            # 加载图像
            img1 = Image.open(image1_path).convert('RGB')
            img2 = Image.open(image2_path).convert('RGB')
            
            # 统一尺寸
            size = (1920, 1080)
            img1 = img1.resize(size)
            img2 = img2.resize(size)
            
            # 转换为 numpy 数组
            arr1 = np.array(img1)
            arr2 = np.array(img2)
            
            # 计算 SSIM
            score, _ = ssim(arr1, arr2, multichannel=True, full=True, channel_axis=2)
            
            return float(score)
        except Exception as e:
            print(f"[VisualEvaluator] SSIM 计算失败: {e}")
            return 0.0
    
    def _extract_elements(self, screenshot_path: Path) -> List[ElementInfo]:
        """
        从截图中提取元素信息
        使用计算机视觉或 DOM 分析
        """
        elements = []
        
        try:
            # 这里可以使用更复杂的 CV 模型
            # 简化实现：基于 OCR 提取文本块作为元素
            import pytesseract
            from PIL import Image
            
            img = Image.open(screenshot_path)
            
            # OCR 提取文本和位置
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            
            for i, text in enumerate(data['text']):
                if text.strip() and int(data['conf'][i]) > 60:
                    element = ElementInfo(
                        tag="text",
                        x=float(data['left'][i]),
                        y=float(data['top'][i]),
                        width=float(data['width'][i]),
                        height=float(data['height'][i]),
                        text=text.strip()
                    )
                    elements.append(element)
            
        except Exception as e:
            print(f"[VisualEvaluator] 元素提取失败: {e}")
        
        return elements
    
    def _compare_layout(self, 
                       elements1: List[ElementInfo], 
                       elements2: List[ElementInfo]) -> float:
        """
        对比布局相似度
        
        基于元素的空间分布和相对位置
        """
        if not elements1 or not elements2:
            return 0.0
        
        # 计算布局特征
        def get_layout_features(elements):
            if not elements:
                return None
            
            # 计算边界框
            xs = [e.x for e in elements]
            ys = [e.y for e in elements]
            widths = [e.width for e in elements]
            heights = [e.height for e in elements]
            
            return {
                'min_x': min(xs),
                'max_x': max(xs) + max(widths),
                'min_y': min(ys),
                'max_y': max(ys) + max(heights),
                'center_x': np.mean([e.x + e.width/2 for e in elements]),
                'center_y': np.mean([e.y + e.height/2 for e in elements]),
                'count': len(elements)
            }
        
        features1 = get_layout_features(elements1)
        features2 = get_layout_features(elements2)
        
        if not features1 or not features2:
            return 0.0
        
        # 计算相似度
        similarities = []
        
        # 元素数量相似度
        count_sim = min(features1['count'], features2['count']) / max(features1['count'], features2['count'])
        similarities.append(count_sim)
        
        # 中心点相似度
        center_sim = 1.0 - min(
            abs(features1['center_x'] - features2['center_x']) / 1920,
            abs(features1['center_y'] - features2['center_y']) / 1080
        )
        similarities.append(max(0, center_sim))
        
        return np.mean(similarities)
    
    def _compare_elements(self,
                         elements1: List[ElementInfo],
                         elements2: List[ElementInfo]) -> float:
        """
        对比元素完整性
        
        检查关键元素是否都存在
        """
        if not elements1:
            return 0.0
        
        if not elements2:
            return 0.0
        
        # 提取文本内容
        texts1 = set(e.text.lower() for e in elements1 if e.text)
        texts2 = set(e.text.lower() for e in elements2 if e.text)
        
        if not texts1:
            return 0.0
        
        # 计算文本匹配度
        matched = texts1 & texts2
        coverage = len(matched) / len(texts1)
        
        return coverage
    
    def _compare_styles(self,
                       image1_path: Path,
                       image2_path: Path) -> float:
        """
        对比样式一致性
        
        基于颜色分布和整体视觉风格
        """
        try:
            from PIL import Image
            import colorsys
            
            img1 = Image.open(image1_path).convert('RGB')
            img2 = Image.open(image2_path).convert('RGB')
            
            # 统一尺寸
            size = (400, 300)
            img1 = img1.resize(size)
            img2 = img2.resize(size)
            
            # 计算颜色直方图
            def get_color_histogram(img):
                pixels = list(img.getdata())
                
                # 简化：计算主要颜色分布
                hues = []
                saturations = []
                values = []
                
                for r, g, b in pixels:
                    h, s, v = colorsys.rgb_to_hsv(r/255, g/255, b/255)
                    hues.append(h)
                    saturations.append(s)
                    values.append(v)
                
                return {
                    'mean_hue': np.mean(hues),
                    'mean_sat': np.mean(saturations),
                    'mean_val': np.mean(values)
                }
            
            hist1 = get_color_histogram(img1)
            hist2 = get_color_histogram(img2)
            
            # 计算相似度
            hue_diff = abs(hist1['mean_hue'] - hist2['mean_hue'])
            sat_diff = abs(hist1['mean_sat'] - hist2['mean_sat'])
            val_diff = abs(hist1['mean_val'] - hist2['mean_val'])
            
            # 综合评分
            similarity = 1.0 - (hue_diff + sat_diff + val_diff) / 3
            
            return max(0.0, min(1.0, similarity))
        
        except Exception as e:
            print(f"[VisualEvaluator] 样式对比失败: {e}")
            return 0.5
