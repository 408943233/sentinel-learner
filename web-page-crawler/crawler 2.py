#!/usr/bin/env python3
"""
网页自动化爬虫 - 遍历页面元素并截图
用于银河证券H5交易页面测试
"""

import os
import sys
import time
import json
from datetime import datetime
from urllib.parse import urljoin, urlparse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import (
    ElementNotInteractableException,
    StaleElementReferenceException,
    TimeoutException,
    NoSuchElementException
)
from webdriver_manager.chrome import ChromeDriverManager


class WebPageCrawler:
    """网页爬虫 - 自动遍历页面元素并截图"""
    
    def __init__(self, output_dir="screenshots"):
        self.output_dir = output_dir
        self.visited_urls = set()
        self.page_tree = {
            "root": None,
            "pages": {}
        }
        self.screenshot_count = 0
        self.driver = None
        
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        
    def setup_driver(self):
        """配置Chrome浏览器"""
        chrome_options = Options()
        
        # 无头模式（不显示浏览器窗口，避免macOS安全拦截）
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--window-size=375,812")
        
        # 手机模式模拟
        mobile_emulation = {
            "deviceMetrics": {"width": 375, "height": 812, "pixelRatio": 3.0},
            "userAgent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15"
        }
        chrome_options.add_experimental_option("mobileEmulation", mobile_emulation)
        
        # 其他配置
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--ignore-certificate-errors")
        chrome_options.add_argument("--ignore-ssl-errors")
        
        # 处理HTTPS证书错误
        chrome_options.add_argument("--allow-insecure-localhost")
        chrome_options.add_argument("--allow-running-insecure-content")
        
        # 禁用安全限制（macOS需要）
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--disable-features=IsolateOrigins,site-per-process")
        
        # 使用webdriver-manager自动管理ChromeDriver
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.driver.set_page_load_timeout(15)
        self.driver.set_script_timeout(15)
        self.driver.implicitly_wait(5)
        
    def login(self, url, username, password):
        """登录页面"""
        print(f"访问登录页面: {url}")
        try:
            self.driver.get(url)
        except TimeoutException:
            print("页面加载超时，尝试继续执行...")
            # 停止页面加载
            self.driver.execute_script("window.stop();")
        time.sleep(3)
        
        # 截图登录页
        self.take_screenshot("login_page")
        
        try:
            print("查找登录入口...")
            
            # 等待页面加载
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # 先尝试查找账号输入框（可能已经在登录页）
            username_inputs = self.driver.find_elements(By.XPATH, 
                "//input[contains(@placeholder, '账号') or contains(@placeholder, '用户名') or @type='text']")
            password_inputs = self.driver.find_elements(By.XPATH, 
                "//input[@type='password']")
            
            # 如果没找到输入框，先点击"买入"等功能按钮触发登录弹窗
            if not username_inputs or not password_inputs:
                print("未找到登录表单，点击功能按钮触发登录弹窗...")
                
                # 查找功能按钮（买入、卖出等）
                func_buttons = self.driver.find_elements(By.XPATH,
                    "//*[contains(text(), '买入') or contains(text(), '卖出') or " +
                    "contains(text(), '新股') or contains(text(), '申购')]")
                
                if func_buttons:
                    print(f"找到 {len(func_buttons)} 个功能按钮，点击第一个触发登录...")
                    try:
                        # 滚动到元素并点击
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", func_buttons[0])
                        time.sleep(1)
                        func_buttons[0].click()
                        print("已点击功能按钮，等待登录弹窗...")
                        time.sleep(5)  # 增加等待时间，等待弹窗动画
                        self.take_screenshot("login_form_opened")
                        
                        # 再次查找登录表单 - 根据实际弹窗调整选择器
                        # 客户号输入框
                        username_inputs = self.driver.find_elements(By.XPATH, 
                            "//input[contains(@placeholder, '客户号') or contains(@placeholder, '账号') or " +
                            "contains(@placeholder, '用户名') or @type='text']")
                        # 交易密码输入框 - 更宽泛的匹配
                        password_inputs = self.driver.find_elements(By.XPATH, 
                            "//input[contains(@placeholder, '密码') or @type='password' or contains(@class, 'password')] | " +
                            "//div[contains(@class, 'password')]//input | " +
                            "//*[contains(text(), '交易密码')]/following-sibling::input")
                    except Exception as e:
                        print(f"点击功能按钮失败: {e}")
                        return False
                else:
                    print("未找到功能按钮")
                    return False
            
            # 填写账号密码
            if username_inputs and password_inputs:
                print("找到登录表单，填写账号密码...")
                
                # 强制使用JavaScript方式填写，确保输入成功
                print(f"  填写账号: {username}")
                self.driver.execute_script(
                    "arguments[0].focus(); " +
                    "arguments[0].value = arguments[1]; " +
                    "arguments[0].dispatchEvent(new Event('input', { bubbles: true })); " +
                    "arguments[0].dispatchEvent(new Event('change', { bubbles: true })); " +
                    "arguments[0].dispatchEvent(new KeyboardEvent('keydown', {key: 'Tab', bubbles: true})); " +
                    "arguments[0].dispatchEvent(new KeyboardEvent('keyup', {key: 'Tab', bubbles: true}));",
                    username_inputs[0], username
                )
                
                time.sleep(1)
                
                print(f"  填写密码")
                self.driver.execute_script(
                    "arguments[0].focus(); " +
                    "arguments[0].value = arguments[1]; " +
                    "arguments[0].dispatchEvent(new Event('input', { bubbles: true })); " +
                    "arguments[0].dispatchEvent(new Event('change', { bubbles: true })); " +
                    "arguments[0].dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true})); " +
                    "arguments[0].dispatchEvent(new KeyboardEvent('keyup', {key: 'Enter', bubbles: true}));",
                    password_inputs[0], password
                )
                
                time.sleep(1)
                
                # 查找登录按钮 - 优先按ID查找
                login_buttons = self.driver.find_elements(By.ID, "btn_login")
                
                # 如果没找到，再按文本查找
                if not login_buttons:
                    login_buttons = self.driver.find_elements(By.XPATH,
                        "//*[contains(text(), '确认登录') or contains(text(), '登录') or contains(text(), '确定')]" +
                        "[self::button or self::div or self::a]")
                
                if login_buttons:
                    print("点击登录按钮...")
                    try:
                        # 使用JavaScript点击，确保触发所有事件
                        self.driver.execute_script(
                            "arguments[0].focus(); " +
                            "arguments[0].click(); " +
                            "arguments[0].dispatchEvent(new Event('click', { bubbles: true }));",
                            login_buttons[0]
                        )
                    except Exception as e:
                        print(f"  点击失败，使用备用方式: {e}")
                        self.driver.execute_script("arguments[0].click();", login_buttons[0])
                    
                    # 增加等待时间，确保登录请求完成
                    time.sleep(5)
                    
                    # 截图登录后页面
                    self.take_screenshot("after_login")
                    
                    # 检查是否登录成功
                    current_url = self.driver.current_url
                    page_source = self.driver.page_source
                    
                    # 检查是否仍在登录页面或包含登录失败提示
                    if "请输入交易密码" in page_source or "登录" in page_source.lower():
                        print("登录失败，仍显示登录提示")
                        # 尝试再次填写密码
                        print("再次尝试填写密码...")
                        self.driver.execute_script(
                            "arguments[0].focus(); " +
                            "arguments[0].value = arguments[1]; " +
                            "arguments[0].dispatchEvent(new Event('input', { bubbles: true })); " +
                            "arguments[0].dispatchEvent(new Event('change', { bubbles: true }));",
                            password_inputs[0], password
                        )
                        time.sleep(1)
                        self.driver.execute_script("arguments[0].click();", login_buttons[0])
                        time.sleep(3)
                        self.take_screenshot("after_login_second_attempt")
                        
                    return True
                else:
                    print("未找到登录按钮")
            else:
                print("点击登录入口后仍未找到登录表单")
                return False
                    
        except Exception as e:
            print(f"登录过程出错: {e}")
            import traceback
            traceback.print_exc()
            
        return False
    
    def take_screenshot(self, name):
        """截图并保存"""
        self.screenshot_count += 1
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.screenshot_count:03d}_{name}_{timestamp}.png"
        filepath = os.path.join(self.output_dir, filename)
        
        self.driver.save_screenshot(filepath)
        print(f"  截图保存: {filename}")
        
        return filepath
    
    def get_clickable_elements(self):
        """获取页面上所有可点击的元素"""
        # 等待页面完全加载
        time.sleep(2)
        
        # 滚动页面确保所有元素加载
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)
        
        clickable_selectors = [
            "button",
            "a",
            "[onclick]",
            "[role='button']",
            "[role='link']",
            "[tabindex]",
            ".btn",
            ".button",
            "input[type='button']",
            "input[type='submit']",
            "input[type='text']",
            "input[type='password']",
            "[class*='btn']",
            "[class*='button']",
            "[class*='item']",
            "[class*='cell']",
            "[class*='menu']",
            "[class*='nav']",
            "[class*='tab']",
            "div",  # 移动端很多可点击div
            "span",
            "li"
        ]
        
        elements = []
        for selector in clickable_selectors:
            try:
                found = self.driver.find_elements(By.CSS_SELECTOR, selector)
                for elem in found:
                    try:
                        if elem.is_displayed():
                            # 获取元素位置和大小
                            location = elem.location
                            size = elem.size
                            
                            # 过滤太小的元素（可能是装饰性元素）
                            if size.get('width', 0) < 20 or size.get('height', 0) < 20:
                                continue
                            
                            # 获取元素信息
                            text = elem.text.strip()[:50] if elem.text else ""
                            elem_class = elem.get_attribute("class") or ""
                            elem_id = elem.get_attribute("id") or ""
                            
                            # 只保留有文本或特定class的元素
                            if text or 'btn' in elem_class or 'button' in elem_class or 'item' in elem_class:
                                elem_info = {
                                    "element": elem,
                                    "tag": elem.tag_name,
                                    "text": text,
                                    "class": elem_class,
                                    "id": elem_id,
                                    "selector": selector,
                                    "location": location,
                                    "size": size
                                }
                                elements.append(elem_info)
                    except:
                        continue
            except:
                continue
                
        # 去重
        seen = set()
        unique_elements = []
        for elem in elements:
            key = f"{elem['tag']}_{elem['text']}_{elem['class']}_{elem['location']}"
            if key not in seen and elem['text']:  # 只保留有文本的元素
                seen.add(key)
                unique_elements.append(elem)
                
        return unique_elements
    
    def click_element_and_capture(self, elem_info, parent_path=""):
        """点击元素并截图"""
        elem = elem_info["element"]
        text = elem_info["text"] or elem_info["id"] or elem_info["class"][:20] or "unknown"
        
        # 构建路径名
        safe_text = "".join(c for c in text if c.isalnum() or c in "_-").strip()[:30]
        current_path = f"{parent_path}/{safe_text}" if parent_path else safe_text
        
        print(f"\n点击: {text[:30]} ({elem_info['tag']})")
        
        try:
            # 记录当前URL
            current_url = self.driver.current_url
            
            # 滚动到元素位置
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
            time.sleep(0.5)
            
            # 截图点击前
            before_screenshot = self.take_screenshot(f"before_{current_path}")
            
            # 点击元素
            elem.click()
            time.sleep(2)
            
            # 截图点击后
            after_screenshot = self.take_screenshot(f"after_{current_path}")
            
            # 记录页面信息
            new_url = self.driver.current_url
            page_info = {
                "path": current_path,
                "element_text": text,
                "element_tag": elem_info["tag"],
                "before_url": current_url,
                "after_url": new_url,
                "before_screenshot": before_screenshot,
                "after_screenshot": after_screenshot
            }
            
            self.page_tree["pages"][current_path] = page_info
            
            # 如果URL变化了，记录为新页面
            if new_url != current_url:
                print(f"  页面跳转: {new_url}")
                if new_url not in self.visited_urls:
                    self.visited_urls.add(new_url)
                    # 递归探索新页面
                    self.explore_page(current_path)
                    
            return True
            
        except Exception as e:
            print(f"  点击失败: {e}")
            return False
    
    def explore_page(self, parent_path=""):
        """探索当前页面的所有可点击元素"""
        print(f"\n{'='*60}")
        print(f"探索页面: {self.driver.current_url}")
        print(f"路径: {parent_path or 'root'}")
        print(f"{'='*60}")
        
        # 获取可点击元素
        elements = self.get_clickable_elements()
        print(f"找到 {len(elements)} 个可点击元素")
        
        # 优先点击买入、卖出等关键按钮
        priority_keywords = ["买入", "卖出", "撤单", "持仓", "查询", "转账", "申购", "理财"]
        
        # 排序：优先处理关键按钮
        def sort_key(elem):
            text = elem["text"].lower()
            for i, keyword in enumerate(priority_keywords):
                if keyword in text:
                    return (i, text)
            return (999, text)
        
        elements.sort(key=sort_key)
        
        # 点击每个元素
        for i, elem_info in enumerate(elements[:20]):  # 限制最多20个，避免过多
            try:
                # 重新获取元素（避免stale element）
                fresh_elem = self.refresh_element(elem_info)
                if fresh_elem:
                    elem_info["element"] = fresh_elem
                    self.click_element_and_capture(elem_info, parent_path)
                    
                    # 返回原页面（如果不是新页面）
                    if parent_path:
                        self.driver.back()
                        time.sleep(2)
                        
            except Exception as e:
                print(f"  处理元素时出错: {e}")
                continue
    
    def refresh_element(self, elem_info):
        """重新获取元素（处理stale element）"""
        try:
            # 尝试用相同的选择器重新查找
            selector = elem_info["selector"]
            text = elem_info["text"]
            
            if elem_info["id"]:
                elements = self.driver.find_elements(By.ID, elem_info["id"])
            elif text:
                xpath = f"//{elem_info['tag']}[contains(text(), '{text}')]"
                elements = self.driver.find_elements(By.XPATH, xpath)
            else:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
            
            for elem in elements:
                if elem.is_displayed():
                    return elem
        except:
            pass
        return None
    
    def save_page_tree(self):
        """保存页面路径树"""
        tree_file = os.path.join(self.output_dir, "page_tree.json")
        with open(tree_file, "w", encoding="utf-8") as f:
            json.dump(self.page_tree, f, ensure_ascii=False, indent=2)
        print(f"\n页面路径树已保存: {tree_file}")
        
    def run(self, url, username=None, password=None):
        """运行爬虫"""
        try:
            self.setup_driver()
            
            # 如果需要登录
            if username and password:
                if not self.login(url, username, password):
                    print("登录失败，继续以未登录状态探索")
                    self.driver.get(url)
                    time.sleep(3)
            else:
                self.driver.get(url)
                time.sleep(3)
            
            # 截图首页
            self.take_screenshot("index_page")
            self.visited_urls.add(self.driver.current_url)
            
            # 探索页面
            self.explore_page()
            
            # 保存结果
            self.save_page_tree()
            
            print(f"\n{'='*60}")
            print(f"爬取完成!")
            print(f"共截图: {self.screenshot_count} 张")
            print(f"探索页面: {len(self.visited_urls)} 个")
            print(f"输出目录: {self.output_dir}")
            print(f"{'='*60}")
            
        except Exception as e:
            print(f"运行出错: {e}")
            import traceback
            traceback.print_exc()
            
        finally:
            if self.driver:
                self.driver.quit()


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="网页自动化爬虫 - 遍历元素并截图")
    parser.add_argument("--url", default="https://thirdtest.chinastock.com.cn:7703/site/h5trade/NewHome/index.html",
                        help="目标URL")
    parser.add_argument("--username", default="10100000004", help="登录账号")
    parser.add_argument("--password", default="112233", help="登录密码")
    parser.add_argument("--output", default="screenshots", help="截图输出目录")
    
    args = parser.parse_args()
    
    print("="*60)
    print("网页自动化爬虫")
    print("="*60)
    print(f"目标URL: {args.url}")
    print(f"输出目录: {args.output}")
    print("="*60)
    print()
    
    crawler = WebPageCrawler(output_dir=args.output)
    crawler.run(args.url, args.username, args.password)


if __name__ == "__main__":
    main()
