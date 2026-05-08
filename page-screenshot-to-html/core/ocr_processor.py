"""
OCR处理器模块 - 单例模式 + LRU缓存
"""
import hashlib
import re
from functools import lru_cache
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import numpy as np
from PIL import Image
import cv2
import pytesseract

try:
    from paddleocr import PaddleOCR
    PADDLE_AVAILABLE = True
except ImportError:
    PADDLE_AVAILABLE = False

from .config import get_config
from .exceptions import OCRError


@dataclass
class TextBlock:
    """文本块数据结构"""
    text: str
    x: int
    y: int
    w: int
    h: int
    confidence: float = 1.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'text': self.text,
            'x': self.x,
            'y': self.y,
            'w': self.w,
            'h': self.h,
            'confidence': self.confidence
        }


class OCRProcessor:
    """OCR处理器 - 单例模式"""
    _instance: Optional['OCRProcessor'] = None
    _initialized: bool = False
    
    def __new__(cls) -> 'OCRProcessor':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if OCRProcessor._initialized:
            return
            
        self.config = get_config().ocr
        self._paddle_ocr: Optional[Any] = None
        self._cache: Dict[str, List[TextBlock]] = {}
        self._cache_size = self.config.cache_size
        OCRProcessor._initialized = True
    
    @property
    def paddle_ocr(self) -> Any:
        """懒加载PaddleOCR实例"""
        if self._paddle_ocr is None and PADDLE_AVAILABLE:
            # 确保语言设置有效
            lang = self.config.lang
            valid_langs = ['ch', 'ch_doc', 'en', 'korean', 'japan', 'chinese_cht', 
                          'ta', 'te', 'ka', 'latin', 'arabic', 'cyrillic', 'devanagari']
            if lang not in valid_langs:
                print(f"  ⚠️ 无效的语言设置 '{lang}'，使用默认 'ch'")
                lang = 'ch'
            
            self._paddle_ocr = PaddleOCR(
                lang=lang,
                use_angle_cls=False,
                use_gpu=self.config.use_gpu,
                show_log=False,
                max_batch_size=self.config.max_batch_size,
                use_dilation=True,
                det_db_score_mode='slow',
                rec_batch_num=self.config.max_batch_size,
                det_db_thresh=self.config.det_db_thresh,
                det_db_box_thresh=self.config.det_db_box_thresh,
                drop_score=self.config.drop_score,
                det_db_unclip_ratio=1.5,
                max_text_length=25,
                rec_algorithm='SVTR_LCNet',
            )
        return self._paddle_ocr
    
    def _get_image_hash(self, image: Image.Image) -> str:
        """计算图片哈希用于缓存"""
        img_bytes = image.tobytes()
        return hashlib.md5(img_bytes).hexdigest()
    
    def extract_text_with_positions(self, image: Image.Image) -> List[TextBlock]:
        """
        提取带位置信息的文本
        优先使用PaddleOCR，失败时回退到Tesseract
        """
        # 检查缓存
        if self.config.enable_cache:
            image_hash = self._get_image_hash(image)
            if image_hash in self._cache:
                print(f"  📦 OCR缓存命中")
                return self._cache[image_hash]
        
        # 尝试PaddleOCR
        if PADDLE_AVAILABLE and self.paddle_ocr is not None:
            try:
                result = self._extract_with_paddle(image)
                if result:
                    if self.config.enable_cache:
                        self._update_cache(image_hash, result)
                    return result
            except Exception as e:
                print(f"  ⚠️ PaddleOCR失败: {e}，回退到Tesseract")
        
        # 回退到Tesseract
        result = self._extract_with_tesseract(image)
        if self.config.enable_cache:
            self._update_cache(image_hash, result)
        return result
    
    def _extract_with_paddle(self, image: Image.Image) -> List[TextBlock]:
        """使用PaddleOCR提取文本"""
        image_np = np.array(image)
        result = self.paddle_ocr.ocr(image_np, cls=False)
        
        if not result or not result[0]:
            return []
        
        text_blocks = []
        for item in result[0]:
            if item[1][1] > self.config.drop_score:
                coord = item[0]
                text = item[1][0]
                confidence = item[1][1]
                
                # 后处理：拆分合并的文本
                split_results = self._split_text_by_patterns(text, coord)
                
                for split_text, split_coord in split_results:
                    x = min(split_coord[0][0], split_coord[3][0])
                    y = min(split_coord[0][1], split_coord[1][1])
                    box_w = max(split_coord[1][0], split_coord[2][0]) - x
                    box_h = max(split_coord[2][1], split_coord[3][1]) - y
                    
                    text_blocks.append(TextBlock(
                        text=split_text,
                        x=int(x),
                        y=int(y),
                        w=int(box_w),
                        h=int(box_h),
                        confidence=confidence
                    ))
        
        print(f"  ✅ PaddleOCR识别: {len(text_blocks)} 个文本块")
        return text_blocks
    
    def _extract_with_tesseract(self, image: Image.Image) -> List[TextBlock]:
        """使用Tesseract OCR作为后备方案"""
        img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        data = pytesseract.image_to_data(
            gray, 
            lang='chi_sim+eng', 
            output_type=pytesseract.Output.DICT
        )
        
        text_blocks = []
        n_boxes = len(data['text'])
        
        for i in range(n_boxes):
            text = data['text'][i].strip()
            conf = int(data['conf'][i])
            
            if conf < 30 or not text:
                continue
                
            x, y = data['left'][i], data['top'][i]
            w, h = data['width'][i], data['height'][i]
            
            text_blocks.append(TextBlock(
                text=text,
                x=x,
                y=y,
                w=w,
                h=h,
                confidence=conf / 100.0
            ))
        
        print(f"  ✅ Tesseract识别: {len(text_blocks)} 个文本块")
        return text_blocks
    
    def _split_text_by_patterns(self, text: str, coord: List[List[float]]) -> List[Tuple[str, List[List[float]]]]:
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
    
    def _update_cache(self, image_hash: str, result: List[TextBlock]):
        """更新缓存，使用LRU策略"""
        if len(self._cache) >= self._cache_size:
            # 移除最旧的缓存
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
        
        self._cache[image_hash] = result
    
    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()
        print("  🗑️ OCR缓存已清空")
    
    def extract_text_only(self, image: Image.Image) -> str:
        """仅提取文本内容（不带位置）"""
        blocks = self.extract_text_with_positions(image)
        return '\n'.join([block.text for block in blocks])


# 便捷函数
def get_ocr_processor() -> OCRProcessor:
    """获取OCR处理器实例"""
    return OCRProcessor()
