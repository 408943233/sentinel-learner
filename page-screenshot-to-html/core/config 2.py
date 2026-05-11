"""
配置管理模块 - 使用pydantic-settings集中管理所有配置
"""
from typing import Optional, List
from pydantic import Field, validator
from pydantic_settings import BaseSettings
import os

# 预先加载.env文件
try:
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
except ImportError:
    pass


class APIConfig(BaseSettings):
    """API配置"""
    kimi_api_key: Optional[str] = Field(default=None, env="KIMI_CODING_API_KEY")
    kimi_base_url: str = Field(default="https://api.kimi.com/coding/", env="KIMI_CODING_BASE_URL")
    kimi_model: str = Field(default="k2p5", env="KIMI_CODING_MODEL")
    
    openclaw_api_key: Optional[str] = Field(default=None, env="OPENCLAW_API_KEY")
    openclaw_base_url: str = Field(default="https://api.openclaw.dev/v1", env="OPENCLAW_BASE_URL")
    
    moonshot_api_key: Optional[str] = Field(default=None, env="MOONSHOT_API_KEY")
    moonshot_base_url: str = Field(default="https://api.moonshot.cn/v1", env="MOONSHOT_BASE_URL")
    
    api_timeout: int = Field(default=120, env="API_TIMEOUT")
    max_retries: int = Field(default=10, env="API_MAX_RETRIES")
    retry_delay: float = Field(default=5.0, env="API_RETRY_DELAY")
    max_retry_delay: float = Field(default=300.0, env="API_MAX_RETRY_DELAY")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


class OCRConfig(BaseSettings):
    """OCR配置"""
    use_gpu: bool = Field(default=False, env="OCR_USE_GPU")
    lang: str = Field(default="ch", env="OCR_LANG")
    det_db_thresh: float = Field(default=0.1, env="OCR_DET_DB_THRESH")
    det_db_box_thresh: float = Field(default=0.3, env="OCR_DET_DB_BOX_THRESH")
    drop_score: float = Field(default=0.2, env="OCR_DROP_SCORE")
    max_batch_size: int = Field(default=1024, env="OCR_MAX_BATCH_SIZE")
    enable_cache: bool = Field(default=True, env="OCR_ENABLE_CACHE")
    cache_size: int = Field(default=100, env="OCR_CACHE_SIZE")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


class ImageConfig(BaseSettings):
    """图像处理配置"""
    max_image_size: int = Field(default=4096, env="MAX_IMAGE_SIZE")
    default_dpr: int = Field(default=3, env="DEFAULT_DPR")
    logical_width: int = Field(default=390, env="LOGICAL_WIDTH")
    logical_height: int = Field(default=844, env="LOGICAL_HEIGHT")
    status_bar_height: int = Field(default=24, env="STATUS_BAR_HEIGHT")
    nav_bar_height: int = Field(default=44, env="NAV_BAR_HEIGHT")
    bottom_bar_height: int = Field(default=50, env="BOTTOM_BAR_HEIGHT")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


class OutputConfig(BaseSettings):
    """输出配置"""
    output_dir: str = Field(default="./output", env="OUTPUT_DIR")
    icons_dir: str = Field(default="./output/icons", env="ICONS_DIR")
    save_intermediate: bool = Field(default=False, env="SAVE_INTERMEDIATE")
    generate_report: bool = Field(default=True, env="GENERATE_REPORT")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


class PerformanceConfig(BaseSettings):
    """性能配置"""
    enable_monitoring: bool = Field(default=True, env="ENABLE_MONITORING")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    enable_async: bool = Field(default=True, env="ENABLE_ASYNC")
    max_workers: int = Field(default=4, env="MAX_WORKERS")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


def _get_env(key: str, default=None):
    """从环境变量获取值"""
    return os.environ.get(key, default)


class AppConfig:
    """应用主配置 - 直接使用os.environ读取"""
    
    def __init__(self):
        # API配置
        self.kimi_api_key: Optional[str] = _get_env("KIMI_CODING_API_KEY")
        self.kimi_base_url: str = _get_env("KIMI_CODING_BASE_URL", "https://api.kimi.com/coding/")
        self.kimi_model: str = _get_env("KIMI_CODING_MODEL", "k2p5")
        
        self.openclaw_api_key: Optional[str] = _get_env("OPENCLAW_API_KEY")
        self.openclaw_base_url: str = _get_env("OPENCLAW_BASE_URL", "https://api.openclaw.dev/v1")
        
        self.moonshot_api_key: Optional[str] = _get_env("MOONSHOT_API_KEY")
        self.moonshot_base_url: str = _get_env("MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1")
        
        self.api_timeout: int = int(_get_env("API_TIMEOUT", "120"))
        self.max_retries: int = int(_get_env("API_MAX_RETRIES", "5"))
        self.retry_delay: float = float(_get_env("API_RETRY_DELAY", "1.0"))
        self.max_retry_delay: float = float(_get_env("API_MAX_RETRY_DELAY", "60.0"))
        
        # OCR配置
        self.ocr_use_gpu: bool = _get_env("OCR_USE_GPU", "false").lower() == "true"
        self.ocr_lang: str = _get_env("OCR_LANG", "ch")
        self.ocr_det_db_thresh: float = float(_get_env("OCR_DET_DB_THRESH", "0.1"))
        self.ocr_det_db_box_thresh: float = float(_get_env("OCR_DET_DB_BOX_THRESH", "0.3"))
        self.ocr_drop_score: float = float(_get_env("OCR_DROP_SCORE", "0.2"))
        self.ocr_max_batch_size: int = int(_get_env("OCR_MAX_BATCH_SIZE", "1024"))
        self.ocr_enable_cache: bool = _get_env("OCR_ENABLE_CACHE", "true").lower() == "true"
        self.ocr_cache_size: int = int(_get_env("OCR_CACHE_SIZE", "100"))
        
        # 图像配置
        self.max_image_size: int = int(_get_env("MAX_IMAGE_SIZE", "4096"))
        self.default_dpr: int = int(_get_env("DEFAULT_DPR", "3"))
        self.logical_width: int = int(_get_env("LOGICAL_WIDTH", "390"))
        self.logical_height: int = int(_get_env("LOGICAL_HEIGHT", "844"))
        self.status_bar_height: int = int(_get_env("STATUS_BAR_HEIGHT", "24"))
        self.nav_bar_height: int = int(_get_env("NAV_BAR_HEIGHT", "44"))
        self.bottom_bar_height: int = int(_get_env("BOTTOM_BAR_HEIGHT", "50"))
        
        # 输出配置
        self.output_dir: str = _get_env("OUTPUT_DIR", "./output")
        self.icons_dir: str = _get_env("ICONS_DIR", "./output/icons")
        self.save_intermediate: bool = _get_env("SAVE_INTERMEDIATE", "false").lower() == "true"
        self.generate_report: bool = _get_env("GENERATE_REPORT", "true").lower() == "true"
        
        # 性能配置
        self.enable_monitoring: bool = _get_env("ENABLE_MONITORING", "true").lower() == "true"
        self.log_level: str = _get_env("LOG_LEVEL", "INFO")
        self.enable_async: bool = _get_env("ENABLE_ASYNC", "true").lower() == "true"
        self.max_workers: int = int(_get_env("MAX_WORKERS", "4"))
        
        self.debug: bool = _get_env("DEBUG", "false").lower() == "true"
        self.accuracy: str = _get_env("ACCURACY", "medium")
        
        # 确保输出目录存在
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.icons_dir, exist_ok=True)
    
    # 兼容旧代码的属性访问
    @property
    def api(self):
        class APIWrapper:
            pass
        wrapper = APIWrapper()
        wrapper.kimi_api_key = self.kimi_api_key
        wrapper.kimi_base_url = self.kimi_base_url
        wrapper.kimi_model = self.kimi_model
        wrapper.openclaw_api_key = self.openclaw_api_key
        wrapper.openclaw_base_url = self.openclaw_base_url
        wrapper.moonshot_api_key = self.moonshot_api_key
        wrapper.moonshot_base_url = self.moonshot_base_url
        wrapper.api_timeout = self.api_timeout
        wrapper.max_retries = self.max_retries
        wrapper.retry_delay = self.retry_delay
        wrapper.max_retry_delay = self.max_retry_delay
        return wrapper
    
    @property
    def ocr(self):
        class OCRWrapper:
            pass
        wrapper = OCRWrapper()
        wrapper.use_gpu = self.ocr_use_gpu
        wrapper.lang = self.ocr_lang
        wrapper.det_db_thresh = self.ocr_det_db_thresh
        wrapper.det_db_box_thresh = self.ocr_det_db_box_thresh
        wrapper.drop_score = self.ocr_drop_score
        wrapper.max_batch_size = self.ocr_max_batch_size
        wrapper.enable_cache = self.ocr_enable_cache
        wrapper.cache_size = self.ocr_cache_size
        return wrapper
    
    @property
    def image(self):
        class ImageWrapper:
            pass
        wrapper = ImageWrapper()
        wrapper.max_image_size = self.max_image_size
        wrapper.default_dpr = self.default_dpr
        wrapper.logical_width = self.logical_width
        wrapper.logical_height = self.logical_height
        wrapper.status_bar_height = self.status_bar_height
        wrapper.nav_bar_height = self.nav_bar_height
        wrapper.bottom_bar_height = self.bottom_bar_height
        return wrapper
    
    @property
    def output(self):
        class OutputWrapper:
            pass
        wrapper = OutputWrapper()
        wrapper.output_dir = self.output_dir
        wrapper.icons_dir = self.icons_dir
        wrapper.save_intermediate = self.save_intermediate
        wrapper.generate_report = self.generate_report
        return wrapper
    
    @property
    def performance(self):
        class PerformanceWrapper:
            pass
        wrapper = PerformanceWrapper()
        wrapper.enable_monitoring = self.enable_monitoring
        wrapper.log_level = self.log_level
        wrapper.enable_async = self.enable_async
        wrapper.max_workers = self.max_workers
        return wrapper


# 全局配置实例
_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """获取全局配置实例（单例模式）"""
    global _config
    if _config is None:
        _config = AppConfig()
    return _config


def reload_config() -> AppConfig:
    """重新加载配置"""
    global _config
    _config = None
    # 强制重新加载环境变量
    from pydantic_settings import SettingsConfigDict
    # 清除缓存后重新创建
    _config = AppConfig(_env_file='.env', _env_file_encoding='utf-8')
    return _config
