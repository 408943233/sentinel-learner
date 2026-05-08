"""
SSIM图像相似度分析模块
用于对比生成的HTML截图与原图的相似度
"""

import cv2
import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from pathlib import Path

try:
    from skimage.metrics import structural_similarity as ssim
    SKIMAGE_AVAILABLE = True
except ImportError:
    SKIMAGE_AVAILABLE = False
    print("  ⚠️ scikit-image未安装，SSIM功能将不可用")


@dataclass
class SSIMBlock:
    """SSIM区块信息"""
    x: int
    y: int
    width: int
    height: int
    ssim: float
    level: int = 0
    is_leaf: bool = True
    element_count: int = 0
    merged: bool = False


class SSIMAnalyzer:
    """SSIM图像相似度分析器"""
    
    def __init__(self):
        if not SKIMAGE_AVAILABLE:
            raise ImportError("scikit-image is required for SSIM analysis. Install with: pip install scikit-image")
    
    def calculate_ssim(self, image1_path: str, image2_path: str) -> float:
        """
        计算两张图像的SSIM相似度 - 严肃像素级比对
        
        Returns:
            综合SSIM评分 (0-1)
        """
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
    
    def calculate_ssim_by_blocks(
        self, 
        image1_path: str, 
        image2_path: str, 
        num_blocks: int = 4,
        elements: Optional[List[Dict]] = None
    ) -> Tuple[Optional[List[SSIMBlock]], float]:
        """
        分区块计算SSIM，定位得分最低的区域（考虑语义边界）
        
        Returns:
            (区块列表, 最低SSIM分数)
        """
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
                blocks.sort(key=lambda x: x.ssim)
                min_ssim = blocks[0].ssim
            else:
                min_ssim = 1.0
            
            return blocks, min_ssim
        except Exception as e:
            print(f"区块SSIM计算失败: {e}")
            return None, 0.0
    
    def _uniform_block_ssim(self, gray1: np.ndarray, gray2: np.ndarray, num_blocks: int) -> List[SSIMBlock]:
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
                    
                    blocks.append(SSIMBlock(
                        x=x1,
                        y=y1,
                        width=x2 - x1,
                        height=y2 - y1,
                        ssim=block_ssim
                    ))
        
        return blocks
    
    def _quadtree_ssim(
        self, 
        gray1: np.ndarray, 
        gray2: np.ndarray, 
        elements: List[Dict],
        width: int,
        height: int,
        x: int = 0,
        y: int = 0,
        level: int = 0,
        max_level: int = 4,
        min_size: int = 100
    ) -> List[SSIMBlock]:
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
                
                blocks.append(SSIMBlock(
                    x=x,
                    y=y,
                    width=x2 - x,
                    height=y2 - y,
                    ssim=block_ssim,
                    level=level,
                    is_leaf=True
                ))
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
                
                blocks.append(SSIMBlock(
                    x=x,
                    y=y,
                    width=x2 - x,
                    height=y2 - y,
                    ssim=block_ssim,
                    level=level,
                    is_leaf=True,
                    element_count=len(region_elements)
                ))
        
        return blocks
    
    def _get_elements_in_region(
        self, 
        elements: List[Dict], 
        x: int, 
        y: int, 
        width: int, 
        height: int
    ) -> List[Dict]:
        """获取区域内的元素"""
        region_elements = []
        for element in elements:
            bbox = element.get('bbox', [0, 0, 0, 0])
            ex1, ey1, ex2, ey2 = bbox
            # 检查元素是否与区域重叠
            overlap_x = max(0, min(ex2, x + width) - max(ex1, x))
            overlap_y = max(0, min(ey2, y + height) - max(ey1, y))
            
            if overlap_x > 0 and overlap_y > 0:
                region_elements.append(element)
        
        return region_elements
    
    def _should_split_region(
        self, 
        elements: List[Dict], 
        width: int, 
        height: int, 
        level: int
    ) -> bool:
        """
        判断是否应该继续分割区域
        基于内容复杂度和区域大小
        """
        if len(elements) == 0:
            return False
        
        # 计算内容密度
        total_element_area = sum(
            (e.get('bbox', [0, 0, 0, 0])[2] - e.get('bbox', [0, 0, 0, 0])[0]) * 
            (e.get('bbox', [0, 0, 0, 0])[3] - e.get('bbox', [0, 0, 0, 0])[1])
            for e in elements
        )
        region_area = width * height
        density = total_element_area / region_area if region_area > 0 else 0
        
        # 如果内容密度高且元素数量多，继续分割
        if density > 0.3 and len(elements) > 2:
            return True
        
        # 如果元素类型多样，继续分割
        element_types = set(e.get('type', 'unknown') for e in elements)
        if len(element_types) > 2:
            return True
        
        return False
    
    def _find_semantic_split_point(
        self, 
        elements: List[Dict], 
        x: int, 
        y: int, 
        width: int, 
        height: int
    ) -> Tuple[Optional[int], Optional[int]]:
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
            bbox = element.get('bbox', [0, 0, 0, 0])
            ex1, ey1, ex2, ey2 = bbox
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
    
    def find_low_ssim_regions(
        self, 
        image1_path: str, 
        image2_path: str, 
        elements: Optional[List[Dict]] = None,
        threshold: float = 0.95
    ) -> List[SSIMBlock]:
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
            low_regions = [b for b in blocks if b.ssim < threshold]
            
            # 按SSIM分数排序
            low_regions.sort(key=lambda x: x.ssim)
            
            # 合并相邻的低SSIM区域（考虑整体性）
            merged_regions = self._merge_adjacent_regions(low_regions)
            
            # 确保区域不重叠（保留最低SSIM的区域）
            unique_regions = self._remove_overlapping_regions(merged_regions)
            
            print(f"四叉树分割生成 {len(blocks)} 个区块，发现 {len(low_regions)} 个低SSIM区域，合并后 {len(unique_regions)} 个")
            
            return unique_regions[:5]  # 返回前5个最低的区域
        except Exception as e:
            print(f"查找低SSIM区域失败: {e}")
            return []
    
    def _merge_adjacent_regions(self, regions: List[SSIMBlock], max_gap: int = 50) -> List[SSIMBlock]:
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
            from copy import copy
            current = copy(region)
            used.add(i)
            
            # 查找可以合并的相邻区域
            for j, other in enumerate(regions[i+1:], start=i+1):
                if j in used:
                    continue
                
                # 检查是否相邻（考虑间隙）
                x_gap = abs(current.x + current.width - other.x)
                y_gap = abs(current.y + current.height - other.y)
                
                # 水平相邻
                horizontal_adjacent = (
                    abs(current.y - other.y) < max_gap and
                    abs(current.height - other.height) < max_gap and
                    x_gap < max_gap
                )
                
                # 垂直相邻
                vertical_adjacent = (
                    abs(current.x - other.x) < max_gap and
                    abs(current.width - other.width) < max_gap and
                    y_gap < max_gap
                )
                
                if horizontal_adjacent or vertical_adjacent:
                    # 合并区域
                    new_x = min(current.x, other.x)
                    new_y = min(current.y, other.y)
                    new_x2 = max(current.x + current.width, other.x + other.width)
                    new_y2 = max(current.y + current.height, other.y + other.height)
                    
                    current.x = new_x
                    current.y = new_y
                    current.width = new_x2 - new_x
                    current.height = new_y2 - new_y
                    current.ssim = min(current.ssim, other.ssim)  # 取最低SSIM
                    current.merged = True
                    
                    used.add(j)
            
            merged.append(current)
        
        return merged
    
    def _remove_overlapping_regions(
        self, 
        regions: List[SSIMBlock], 
        overlap_threshold: float = 0.3
    ) -> List[SSIMBlock]:
        """
        移除重叠的区域，保留SSIM最低的区域
        """
        if not regions:
            return []
        
        # 按SSIM排序（低到高）
        sorted_regions = sorted(regions, key=lambda x: x.ssim)
        
        unique_regions = []
        
        for region in sorted_regions:
            overlap = False
            for existing in unique_regions:
                # 计算重叠率
                x1 = max(region.x, existing.x)
                y1 = max(region.y, existing.y)
                x2 = min(region.x + region.width, existing.x + existing.width)
                y2 = min(region.y + region.height, existing.y + existing.height)
                
                if x2 > x1 and y2 > y1:
                    overlap_area = (x2 - x1) * (y2 - y1)
                    region_area = region.width * region.height
                    if overlap_area / region_area > overlap_threshold:
                        overlap = True
                        break
            
            if not overlap:
                unique_regions.append(region)
        
        return unique_regions


# 便捷函数
def get_ssim_analyzer() -> SSIMAnalyzer:
    """获取SSIM分析器实例"""
    return SSIMAnalyzer()
