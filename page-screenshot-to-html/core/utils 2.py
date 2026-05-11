"""
工具函数模块
"""
import os
import re
import base64
from typing import Optional, Tuple
from PIL import Image


def get_image_size(image_path: str) -> Tuple[int, int]:
    """获取图片尺寸"""
    with Image.open(image_path) as img:
        return img.size


def resize_image_if_needed(image: Image.Image, max_size: int = 4096) -> Image.Image:
    """如果图片过大则调整大小"""
    width, height = image.size
    
    if width <= max_size and height <= max_size:
        return image
    
    # 计算缩放比例
    ratio = min(max_size / width, max_size / height)
    new_width = int(width * ratio)
    new_height = int(height * ratio)
    
    print(f"  📐 图片过大，调整大小: {width}x{height} -> {new_width}x{new_height}")
    return image.resize((new_width, new_height), Image.Resampling.LANCZOS)


def image_to_base64(image_path: str, max_size: Optional[int] = None) -> str:
    """将图片转换为base64编码"""
    with open(image_path, 'rb') as f:
        image_data = f.read()
    
    # 如果需要调整大小
    if max_size:
        image = Image.open(image_path)
        image = resize_image_if_needed(image, max_size)
        
        # 转换为bytes
        import io
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG', quality=95)
        image_data = buffer.getvalue()
    
    return base64.b64encode(image_data).decode('utf-8')


def clean_html_response(html: str) -> str:
    """清理API返回的HTML响应"""
    # 移除markdown代码块标记
    html = re.sub(r'^```html\s*', '', html, flags=re.IGNORECASE)
    html = re.sub(r'```\s*$', '', html)
    
    # 移除可能的解释文字
    lines = html.split('\n')
    result_lines = []
    in_html = False
    
    for line in lines:
        stripped = line.strip()
        
        # 找到HTML开始
        if stripped.startswith('<!DOCTYPE') or stripped.startswith('<html'):
            in_html = True
        
        if in_html:
            result_lines.append(line)
        
        # 找到HTML结束
        if stripped == '</html>':
            break
    
    return '\n'.join(result_lines)


def sanitize_filename(filename: str) -> str:
    """清理文件名，移除非法字符"""
    # 移除或替换非法字符
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    filename = filename.strip('. ')
    return filename


def ensure_dir(path: str) -> str:
    """确保目录存在，如果不存在则创建"""
    os.makedirs(path, exist_ok=True)
    return path


def format_duration(seconds: float) -> str:
    """格式化时间间隔"""
    if seconds < 1:
        return f"{seconds*1000:.0f}ms"
    elif seconds < 60:
        return f"{seconds:.1f}s"
    else:
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}m{secs:.0f}s"


def truncate_string(s: str, max_length: int = 100, suffix: str = '...') -> str:
    """截断字符串"""
    if len(s) <= max_length:
        return s
    return s[:max_length - len(suffix)] + suffix


def merge_spaces(text: str) -> str:
    """合并中文字符间的空格"""
    # 匹配中文字符间的空格
    import re
    # 先合并多个空格为一个
    text = re.sub(r' +', ' ', text)
    # 移除中文字符间的空格
    text = re.sub(r'([\u4e00-\u9fa5]) ([\u4e00-\u9fa5])', r'\1\2', text)
    return text


def calculate_dpr(original_width: int, logical_width: int = 390) -> float:
    """计算设备像素比"""
    return original_width / logical_width


def logical_to_physical(logical_px: int, dpr: float) -> int:
    """逻辑像素转物理像素"""
    return int(logical_px * dpr)


def physical_to_logical(physical_px: int, dpr: float) -> int:
    """物理像素转逻辑像素"""
    return int(physical_px / dpr)


class ProgressBar:
    """简单的进度条"""
    
    def __init__(self, total: int, desc: str = "Processing", width: int = 40):
        self.total = total
        self.desc = desc
        self.width = width
        self.current = 0
    
    def update(self, n: int = 1):
        """更新进度"""
        self.current += n
        self._draw()
    
    def _draw(self):
        """绘制进度条"""
        percent = self.current / self.total if self.total > 0 else 1
        filled = int(self.width * percent)
        bar = '█' * filled + '░' * (self.width - filled)
        print(f'\r{self.desc}: [{bar}] {percent*100:.1f}% ({self.current}/{self.total})', end='', flush=True)
    
    def finish(self):
        """完成进度条"""
        self.current = self.total
        self._draw()
        print()  # 换行
