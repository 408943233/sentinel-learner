"""
图标提取模块 - 改进版
从截图中提取小图标并保存，过滤文字误判
"""

import cv2
import numpy as np
from PIL import Image
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class IconInfo:
    """图标信息"""
    x: int
    y: int
    width: int
    height: int
    image: np.ndarray
    confidence: float = 1.0
    is_likely_text: bool = False  # 标记是否可能是文字


class IconExtractor:
    """图标提取器 - 改进版，能过滤文字"""
    
    def __init__(self, min_size: int = 20, max_size: int = 80):
        self.min_size = min_size
        self.max_size = max_size
    
    def extract_icons(
        self, 
        image: Image.Image, 
        elements: Optional[List[Dict]] = None,
        output_dir: Optional[str] = None,
        filter_text: bool = True  # 是否过滤文字
    ) -> List[IconInfo]:
        """
        从图像中提取图标
        
        Args:
            image: 输入图像（PIL Image，保持原始分辨率）
            elements: 检测到的元素列表（可选）
            output_dir: 图标保存目录（可选）
            filter_text: 是否过滤疑似文字的图标
        
        Returns:
            提取的图标列表
        """
        # 保持原始分辨率，不缩放
        img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        icons = []

        # 策略：优先使用OmniParser检测到的icon类型元素
        # 如果OmniParser没有检测到足够的图标，再考虑使用轮廓检测
        if elements:
            for elem in elements:
                # 支持字典和OmniElement对象
                if hasattr(elem, 'type'):
                    elem_type = elem.type
                    bbox = elem.bbox if hasattr(elem, 'bbox') else [0, 0, 0, 0]
                    confidence = elem.confidence if hasattr(elem, 'confidence') else 1.0
                else:
                    elem_type = elem.get('type', '')
                    bbox = elem.get('bbox', [0, 0, 0, 0])
                    confidence = elem.get('confidence', 1.0)

                # 只提取明确标记为icon的元素
                if elem_type == 'icon':
                    x1, y1, x2, y2 = map(int, bbox)

                    # 检查尺寸
                    w, h = x2 - x1, y2 - y1
                    if self.min_size <= w <= self.max_size and self.min_size <= h <= self.max_size:
                        icon_img = img[y1:y2, x1:x2]

                        icons.append(IconInfo(
                            x=x1, y=y1, width=w, height=h,
                            image=icon_img,
                            confidence=confidence,
                            is_likely_text=False  # OmniParser已经识别为icon，信任它
                        ))

        # 如果OmniParser没有检测到足够的图标，使用轮廓检测作为补充
        # 但只在没有提供elements或检测到的图标很少时才使用
        if len(icons) < 3 and elements is None:
            contour_icons = self._extract_by_contours(img, gray, filter_text)
            icons.extend(contour_icons)

        # 去重（根据位置）
        icons = self._deduplicate_icons(icons)

        # 按置信度排序
        icons.sort(key=lambda x: x.confidence, reverse=True)

        # 保存图标
        if output_dir and icons:
            self._save_icons(icons, output_dir)

        return icons
    
    def _is_likely_text(self, img: np.ndarray) -> bool:
        """
        判断图像是否可能是文字 - 增强版
        
        文字特征：
        1. 宽高比通常较大（横向文字）或较小（竖向文字）
        2. 内部结构复杂（有笔画）
        3. 颜色分布单一（通常是纯色文字）
        4. 边缘特征：文字通常有较多的垂直/水平边缘
        5. 笔画分布：文字笔画分布有规律（如汉字有横竖撇捺）
        6. 对称性：图标通常有较好的对称性，文字不对称
        """
        h, w = img.shape[:2]
        
        # 1. 检查宽高比 - 文字通常比较细长（但一些图标也可能是细长的）
        aspect_ratio = w / h if h > 0 else 1
        if aspect_ratio > 4.0 or aspect_ratio < 0.25:  # 放宽限制
            return True
        
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # 2. 检查是否包含明显的文字笔画模式
        # 二值化
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        
        # 3. 检查水平投影（文字通常有规律的行结构）
        h_projection = np.sum(binary, axis=1) / 255
        # 文字通常有多个峰值（行）
        h_peaks = np.sum(h_projection > np.mean(h_projection) * 1.5)
        if h_peaks >= 4 and h > 35:  # 多行结构，可能是文字（提高阈值）
            # 检查峰值分布是否规律
            peak_positions = np.where(h_projection > np.mean(h_projection) * 1.5)[0]
            if len(peak_positions) >= 4:
                # 计算峰值间距的方差，文字通常间距规律
                peak_diffs = np.diff(peak_positions)
                if len(peak_diffs) > 1 and np.std(peak_diffs) < 3:  # 更严格的方差要求
                    return True
        
        # 4. 检查垂直投影（文字通常有规律的列结构）
        v_projection = np.sum(binary, axis=0) / 255
        # 检查是否有规律的垂直笔画
        v_peaks = np.sum(v_projection > np.mean(v_projection) * 1.3)
        if v_peaks >= 6:  # 多个垂直笔画（提高阈值）
            return True
        
        # 5. 检查颜色分布 - 文字通常颜色单一
        color_std = np.std(gray)
        if color_std < 25:  # 颜色变化很小，可能是纯色块
            return False  # 可能是图标背景
        
        # 6. 检查边缘密度和分布
        edges = cv2.Canny(gray, 50, 150)
        edge_density = np.sum(edges > 0) / (w * h)
        
        # 7. 检查笔画特征
        # 使用形态学操作检测线条
        vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(3, h // 4)))
        horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(3, w // 4), 1))

        vertical_lines = cv2.morphologyEx(edges, cv2.MORPH_OPEN, vertical_kernel)
        horizontal_lines = cv2.morphologyEx(edges, cv2.MORPH_OPEN, horizontal_kernel)

        vertical_ratio = np.sum(vertical_lines > 0) / (w * h)
        horizontal_ratio = np.sum(horizontal_lines > 0) / (w * h)

        # 文字特征：有较多垂直和水平笔画（提高阈值）
        if vertical_ratio > 0.12 and horizontal_ratio > 0.08:
            return True
        
        # 8. 检查轮廓数量和分布
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # 文字通常有很多小轮廓（笔画）
        if len(contours) >= 4:
            # 检查轮廓大小分布
            areas = [cv2.contourArea(c) for c in contours]
            avg_area = np.mean(areas)
            # 如果有很多小轮廓且大小相近，可能是文字
            small_contours = sum(1 for a in areas if a < avg_area * 0.5)
            if small_contours >= 3:
                return True
        
        # 9. 检查对称性 - 图标通常有较好的对称性
        # 水平对称性
        left_half = gray[:, :w//2]
        right_half = np.fliplr(gray[:, w//2:])
        min_w = min(left_half.shape[1], right_half.shape[1])
        if min_w > 0:
            h_symmetry = np.corrcoef(
                left_half[:, :min_w].flatten(), 
                right_half[:, :min_w].flatten()
            )[0, 1]
            # 图标通常有较好的对称性，文字不对称
            if h_symmetry < 0.3 and len(contours) >= 3:
                return True
        
        # 10. 检查是否是数字或字母（简单的几何形状）
        # 数字和字母通常有特定的宽高比和笔画数
        if 0.3 < aspect_ratio < 0.6 and len(contours) >= 2:
            # 可能是数字或窄字母（如i, l, 1）
            if h > 25 and w < 20:
                # 进一步检查：数字/字母通常有特定的笔画模式
                # 检查是否有明显的水平笔画（如横线）
                if horizontal_ratio > 0.1:
                    return True

        # 11. 检查内部空洞（文字通常没有内部空洞，图标可能有）
        # 反转二值图
        binary_inv = cv2.bitwise_not(binary)
        num_labels, _, _, _ = cv2.connectedComponentsWithStats(binary_inv, connectivity=8)
        # 文字通常只有1-2个连通区域（前景）
        # 图标可能有更多（如圆环有2个：外环和内环）
        # 放宽条件：只有当同时满足多个条件时才认为是文字
        if num_labels <= 2 and len(contours) >= 4 and edge_density > 0.1:
            return True

        return False
    
    def _extract_by_contours(self, img: np.ndarray, gray: np.ndarray, filter_text: bool = True) -> List[IconInfo]:
        """通过轮廓检测提取图标 - 改进版"""
        icons = []
        
        # 使用自适应阈值，更好地处理不同背景
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY_INV, 11, 2
        )
        
        # 形态学操作，连接相近的组件
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        
        # 查找轮廓
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            
            # 过滤尺寸 - 更严格的范围
            if not (self.min_size <= w <= self.max_size and self.min_size <= h <= self.max_size):
                continue
            
            # 过滤宽高比 - 图标通常接近正方形或圆形
            aspect_ratio = w / h if h > 0 else 0
            if not (0.5 <= aspect_ratio <= 2.0):
                continue
            
            # 过滤面积 - 轮廓面积应该占bounding box的一定比例
            area = cv2.contourArea(contour)
            bbox_area = w * h
            fill_ratio = area / bbox_area if bbox_area > 0 else 0
            
            # 图标通常有较高的填充率（实心）或特定形状
            if fill_ratio < 0.1 or fill_ratio > 0.95:
                continue
            
            # 提取图标区域
            icon_img = img[y:y+h, x:x+w]
            
            # 检查是否是文字
            is_text = self._is_likely_text(icon_img) if filter_text else False
            
            # 计算置信度
            confidence = fill_ratio * 0.5 + min(w, h) / self.max_size * 0.5
            
            icons.append(IconInfo(
                x=x, y=y, width=w, height=h,
                image=icon_img,
                confidence=confidence,
                is_likely_text=is_text
            ))
        
        return icons
    
    def _deduplicate_icons(self, icons: List[IconInfo], threshold: int = 10) -> List[IconInfo]:
        """根据位置去重"""
        if not icons:
            return icons
        
        # 按位置排序
        icons.sort(key=lambda x: (x.y, x.x))
        
        unique_icons = [icons[0]]
        
        for icon in icons[1:]:
            # 检查是否与已保存的图标重叠
            is_duplicate = False
            for saved in unique_icons:
                # 计算中心点距离
                dx = abs((icon.x + icon.width/2) - (saved.x + saved.width/2))
                dy = abs((icon.y + icon.height/2) - (saved.y + saved.height/2))
                
                if dx < threshold and dy < threshold:
                    is_duplicate = True
                    # 保留置信度更高的
                    if icon.confidence > saved.confidence:
                        unique_icons.remove(saved)
                        unique_icons.append(icon)
                    break
            
            if not is_duplicate:
                unique_icons.append(icon)
        
        return unique_icons
    
    def _save_icons(self, icons: List[IconInfo], output_dir: str):
        """保存提取的图标 - 使用原始分辨率"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # 清空旧图标
        for old_file in output_path.glob("icon_*.png"):
            old_file.unlink()
        
        saved_count = 0
        for i, icon in enumerate(icons):
            # 跳过明显是文字的
            if icon.is_likely_text:
                continue
            
            icon_path = output_path / f"icon_{saved_count:03d}_{icon.width}x{icon.height}_{icon.x}_{icon.y}.png"
            
            # 保存为PNG，保持原始质量
            cv2.imwrite(str(icon_path), icon.image, [cv2.IMWRITE_PNG_COMPRESSION, 3])
            saved_count += 1
        
        print(f"  💾 已保存 {saved_count} 个图标到: {output_dir}")
        print(f"  📝 过滤了 {len([i for i in icons if i.is_likely_text])} 个疑似文字的图标")


# 便捷函数
def extract_icons_from_image(
    image: Image.Image,
    elements: Optional[List[Dict]] = None,
    output_dir: Optional[str] = None,
    filter_text: bool = True
) -> List[IconInfo]:
    """从图像中提取图标"""
    extractor = IconExtractor()
    return extractor.extract_icons(image, elements, output_dir, filter_text)
