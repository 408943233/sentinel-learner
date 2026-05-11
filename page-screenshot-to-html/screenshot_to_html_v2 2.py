#!/usr/bin/env python3
"""
截图转HTML工具 v2.0 - 优化版本
集成所有核心模块，提供高性能、可维护的代码
"""
import argparse
import os
import sys
from pathlib import Path
from typing import Optional

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core import (
    get_config, reload_config,
    OCRProcessor, get_ocr_processor,
    APIClientManager, get_api_manager,
    ImageAnalyzer,
    HTMLProcessor, process_html,
    PerformanceMonitor, Timer, monitor,
    image_to_base64, clean_html_response, ensure_dir,
    format_duration, ProgressBar,
    get_ssim_analyzer, get_html_renderer, get_chromedriver_path
)
from core.omniparser_processor import OmniParserProcessor, get_omniparser_processor
from core.exceptions import ScreenshotToHTMLError, APIError
from PIL import Image


class ScreenshotToHTML:
    """截图转HTML主类"""
    
    def __init__(
        self,
        image_path: str,
        output_path: Optional[str] = None,
        debug: bool = False,
        use_api: bool = True,
        enable_ssim: bool = False,
        enable_icon_extraction: bool = False
    ):
        self.image_path = image_path
        self.debug = debug
        self.use_api = use_api
        self.enable_ssim = enable_ssim
        self.enable_icon_extraction = enable_icon_extraction
        
        # 加载配置
        self.config = get_config()
        
        # 设置输出路径
        if output_path:
            self.output_path = output_path
        else:
            base_name = Path(image_path).stem
            self.output_path = os.path.join(
                self.config.output.output_dir,
                f"{base_name}.html"
            )
        
        # 确保输出目录存在
        ensure_dir(os.path.dirname(self.output_path))
        
        # 初始化组件
        self.ocr = get_ocr_processor()
        self.omniparser = get_omniparser_processor()
        self.api_manager = get_api_manager()
        self.image_analyzer = ImageAnalyzer()
        self.html_processor = HTMLProcessor()
        
        # 可选组件
        self.ssim_analyzer = None
        self.html_renderer = None
        
        if self.enable_ssim:
            try:
                self.ssim_analyzer = get_ssim_analyzer()
                self.html_renderer = get_html_renderer()
                print("  ✓ SSIM分析和HTML渲染已启用")
            except ImportError as e:
                print(f"  ⚠️ SSIM功能不可用: {e}")
                self.enable_ssim = False

        # 加载图片
        self.image = Image.open(image_path)
        print(f"📸 加载图片: {image_path} ({self.image.width}x{self.image.height})")
    
    def process(self) -> str:
        """处理图片并生成HTML"""
        print("\n" + "="*60)
        print("开始处理")
        print("="*60)

        try:
            # 1. OmniParser UI元素检测
            omni_elements = []
            omni_success = False
            with Timer("omniparser_detection"):
                print("\n🎯 步骤1: OmniParser V2检测UI元素...")
                omni_elements, omni_success = self.omniparser.detect_elements(self.image)
                if omni_success:
                    print(f"  ✅ OmniParser成功，检测到 {len(omni_elements)} 个UI元素")
                    # 仅在debug模式下保存调试输出
                    if self.debug:
                        self.omniparser.save_debug_output(self.image_path, omni_elements)
                else:
                    print("  ⚠️ OmniParser失败，将使用备用方法")
            
            # 1.5 图标提取（已禁用）
            # 注意：自动图标提取功能已禁用，因为OmniParser主要检测文本而非图标
            # 如需图标，建议在生成HTML后手动添加或使用SVG绘制
            if self.enable_icon_extraction:
                print("\n🖼️ 步骤1.5: 图标提取（已跳过）")
                print("  ℹ️ 自动图标提取已禁用，AI将在HTML中使用SVG/CSS绘制图标")

            # 2. 图像分析
            with Timer("image_analysis"):
                print("\n🔍 步骤2: 分析图像...")
                image_analysis = self.image_analyzer.analyze(self.image)
                print(f"  ✓ 提取了 {len(image_analysis['colors'])} 种主要颜色")
                print(f"  ✓ 识别了 {len(image_analysis['layout'])} 个布局区域")

            # 3. OCR文本提取
            with Timer("ocr_extraction"):
                print("\n📝 步骤3: 提取文本...")
                text_blocks = self.ocr.extract_text_with_positions(self.image)
                text_content = '\n'.join([block.text for block in text_blocks])
                print(f"  ✓ 提取了 {len(text_blocks)} 个文本块")

            # 4. 生成HTML
            if self.use_api:
                with Timer("html_generation"):
                    print("\n🎨 步骤4: 生成HTML...")
                    html = self._generate_html_with_api(
                        image_analysis, text_blocks, text_content, omni_elements, omni_success
                    )
            else:
                print("\n⚠️ 跳过API调用，使用基础HTML模板")
                html = self._generate_basic_html(text_blocks)
            
            # 5. HTML后处理
            with Timer("html_processing"):
                print("\n🔧 步骤5: 处理HTML...")
                # 传递api_manager和原始图片以便修复问题时调用LLM
                base64_image = image_to_base64(self.image_path)
                html, issues = process_html(
                    html, 
                    api_manager=self.api_manager if self.use_api else None,
                    base64_image=base64_image
                )
                
                if issues:
                    print(f"  ⚠️ 发现 {len(issues)} 个问题未修复:")
                    for issue in issues:
                        print(f"    - [{issue.severity}] {issue.message}")
                else:
                    print("  ✓ HTML检查通过")
            
            # 6. 保存结果
            with open(self.output_path, 'w', encoding='utf-8') as f:
                f.write(html)

            print(f"\n✅ HTML已保存: {self.output_path}")
            
            # 7. SSIM对比（可选）
            if self.enable_ssim and self.html_renderer:
                with Timer("ssim_comparison"):
                    print("\n📊 步骤7: SSIM图像对比...")
                    # 仅在debug模式下保存截图
                    screenshot_path = self.output_path.replace('.html', '_screenshot.png') if self.debug else None
                    ssim_score = self.html_renderer.compare_with_original(
                        self.output_path,
                        self.image_path,
                        screenshot_path,
                        window_size=(self.image.width, self.image.height)
                    )
                    if ssim_score is not None:
                        print(f"  ✓ SSIM相似度: {ssim_score:.4f}")
                        if ssim_score < 0.95:
                            print(f"  ⚠️ 相似度较低，建议检查生成的HTML")

            # 8. 打印性能报告
            if self.config.performance.enable_monitoring:
                monitor.print_report()
            
            return self.output_path
            
        except Exception as e:
            print(f"\n❌ 处理失败: {e}")
            if self.debug:
                import traceback
                traceback.print_exc()
            raise
    
    def _generate_html_with_api(
        self,
        image_analysis: dict,
        text_blocks: list,
        text_content: str,
        omni_elements: list,
        omni_success: bool
    ) -> str:
        """使用API生成HTML"""
        # 编码图片
        base64_image = image_to_base64(self.image_path)

        # 构建提示词
        prompt = self._build_prompt(image_analysis, text_blocks, text_content, omni_elements, omni_success)

        # 调用API
        response = self.api_manager.call_with_fallback(base64_image, prompt)

        if response:
            print(f"  ✓ {response.provider.value} API调用成功 ({format_duration(response.latency)})")
            return clean_html_response(response.content)
        else:
            raise APIError("所有API调用失败")

    def _build_prompt(
        self,
        image_analysis: dict,
        text_blocks: list,
        text_content: str,
        omni_elements: list,
        omni_success: bool
    ) -> str:
        """构建完整的API提示词"""
        dimensions = image_analysis['dimensions']
        colors = image_analysis['colors']
        layout = image_analysis['layout']

        # 格式化颜色信息
        color_info = '\n'.join([
            f"  - {c.hex} (RGB{c.rgb}, {c.percentage:.1f}%)"
            for c in colors[:10]
        ])

        # 格式化布局信息
        layout_info = '\n'.join([
            f"  - 区域{i+1}: y={s.y_start}-{s.y_end}, 高度={s.height}px, 背景={s.bg_color}, 类型={s.section_type}"
            for i, s in enumerate(layout[:15])
        ])

        # 格式化文本块（前50个）
        text_info = '\n'.join([
            f"  - '{b.text}' @ ({b.x}, {b.y}, {b.w}x{b.h})"
            for b in text_blocks[:50]
        ])

        # 格式化OmniParser结果
        omni_info = ""
        if omni_success and omni_elements:
            omni_info = self.omniparser.get_elements_description(omni_elements)
        else:
            omni_info = "OmniParser检测失败或未检测到UI元素"
        
        # 计算bottom-bar的top位置
        # 底部导航栏固定在页面底部，高度约50-56px
        bottom_bar_height = 56
        bottom_bar_top = self.config.image.logical_height - bottom_bar_height
        
        # 计算实际的逻辑高度（基于图片实际尺寸）
        actual_logical_height = dimensions['height'] / dimensions['dpr']
        actual_logical_width = dimensions['width'] / dimensions['dpr']
        
        # 计算bottom-bar的正确位置
        bottom_bar_height = 56
        bottom_bar_top = actual_logical_height - bottom_bar_height
        
        prompt = f"""你是一个专业的前端开发工程师，请将这张截图转换为高保真HTML代码。

## 重要提示
**你是多模态AI模型，可以直接看到并理解图片内容。**
- OCR检测结果可能不完整，请根据图片实际视觉内容补全遗漏的元素
- 特别注意图表区域下方的功能按钮（主力密码、神奇电波、主力跟踪、资金博弈）
- 所有像素值必须使用逻辑像素（物理像素 ÷ DPR）

## 图片信息
- 物理尺寸: {dimensions['width']}x{dimensions['height']} 像素
- 设备像素比(DPR): {dimensions['dpr']:.2f}
- **逻辑尺寸（CSS中使用）: {actual_logical_width:.0f}x{actual_logical_height:.0f}px**

## 主要颜色（按使用频率排序）
{color_info}

## 布局区域分析（从上到下，物理像素）
{layout_info}

## OmniParser V2 UI元素检测结果（仅供参考）
{omni_info}

## OCR检测到的文本（可能不完整，仅供参考）
{text_info}

## OCR完整文本（可能不完整）
{text_content}

## 页面类型识别（重要）

根据图片内容判断页面类型：

1. **完整页面**: 正常的应用页面，从上到下完整布局
2. **弹框/浮层**: 
   - 背景通常是半透明深色遮罩（rgba(0,0,0,0.5) 或类似）
   - 中间有一个白色或浅色的内容区域
   - 内容区域通常是圆角
   - 底部可能有"确定"/"取消"按钮
   - 页面其他部分不可交互

**如果是弹框页面**：
- body背景使用半透明黑色遮罩: `background: rgba(0,0,0,0.5)`
- 弹框容器居中显示: 
  ```css
  .modal-overlay {{
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(0,0,0,0.5);
      display: flex;
      align-items: flex-end; /* 底部弹出 */
      justify-content: center;
      z-index: 100;
  }}
  .modal-content {{
      background: #fff;
      width: 390px; /* 或根据实际尺寸 */
      border-radius: 16px 16px 0 0; /* 底部弹框圆角 */
      padding: 20px 16px;
      /* 严禁使用 max-height 或 overflow: scroll，这会导致滑动效果 */
      overflow: visible;
  }}
  ```
- **严禁**在弹框中使用 `max-height`、`overflow: scroll`、`overflow: auto` 等会导致滑动的属性
- 弹框内容必须**完全平铺展示**，不能有任何滚动效果
- 弹框内容只包含弹框内的文字和按钮
- 不要生成为完整页面布局

## 布局结构要求（必须严格遵守）

根据布局区域分析，页面应该分为以下几个section，每个section使用对应的CSS类：

1. **status-bar** (y=0-47, 高度47px, 背景色: 从布局区域提取)
   - 显示时间、信号、电量等
   - 使用白色或深色文字（根据背景色对比度决定）

2. **nav-bar** (y=47-91, 高度44px, 背景色: 从布局区域提取)
   - 页面标题居中
   - 返回按钮在左侧
   - 右侧可能有功能按钮

3. **stock-header** (股票信息头部区域)
   - 股票名称、代码
   - 当前价格、涨跌幅
   - 使用大字体显示价格

4. **stock-info** (股票详细信息区域)
   - 今开、最高、最低、换手、成交量、成交额
   - 使用网格布局或flex布局

5. **chart-section** (图表区域，必须包含所有图表子区域)
   - 主图区域: K线图/分时图 (约291px开始)
   - 附图1: MACD指标区域 (在主图下方)
   - 附图2: 成交量区域 (在MACD下方)
   - 注意: chart-section的高度必须足够包含所有子区域，不要截断
   - 指标选择按钮（分时、日K、周K、月K等）

6. **feature-buttons** (功能按钮区域，在chart-section下方)
   - 位置: 在成交量图表下方，大约在逻辑y=600-650px位置
   - **必须包含4个功能按钮: 主力密码、神奇电波、主力跟踪、资金博弈**
   - 样式: 横向排列，每个按钮有图标和文字
   - 背景色: 白色或浅灰色
   - **注意: OCR可能未检测到这些按钮，请根据图片视觉内容生成**

7. **bottom-bar** (底部导航栏，必须同时定义top和bottom)
   - top: {bottom_bar_top:.0f}px (必须明确定义，位于页面最底部)
   - bottom: 0
   - left: 0
   - right: 0
   - 高度: {bottom_bar_height}px
   - 背景色: 白色
   - 包含: 下单、条件下单、盯盘助手、删自选等按钮

## 图标绘制说明

由于自动图标提取功能已禁用，请使用以下方式在HTML中绘制图标：

1. **使用SVG绘制简单图标**（推荐）：
   - 返回按钮: `<svg viewBox="0 0 24 24"><path d="M15.41 7.41L14 6l-6 6 6 6 1.41-1.41L10.83 12z"/></svg>`
   - 搜索图标: `<svg viewBox="0 0 24 24"><path d="M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>`
   - 更多图标: `<svg viewBox="0 0 24 24"><path d="M6 10c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm12 0c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm-6 0c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z"/></svg>`
   - 箭头图标: `<svg viewBox="0 0 24 24"><path d="M8.59 16.59L13.17 12 8.59 7.41 10 6l6 6-6 6-1.41-1.41z"/></svg>`

2. **使用CSS绘制简单形状**：
   - 圆形: `border-radius: 50%`
   - 箭头: 使用border技巧
   - 线条: 使用div的border

3. **图标样式**：
   - 图标尺寸: 24x24px 或根据上下文调整
   - 图标颜色: 使用提取的主色调或白色/深色
   - 图标容器: 使用flex布局居中

## 样式规范（必须严格遵守）

1. **根容器**（必须严格遵守）:
   ```css
   .page-container {{
       width: {self.config.image.logical_width}px;
       min-height: auto;  /* 高度由内容自适应，不要设置固定高度 */
       overflow: visible;
       margin: 0 auto;
   }}
   ```
   - **严禁**设置固定高度（如 `height: 844px` 或 `min-height: 200px`）
   - 容器高度必须**由内容自适应**
   - 如果内容超出视口，容器应该自动扩展

2. **Section样式**（必须严格遵守）:
   - 每个section使用 `position: absolute`
   - 必须定义 top，但**高度应该根据内容自适应**（使用 `height: auto` 或 `min-height`）
   - left: 0, right: 0
   - **严禁设置固定高度**（如 height: 600px），这会导致页面过长
   - **正确做法**: 使用 `height: auto` 让内容决定高度，或使用 `min-height` 设置最小高度
   - 背景色必须使用提取的颜色
   - 示例:
     ```css
     .section-name {{
         position: absolute;
         top: 100px;        /* 必须定义 */
         left: 0;
         right: 0;
         height: auto;      /* 让内容自适应 */
         min-height: 200px; /* 可选：设置最小高度 */
         background: #ff0000;  /* 使用提取的颜色 */
     }}
     ```
   - **重要**: 
     - 布局区域分析中的高度仅供参考，不要直接使用
     - 每个section的实际高度应该紧凑地包裹其内容
     - 相邻section的top值应该根据前一个section的实际高度计算

3. **文本样式**:
   - 使用 `position: absolute`
   - 位置必须参考OCR检测到的坐标
   - 字体大小根据文本框高度计算: font-size = height * 0.6
   - 颜色根据内容类型决定：
     * 价格上涨: #ff4757 (红色)
     * 价格下跌: #22c55e (绿色)
     * 普通文本: #333333 或 #666666

4. **禁止事项（必须严格遵守）**:
   - 禁止 animation、transition
   - 禁止 hover效果
   - 禁止 JavaScript
   - **严禁使用emoji字符**（必须使用SVG替代，如用`<svg>`代替⭐❤️📈等）
   - **严禁使用 `position: sticky` 或 `position: fixed`**（会导致滑动效果）
   - **严禁使用 `overflow: scroll/auto/hidden`**（所有内容必须平铺，不能滚动）
   - **严禁使用 `position: absolute` 进行区块布局**（会导致区块叠加）
   - **页面必须使用正常文档流布局**（使用margin/padding控制间距，而不是top定位）
   - **页面必须完全平铺，不能有任何滑动/滚动效果**
   - 禁止自创颜色，必须使用提取的颜色
   - **严禁添加图片中不存在的元素**（如bottom-bar、导航栏等）
   - **严禁编造内容**，所有文本必须来自OCR检测结果或图片实际内容
   - **严禁假设UI组件**，只生成图片中实际可见的元素
   - **严禁截断内容**，必须生成完整的HTML（包含</body></html>）

5. **响应式**:
   - body使用: display: flex; justify-content: center;
   - 页面在容器中居中显示

## 输出要求

1. 返回完整HTML代码（包含<!DOCTYPE html>）
2. 包含完整的CSS样式（在<style>标签中）
3. 不要添加任何解释文字
4. 确保代码格式正确，可以正常运行
5. **最重要的是：严格按照布局区域分析中的section划分和背景色来构建HTML结构**
"""
        return prompt
    
    def _generate_basic_html(self, text_blocks: list) -> str:
        """生成基础HTML（不使用API）"""
        html_parts = [
            '<!DOCTYPE html>',
            '<html lang="zh-CN">',
            '<head>',
            '    <meta charset="UTF-8">',
            '    <meta name="viewport" content="width=device-width, initial-scale=1.0">',
            '    <title>Generated HTML</title>',
            '    <style>',
            '        body { margin: 0 auto; display: flex; justify-content: center; background: #f0f0f0; }',
            f'        .page-container {{ position: relative; width: {self.config.image.logical_width}px; height: {self.config.image.logical_height}px; background: white; }}',
            '        .text-element { position: absolute; white-space: nowrap; }',
            '    </style>',
            '</head>',
            '<body>',
            '    <div class="page-container">'
        ]
        
        for block in text_blocks:
            html_parts.append(
                f'        <div class="text-element" style="left: {block.x}px; top: {block.y}px; '
                f'font-size: {max(10, block.h // 2)}px;">{block.text}</div>'
            )
        
        html_parts.extend([
            '    </div>',
            '</body>',
            '</html>'
        ])
        
        return '\n'.join(html_parts)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='截图转HTML工具 v2.0')
    parser.add_argument('image', help='输入图片路径')
    parser.add_argument('-o', '--output', help='输出HTML路径')
    parser.add_argument('-d', '--debug', action='store_true', help='调试模式')
    parser.add_argument('--no-api', action='store_true', help='不使用API，仅生成基础HTML')
    parser.add_argument('--config', help='配置文件路径')
    parser.add_argument('--ssim', action='store_true', help='启用SSIM图像对比')
    parser.add_argument('--icons', action='store_true', help='启用图标提取（已禁用，保留参数用于兼容）')
    
    args = parser.parse_args()
    
    # 如果指定了配置文件，重新加载配置
    if args.config:
        os.environ['CONFIG_FILE'] = args.config
        reload_config()
    
    try:
        converter = ScreenshotToHTML(
            image_path=args.image,
            output_path=args.output,
            debug=args.debug,
            use_api=not args.no_api,
            enable_ssim=args.ssim,
            enable_icon_extraction=args.icons
        )
        
        output_path = converter.process()
        print(f"\n🎉 完成! 输出文件: {output_path}")
        
    except ScreenshotToHTMLError as e:
        print(f"\n❌ 错误: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 未预期的错误: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
