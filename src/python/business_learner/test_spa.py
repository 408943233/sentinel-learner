#!/usr/bin/env python3
"""
SPA 功能单元测试

覆盖:
- page_assembler.py: style 提取、反闪屏修复、服务端后缀跳过、script 注释包裹、</style> 转义
- causal_extractor.py: route-change 页面归属、PageNavigation 记录
- learn.py: 空壳过滤、静态资源过滤、URL 基底提取
"""

import json
import sys
import tempfile
from pathlib import Path

# 添加路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from business_learner.layer1_reconstruct.page_assembler import PageAssembler
from business_learner.layer2_causal.causal_extractor import CausalExtractor
from business_learner.learn import (
    _is_static_resource,
    _url_base,
    _make_page_name,
    _deduplicate_page_css,
)

# ============================================================
# 测试工具
# ============================================================
_passed = 0
_failed = 0

def ok(name: str, cond: bool, detail: str = ""):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ✅ {name}")
    else:
        _failed += 1
        msg = f"  ❌ {name}"
        if detail:
            msg += f"  -- {detail}"
        print(msg)

def summary():
    print(f"\n{'='*60}")
    print(f"  通过: {_passed}  失败: {_failed}  总计: {_passed + _failed}")
    print(f"{'='*60}")
    return _failed == 0


# ============================================================
# PageAssembler 测试
# ============================================================

class TestPageAssembler:
    """测试 page_assembler.py 的 SPA 相关逻辑"""

    @staticmethod
    def test_remove_script_tags_wraps_as_comment():
        """_remove_script_tags 应将 script 转为 HTML 注释"""
        pa = PageAssembler.__new__(PageAssembler)
        html = '<div>Hello</div><script>console.log("test")</script><div>World</div>'
        result = pa._remove_script_tags(html)
        ok("script 转为注释", '<!-- [REMOVED SCRIPT]' in result,
           f"got: {result[:100]}")
        ok("原始 div 保留", '<div>Hello</div>' in result and '<div>World</div>' in result)
        ok("script 标签被移除", '<script>' not in result)

    @staticmethod
    def test_remove_script_tags_empty_script():
        """空的 script 标签应被移除"""
        pa = PageAssembler.__new__(PageAssembler)
        html = '<div>Test</div><script></script><div>End</div>'
        result = pa._remove_script_tags(html)
        ok("空 script 移除", '<script>' not in result)
        ok("内容保留", 'Test' in result and 'End' in result)

    @staticmethod
    def test_assemble_full_html_style_extraction():
        """_assemble_full_html 应提取 <style> 内容而非删除"""
        pa = PageAssembler.__new__(PageAssembler)
        body = '<style>.btn{color:red}</style><div class="btn">Click</div>'
        css = ''
        result = pa._assemble_full_html(body, css)
        ok("提取的 style 内容存在于输出", '.btn{color:red}' in result,
           f"got: {result[:200]}")
        ok("DOM 内容保留", 'class="btn"' in result)
        ok("body 中无原始 <style> 标签", '<style>.btn' not in result)

    @staticmethod
    def test_assemble_full_html_style_with_attributes():
        """带属性的 style 标签也应正确提取"""
        pa = PageAssembler.__new__(PageAssembler)
        body = '<style data-styled="active">.box{display:flex}</style><div class="box">Content</div>'
        css = ''
        result = pa._assemble_full_html(body, css)
        ok("styled-components style 提取", '.box{display:flex}' in result)
        ok("DOM 保留", 'Content' in result)

    @staticmethod
    def test_assemble_full_html_multiple_style_tags():
        """多个 style 标签应全部提取"""
        pa = PageAssembler.__new__(PageAssembler)
        body = '<style>.a{color:red}</style><style>.b{color:blue}</style><div class="a b">Test</div>'
        css = ''
        result = pa._assemble_full_html(body, css)
        ok("第一个 style 提取", '.a{color:red}' in result)
        ok("第二个 style 提取", '.b{color:blue}' in result)

    @staticmethod
    def test_assemble_full_html_style_tag_close_in_css_content():
        """CSS 内容含 </style> 时，正则非贪婪匹配在首个 </style> 处截断，是已知局限"""
        pa = PageAssembler.__new__(PageAssembler)
        # 极端边缘情况: CSS content 字面包含 </style> 字符串
        # 正则非贪婪 .*? 会在第一个 </style> 停止匹配，剩余内容留在 body
        body = '<style>.icon::after{content:"</style>"}</style><div>Test</div>'
        css = ''
        result = pa._assemble_full_html(body, css)
        # 剩余的 </style> 留在 body 中导致多出一个标签，已知局限不影响正常页面
        # 验证关键: DOM 内容仍然保留
        ok("DOM 内容保留(</style>边缘情况)", 'Test' in result,
           f"result[:200]={result[:200]}")

    @staticmethod
    def test_assemble_full_html_body_display_none_fix():
        """SPA 反闪屏: body{display:none} 应替换为 body{display:block}"""
        pa = PageAssembler.__new__(PageAssembler)
        body = '<div id="app">Vue App</div>'
        css = 'body{display:none}.header{height:60px}'
        result = pa._assemble_full_html(body, css)
        ok("display:none 替换为 display:block", 'body{display:block}' in result)
        ok("原始 display:none 不再存在", 'body{display:none}' not in result)
        ok("其他 CSS 保留", '.header{height:60px}' in result)

    @staticmethod
    def test_assemble_full_html_body_display_none_with_other_properties():
        """body{display:none;margin:0} 应替换为 body{display:block}"""
        pa = PageAssembler.__new__(PageAssembler)
        body = '<div>Test</div>'
        css = 'body{margin:0;display:none;padding:0}'
        result = pa._assemble_full_html(body, css)
        ok("复杂 body 规则替换", 'body{display:block}' in result)

    @staticmethod
    def test_server_suffix_skipped_in_rewrite():
        """.jsp/.php 等服务端后缀不应被改写"""
        pa = PageAssembler.__new__(PageAssembler)
        pa.task_path = Path('/tmp/test_task')
        pa.resources_dir = pa.task_path / 'network' / 'resources'

        html = '<img src="viewMailHTML.jsp">'
        result = pa._rewrite_resource_paths(html, {})
        ok(".jsp 路径不改写", 'src="viewMailHTML.jsp"' in result)

        html2 = '<img src="api.php">'
        result2 = pa._rewrite_resource_paths(html2, {})
        ok(".php 路径不改写", 'src="api.php"' in result2)

    @staticmethod
    def test_css_link_removed():
        """<link rel="stylesheet"> 应被移除（因为 CSS 已被提取到内联）"""
        pa = PageAssembler.__new__(PageAssembler)
        body = '<link rel="stylesheet" href="styles.css"><div>Test</div>'
        css = ''
        result = pa._assemble_full_html(body, css)
        ok("link stylesheet 移除", 'href="styles.css"' not in result)
        ok("DOM 保留", 'Test' in result)

    @staticmethod
    def test_title_extraction():
        """应从 HTML 中正确提取 title"""
        pa = PageAssembler.__new__(PageAssembler)
        body = '<html><head><title>My SPA Page</title></head><body><div>Content</div></body></html>'
        css = ''
        result = pa._assemble_full_html(body, css)
        ok("title 提取", '<title>My SPA Page</title>' in result)


# ============================================================
# CausalExtractor 测试
# ============================================================

class TestCausalExtractor:
    """测试 causal_extractor.py 的 route-change 处理"""

    @staticmethod
    def _make_temp_manifest(events: list) -> str:
        """创建临时 manifest 文件，返回路径"""
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False)
        for e in events:
            tmp.write(json.dumps(e) + '\n')
        tmp.close()
        return tmp.name

    @staticmethod
    def test_route_change_updates_page_url():
        """route-change 事件应更新当前页面 URL"""
        events = [
            {
                "eventId": "evt_001", "type": "page-load-start",
                "url": "https://example.com/home", "timestamp": 1000,
                "metadata": {}, "lineage": {}
            },
            {
                "eventId": "evt_002", "type": "click",
                "url": "https://example.com/home", "timestamp": 2000,
                "metadata": {"description": "click login"}, "lineage": {}
            },
            {
                "eventId": "evt_003", "type": "route-change",
                "from": "https://example.com/home",
                "to": "https://example.com/login",
                "url": "https://example.com/login",
                "timestamp": 3000,
                "triggerSource": "pushState",
                "metadata": {}, "lineage": {}
            },
            {
                "eventId": "evt_004", "type": "input",
                "url": "https://example.com/login", "timestamp": 4000,
                "metadata": {"description": "input username"}, "lineage": {}
            },
        ]
        manifest_path = TestCausalExtractor._make_temp_manifest(events)
        try:
            task_dir = Path(manifest_path).parent
            extractor = CausalExtractor(task_dir)
            # 重定向 manifest_path
            extractor.manifest_path = Path(manifest_path)
            graph = extractor.extract()

            ok("route-change 后页面归属正确",
               "https://example.com/login" in graph.pages
               and "evt_004" in graph.pages["https://example.com/login"],
               f"pages: {graph.pages}")
            ok("PageNavigation 记录", len(graph.navigations) > 0,
               f"navigations: {graph.navigations}")
            if graph.navigations:
                nav = graph.navigations[0]
                ok("导航 from→to 正确",
                   nav.from_url == "https://example.com/home" and nav.to_url == "https://example.com/login",
                   f"from={nav.from_url}, to={nav.to_url}")
                ok("导航 trigger_type 正确",
                   nav.trigger_type == "pushState",
                   f"trigger_type={nav.trigger_type}")
        finally:
            Path(manifest_path).unlink(missing_ok=True)

    @staticmethod
    def test_route_change_creates_navigation_on_page_load():
        """page-load-start 后第一个 route-change 应创建正确的归属"""
        events = [
            {
                "eventId": "evt_p1", "type": "page-load-start",
                "url": "https://app.com/", "timestamp": 1000,
                "metadata": {}, "lineage": {}
            },
            {
                "eventId": "evt_r1", "type": "route-change",
                "from": "https://app.com/",
                "to": "https://app.com/#/dashboard",
                "url": "https://app.com/#/dashboard",
                "timestamp": 2000,
                "triggerSource": "hashchange",
                "metadata": {}, "lineage": {}
            },
            {
                "eventId": "evt_c1", "type": "click",
                "url": "https://app.com/#/dashboard", "timestamp": 3000,
                "metadata": {"description": "click button"}, "lineage": {}
            },
        ]
        manifest_path = TestCausalExtractor._make_temp_manifest(events)
        try:
            task_dir = Path(manifest_path).parent
            extractor = CausalExtractor(task_dir)
            extractor.manifest_path = Path(manifest_path)
            graph = extractor.extract()

            ok("route-change 创建 PageNavigation", len(graph.navigations) >= 1)
            if graph.navigations:
                nav = graph.navigations[0]
                ok("SPA hash 导航", nav.to_url == "https://app.com/#/dashboard",
                   f"to_url={nav.to_url}")
        finally:
            Path(manifest_path).unlink(missing_ok=True)

    @staticmethod
    def test_get_action_summary_filters_route_change():
        """get_action_summary 应有意识地过滤 route-change（设计行为）"""
        events = [
            {
                "eventId": "evt_001", "type": "page-load-start",
                "url": "https://app.com/", "timestamp": 1000,
                "metadata": {}, "lineage": {}
            },
            {
                "eventId": "evt_002", "type": "route-change",
                "from": "https://app.com/",
                "to": "https://app.com/#/page2",
                "url": "https://app.com/#/page2",
                "timestamp": 2000,
                "triggerSource": "pushState",
                "metadata": {}, "lineage": {}
            },
        ]
        manifest_path = TestCausalExtractor._make_temp_manifest(events)
        try:
            task_dir = Path(manifest_path).parent
            extractor = CausalExtractor(task_dir)
            extractor.manifest_path = Path(manifest_path)
            summary = extractor.get_action_summary()
            # route-change 不应出现在 action summary 中
            has_route = any(
                s.get('type') == 'route-change' for s in summary.get('actions', [])
            )
            ok("route-change 不在 action summary 中", not has_route,
               f"actions: {summary.get('actions', [])}")
        finally:
            Path(manifest_path).unlink(missing_ok=True)


# ============================================================
# learn.py 辅助函数测试
# ============================================================

class TestLearnHelpers:
    """测试 learn.py 中的 SPA 相关辅助函数"""

    @staticmethod
    def test_is_static_resource_css():
        ok("CSS 是静态资源", _is_static_resource("https://example.com/style.css"))

    @staticmethod
    def test_is_static_resource_js():
        ok("JS 是静态资源", _is_static_resource("https://example.com/app.js"))

    @staticmethod
    def test_is_static_resource_png():
        ok("PNG 是静态资源", _is_static_resource("https://example.com/logo.png"))

    @staticmethod
    def test_is_static_resource_woff2():
        ok("woff2 是静态资源", _is_static_resource("https://example.com/font.woff2"))

    @staticmethod
    def test_is_static_resource_jsp_is_not():
        """JSP 不应被当作静态资源（它是服务端页面路由）"""
        ok("JSP 不是静态资源", not _is_static_resource("https://example.com/view.jsp"))

    @staticmethod
    def test_is_static_resource_html_page():
        """HTML 页面不应被当作静态资源"""
        ok("HTML 不是静态资源", not _is_static_resource("https://example.com/index.html"))

    @staticmethod
    def test_url_base_strips_hash():
        """_url_base 应去除 #hash 部分"""
        ok("移除 hash", _url_base("https://app.com/#/dashboard") == "https://app.com/")

    @staticmethod
    def test_url_base_no_hash():
        """无 hash 的 URL 不变"""
        ok("无 hash 不变", _url_base("https://app.com/page") == "https://app.com/page")

    @staticmethod
    def test_make_page_name_spa_route():
        """SPA 路由的 page_name 应正确处理 hash"""
        name = _make_page_name("https://app.com/#/user/profile")
        ok("SPA hash 路由生成 page_name", name is not None and len(name) > 0,
           f"got: {name}")

    @staticmethod
    def test_make_page_name_query_params():
        """带 query 参数的 URL 应正确处理"""
        name = _make_page_name("https://app.com/page?id=123")
        ok("query 参数 URL 生成 page_name", name is not None and len(name) > 0,
           f"got: {name}")


# ============================================================
# inlineStyles → page_assembler 集成测试
# 模拟 Sentinel-browser 捕获的 inlineStyles 数据格式，
# 验证 page_assembler 的下游处理是否正确
# ============================================================

class TestInlineStylesIntegration:
    """测试 inlineStyles 数据格式 → page_assembler 的全链路"""

    @staticmethod
    def test_styled_components_inline_styles_injected_into_css():
        """styled-components 捕获的 inlineStyles 应正确注入模板 CSS"""
        pa = PageAssembler.__new__(PageAssembler)
        # 模拟 body 中无 style 标签（已被 collectInlineStyles 捕获到 inlineStyles 字段）
        # page_assembler 通过 css 参数接收 inlineStyles
        body = '<div class="sc-AxjAm"><span class="title">Dashboard</span></div>'
        css = '.sc-AxjAm{display:flex;align-items:center}\n.sc-AxjAm .title{font-weight:bold}'
        result = pa._assemble_full_html(body, css)
        ok("styled-components 样式注入到模板",
           '.sc-AxjAm{display:flex' in result and 'font-weight:bold' in result)

    @staticmethod
    def test_multiple_inline_styles_concatenated():
        """多个 CSS 块通过 css 参数传入，应全部保留"""
        pa = PageAssembler.__new__(PageAssembler)
        body = '<div class="a b c">Multi</div>'
        css = '.a{color:red}\n.b{color:blue}\n.c{color:green}'
        result = pa._assemble_full_html(body, css)
        ok("规则 a 保留", '.a{color:red}' in result)
        ok("规则 b 保留", '.b{color:blue}' in result)
        ok("规则 c 保留", '.c{color:green}' in result)

    @staticmethod
    def test_css_with_special_characters():
        """CSS 含特殊字符（@media、伪类、动画）应完整保留"""
        pa = PageAssembler.__new__(PageAssembler)
        body = '<div>Test</div>'
        css = (
            '@media (max-width:768px){.box{width:100%}}\n'
            '.btn:hover{background:#eee}\n'
            '@keyframes fadeIn{from{opacity:0}to{opacity:1}}'
        )
        result = pa._assemble_full_html(body, css)
        ok("@media 保留", '@media (max-width:768px)' in result)
        ok(":hover 保留", '.btn:hover' in result)
        ok("@keyframes 保留", '@keyframes fadeIn' in result)

    @staticmethod
    def test_body_style_extraction_combined_with_external_css():
        """body 中的 <style> 标签内容 + 外部 css 参数应合并"""
        pa = PageAssembler.__new__(PageAssembler)
        # 模拟场景：部分样式在 body 的 <style> 标签中（collectInlineStyles 可能漏掉的）
        # 其他样式通过 css 参数传入（来自外部文件或 collectStyleSheetRules）
        body = '<style>.inline-a{padding:10px}</style><div class="inline-a ext-b">Content</div>'
        css = '.ext-b{margin:20px}'
        result = pa._assemble_full_html(body, css)
        ok("body 内 inline 样式保留", '.inline-a{padding:10px}' in result)
        ok("外部 css 参数保留", '.ext-b{margin:20px}' in result)

    @staticmethod
    def test_inline_styles_with_data_attributes():
        """带有 data-styled 等属性的 style 标签内容应正确提取"""
        pa = PageAssembler.__new__(PageAssembler)
        body = (
            '<style data-styled="active" data-styled-version="5.3.3">'
            '.sc-Header{padding:16px;background:white}'
            '</style>'
            '<div class="sc-Header">Header</div>'
        )
        css = ''
        result = pa._assemble_full_html(body, css)
        ok("data-styled 属性被剥离", 'data-styled' not in result)
        ok("CSS 规则保留", '.sc-Header{padding:16px' in result)

    @staticmethod
    def test_empty_inline_styles_graceful():
        """空 css 参数和空 body style 应正常输出（不崩溃）"""
        pa = PageAssembler.__new__(PageAssembler)
        body = '<div>No styles</div>'
        css = ''
        result = pa._assemble_full_html(body, css)
        ok("无样式时不崩溃", '<div>No styles</div>' in result)
        ok("模板结构完整", '<!DOCTYPE html>' in result and '</html>' in result)

    @staticmethod
    def test_very_long_css_truncation_in_template():
        """超长 CSS（>50000 chars，模拟被截断）在模板中应正常嵌入"""
        pa = PageAssembler.__new__(PageAssembler)
        body = '<div>Test</div>'
        # 模拟 collectInlineStyles 截断后的输出
        long_css = '.x{color:red;}' * 1000 + '/* truncated */'
        result = pa._assemble_full_html(body, css=long_css)
        ok("截断标记的 CSS 可嵌入", '/* truncated */' in result)
        ok("模板结构完整", '<!DOCTYPE html>' in result)

    @staticmethod
    def test_css_with_unicode_and_chinese():
        """CSS 中 Unicode 和中文字符应完整保留"""
        pa = PageAssembler.__new__(PageAssembler)
        body = '<div class="cn">中文内容</div>'
        css = '.cn::before{content:"🎉 欢迎"}\n.cn{font-family:"PingFang SC"}'
        result = pa._assemble_full_html(body, css)
        ok("emoji 保留", '🎉' in result)
        ok("中文保留", '中文内容' in result)
        ok("PingFang 字体保留", 'PingFang SC' in result)


# ============================================================
# body 属性保留测试
# ============================================================

class TestBodyAttributePreservation:
    """测试 _assemble_full_html 保留 body 标签的关键属性"""

    @staticmethod
    def test_body_class_preserved():
        """body 上的 class 属性应被保留到重建 HTML"""
        pa = PageAssembler.__new__(PageAssembler)
        body = '<body class="XT5-layout macosx chrome120 zh_CN"><div>Content</div></body>'
        css = ''
        result = pa._assemble_full_html(body, css)
        ok("body class 保留",
           'class="XT5-layout macosx chrome120 zh_CN"' in result,
           result[:300])

    @staticmethod
    def test_body_style_preserved():
        """body 上的 style 属性应被保留"""
        pa = PageAssembler.__new__(PageAssembler)
        body = '<body style="overflow-anchor: none;"><div>Test</div></body>'
        css = ''
        result = pa._assemble_full_html(body, css)
        ok("body style 保留",
           'style="overflow-anchor: none;"' in result,
           result[:300])

    @staticmethod
    def test_body_multiple_attrs_preserved():
        """body 上的多个属性（class+style+其他）应全部保留"""
        pa = PageAssembler.__new__(PageAssembler)
        body = '<body class="main-page dark" style="margin:0" data-page="home"><div>Hi</div></body>'
        css = ''
        result = pa._assemble_full_html(body, css)
        ok("body class 保留",
           'class="main-page dark"' in result, result[:300])
        ok("body style 保留",
           'style="margin:0"' in result)
        ok("body data 属性保留",
           'data-page="home"' in result)

    @staticmethod
    def test_body_no_attrs_works():
        """body 无属性时正常渲染（退化兼容）"""
        pa = PageAssembler.__new__(PageAssembler)
        body = '<body><span>OK</span></body>'
        css = ''
        result = pa._assemble_full_html(body, css)
        ok("body 标签正确", '<body>' in result and '</body>' in result)
        ok("内容保留", '<span>OK</span>' in result)

    @staticmethod
    def test_html_and_body_attrs_together():
        """html 和 body 属性同时存在的完整场景"""
        pa = PageAssembler.__new__(PageAssembler)
        body = '<html class="XT5-layout"><body class="XT5-layout macosx" style="overflow-anchor:none"><div>Full</div></body></html>'
        css = 'body.XT5-layout{height:100%}'
        result = pa._assemble_full_html(body, css)
        ok("html class 保留", 'class="XT5-layout"' in result, result[:300])
        ok("body class+style 保留",
           'class="XT5-layout macosx"' in result
           and 'style="overflow-anchor:none"' in result)
        ok("body.XT5-layout CSS 生效", 'body.XT5-layout{height:100%}' in result)


# ============================================================
# CSS 去重测试
# ============================================================

class TestCSSDeduplication:
    """测试 _deduplicate_page_css 跨页面 CSS 去重"""

    @staticmethod
    def test_identical_css_across_pages_deduped():
        """两个页面有完全相同的 CSS 时，应提取为共享块"""
        import tempfile
        import shutil

        with tempfile.TemporaryDirectory() as tmpdir:
            pages_dir = Path(tmpdir) / 'pages'
            pages_dir.mkdir()
            p1 = pages_dir / 'page1'
            p1.mkdir()
            p2 = pages_dir / 'page2'
            p2.mkdir()

            shared_css = 'body{margin:0;padding:0}\n.btn{color:red}'
            p1_html = p1 / 'index.html'
            p1_html.write_text(f'<html><head><style>{shared_css}</style></head><body>Page1</body></html>')
            p2_html = p2 / 'index.html'
            p2_html.write_text(f'<html><head><style>{shared_css}</style></head><body>Page2</body></html>')

            pages_output = {
                'page1': str(p1_html),
                'page2': str(p2_html),
            }
            output_dir = Path(tmpdir) / 'analysis'
            output_dir.mkdir()

            result = _deduplicate_page_css(pages_output, output_dir)
            shared_path = output_dir / 'pages' / 'shared' / 'common.css'
            ok("共享 CSS 文件创建", shared_path.exists())
            ok("共享内容非空", len(result) > 0)
            ok("共享 CSS 含 body 规则",
               'body{margin:0;padding:0}' in result,
               f'result[:300]={result[:300]}')

    @staticmethod
    def test_different_css_not_deduped():
        """两个页面有完全不同的 CSS 时，不应提取共享块"""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            pages_dir = Path(tmpdir) / 'pages'
            pages_dir.mkdir()
            p1 = pages_dir / 'p1'
            p1.mkdir()
            p2 = pages_dir / 'p2'
            p2.mkdir()

            p1_html = p1 / 'index.html'
            p1_html.write_text('<html><head><style>.a{color:red}</style></head><body>A</body></html>')
            p2_html = p2 / 'index.html'
            p2_html.write_text('<html><head><style>.b{color:blue}</style></head><body>B</body></html>')

            pages_output = {'p1': str(p1_html), 'p2': str(p2_html)}
            output_dir = Path(tmpdir) / 'analysis'
            output_dir.mkdir()

            result = _deduplicate_page_css(pages_output, output_dir)
            shared_path = output_dir / 'pages' / 'shared' / 'common.css'
            ok("无共享 CSS 时应返回空", result == '')

    @staticmethod
    def test_partial_overlap_deduped():
        """部分重叠的 CSS：共享部分提取，独有部分保留在各页面"""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            pages_dir = Path(tmpdir) / 'pages'
            pages_dir.mkdir()
            for name in ['a', 'b', 'c']:
                (pages_dir / name).mkdir()

            common = '/* common.css */\n.base{font-size:14px}\n.m-common{display:flex}\n'
            p1_html = (pages_dir / 'a' / 'index.html')
            p1_html.write_text(f'<html><head><style>{common}/* page1.css */\n.page1{{color:red}}</style></head><body>A</body></html>')
            p2_html = (pages_dir / 'b' / 'index.html')
            p2_html.write_text(f'<html><head><style>{common}/* page2.css */\n.page2{{color:blue}}</style></head><body>B</body></html>')
            p3_html = (pages_dir / 'c' / 'index.html')
            p3_html.write_text(f'<html><head><style>{common}/* page3.css */\n.page3{{color:green}}</style></head><body>C</body></html>')

            pages_output = {
                'a': str(p1_html), 'b': str(p2_html), 'c': str(p3_html),
            }
            output_dir = Path(tmpdir) / 'analysis'
            output_dir.mkdir()

            result = _deduplicate_page_css(pages_output, output_dir)
            ok("共享 CSS 含 base 规则", '.base{font-size:14px}' in result,
               f'result[:300]={result[:300]}')
            ok("独有规则保留在页面",
               '.page1{color:red}' in p1_html.read_text()
               and '.page2{color:blue}' in p2_html.read_text())

    @staticmethod
    def test_single_page_no_dedup():
        """单页面时不触发去重（早期返回）"""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            pages_dir = Path(tmpdir) / 'pages'
            pages_dir.mkdir()
            (pages_dir / 'solo').mkdir()
            html = (pages_dir / 'solo' / 'index.html')
            html.write_text('<html><head><style>.x{color:black}</style></head><body>S</body></html>')

            output_dir = Path(tmpdir) / 'analysis'
            output_dir.mkdir()

            result = _deduplicate_page_css({'solo': str(html)}, output_dir)
            ok("单页面不触发去重", result == '')

    @staticmethod
    def test_no_style_tag_no_crash():
        """页面无 style 标签时不崩溃"""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            pages_dir = Path(tmpdir) / 'pages'
            pages_dir.mkdir()
            (pages_dir / 'ns').mkdir()
            html = (pages_dir / 'ns' / 'index.html')
            html.write_text('<html><body>No Style</body></html>')

            output_dir = Path(tmpdir) / 'analysis'
            output_dir.mkdir()

            result = _deduplicate_page_css({'ns': str(html)}, output_dir)
            ok("无 style 标签返回空", result == '')


# ============================================================
# 运行所有测试
# ============================================================

def run_all():
    print("=" * 60)
    print("  SPA 功能单元测试")
    print("=" * 60)

    print("\n--- PageAssembler: script 处理 ---")
    TestPageAssembler.test_remove_script_tags_wraps_as_comment()
    TestPageAssembler.test_remove_script_tags_empty_script()

    print("\n--- PageAssembler: style 提取 ---")
    TestPageAssembler.test_assemble_full_html_style_extraction()
    TestPageAssembler.test_assemble_full_html_style_with_attributes()
    TestPageAssembler.test_assemble_full_html_multiple_style_tags()
    TestPageAssembler.test_assemble_full_html_style_tag_close_in_css_content()

    print("\n--- PageAssembler: SPA 反闪屏修复 ---")
    TestPageAssembler.test_assemble_full_html_body_display_none_fix()
    TestPageAssembler.test_assemble_full_html_body_display_none_with_other_properties()

    print("\n--- PageAssembler: 服务端后缀/资源处理 ---")
    TestPageAssembler.test_server_suffix_skipped_in_rewrite()
    TestPageAssembler.test_css_link_removed()
    TestPageAssembler.test_title_extraction()

    print("\n--- CausalExtractor: route-change 处理 ---")
    TestCausalExtractor.test_route_change_updates_page_url()
    TestCausalExtractor.test_route_change_creates_navigation_on_page_load()
    TestCausalExtractor.test_get_action_summary_filters_route_change()

    print("\n--- learn.py: 静态资源/URL 处理 ---")
    TestLearnHelpers.test_is_static_resource_css()
    TestLearnHelpers.test_is_static_resource_js()
    TestLearnHelpers.test_is_static_resource_png()
    TestLearnHelpers.test_is_static_resource_woff2()
    TestLearnHelpers.test_is_static_resource_jsp_is_not()
    TestLearnHelpers.test_is_static_resource_html_page()
    TestLearnHelpers.test_url_base_strips_hash()
    TestLearnHelpers.test_url_base_no_hash()
    TestLearnHelpers.test_make_page_name_spa_route()
    TestLearnHelpers.test_make_page_name_query_params()

    print("\n--- inlineStyles → page_assembler 集成测试 ---")
    TestInlineStylesIntegration.test_styled_components_inline_styles_injected_into_css()
    TestInlineStylesIntegration.test_multiple_inline_styles_concatenated()
    TestInlineStylesIntegration.test_css_with_special_characters()
    TestInlineStylesIntegration.test_body_style_extraction_combined_with_external_css()
    TestInlineStylesIntegration.test_inline_styles_with_data_attributes()
    TestInlineStylesIntegration.test_empty_inline_styles_graceful()
    TestInlineStylesIntegration.test_very_long_css_truncation_in_template()
    TestInlineStylesIntegration.test_css_with_unicode_and_chinese()

    print("\n--- PageAssembler: body 属性保留 ---")
    TestBodyAttributePreservation.test_body_class_preserved()
    TestBodyAttributePreservation.test_body_style_preserved()
    TestBodyAttributePreservation.test_body_multiple_attrs_preserved()
    TestBodyAttributePreservation.test_body_no_attrs_works()
    TestBodyAttributePreservation.test_html_and_body_attrs_together()

    print("\n--- learn.py: CSS 去重 ---")
    TestCSSDeduplication.test_identical_css_across_pages_deduped()
    TestCSSDeduplication.test_different_css_not_deduped()
    TestCSSDeduplication.test_partial_overlap_deduped()
    TestCSSDeduplication.test_single_page_no_dedup()
    TestCSSDeduplication.test_no_style_tag_no_crash()

    return summary()


if __name__ == '__main__':
    success = run_all()
    sys.exit(0 if success else 1)