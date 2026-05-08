---
name: 页面截图转HTML
version: 1.2.0
description: 将页面截图转换为HTML代码，支持识别页面结构、元素和样式。使用Kimi Coding API (k2p5模型) 进行智能分析。
homepage: https://github.com/openclaw/skills
metadata: {"clawdbot":{"emoji":"🖼️","requires":{"bins":["python3","tesseract","google-chrome"],"env":["KIMI_CODING_API_KEY"],"pip":["Pillow","opencv-python","pytesseract","anthropic","openai","requests","scikit-image","scikit-learn","ultralytics","selenium","webdriver-manager","numpy","glob2"]},"install":[{"id":"python-apt","kind":"apt","package":"python3 python3-pip python3-venv","bins":["python3"],"label":"Install Python (apt)"},{"id":"tesseract-apt","kind":"apt","package":"tesseract-ocr tesseract-ocr-chi-sim","bins":["tesseract"],"label":"Install Tesseract OCR (apt)"},{"id":"chrome-apt","kind":"apt","package":"google-chrome-stable","bins":["google-chrome"],"label":"Install Google Chrome (apt)"}]}}
---

# 页面截图转HTML

将网页或应用程序的截图转换为HTML代码，支持识别页面结构、元素和样式。

## 功能特点

- 识别页面布局和结构
- 提取文本内容
- 分析颜色和样式
- 生成语义化HTML代码
- 支持响应式设计
- 使用Kimi K2.5多模态大模型进行智能分析
- 生成HTML后与原图进行SSIM对比，确保相似度≥0.95

## 快速开始

### 基本用法

```bash
python3 {baseDir}/scripts/screenshot_to_html.py --image /path/to/screenshot.png --output /path/to/output.html
```

### 使用Kimi K2.5多模态模型

```bash
# 使用Kimi K2.5多模态模型进行智能分析
python3 {baseDir}/scripts/screenshot_to_html.py --image /path/to/screenshot.png --output /path/to/output.html --use-kimi

# 指定Kimi API密钥
export KIMI_API_KEY="your-kimi-api-key"
python3 {baseDir}/scripts/screenshot_to_html.py --image /path/to/screenshot.png --output /path/to/output.html --use-kimi
```

### 高级选项

```bash
# 指定输出目录
python3 {baseDir}/scripts/screenshot_to_html.py --image /path/to/screenshot.png --output-dir /path/to/output

# 调整识别精度
python3 {baseDir}/scripts/screenshot_to_html.py --image /path/to/screenshot.png --output /path/to/output.html --accuracy high

# 使用示例图片测试
python3 {baseDir}/scripts/screenshot_to_html.py --image /Downloads/ai-etf-design/参考图/AI-ETF首页(已签约).JPG --output /tmp/ai-etf-home.html --use-kimi
```

## 工作原理

1. **图像预处理**：调整图像大小、增强对比度
2. **颜色提取**：使用K-means聚类算法提取主要颜色
3. **目标检测**：使用YOLOv5识别和定位UI元素
4. **文本提取**：使用Tesseract OCR提取文本内容
5. **布局分析**：基于目标检测结果分析页面布局结构
6. **智能分析**：使用Kimi K2.5多模态模型进行深度分析
7. **HTML生成**：根据分析结果生成语义化HTML代码
8. **HTML渲染**：使用Selenium渲染生成的HTML
9. **SSIM对比**：计算渲染结果与原图的SSIM相似度，确保≥0.95
10. **优化迭代**：如果SSIM不达标，自动调整HTML样式

## 依赖项

- Python 3.8+
- Tesseract OCR
- Pillow (图像处理)
- OpenCV (计算机视觉)
- pytesseract (OCR接口)
- OpenAI (用于Kimi API调用)
- scikit-image (用于SSIM计算)
- scikit-learn (用于K-means颜色聚类)
- ultralytics (YOLOv5目标检测)
- Selenium (用于HTML渲染和截图)
- webdriver-manager (用于管理WebDriver)

## 示例

### 输入输出示例

**输入**：网页截图 `AI-ETF首页(已签约).JPG`

**输出**：`ai-etf-home.html`

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI ETF 首页</title>
    <style>
        body {
            font-family: 'PingFang SC', 'Microsoft YaHei', Arial, sans-serif;
            margin: 0;
            padding: 0;
            background-color: #ffffff;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            text-align: center;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        .hero-section {
            text-align: center;
            padding: 60px 20px;
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            margin-bottom: 30px;
        }
        .hero-title {
            font-size: 48px;
            color: #333;
            margin-bottom: 20px;
        }
        .hero-subtitle {
            font-size: 24px;
            color: #666;
            margin-bottom: 30px;
        }
        .button {
            background-color: #667eea;
            color: white;
            padding: 15px 40px;
            border: none;
            border-radius: 30px;
            cursor: pointer;
            font-size: 18px;
            transition: all 0.3s ease;
        }
        .button:hover {
            background-color: #764ba2;
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.2);
        }
        .feature-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 30px;
            padding: 40px 20px;
        }
        .feature-card {
            background: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            transition: transform 0.3s ease;
        }
        .feature-card:hover {
            transform: translateY(-5px);
        }
        .feature-title {
            font-size: 24px;
            color: #333;
            margin-bottom: 15px;
        }
        .feature-description {
            color: #666;
            line-height: 1.6;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>AI ETF 智能投资平台</h1>
    </div>
    <div class="hero-section">
        <h2 class="hero-title">智能投资，未来可期</h2>
        <p class="hero-subtitle">基于人工智能的ETF投资策略，让投资更简单</p>
        <button class="button">立即开始</button>
    </div>
    <div class="container">
        <div class="feature-grid">
            <div class="feature-card">
                <h3 class="feature-title">智能分析</h3>
                <p class="feature-description">利用AI技术深度分析市场数据，提供精准的投资建议</p>
            </div>
            <div class="feature-card">
                <h3 class="feature-title">实时监控</h3>
                <p class="feature-description">24小时实时监控市场动态，及时把握投资机会</p>
            </div>
            <div class="feature-card">
                <h3 class="feature-title">风险控制</h3>
                <p class="feature-description">智能风险评估系统，有效控制投资风险</p>
            </div>
        </div>
    </div>
</body>
</html>
```

## 注意事项

- 截图质量越高，识别效果越好
- 使用Kimi K2.5多模态模型可以获得更精确的分析结果
- 生成的HTML代码可能需要手动调整以达到最佳效果
- 支持的文件格式：PNG、JPG、JPEG、WEBP
- 需要设置KIMI_API_KEY环境变量或通过参数传递

## 环境配置

### 安装依赖

```bash
# 安装Python
brew install python

# 安装Tesseract OCR
brew install tesseract

# 安装Python依赖包
pip3 install Pillow opencv-python pytesseract openai scikit-image scikit-learn ultralytics selenium webdriver-manager

# 安装Chrome浏览器（如果未安装）
brew install --cask google-chrome
```

### 配置Kimi API

```bash
# 设置Kimi API密钥
export KIMI_API_KEY="your-kimi-api-key"

# 或者将API密钥添加到 ~/.zshrc 或 ~/.bash_profile
echo 'export KIMI_API_KEY="your-kimi-api-key"' >> ~/.zshrc
source ~/.zshrc
```

## 后续计划

- 支持批量处理多个截图
- 增加CSS样式自动提取功能
- 支持JavaScript交互元素识别
- 提供在线预览功能
