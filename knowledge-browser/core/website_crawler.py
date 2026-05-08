#!/usr/bin/env python3
"""
网站爬虫模块 - 自动爬取网站所有下级链接
"""
import os
import json
import time
import threading
import queue
from typing import Set, List, Dict, Optional, Callable
from urllib.parse import urljoin, urlparse
from datetime import datetime


class CrawlResult:
    """爬取结果"""
    def __init__(self, url: str, depth: int):
        self.url = url
        self.depth = depth
        self.status_code = 0
        self.title = ""
        self.links: List[str] = []
        self.html = ""
        self.screenshot_path = ""
        self.crawl_time = datetime.now()
        self.error = ""
        
    def to_dict(self) -> Dict:
        return {
            "url": self.url,
            "depth": self.depth,
            "status_code": self.status_code,
            "title": self.title,
            "links_count": len(self.links),
            "links": self.links[:20],  # 只保存前20个链接
            "screenshot": self.screenshot_path,
            "crawl_time": self.crawl_time.isoformat(),
            "error": self.error
        }


class WebsiteCrawler:
    """网站爬虫"""
    
    def __init__(self, browser_engine, output_dir: str = "output"):
        self.browser_engine = browser_engine
        self.output_dir = output_dir
        
        # 爬取配置
        self.max_depth = 3  # 最大爬取深度
        self.max_pages = 100  # 最大页面数
        self.same_domain_only = True  # 只爬取同域名
        self.include_external = False  # 是否包含外部链接
        
        # 爬取状态
        self.visited_urls: Set[str] = set()
        self.url_queue: queue.Queue = queue.Queue()
        self.results: List[CrawlResult] = []
        self.is_crawling = False
        
        # 线程控制
        self._crawl_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # 回调函数
        self.on_page_crawled: Optional[Callable] = None
        self.on_crawl_complete: Optional[Callable] = None
        self.on_progress: Optional[Callable] = None
        self.on_log: Optional[Callable] = None  # 日志回调
        
        # 创建输出目录
        self.crawl_dir = os.path.join(output_dir, "crawl")
        os.makedirs(self.crawl_dir, exist_ok=True)
        
    def start_crawl(self, start_url: str, max_depth: int = 3, max_pages: int = 100) -> str:
        """开始爬取网站"""
        if self.is_crawling:
            return "爬取已在进行中"
            
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.is_crawling = True
        self._stop_event.clear()
        
        # 重置状态
        self.visited_urls.clear()
        self.results.clear()
        while not self.url_queue.empty():
            self.url_queue.get()
            
        # 添加起始URL
        self.url_queue.put((start_url, 0))
        
        # 启动爬取线程
        self._crawl_thread = threading.Thread(target=self._crawl_loop, daemon=True)
        self._crawl_thread.start()
        
        self._log(f"🕷️ 开始爬取: {start_url}")
        self._log(f"   最大深度: {max_depth}, 最大页面数: {max_pages}")
        
        return f"开始爬取 {start_url}"
        
    def _log(self, message: str):
        """输出日志"""
        print(message)
        if self.on_log:
            try:
                self.on_log(message)
            except:
                pass
        
    def _crawl_loop(self):
        """爬取主循环"""
        base_domain = ""
        
        while not self._stop_event.is_set() and len(self.visited_urls) < self.max_pages:
            try:
                # 获取下一个URL
                url, depth = self.url_queue.get(timeout=1.0)
                
                # 跳过已访问的URL
                if url in self.visited_urls:
                    continue
                    
                # 检查深度
                if depth > self.max_depth:
                    continue
                    
                # 解析基础域名
                if not base_domain:
                    base_domain = urlparse(url).netloc
                    
                # 检查是否同域名
                if self.same_domain_only:
                    current_domain = urlparse(url).netloc
                    if current_domain != base_domain:
                        continue
                        
                self._log(f"🕷️ 正在爬取 [{len(self.visited_urls)+1}/{self.max_pages}] (深度{depth}): {url}")
                
                # 爬取页面
                result = self._crawl_page(url, depth)
                
                if result:
                    self.visited_urls.add(url)
                    self.results.append(result)
                    
                    # 回调
                    if self.on_page_crawled:
                        try:
                            self.on_page_crawled(result)
                        except:
                            pass
                            
                    # 添加新链接到队列
                    for link in result.links:
                        if link not in self.visited_urls:
                            self.url_queue.put((link, depth + 1))
                            
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
                            
                # 短暂延迟，避免请求过快
                time.sleep(0.5)
                
            except queue.Empty:
                # 队列为空，检查是否完成
                if self.url_queue.empty():
                    break
            except Exception as e:
                self._log(f"⚠️ 爬取错误: {e}")
                continue
                
        # 爬取完成
        self.is_crawling = False
        self._save_results()
        
        self._log(f"✅ 爬取完成: 共 {len(self.results)} 个页面")
        
        if self.on_crawl_complete:
            try:
                self.on_crawl_complete(self.results)
            except:
                pass
                
    def _crawl_page(self, url: str, depth: int) -> Optional[CrawlResult]:
        """爬取单个页面"""
        result = CrawlResult(url, depth)
        
        try:
            # 导航到页面
            self.browser_engine.navigate(url)
            
            # 等待页面加载
            time.sleep(2)
            
            # 获取页面信息
            page_info = self.browser_engine._send_command({
                'type': 'get_page_info'
            })
            
            if page_info:
                result.title = page_info.get('title', '')
                result.status_code = page_info.get('status', 200)
                
            # 获取页面HTML
            result.html = self.browser_engine.get_full_page()
            
            # 提取链接
            result.links = self._extract_links(result.html, url)
            
            # 截图
            try:
                screenshot_path = self.browser_engine.take_screenshot(
                    name=f"crawl_{len(self.visited_urls)}"
                )
                result.screenshot_path = screenshot_path
            except:
                pass
                
        except Exception as e:
            result.error = str(e)
            self._log(f"⚠️ 爬取页面失败 {url}: {e}")
            
        return result
        
    def _extract_links(self, html: str, base_url: str) -> List[str]:
        """从HTML中提取链接"""
        links = []
        
        try:
            # 使用正则提取链接
            import re
            
            # 提取 href="..." 或 href='...'
            href_pattern = r'href=["\']([^"\']+)["\']'
            matches = re.findall(href_pattern, html)
            
            for match in matches:
                # 跳过锚点链接
                if match.startswith('#'):
                    continue
                    
                # 跳过javascript链接
                if match.startswith('javascript:'):
                    continue
                    
                # 跳过mailto链接
                if match.startswith('mailto:'):
                    continue
                    
                # 转换为绝对URL
                absolute_url = urljoin(base_url, match)
                
                # 移除锚点
                absolute_url = absolute_url.split('#')[0]
                
                # 去重
                if absolute_url not in links:
                    links.append(absolute_url)
                    
        except Exception as e:
            print(f"⚠️ 提取链接失败: {e}")
            
        return links[:50]  # 限制每个页面的链接数量
        
    def _save_results(self):
        """保存爬取结果"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 保存JSON结果
        results_file = os.path.join(self.crawl_dir, f"crawl_results_{timestamp}.json")
        
        data = {
            "crawl_time": timestamp,
            "total_pages": len(self.results),
            "max_depth": self.max_depth,
            "pages": [r.to_dict() for r in self.results]
        }
        
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
        self._log(f"💾 爬取结果已保存: {results_file}")
        
        # 生成报告
        self._generate_report(timestamp)
        
    def _generate_report(self, timestamp: str):
        """生成爬取报告"""
        report_file = os.path.join(self.crawl_dir, f"crawl_report_{timestamp}.txt")
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("=" * 60 + "\n")
            f.write("网站爬取报告\n")
            f.write("=" * 60 + "\n\n")
            
            f.write(f"爬取时间: {timestamp}\n")
            f.write(f"总页面数: {len(self.results)}\n")
            f.write(f"最大深度: {self.max_depth}\n\n")
            
            # 统计信息
            domain_counts = {}
            for result in self.results:
                domain = urlparse(result.url).netloc
                domain_counts[domain] = domain_counts.get(domain, 0) + 1
                
            f.write("域名分布:\n")
            for domain, count in sorted(domain_counts.items(), key=lambda x: x[1], reverse=True):
                f.write(f"  {domain}: {count} 页\n")
                
            f.write("\n" + "=" * 60 + "\n")
            f.write("页面列表\n")
            f.write("=" * 60 + "\n\n")
            
            for i, result in enumerate(self.results, 1):
                f.write(f"[{i}] {result.url}\n")
                f.write(f"    标题: {result.title}\n")
                f.write(f"    深度: {result.depth}\n")
                f.write(f"    链接数: {len(result.links)}\n")
                if result.error:
                    f.write(f"    错误: {result.error}\n")
                f.write("\n")
                
        self._log(f"📄 爬取报告已生成: {report_file}")
        
    def stop_crawl(self):
        """停止爬取"""
        if not self.is_crawling:
            return
            
        self._stop_event.set()
        self.is_crawling = False
        
        if self._crawl_thread and self._crawl_thread.is_alive():
            self._crawl_thread.join(timeout=5)
            
        self._log("🛑 爬取已停止")
        
    def get_crawl_status(self) -> Dict:
        """获取爬取状态"""
        return {
            "is_crawling": self.is_crawling,
            "visited_count": len(self.visited_urls),
            "queue_size": self.url_queue.qsize(),
            "results_count": len(self.results)
        }
        
    def get_site_map(self) -> Dict:
        """获取站点地图"""
        site_map = {}
        
        for result in self.results:
            url = result.url
            links = result.links
            
            site_map[url] = {
                "title": result.title,
                "links": links,
                "depth": result.depth
            }
            
        return site_map
