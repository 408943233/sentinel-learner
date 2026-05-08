"""
自定义异常类模块
"""


class ScreenshotToHTMLError(Exception):
    """基础异常类"""
    pass


class OCRError(ScreenshotToHTMLError):
    """OCR处理异常"""
    pass


class APIError(ScreenshotToHTMLError):
    """API调用异常"""
    def __init__(self, message: str, status_code: int = None, response_text: str = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class RateLimitError(APIError):
    """API限流异常"""
    pass


class TimeoutError(APIError):
    """API超时异常"""
    pass


class ImageProcessingError(ScreenshotToHTMLError):
    """图像处理异常"""
    pass


class HTMLGenerationError(ScreenshotToHTMLError):
    """HTML生成异常"""
    pass


class ConfigError(ScreenshotToHTMLError):
    """配置异常"""
    pass
