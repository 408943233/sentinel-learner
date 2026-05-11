"""
HTML处理器模块 - 清理和修复HTML
"""
import re
from typing import List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class HTMLIssue:
    """HTML问题"""
    type: str
    message: str
    severity: str  # 'error', 'warning', 'info'
    line_number: Optional[int] = None


class HTMLProcessor:
    """HTML处理器 - 检测和修复问题"""
    
    # 问题检测规则
    EMOJI_PATTERN = re.compile("["
        u"\U0001F600-\U0001F64F"  # emoticons
        u"\U0001F300-\U0001F5FF"  # symbols & pictographs
        u"\U0001F680-\U0001F6FF"  # transport & map symbols
        u"\U0001F1E0-\U0001F1FF"  # flags
        u"\U00002702-\U000027B0"
        u"\U000024C2-\U0001F251"
        "\u2764\uFE0F"  # ❤️
        "\u2728"  # ✨
        "\u2B50"  # ⭐
        "\U0001F4C8"  # 📈
        "\U0001F4B0"  # 💰
        "\U0001F4CA"  # 📊
        "]+", flags=re.UNICODE)
    
    HTML_ENTITY_EMOJI = re.compile(r'&#\d{5,6};')
    
    ANIMATION_PATTERN = re.compile(
        r'transition:|animation:|@keyframes|animation-name',
        re.IGNORECASE
    )
    
    SCROLL_PATTERN = re.compile(
        r'overflow-y:\s*(auto|scroll)|overflow:\s*(auto|scroll)',
        re.IGNORECASE
    )
    
    HOVER_PATTERN = re.compile(r':hover', re.IGNORECASE)
    
    JS_PATTERN = re.compile(r'<script|on\w+\s*=', re.IGNORECASE)
    
    FIXED_POSITION_PATTERN = re.compile(r'position:\s*fixed', re.IGNORECASE)
    
    # 检测sticky定位（会导致滑动效果）
    STICKY_PATTERN = re.compile(r'position:\s*sticky', re.IGNORECASE)
    
    # 检测absolute定位（可能导致区块叠加）
    ABSOLUTE_POSITION_PATTERN = re.compile(r'position:\s*absolute', re.IGNORECASE)
    
    # 检测固定高度（如 min-height: 200px）
    FIXED_MIN_HEIGHT_PATTERN = re.compile(r'min-height:\s*\d+px', re.IGNORECASE)
    
    # 检测overflow hidden（会导致截断）
    OVERFLOW_HIDDEN_PATTERN = re.compile(r'overflow:\s*hidden', re.IGNORECASE)
    
    # 检测固定高度问题 (如 height: 600px)
    FIXED_HEIGHT_PATTERN = re.compile(
        r'height:\s*(\d{3,4})px',
        re.IGNORECASE
    )
    
    def __init__(self):
        self.issues: List[HTMLIssue] = []
    
    def detect_issues(self, html: str) -> List[HTMLIssue]:
        """检测HTML中的问题"""
        self.issues = []
        
        # 1. 检测emoji
        if self.EMOJI_PATTERN.search(html):
            self.issues.append(HTMLIssue(
                type='emoji',
                message='检测到emoji字符，请使用SVG替代',
                severity='warning'
            ))
        
        # 2. 检测HTML实体emoji
        if self.HTML_ENTITY_EMOJI.search(html):
            self.issues.append(HTMLIssue(
                type='html_entity_emoji',
                message='检测到HTML实体emoji，请使用SVG替代',
                severity='warning'
            ))
        
        # 3. 检测动画
        if self.ANIMATION_PATTERN.search(html):
            self.issues.append(HTMLIssue(
                type='animation',
                message='检测到CSS动画效果，建议移除',
                severity='warning'
            ))
        
        # 4. 检测滚动
        if self.SCROLL_PATTERN.search(html):
            self.issues.append(HTMLIssue(
                type='scroll',
                message='检测到滚动效果，建议改为平铺展示',
                severity='warning'
            ))
        
        # 5. 检测hover
        if self.HOVER_PATTERN.search(html):
            self.issues.append(HTMLIssue(
                type='hover',
                message='检测到hover效果，建议移除',
                severity='info'
            ))
        
        # 6. 检测JavaScript
        if self.JS_PATTERN.search(html):
            self.issues.append(HTMLIssue(
                type='javascript',
                message='检测到JavaScript代码，建议移除',
                severity='error'
            ))
        
        # 7. 检测fixed定位
        if self.FIXED_POSITION_PATTERN.search(html):
            self.issues.append(HTMLIssue(
                type='fixed_position',
                message='检测到fixed定位，建议改为absolute',
                severity='warning'
            ))
        
        # 8. 检测sticky定位（会导致滑动效果）
        if self.STICKY_PATTERN.search(html):
            self.issues.append(HTMLIssue(
                type='sticky_position',
                message='检测到sticky定位，会导致滑动效果，必须移除',
                severity='error'
            ))
        
        # 9. 检测overflow hidden（会导致内容截断）
        if self.OVERFLOW_HIDDEN_PATTERN.search(html):
            self.issues.append(HTMLIssue(
                type='overflow_hidden',
                message='检测到overflow: hidden，会导致内容截断，必须移除',
                severity='error'
            ))
        
        # 10. 检测absolute定位（可能导致区块叠加）
        if self.ABSOLUTE_POSITION_PATTERN.search(html):
            self.issues.append(HTMLIssue(
                type='absolute_position',
                message='检测到absolute定位，可能导致区块叠加，建议使用正常文档流',
                severity='warning'
            ))
        
        # 11. 检测固定min-height
        if self.FIXED_MIN_HEIGHT_PATTERN.search(html):
            self.issues.append(HTMLIssue(
                type='fixed_min_height',
                message='检测到固定min-height，可能导致内容截断，建议改为auto',
                severity='warning'
            ))
        
        # 12. 检测箭头数量（可能的幻觉）
        arrow_count = len(re.findall(r'class="[^"]*arrow[^"]*"', html, re.IGNORECASE))
        if arrow_count > 10:
            self.issues.append(HTMLIssue(
                type='arrow_hallucination',
                message=f'检测到{arrow_count}个箭头，可能存在幻觉',
                severity='warning'
            ))
        
        # 9. 检测固定高度问题
        fixed_heights = self.FIXED_HEIGHT_PATTERN.findall(html)
        if fixed_heights:
            large_heights = [h for h in fixed_heights if int(h) > 300]
            if large_heights:
                self.issues.append(HTMLIssue(
                    type='fixed_height',
                    message=f'检测到固定高度设置: {", ".join(set(large_heights))}px，建议改为自适应高度',
                    severity='warning'
                ))
        
        return self.issues
    
    def auto_fix(self, html: str) -> Tuple[str, List[HTMLIssue]]:
        """
        自动修复可修复的问题
        返回: (修复后的HTML, 剩余需要手动修复的问题)
        """
        self.detect_issues(html)
        
        fixed_html = html
        auto_fixed = []
        remaining = []
        
        for issue in self.issues:
            if issue.type == 'javascript':
                fixed_html = self._fix_javascript(fixed_html)
                auto_fixed.append(issue)
            
            elif issue.type == 'hover':
                fixed_html = self._fix_hover(fixed_html)
                auto_fixed.append(issue)
            
            elif issue.type == 'fixed_position':
                fixed_html = self._fix_fixed_position(fixed_html)
                auto_fixed.append(issue)
            
            elif issue.type == 'fixed_height':
                fixed_html = self._fix_fixed_height(fixed_html)
                auto_fixed.append(issue)
            
            elif issue.type == 'sticky_position':
                fixed_html = self._fix_sticky_position(fixed_html)
                auto_fixed.append(issue)
            
            elif issue.type == 'overflow_hidden':
                fixed_html = self._fix_overflow_hidden(fixed_html)
                auto_fixed.append(issue)
            
            elif issue.type == 'absolute_position':
                fixed_html = self._fix_absolute_position(fixed_html)
                auto_fixed.append(issue)
            
            elif issue.type == 'fixed_min_height':
                fixed_html = self._fix_fixed_min_height(fixed_html)
                auto_fixed.append(issue)
            
            else:
                remaining.append(issue)
        
        if auto_fixed:
            print(f"  🔧 自动修复了 {len(auto_fixed)} 个问题:")
            for issue in auto_fixed:
                print(f"    ✓ {issue.message}")
        
        if remaining:
            print(f"  ⚠️ 仍有 {len(remaining)} 个问题需要手动处理")
        
        return fixed_html, remaining
    
    def _fix_javascript(self, html: str) -> str:
        """移除JavaScript代码"""
        # 移除script标签
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        # 移除事件处理器
        html = re.sub(r'\s*on\w+\s*=\s*["\'][^"\']*["\']', '', html, flags=re.IGNORECASE)
        return html
    
    def _fix_hover(self, html: str) -> str:
        """移除hover效果"""
        # 移除:hover规则
        html = re.sub(r'[^}]*:hover\s*\{[^}]*\}', '', html, flags=re.DOTALL | re.IGNORECASE)
        return html
    
    def _fix_fixed_position(self, html: str) -> str:
        """将fixed改为absolute"""
        html = re.sub(r'position:\s*fixed', 'position: absolute', html, flags=re.IGNORECASE)
        return html
    
    def _fix_fixed_height(self, html: str) -> str:
        """将固定高度改为自适应高度"""
        # 将大于300px的固定高度改为auto
        def replace_large_height(match):
            height_val = int(match.group(1))
            if height_val > 300:
                return 'height: auto;\n            min-height: 200px'
            return match.group(0)
        
        html = self.FIXED_HEIGHT_PATTERN.sub(replace_large_height, html)
        return html
    
    def _fix_sticky_position(self, html: str) -> str:
        """移除sticky定位，改为static"""
        # 移除position: sticky
        html = re.sub(r'position:\s*sticky\s*;?', '', html, flags=re.IGNORECASE)
        # 移除相关的top/bottom/left/right/z-index
        html = re.sub(r'\s*top:\s*\d+px\s*;?', '', html, flags=re.IGNORECASE)
        html = re.sub(r'\s*z-index:\s*\d+\s*;?', '', html, flags=re.IGNORECASE)
        return html
    
    def _fix_overflow_hidden(self, html: str) -> str:
        """移除overflow: hidden"""
        html = re.sub(r'overflow:\s*hidden\s*;?', 'overflow: visible;', html, flags=re.IGNORECASE)
        return html
    
    def _fix_absolute_position(self, html: str) -> str:
        """将absolute定位改为static（保留内部元素的absolute）"""
        # 只修复.page-container的position: absolute
        html = re.sub(
            r'(.page-container\s*\{[^}]*?)position:\s*absolute',
            r'\1position: static',
            html,
            flags=re.IGNORECASE | re.DOTALL
        )
        return html
    
    def _fix_fixed_min_height(self, html: str) -> str:
        """将固定min-height改为auto"""
        # 将min-height: 200px等改为min-height: auto
        html = re.sub(r'min-height:\s*\d+px', 'min-height: auto', html, flags=re.IGNORECASE)
        return html
    
    def generate_fix_prompt(self, html: str, issues: List[HTMLIssue]) -> Optional[str]:
        """生成修复提示词"""
        if not issues:
            return None
        
        prompt_parts = ["【HTML修复任务】\n"]
        prompt_parts.append("请修复以下HTML代码中的问题:\n")
        
        for i, issue in enumerate(issues, 1):
            prompt_parts.append(f"\n## 问题 {i}: {issue.message}")
            
            if issue.type == 'emoji':
                emojis = self.EMOJI_PATTERN.findall(html)
                if emojis:
                    prompt_parts.append(f"**需要移除的emoji**: {', '.join(set(emojis))}")
                    prompt_parts.append("**修复方法**: 将这些emoji替换为SVG图标或删除")
            
            elif issue.type == 'html_entity_emoji':
                entities = self.HTML_ENTITY_EMOJI.findall(html)
                if entities:
                    prompt_parts.append(f"**需要移除的HTML实体**: {', '.join(set(entities))}")
                    prompt_parts.append("**修复方法**: 将这些实体替换为SVG图标或删除")
            
            elif issue.type == 'animation':
                prompt_parts.append("**修复方法**: 删除transition、animation、@keyframes相关代码")
            
            elif issue.type == 'scroll':
                prompt_parts.append("**修复方法**: 删除overflow-y: auto/scroll，改为overflow: visible")
        
        prompt_parts.append(f"\n\n【当前HTML代码】\n```html\n{html}\n```")
        prompt_parts.append("\n\n【修复要求】")
        prompt_parts.append("1. 只修改上述指出的问题")
        prompt_parts.append("2. 保持HTML结构完整")
        prompt_parts.append("3. 返回完整的修复后HTML代码")
        prompt_parts.append("4. 不要添加任何解释")
        
        return '\n'.join(prompt_parts)
    
    def validate_html(self, html: str) -> bool:
        """验证HTML基本结构"""
        checks = [
            html.strip().startswith('<!DOCTYPE') or html.strip().startswith('<html'),
            '</html>' in html,
            '<head>' in html and '</head>' in html,
            '<body>' in html and '</body>' in html,
        ]
        return all(checks)
    
    def clean(self, html: str) -> str:
        """全面清理HTML"""
        # 移除markdown代码块
        html = re.sub(r'^```html\s*', '', html, flags=re.IGNORECASE)
        html = re.sub(r'```\s*$', '', html)
        
        # 修复自闭合标签
        html = re.sub(r'<(br|hr|img|input|meta|link)([^>]*)>', r'<\1\2 />', html)
        
        # 规范化空白字符
        html = re.sub(r'\n\s*\n', '\n', html)
        
        return html.strip()


# 便捷函数
def process_html(html: str, api_manager=None, base64_image: str = "", max_retries: int = 3) -> Tuple[str, List[HTMLIssue]]:
    """处理HTML，自动修复并将剩余问题提交给LLM修复"""
    processor = HTMLProcessor()
    fixed_html, issues = processor.auto_fix(html)
    fixed_html = processor.clean(fixed_html)
    
    # 如果还有未修复的问题，提交给LLM修复
    if issues and api_manager:
        print(f"  🔄 将{len(issues)}个问题提交给LLM修复...")
        
        for attempt in range(max_retries):
            # 生成修复提示词
            fix_prompt = processor.generate_fix_prompt(fixed_html, issues)
            if not fix_prompt:
                break
            
            try:
                # 调用LLM修复 - 传入原始图片base64
                response = api_manager.call_with_fallback(base64_image, fix_prompt)
                if response and response.content:
                    fixed_html = response.content
                    fixed_html = processor.clean(fixed_html)
                    
                    # 重新检测问题
                    fixed_html, issues = processor.auto_fix(fixed_html)
                    fixed_html = processor.clean(fixed_html)
                    
                    if not issues:
                        print(f"  ✅ LLM修复成功，所有问题已解决")
                        break
                    else:
                        print(f"  ⚠️ 修复后仍有{len(issues)}个问题，继续修复...")
                else:
                    print(f"  ❌ LLM修复失败: 无响应")
                    break
                    
            except Exception as e:
                print(f"  ❌ LLM修复失败: {e}")
                break
    
    return fixed_html, issues
