"""
OmniParser V2 处理器模块 - 检测UI元素
支持多线程，每个线程有独立的OmniParser实例
"""
import os
import sys
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from PIL import Image
import numpy as np

from .config import get_config
from .performance_monitor import monitor


@dataclass
class OmniElement:
    """OmniParser检测到的元素"""
    id: int
    type: str  # 'icon', 'text', 'button', 'image', etc.
    bbox: Tuple[float, float, float, float]  # x1, y1, x2, y2 (ratio)
    content: str
    confidence: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'type': self.type,
            'bbox': self.bbox,
            'content': self.content,
            'confidence': self.confidence
        }


class OmniParserProcessor:
    """OmniParser V2 处理器 - 多线程安全版本
    
    每个线程拥有独立的OmniParser实例，避免资源抢占
    """
    
    # 线程本地存储，每个线程有自己的OmniParser实例
    _thread_local = threading.local()
    
    # 类级别的锁，用于保护共享资源的初始化
    _init_lock = threading.Lock()
    
    # 类级别的共享配置（只读，线程安全）
    _shared_config = None
    _omniparser_path = None
    _som_model_path = None
    _caption_model_path = None
    
    def __init__(self):
        self.config = get_config()
        
        # 只在第一次初始化时设置共享配置
        with self._init_lock:
            if OmniParserProcessor._shared_config is None:
                # OmniParser路径
                OmniParserProcessor._omniparser_path = os.path.join(
                    os.path.dirname(os.path.dirname(__file__)),
                    'OmniParser'
                )
                
                # 模型路径
                OmniParserProcessor._som_model_path = os.path.join(
                    OmniParserProcessor._omniparser_path, 
                    'weights', 'icon_detect', 'model.pt'
                )
                OmniParserProcessor._caption_model_path = os.path.join(
                    OmniParserProcessor._omniparser_path, 
                    'weights', 'icon_caption_florence'
                )
                
                # 检查是否有caption模型，如果没有则禁用
                has_caption_model = os.path.exists(OmniParserProcessor._caption_model_path)
                
                OmniParserProcessor._shared_config = {
                    'som_model_path': OmniParserProcessor._som_model_path,
                    'caption_model_name': 'florence2' if has_caption_model else None,
                    'caption_model_path': OmniParserProcessor._caption_model_path if has_caption_model else None,
                    'BOX_TRESHOLD': 0.05
                }
    
    def _get_thread_local_parser(self):
        """获取当前线程的OmniParser实例（每个线程独立）"""
        # 检查当前线程是否已有实例
        if not hasattr(OmniParserProcessor._thread_local, 'omniparser'):
            # 添加OmniParser到Python路径
            if OmniParserProcessor._omniparser_path not in sys.path:
                sys.path.insert(0, OmniParserProcessor._omniparser_path)
            
            # 检查模型文件
            if not os.path.exists(OmniParserProcessor._som_model_path):
                print(f"  ⚠️ OmniParser模型不存在: {OmniParserProcessor._som_model_path}")
                OmniParserProcessor._thread_local.omniparser = None
                return None
            
            try:
                # 先导入transformers（避免多线程导入问题）
                import transformers
                from transformers import AutoProcessor, AutoModelForCausalLM
                
                # 导入并初始化（每个线程独立）
                from util.omniparser import Omniparser
                
                thread_id = threading.current_thread().ident
                print(f"  🔄 [线程{thread_id}] 正在加载OmniParser V2模型...")
                
                OmniParserProcessor._thread_local.omniparser = Omniparser(
                    OmniParserProcessor._shared_config
                )
                print(f"  ✅ [线程{thread_id}] OmniParser V2初始化成功")
                
            except Exception as e:
                print(f"  ⚠️ OmniParser初始化失败: {e}")
                import traceback
                traceback.print_exc()
                OmniParserProcessor._thread_local.omniparser = None
        
        return OmniParserProcessor._thread_local.omniparser
    
    @monitor.track_time("omniparser_detection")
    def detect_elements(self, image: Image.Image) -> Tuple[List[OmniElement], bool]:
        """
        检测图片中的UI元素 - 多线程安全版本
        每个线程使用独立的OmniParser实例
        
        返回: (元素列表, 是否成功)
        """
        # 获取当前线程的OmniParser实例
        parser = self._get_thread_local_parser()
        if parser is None:
            return [], False
        
        try:
            import io
            import base64
            
            # 转换图片为base64
            buffer = io.BytesIO()
            image.save(buffer, format='PNG')
            image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            # 调用OmniParser（线程安全，每个线程有自己的实例）
            thread_id = threading.current_thread().ident
            print(f"  🔍 [线程{thread_id}] 使用OmniParser V2检测UI元素...")
            labeled_img, parsed_content = parser.parse(image_base64)
            
            # 解析结果
            elements = self._parse_results(parsed_content)
            
            if len(elements) > 0:
                print(f"  ✅ [线程{thread_id}] OmniParser检测到 {len(elements)} 个元素")
                return elements, True
            else:
                print(f"  ⚠️ [线程{thread_id}] OmniParser未检测到任何元素")
                return [], False
                
        except Exception as e:
            thread_id = threading.current_thread().ident
            print(f"  ⚠️ [线程{thread_id}] OmniParser检测失败: {e}")
            return [], False
    
    def _parse_results(self, parsed_content: List[str]) -> List[OmniElement]:
        """解析OmniParser输出"""
        elements = []
        
        for i, content in enumerate(parsed_content):
            try:
                # 解析格式: "Type: description" 或包含坐标信息
                if ':' in content:
                    parts = content.split(':', 1)
                    elem_type = parts[0].strip().lower()
                    description = parts[1].strip() if len(parts) > 1 else ""
                else:
                    elem_type = 'unknown'
                    description = content
                
                # 映射类型
                type_mapping = {
                    'icon': 'icon',
                    'button': 'button',
                    'text': 'text',
                    'image': 'image',
                    'input': 'input',
                    'link': 'link',
                    'checkbox': 'checkbox',
                    'radio': 'radio',
                    'dropdown': 'dropdown',
                    'tab': 'tab',
                    'menu': 'menu',
                    'slider': 'slider',
                    'toggle': 'toggle',
                    'card': 'card',
                    'banner': 'banner',
                    'logo': 'logo',
                    'search': 'search',
                    'notification': 'notification',
                    'badge': 'badge',
                    'avatar': 'avatar',
                    'chart': 'chart',
                    'graph': 'graph'
                }
                
                mapped_type = type_mapping.get(elem_type, 'unknown')
                
                elements.append(OmniElement(
                    id=i,
                    type=mapped_type,
                    bbox=(0.0, 0.0, 1.0, 1.0),  # 默认全图，后续可以从description解析
                    content=description,
                    confidence=0.8
                ))
                
            except Exception as e:
                continue
        
        return elements
    
    def get_elements_description(self, elements: List[OmniElement]) -> str:
        """获取元素的文本描述"""
        if not elements:
            return "未检测到UI元素"
        
        lines = []
        for elem in elements[:30]:  # 只显示前30个
            lines.append(f"  - [{elem.type}] {elem.content}")
        
        if len(elements) > 30:
            lines.append(f"  ... 还有 {len(elements) - 30} 个元素")
        
        return '\n'.join(lines)
    
    def save_debug_output(
        self, 
        image_path: str, 
        elements: List[OmniElement],
        output_dir: Optional[str] = None
    ):
        """保存调试输出"""
        if output_dir is None:
            output_dir = os.path.dirname(image_path) or '.'
        
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        base_name = Path(image_path).stem
        
        # 保存JSON
        json_path = output_path / f'{base_name}_omniparser.json'
        import json
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump([e.to_dict() for e in elements], f, ensure_ascii=False, indent=2)
        
        # 保存文本
        text_path = output_path / f'{base_name}_omniparser.txt'
        with open(text_path, 'w', encoding='utf-8') as f:
            for elem in elements:
                f.write(f"[{elem.type}] {elem.content}\n")
        
        thread_id = threading.current_thread().ident
        print(f"  💾 [线程{thread_id}] 调试输出已保存: {json_path}")


# 全局处理器实例（线程安全）
_omniparser_processor = None
_processor_lock = threading.Lock()


def get_omniparser_processor() -> OmniParserProcessor:
    """获取全局OmniParser处理器实例（线程安全）"""
    global _omniparser_processor
    
    if _omniparser_processor is None:
        with _processor_lock:
            if _omniparser_processor is None:
                _omniparser_processor = OmniParserProcessor()
    
    return _omniparser_processor
