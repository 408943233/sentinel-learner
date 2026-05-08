---
name: "web-crawler"
description: "智能网页爬虫工具，支持JS渲染、页面截图、交互记录。Invoke when user needs to crawl websites, capture screenshots, record interactions, or extract web page data with JavaScript support."
---

# Web Crawler Skill

智能网页爬虫工具，支持JavaScript渲染、自动截图、交互动作记录。

## 功能特性

- ✅ **JavaScript渲染** - 支持动态加载的网页内容
- ✅ **自动截图** - 页面加载完成后自动截图
- ✅ **交互记录** - 记录点击、输入等用户操作
- ✅ **内容变更检测** - 交互后自动保存新的页面状态和截图
- ✅ **分离存储** - 页面代码、截图、动作记录分别保存
- ✅ **异步并发** - 高效爬取多个页面

## 使用方法

### 1. 基础爬取

```python
from crawler import SmartWebCrawler

crawler = SmartWebCrawler(output_dir="output")

# 爬取单个页面
crawler.crawl_sync("https://example.com")
```

### 2. 带交互的爬取

```python
from crawler import SmartWebCrawler
from playwright.sync_api import Page

crawler = SmartWebCrawler(output_dir="output")

def interact(page: Page):
    """自定义交互逻辑"""
    # 点击按钮
    page.click("#submit-btn")
    page.wait_for_timeout(1000)
    
    # 输入文本
    page.fill("#search-input", "关键词")
    page.click("#search-btn")
    page.wait_for_timeout(2000)

crawler.crawl_sync(
    "https://example.com",
    interaction_callback=interact
)
```

### 3. 批量爬取

```python
urls = [
    "https://example.com/page1",
    "https://example.com/page2",
    "https://example.com/page3"
]

crawler.crawl_multiple_sync(urls, max_concurrent=3)
```

## 输出结构

```
output/
├── pages/              # 页面HTML代码
│   ├── example.com_20250101_120000.html
│   └── example.com_20250101_120001.html
├── screenshots/        # 页面截图
│   ├── example.com_20250101_120000.png
│   └── example.com_20250101_120001.png
└── actions/            # 交互动作记录
    └── example.com_actions_20250101_120000.json
```

## 动作记录格式

```json
{
  "url": "https://example.com",
  "timestamp": "2025-01-01T12:00:00",
  "actions": [
    {
      "type": "click",
      "selector": "#submit-btn",
      "timestamp": "2025-01-01T12:00:01"
    },
    {
      "type": "fill",
      "selector": "#search-input",
      "value": "关键词",
      "timestamp": "2025-01-01T12:00:02"
    }
  ]
}
```

## 配置选项

```python
crawler = SmartWebCrawler(
    output_dir="output",           # 输出目录
    headless=False,                # 是否无头模式
    viewport_width=1920,           # 视口宽度
    viewport_height=1080,          # 视口高度
    screenshot_full_page=True,     # 是否全页截图
    wait_for_network_idle=True,    # 等待网络空闲
    delay_range=(1, 3)             # 请求间隔(秒)
)
```

## 依赖安装

```bash
pip install playwright
playwright install chromium
```

## 示例代码

详见 `examples/` 目录：
- `basic_crawl.py` - 基础爬取示例
- `interaction_crawl.py` - 交互式爬取示例
- `batch_crawl.py` - 批量爬取示例
