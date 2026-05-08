"""
HTML渲染和截图模块
使用Selenium渲染HTML并截图
"""

import os
import time
from pathlib import Path
from typing import Optional, Tuple

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    print("  ⚠️ selenium未安装，HTML渲染功能将不可用")

from .chromedriver_manager import get_chromedriver_path


class HTMLRenderer:
    """HTML渲染器"""
    
    def __init__(self):
        if not SELENIUM_AVAILABLE:
            raise ImportError("selenium is required for HTML rendering. Install with: pip install selenium")
        self.chromedriver_path = None
    
    def render_and_capture(
        self, 
        html_path: str, 
        output_image_path: str, 
        window_size: Tuple[int, int] = (390, 844)
    ) -> bool:
        """
        使用Selenium渲染HTML并截图
        
        Args:
            html_path: HTML文件路径
            output_image_path: 输出截图路径
            window_size: 窗口大小 (width, height)
        
        Returns:
            是否成功
        """
        try:
            # 确保输出目录存在
            output_dir = Path(output_image_path).parent
            if output_dir:
                output_dir.mkdir(parents=True, exist_ok=True)
            
            # 检查并设置ChromeDriver
            if not self.chromedriver_path:
                self.chromedriver_path = get_chromedriver_path()
            
            if not self.chromedriver_path:
                print("❌ ChromeDriver设置失败，跳过渲染")
                return False
            
            # 设置Chrome选项
            options = webdriver.ChromeOptions()
            options.add_argument('--headless=new')
            options.add_argument('--disable-gpu')
            options.add_argument(f'--window-size={window_size[0]},{window_size[1]}')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-setuid-sandbox')
            options.add_argument('--disable-web-security')
            options.add_argument('--disable-features=IsolateOrigins,site-per-process')
            options.add_argument('--disable-extensions')
            options.add_argument('--disable-default-apps')
            options.add_argument('--mute-audio')
            options.add_argument('--hide-scrollbars')
            options.add_argument('--force-device-scale-factor=1')
            
            # 使用项目目录下的ChromeDriver
            service = Service(self.chromedriver_path)
            print(f"使用ChromeDriver: {self.chromedriver_path}")
            
            # 初始化驱动
            driver = webdriver.Chrome(service=service, options=options)
            
            # 加载HTML文件
            driver.get(f'file://{os.path.abspath(html_path)}')
            
            # 等待页面加载
            time.sleep(1.5)
            
            # 截图
            driver.save_screenshot(output_image_path)
            
            # 关闭驱动
            driver.quit()
            
            print(f"✅ HTML渲染完成: {output_image_path}")
            return True
            
        except Exception as e:
            print(f"HTML渲染失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def compare_with_original(
        self,
        html_path: str,
        original_image_path: str,
        output_image_path: Optional[str] = None,
        window_size: Tuple[int, int] = (390, 844)
    ) -> Optional[float]:
        """
        渲染HTML并与原图对比
        
        Args:
            html_path: HTML文件路径
            original_image_path: 原始图片路径
            output_image_path: 输出截图路径，为None则不保存截图
            window_size: 窗口大小
        
        Returns:
            SSIM相似度分数，失败返回None
        """
        from .ssim_analyzer import get_ssim_analyzer
        import tempfile
        
        # 如果没有指定输出路径，使用临时文件
        temp_file = None
        if output_image_path is None:
            temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
            output_image_path = temp_file.name
            temp_file.close()
        
        try:
            # 渲染HTML
            success = self.render_and_capture(html_path, output_image_path, window_size)
            if not success:
                return None
            
            # 计算SSIM
            try:
                analyzer = get_ssim_analyzer()
                ssim_score = analyzer.calculate_ssim(original_image_path, output_image_path)
                return ssim_score
            except Exception as e:
                print(f"SSIM计算失败: {e}")
                return None
        finally:
            # 清理临时文件
            if temp_file is not None and os.path.exists(output_image_path):
                os.unlink(output_image_path)


# 便捷函数
def get_html_renderer() -> HTMLRenderer:
    """获取HTML渲染器实例"""
    return HTMLRenderer()
