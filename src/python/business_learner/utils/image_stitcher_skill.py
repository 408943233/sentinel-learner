"""
长图拼接模块 - 使用 OpenCV 直接拼接
替代外部 image-stitch skill，无需依赖 stitch.py
"""

import os
import json
import numpy as np
from pathlib import Path
from typing import List, Tuple, Optional
from dataclasses import dataclass


try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


@dataclass
class StitchResult:
    """拼接结果"""
    success: bool
    output_path: Optional[str]
    error_message: str = ""
    error_status: str = ""  # 错误状态码: NO_OVERLAP_DETECTED, INSUFFICIENT_OVERLAP, LOW_SIMILARITY


class ImageStitcherSkill:
    """图像拼接器 - 使用 OpenCV 直接拼接"""
    
    def __init__(self, skill_path: Optional[str] = None):
        """
        初始化拼接器
        
        Args:
            skill_path: 保留参数用于兼容，不再使用
        """
        if not CV2_AVAILABLE:
            print("[ImageStitcherSkill] 警告: OpenCV (cv2) 未安装，长截图功能将不可用")
            print("  安装命令: pip install opencv-python")
    
    def stitch_vertical(self, image_paths: List[str], 
                       output_path: Optional[str] = None) -> StitchResult:
        """
        垂直拼接多张图片
        
        Args:
            image_paths: 图片路径列表（按从上到下顺序）
            output_path: 输出路径（可选）
            
        Returns:
            拼接结果
        """
        if not CV2_AVAILABLE:
            return StitchResult(
                success=False,
                output_path=None,
                error_message="OpenCV (cv2) 未安装，无法拼接图片",
                error_status="CV2_NOT_AVAILABLE"
            )
        
        if len(image_paths) < 2:
            return StitchResult(
                success=False,
                output_path=None,
                error_message="至少需要2张图片",
                error_status="INSUFFICIENT_IMAGES"
            )
        
        # 确保所有图片存在
        for path in image_paths:
            if not Path(path).exists():
                return StitchResult(
                    success=False,
                    output_path=None,
                    error_message=f"图片不存在: {path}",
                    error_status="FILE_NOT_FOUND"
                )
        
        try:
            # 读取所有图片
            images = []
            for path in image_paths:
                img = cv2.imread(str(path))
                if img is None:
                    return StitchResult(
                        success=False,
                        output_path=None,
                        error_message=f"无法读取图片: {path}",
                        error_status="READ_ERROR"
                    )
                images.append(img)
            
            # 使用智能垂直拼接
            result = self._smart_vertical_stitch(images)
            
            if result is None:
                # 智能拼接失败，使用简单拼接
                print("[ImageStitcherSkill] 智能拼接失败，使用简单拼接")
                result = self._simple_vertical_stitch(images)
            
            if result is None:
                return StitchResult(
                    success=False,
                    output_path=None,
                    error_message="拼接失败",
                    error_status="STITCH_FAILED"
                )
            
            # 保存结果
            if output_path:
                output_file = Path(output_path)
                output_file.parent.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(output_file), result)
                return StitchResult(
                    success=True,
                    output_path=str(output_file)
                )
            else:
                # 默认输出到第一张图片的目录
                default_output = Path(image_paths[0]).parent / "stitched_result.png"
                cv2.imwrite(str(default_output), result)
                return StitchResult(
                    success=True,
                    output_path=str(default_output)
                )
                
        except Exception as e:
            return StitchResult(
                success=False,
                output_path=None,
                error_message=f"拼接错误: {str(e)}",
                error_status="EXCEPTION"
            )
    
    def _simple_vertical_stitch(self, images: List[np.ndarray]) -> Optional[np.ndarray]:
        """
        简单垂直拼接 - 直接堆叠图片
        
        Args:
            images: 图片数组列表
            
        Returns:
            拼接后的图片
        """
        if not images:
            return None
        
        # 统一宽度（使用第一张图片的宽度）
        target_width = images[0].shape[1]
        resized_images = []
        
        for img in images:
            if img.shape[1] != target_width:
                # 等比例缩放
                scale = target_width / img.shape[1]
                new_height = int(img.shape[0] * scale)
                resized = cv2.resize(img, (target_width, new_height))
                resized_images.append(resized)
            else:
                resized_images.append(img)
        
        # 垂直拼接
        result = np.vstack(resized_images)
        return result
    
    def _smart_vertical_stitch(self, images: List[np.ndarray], 
                               overlap_ratio: float = 0.15) -> Optional[np.ndarray]:
        """
        智能垂直拼接 - 检测重叠区域并去除重复
        
        Args:
            images: 图片数组列表
            overlap_ratio: 预期的重叠区域比例
            
        Returns:
            拼接后的图片
        """
        if len(images) < 2:
            return images[0] if images else None
        
        # 统一宽度
        target_width = images[0].shape[1]
        resized_images = []
        
        for img in images:
            if img.shape[1] != target_width:
                scale = target_width / img.shape[1]
                new_height = int(img.shape[0] * scale)
                resized = cv2.resize(img, (target_width, new_height))
                resized_images.append(resized)
            else:
                resized_images.append(img)
        
        # 从第一张开始
        result = resized_images[0]
        
        for i in range(1, len(resized_images)):
            next_img = resized_images[i]
            
            # 尝试找到最佳拼接位置
            stitched = self._find_best_stitch_position(result, next_img, overlap_ratio)
            
            if stitched is not None:
                result = stitched
            else:
                # 如果智能拼接失败，直接拼接
                result = np.vstack([result, next_img])
        
        return result
    
    def _find_best_stitch_position(self, img1: np.ndarray, img2: np.ndarray,
                                    overlap_ratio: float = 0.15) -> Optional[np.ndarray]:
        """
        找到两张图片的最佳拼接位置
        
        Args:
            img1: 第一张图片（上方）
            img2: 第二张图片（下方）
            overlap_ratio: 预期的重叠区域比例
            
        Returns:
            拼接后的图片或 None
        """
        try:
            h1, w1 = img1.shape[:2]
            h2, w2 = img2.shape[:2]
            
            # 计算搜索区域
            overlap_height = int(min(h1, h2) * overlap_ratio)
            search_start = max(0, h1 - overlap_height * 2)
            search_end = h1
            
            if overlap_height < 10:
                # 重叠区域太小，直接拼接
                return np.vstack([img1, img2])
            
            # 提取 img1 底部区域
            img1_bottom = img1[search_start:search_end, :]
            
            # 在 img2 顶部寻找最佳匹配
            best_match_y = 0
            best_similarity = -1
            
            # 只检查 img2 的顶部区域
            search_range = min(h2, overlap_height * 2)
            
            for y in range(0, search_range - overlap_height, 5):  # 步长5加速
                img2_top = img2[y:y+overlap_height, :]
                
                if img2_top.shape[0] != img1_bottom.shape[0]:
                    continue
                
                # 计算相似度（使用模板匹配）
                similarity = self._calculate_similarity(img1_bottom, img2_top)
                
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match_y = y
            
            # 如果相似度太低，可能是没有重叠
            if best_similarity < 0.3:
                return np.vstack([img1, img2])
            
            # 在最佳匹配位置拼接
            # img1 取到 search_start + (search_end - search_start) - (search_end - search_start - best_match_y)
            # 简化为：img1 取到 h1 - overlap_height + best_match_y
            cut_y = h1 - overlap_height + best_match_y
            
            if cut_y > 0 and cut_y < h1:
                result = np.vstack([img1[:cut_y], img2[best_match_y:]])
            else:
                result = np.vstack([img1, img2])
            
            return result
            
        except Exception as e:
            print(f"[ImageStitcherSkill] 智能拼接出错: {e}")
            return None
    
    def _calculate_similarity(self, img1: np.ndarray, img2: np.ndarray) -> float:
        """
        计算两张图片的相似度
        
        Args:
            img1: 第一张图片
            img2: 第二张图片
            
        Returns:
            相似度分数 (0-1)
        """
        try:
            # 确保尺寸相同
            if img1.shape != img2.shape:
                img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))
            
            # 转换为灰度图
            gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
            gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
            
            # 使用结构相似性指数 (SSIM) 或简单相关系数
            # 这里使用归一化相关系数
            result = cv2.matchTemplate(gray1, gray2, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(result)
            
            return max_val
        except Exception:
            # 如果失败，使用简单像素比较
            try:
                diff = cv2.absdiff(img1, img2)
                similarity = 1.0 - (np.mean(diff) / 255.0)
                return max(0, similarity)
            except:
                return 0.0
    
    def create_page_long_screenshot(self, image_paths: List[str], 
                                    output_path: str) -> StitchResult:
        """
        创建页面长截图
        
        Args:
            image_paths: 图片路径列表
            output_path: 输出路径
            
        Returns:
            拼接结果
        """
        return self.stitch_vertical(image_paths, output_path)
