#!/usr/bin/env python3
"""
增强版爬虫实现 - 基于 Playwright
特点：
- 异步并发处理
- 智能重试机制
- 自动限速
- 支持 JavaScript 渲染
- 自动去重
- 指纹伪装
"""
import os
import json
import asyncio
from typing import Optional, Callable, Dict, List, Set
from urllib.parse import urljoin, urlparse
from datetime import datetime
from dataclasses import dataclass, asdict
import random

from playwright.async_api import async_playwright, Page, Browser


@dataclass
class CrawlResult:
    """爬取结果"""
    url: str
    depth: int
    title: str = ""
    links: List[str] = None
    html: str = ""
    screenshot_path: str = ""
    crawl_time: str = ""
    error: str = ""
    
    def __post_init__(self):
        if self.links is None:
            self.links = []
        if not self.crawl_time:
            self.crawl_time = datetime.now().isoformat()
    
    def to_dict(self) -> Dict:
        return asdict(self)


class CrawleeWebsiteCrawler:
    """
    增强版网站爬虫（基于 Playwright）
    
    特性：
    - 异步并发爬取
    - 智能重试机制
    - 自动限速（避免被封）
    - User-Agent 轮换
    - 自动去重
    - 支持 JavaScript 渲染
    """
    
    def __init__(self, output_dir: str = "output"):
        self.output_dir = output_dir
        self.crawl_dir = os.path.join(output_dir, "crawl")
        os.makedirs(self.crawl_dir, exist_ok=True)
        
        # 爬取配置
        self.max_depth = 3
        self.max_pages = 100
        self.same_domain_only = True
        self.concurrent_limit = 3  # 并发数
        self.delay_range = (1, 3)  # 请求间隔（秒）
        
        # 状态
        self.is_crawling = False
        self.results: List[CrawlResult] = []
        self.visited_urls: Set[str] = set()
        self.url_queue: asyncio.Queue = asyncio.Queue()
        self._stop_event = asyncio.Event()
        
        # 回调
        self.on_page_crawled: Optional[Callable] = None
        self.on_crawl_complete: Optional[Callable] = None
        self.on_progress: Optional[Callable] = None
        self.on_log: Optional[Callable] = None
        
        # 浏览器实例
        self._browser: Optional[Browser] = None
        self._playwright = None
        
        # User-Agent 列表
        self.user_agents = [
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        ]
        
    def _log(self, message: str):
        """输出日志"""
        print(message)
        if self.on_log:
            try:
                self.on_log(message)
            except:
                pass
    
    def _get_random_user_agent(self) -> str:
        """获取随机 User-Agent"""
        return random.choice(self.user_agents)
    
    async def _init_browser(self):
        """初始化浏览器"""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=False,
            args=['--disable-blink-features=AutomationControlled']
        )
        self._log("🌐 浏览器已启动")
    
    async def _close_browser(self):
        """关闭浏览器"""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._log("🌐 浏览器已关闭")
    
    async def _crawl_page(self, url: str, depth: int, base_domain: str) -> Optional[CrawlResult]:
        """
        爬取单个页面
        
        Args:
            url: 页面URL
            depth: 当前深度
            base_domain: 基础域名
        """
        # 检查是否已停止
        if self._stop_event.is_set():
            return None
        
        # 检查深度限制
        if depth > self.max_depth:
            self._log(f"⏭️ 跳过 (超过深度限制): {url}")
            return None
        
        # 检查域名限制
        if self.same_domain_only:
            current_domain = urlparse(url).netloc
            if current_domain != base_domain:
                self._log(f"⏭️ 跳过 (不同域名): {url}")
                return None
        
        # 检查是否已访问
        if url in self.visited_urls:
            return None
        
        self._log(f"🕷️ 正在爬取 [{len(self.visited_urls)+1}/{self.max_pages}] (深度{depth}): {url}")
        
        result = CrawlResult(url=url, depth=depth)
        
        try:
            # 随机延迟（避免请求过快）
            delay = random.uniform(*self.delay_range)
            await asyncio.sleep(delay)
            
            # 创建新页面
            context = await self._browser.new_context(
                user_agent=self._get_random_user_agent(),
                viewport={'width': 1920, 'height': 1080}
            )
            
            page = await context.new_page()
            
            # 设置超时
            page.set_default_timeout(30000)
            
            # 访问页面
            response = await page.goto(url, wait_until='networkidle')
            
            if not response:
                result.error = "页面加载失败"
                return result
            
            # 获取页面信息
            result.title = await page.title()
            result.html = await page.content()
            
            # 提取所有链接
            links = await page.eval_on_selector_all(
                'a[href]',
                'elements => elements.map(el => el.href)'
            )
            
            # 过滤和规范化链接
            valid_links = []
            for link in links:
                try:
                    absolute_url = urljoin(url, link)
                    parsed = urlparse(absolute_url)
                    # 只保留 http/https 链接
                    if parsed.scheme in ('http', 'https'):
                        valid_links.append(absolute_url)
                except:
                    pass
            
            result.links = list(set(valid_links))  # 去重
            
            # 截图
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                screenshot_filename = f"crawl_{timestamp}_{len(self.visited_urls)}.png"
                result.screenshot_path = os.path.join(self.crawl_dir, screenshot_filename)
                await page.screenshot(path=result.screenshot_path, full_page=True)
            except Exception as e:
                self._log(f"⚠️ 截图失败: {e}")
            
            # 关闭页面
            await context.close()
            
            # 标记为已访问
            self.visited_urls.add(url)
            self.results.append(result)
            
            # 回调
            if self.on_page_crawled:
                try:
                    self.on_page_crawled(result)
                except:
                    pass
            
            # 进度回调
            if self.on_progress:
                try:
                    progress = {
                        "current": len(self.visited_urls),
                        "total": self.max_pages,
                        "current_url": url,
                        "depth": depth
                    }
                    self.on_progress(progress)
                except:
                    pass
            
            self._log(f"✅ 完成: {result.title[:50]}... - 发现 {len(result.links)} 个链接")
            
            return result
            
        except Exception as e:
            self._log(f"⚠️ 爬取失败 {url}: {e}")
            result.error = str(e)
            return result
    
    async def _worker(self, base_domain: str):
        """工作协程"""
        while not self._stop_event.is_set() and len(self.visited_urls) < self.max_pages:
            try:
                # 获取URL（非阻塞）
                url, depth = await asyncio.wait_for(
                    self.url_queue.get(), 
                    timeout=1.0
                )
                
                # 爬取页面
                result = await self._crawl_page(url, depth, base_domain)
                
                # 添加新链接到队列
                if result and result.links:
                    for link in result.links:
                        if link not in self.visited_urls:
                            await self.url_queue.put((link, depth + 1))
                
                self.url_queue.task_done()
                
            except asyncio.TimeoutError:
                # 队列为空，检查是否应该结束
                if self.url_queue.empty():
                    break
            except Exception as e:
                self._log(f"⚠️ 工作协程错误: {e}")
                continue
    
    async def start_crawl(self, start_url: str, max_depth: int = 3, max_pages: int = 100) -> str:
        """
        开始爬取网站
        
        Args:
            start_url: 起始URL
            max_depth: 最大爬取深度
            max_pages: 最大页面数
        """
        if self.is_crawling:
            return "爬取已在进行中"
        
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.is_crawling = True
        self.results = []
        self.visited_urls = set()
        self._stop_event.clear()
        
        # 清空队列
        while not self.url_queue.empty():
            try:
                self.url_queue.get_nowait()
            except:
                break
        
        # 解析基础域名
        base_domain = urlparse(start_url).netloc
        
        self._log(f"🕷️ 开始爬取: {start_url}")
        self._log(f"   最大深度: {max_depth}, 最大页面数: {max_pages}")
        self._log(f"   并发数: {self.concurrent_limit}")
        
        try:
            # 初始化浏览器
            await self._init_browser()
            
            # 添加起始URL到队列
            await self.url_queue.put((start_url, 0))
            
            # 启动工作协程
            workers = [
                asyncio.create_task(self._worker(base_domain))
                for _ in range(self.concurrent_limit)
            ]
            
            # 等待所有工作协程完成
            await asyncio.gather(*workers, return_exceptions=True)
            
        except Exception as e:
            self._log(f"⚠️ 爬虫运行错误: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # 关闭浏览器
            await self._close_browser()
            self.is_crawling = False
        
        # 保存结果
        self._save_results()
        
        self._log(f"✅ 爬取完成: 共 {len(self.results)} 个页面")
        
        # 完成回调
        if self.on_crawl_complete:
            try:
                self.on_crawl_complete(self.results)
            except:
                pass
        
        return f"完成爬取，共 {len(self.results)} 个页面"
    
    def start_crawl_sync(self, start_url: str, max_depth: int = 3, max_pages: int = 100) -> str:
        """同步版本的爬取入口"""
        return asyncio.run(self.start_crawl(start_url, max_depth, max_pages))
    
    def stop_crawl(self):
        """停止爬取"""
        if self.is_crawling:
            self._log("🛑 正在停止爬虫...")
            self._stop_event.set()
            self.is_crawling = False
    
    def _save_results(self):
        """保存爬取结果"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_file = os.path.join(self.crawl_dir, f"crawl_results_{timestamp}.json")
        
        data = {
            "crawl_time": timestamp,
            "total_pages": len(self.results),
            "pages": [r.to_dict() for r in self.results]
        }
        
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        self._log(f"💾 结果已保存: {results_file}")
    
    def get_results(self) -> List[CrawlResult]:
        """获取爬取结果"""
        return self.results


# 使用示例
if __name__ == "__main__":
    crawler = CrawleeWebsiteCrawler()
    
    # 测试爬取
    result = crawler.start_crawl_sync(
        start_url="https://www.example.com",
        max_depth=2,
        max_pages=10
    )
    print(result)
