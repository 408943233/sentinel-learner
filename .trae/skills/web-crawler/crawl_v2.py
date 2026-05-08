#!/usr/bin/env python3
"""
爬取网页并下载所有资源到本地
"""
import os
import sys
import argparse

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crawler_v2 import SmartWebCrawler


def main():
    parser = argparse.ArgumentParser(description='爬取网页并下载所有资源到本地')
    parser.add_argument('url', help='要爬取的URL')
    parser.add_argument('-o', '--output', default='output/local_assets', help='输出目录')
    parser.add_argument('-d', '--depth', type=int, default=2, help='爬取深度')
    
    args = parser.parse_args()
    
    # 创建爬虫
    crawler = SmartWebCrawler(
        output_dir=args.output,
        headless=False,
        viewport_width=1920,
        viewport_height=1080,
        screenshot_full_page=True
    )
    
    # 爬取
    result = crawler.crawl(args.url, max_depth=args.depth)
    
    print(f"\n{'='*70}")
    print(f"爬取结果:")
    print(f"  标题: {result.title}")
    print(f"  HTML: {result.html_path}")
    print(f"  截图: {result.screenshot_path}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
