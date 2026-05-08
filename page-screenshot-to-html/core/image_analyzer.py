"""
图像分析模块 - 颜色提取、布局分析
"""
import cv2
import numpy as np
from PIL import Image
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
from collections import Counter

from .config import get_config
from .performance_monitor import monitor


@dataclass
class ColorInfo:
    """颜色信息"""
    hex: str
    rgb: Tuple[int, int, int]
    count: int
    percentage: float


@dataclass
class LayoutSection:
    """布局区域"""
    y_start: int
    y_end: int
    height: int
    bg_color: str
    section_type: str = "content"


class ImageAnalyzer:
    """图像分析器"""
    
    def __init__(self):
        self.config = get_config().image
    
    @monitor.track_time("image_analysis")
    def analyze(self, image: Image.Image) -> Dict[str, Any]:
        """全面分析图像"""
        # 转换为OpenCV格式
        img_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        
        analysis = {
            'dimensions': {
                'width': image.width,
                'height': image.height,
                'dpr': self._calculate_dpr(image.width)
            },
            'colors': self._extract_colors(img_cv),
            'layout': self._analyze_layout(img_cv),
            'horizontal_lines': self._detect_horizontal_lines(img_cv),
            'vertical_lines': self._detect_vertical_lines(img_cv)
        }
        
        return analysis
    
    def _calculate_dpr(self, width: int) -> float:
        """计算设备像素比"""
        return width / self.config.logical_width
    
    def _extract_colors(self, img: np.ndarray, top_n: int = 15) -> List[ColorInfo]:
        """提取主要颜色 - 改进版，更准确识别主色调"""
        # 缩小图片以加速处理
        height, width = img.shape[:2]
        if width > 400:
            ratio = 400 / width
            img = cv2.resize(img, (400, int(height * ratio)))
        
        # 转换为RGB
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        
        # 重塑为像素列表
        pixels = img_rgb.reshape(-1, 3)
        
        # 使用更精细的量化（5而不是10）以保留更多颜色细节
        pixels_quantized = pixels // 5 * 5
        
        # 统计颜色频率
        color_counts = Counter(map(tuple, pixels_quantized))
        total_pixels = len(pixels)
        
        # 获取最常见的颜色
        colors = []
        for rgb_quantized, count in color_counts.most_common(top_n * 2):
            # 找到原始像素中最接近这个量化颜色的真实颜色
            mask = np.all(np.abs(pixels - rgb_quantized) <= 5, axis=1)
            if np.any(mask):
                real_pixels = pixels[mask]
                # 使用这些像素的平均值作为代表色
                avg_rgb = tuple(np.mean(real_pixels, axis=0).astype(int))
                hex_color = '#{:02x}{:02x}{:02x}'.format(*avg_rgb)
                colors.append(ColorInfo(
                    hex=hex_color,
                    rgb=avg_rgb,
                    count=count,
                    percentage=count / total_pixels * 100
                ))
        
        # 按百分比排序并返回前top_n个
        colors.sort(key=lambda x: x.percentage, reverse=True)
        return colors[:top_n]
    
    def _analyze_layout(self, img: np.ndarray) -> List[LayoutSection]:
        """分析页面布局"""
        height, width = img.shape[:2]
        
        # 转换为灰度图
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # 水平投影（检测行）
        h_projection = np.mean(gray, axis=1)
        
        # 检测背景色变化
        sections = []
        current_y = 0
        
        # 简单的区域分割：每100像素一个区域
        section_height = 100
        for y in range(0, height, section_height):
            y_end = min(y + section_height, height)
            
            # 提取区域
            region = img[y:y_end, :]
            
            # 计算区域主色调
            bg_color = self._get_dominant_color(region)
            
            sections.append(LayoutSection(
                y_start=y,
                y_end=y_end,
                height=y_end - y,
                bg_color=bg_color,
                section_type=self._detect_section_type(y, y_end, height)
            ))
        
        return sections
    
    def _get_dominant_color(self, img: np.ndarray) -> str:
        """获取图像主色调 - 改进版"""
        # 缩小图像
        if img.shape[0] > 100 or img.shape[1] > 100:
            img = cv2.resize(img, (100, 100))
        
        # 转换为RGB
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        
        # 重塑并量化（使用更精细的量化）
        pixels = img_rgb.reshape(-1, 3)
        pixels_quantized = pixels // 5 * 5
        
        # 统计
        color_counts = Counter(map(tuple, pixels_quantized))
        dominant_quantized = color_counts.most_common(1)[0][0]
        
        # 找到原始像素中最接近这个量化颜色的真实颜色
        mask = np.all(np.abs(pixels - dominant_quantized) <= 5, axis=1)
        if np.any(mask):
            real_pixels = pixels[mask]
            avg_rgb = tuple(np.mean(real_pixels, axis=0).astype(int))
            return '#{:02x}{:02x}{:02x}'.format(*avg_rgb)
        
        return '#{:02x}{:02x}{:02x}'.format(*dominant_quantized)
    
    def _detect_section_type(self, y_start: int, y_end: int, image_height: int) -> str:
        """检测区域类型
        
        Args:
            y_start: 区域起始y坐标
            y_end: 区域结束y坐标
            image_height: 图片总高度
        """
        # 顶部区域 - 状态栏(0-47) + 导航栏(47-91)
        if y_start < 100:
            return "header"
        # 底部区域 - 底部导航栏，通常在图片底部50-60px
        elif y_end > image_height - 100:
            return "bottom"
        # 图表区域 - 根据位置判断
        elif 500 < y_start < 1500:
            return "chart"
        else:
            return "content"
    
    def _detect_horizontal_lines(self, img: np.ndarray, min_length: int = 50) -> List[Dict[str, int]]:
        """检测水平线"""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # 边缘检测
        edges = cv2.Canny(gray, 50, 150)
        
        # 霍夫变换检测直线
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=50, 
                                minLineLength=min_length, maxLineGap=10)
        
        horizontal_lines = []
        if lines is not None:
            for line in lines:
                x1, y1, x2, y2 = line[0]
                # 只保留水平线（y坐标相近）
                if abs(y2 - y1) < 5 and abs(x2 - x1) > min_length:
                    horizontal_lines.append({
                        'y': int((y1 + y2) / 2),
                        'x1': int(x1),
                        'x2': int(x2)
                    })
        
        return horizontal_lines
    
    def _detect_vertical_lines(self, img: np.ndarray, min_length: int = 50) -> List[Dict[str, int]]:
        """检测垂直线"""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=50,
                                minLineLength=min_length, maxLineGap=10)
        
        vertical_lines = []
        if lines is not None:
            for line in lines:
                x1, y1, x2, y2 = line[0]
                # 只保留垂直线（x坐标相近）
                if abs(x2 - x1) < 5 and abs(y2 - y1) > min_length:
                    vertical_lines.append({
                        'x': int((x1 + x2) / 2),
                        'y1': int(y1),
                        'y2': int(y2)
                    })
        
        return vertical_lines
    
    def extract_region(self, image: Image.Image, x: int, y: int, 
                       w: int, h: int) -> Image.Image:
        """提取图像区域"""
        return image.crop((x, y, x + w, y + h))
    
    def get_region_color(self, image: Image.Image, x: int, y: int, 
                         w: int, h: int) -> str:
        """获取区域主色调"""
        region = self.extract_region(image, x, y, w, h)
        img_cv = cv2.cvtColor(np.array(region), cv2.COLOR_RGB2BGR)
        return self._get_dominant_color(img_cv)


# 便捷函数
def analyze_image(image_path: str) -> Dict[str, Any]:
    """分析图片并返回结果"""
    with Image.open(image_path) as img:
        analyzer = ImageAnalyzer()
        return analyzer.analyze(img)
