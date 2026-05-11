#!/usr/bin/env python3
"""简化测试 - 检查ChromeDriver是否正常工作"""

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time

print("测试ChromeDriver...")

chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--ignore-certificate-errors")
chrome_options.add_argument("--window-size=375,812")

try:
    print("启动Chrome...")
    driver = webdriver.Chrome(options=chrome_options)
    print("✓ Chrome启动成功")
    
    print("访问百度...")
    driver.get("https://www.baidu.com")
    print(f"✓ 页面标题: {driver.title}")
    
    driver.quit()
    print("✓ 测试完成")
except Exception as e:
    print(f"✗ 错误: {e}")
    import traceback
    traceback.print_exc()
