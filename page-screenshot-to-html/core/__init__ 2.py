"""
Core模块 - 截图转HTML的核心功能
"""
from .config import get_config, reload_config, AppConfig
from .exceptions import (
    ScreenshotToHTMLError,
    OCRError,
    APIError,
    RateLimitError,
    TimeoutError,
    ImageProcessingError,
    HTMLGenerationError,
    ConfigError
)
from .ocr_processor import OCRProcessor, TextBlock, get_ocr_processor
from .api_client import (
    APIClientManager,
    APIProvider,
    APIResponse,
    get_api_manager
)
from .performance_monitor import PerformanceMonitor, Timer, monitor
from .image_analyzer import ImageAnalyzer, analyze_image
from .html_processor import HTMLProcessor, process_html, HTMLIssue
from .omniparser_processor import OmniParserProcessor, OmniElement, get_omniparser_processor
from .ssim_analyzer import SSIMAnalyzer, SSIMBlock, get_ssim_analyzer
from .chromedriver_manager import ChromeDriverManager, get_chromedriver_path
from .html_renderer import HTMLRenderer, get_html_renderer
# 图标提取模块（已禁用）
# from .icon_extractor import IconExtractor, IconInfo, extract_icons_from_image
from .utils import (
    get_image_size,
    resize_image_if_needed,
    image_to_base64,
    clean_html_response,
    sanitize_filename,
    ensure_dir,
    format_duration,
    truncate_string,
    merge_spaces,
    calculate_dpr,
    logical_to_physical,
    physical_to_logical,
    ProgressBar
)

__all__ = [
    # Config
    'get_config',
    'reload_config',
    'AppConfig',
    
    # Exceptions
    'ScreenshotToHTMLError',
    'OCRError',
    'APIError',
    'RateLimitError',
    'TimeoutError',
    'ImageProcessingError',
    'HTMLGenerationError',
    'ConfigError',
    
    # OCR
    'OCRProcessor',
    'TextBlock',
    'get_ocr_processor',
    
    # API
    'APIClientManager',
    'APIProvider',
    'APIResponse',
    'get_api_manager',
    
    # Performance
    'PerformanceMonitor',
    'Timer',
    'monitor',
    
    # Image Analysis
    'ImageAnalyzer',
    'analyze_image',
    
    # HTML Processing
    'HTMLProcessor',
    'process_html',
    'HTMLIssue',

    # OmniParser
    'OmniParserProcessor',
    'OmniElement',
    'get_omniparser_processor',

    # SSIM Analyzer
    'SSIMAnalyzer',
    'SSIMBlock',
    'get_ssim_analyzer',

    # ChromeDriver Manager
    'ChromeDriverManager',
    'get_chromedriver_path',

    # HTML Renderer
    'HTMLRenderer',
    'get_html_renderer',

    # Icon Extractor (已禁用)
    # 'IconExtractor',
    # 'IconInfo',
    # 'extract_icons_from_image',

    # Utils
    'get_image_size',
    'resize_image_if_needed',
    'image_to_base64',
    'clean_html_response',
    'sanitize_filename',
    'ensure_dir',
    'format_duration',
    'truncate_string',
    'merge_spaces',
    'calculate_dpr',
    'logical_to_physical',
    'physical_to_logical',
    'ProgressBar'
]
