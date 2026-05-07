"""
Network Resources 分析器
分析静态资源加载情况
"""

import json
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from pathlib import Path
from collections import defaultdict


@dataclass
class Resource:
    """静态资源"""
    timestamp: int
    url: str
    resource_type: str  # css, js, image, font, etc.
    size: int
    duration_ms: int
    status: int
    from_cache: bool
    domain: str


@dataclass
class ResourceStats:
    """资源统计"""
    total_count: int
    total_size: int
    by_type: Dict[str, Dict[str, Any]]
    by_domain: Dict[str, int]
    cache_hit_rate: float
    load_timing: Dict[str, float]


@dataclass
class PerformanceImpact:
    """性能影响分析"""
    slowest_resources: List[Dict]
    largest_resources: List[Dict]
    render_blocking: List[str]
    optimization_suggestions: List[str]


@dataclass
class ResourcesAnalysisResult:
    """资源分析结果"""
    resources: List[Resource]
    stats: ResourceStats
    performance: PerformanceImpact
    cdn_usage: Dict[str, Any]
    third_party_analysis: Dict[str, Any]


class ResourcesAnalyzer:
    """静态资源分析器"""
    
    # 资源类型映射
    RESOURCE_TYPES = {
        '.css': 'stylesheet',
        '.js': 'script',
        '.png': 'image',
        '.jpg': 'image',
        '.jpeg': 'image',
        '.gif': 'image',
        '.svg': 'image',
        '.woff': 'font',
        '.woff2': 'font',
        '.ttf': 'font',
        '.eot': 'font',
        '.html': 'document',
        '.json': 'data',
        '.xml': 'data'
    }
    
    # 常见CDN域名
    CDN_DOMAINS = [
        'cdn.', 'cdnjs.', 'unpkg.', 'jsdelivr',
        'ajax.googleapis', 'fonts.googleapis',
        'bootstrapcdn', 'cloudflare'
    ]
    
    def __init__(self, resources_dir: str):
        """
        初始化分析器
        
        Args:
            resources_dir: resources目录路径
        """
        self.resources_dir = Path(resources_dir)
        self.resources: List[Resource] = []
    
    def analyze(self) -> ResourcesAnalysisResult:
        """
        执行完整分析
        
        Returns:
            分析结果
        """
        print("  [Resources分析] 扫描资源文件...")
        self._scan_resources()
        print(f"    发现 {len(self.resources)} 个资源")
        
        print("  [Resources分析] 统计资源类型...")
        stats = self._calculate_stats()
        
        print("  [Resources分析] 分析性能影响...")
        performance = self._analyze_performance()
        
        print("  [Resources分析] 分析CDN使用...")
        cdn_usage = self._analyze_cdn()
        
        print("  [Resources分析] 分析第三方资源...")
        third_party = self._analyze_third_party()
        
        return ResourcesAnalysisResult(
            resources=self.resources,
            stats=stats,
            performance=performance,
            cdn_usage=cdn_usage,
            third_party_analysis=third_party
        )
    
    def _scan_resources(self):
        """扫描资源文件"""
        if not self.resources_dir.exists():
            return
        
        for file_path in self.resources_dir.iterdir():
            if not file_path.is_file():
                continue
            
            # 从文件名解析信息
            # 格式: timestamp_filename.ext
            filename = file_path.name
            parts = filename.split('_', 1)
            
            if len(parts) < 2:
                continue
            
            try:
                timestamp = int(parts[0])
            except:
                timestamp = 0
            
            # 确定资源类型
            resource_type = self._determine_resource_type(filename)
            
            # 获取文件大小
            size = file_path.stat().st_size
            
            # 提取域名（从文件名或路径）
            domain = self._extract_domain(filename)
            
            resource = Resource(
                timestamp=timestamp,
                url=filename,
                resource_type=resource_type,
                size=size,
                duration_ms=0,  # 无法从文件获取
                status=200,  # 假设成功
                from_cache=False,
                domain=domain
            )
            self.resources.append(resource)
        
        # 按时间戳排序
        self.resources.sort(key=lambda x: x.timestamp)
    
    def _determine_resource_type(self, filename: str) -> str:
        """确定资源类型"""
        lower_name = filename.lower()
        
        for ext, rtype in self.RESOURCE_TYPES.items():
            if lower_name.endswith(ext):
                return rtype
        
        return 'unknown'
    
    def _extract_domain(self, filename: str) -> str:
        """从文件名提取域名"""
        # 尝试从文件名中提取域名信息
        # 例如: 1778034753004_icon_95551_92_2x.44efe523.png.png
        parts = filename.split('_')
        
        # 如果包含常见域名特征
        for part in parts:
            if '.' in part and not part.endswith(('.png', '.jpg', '.js', '.css')):
                return part
        
        return 'local'
    
    def _calculate_stats(self) -> ResourceStats:
        """计算统计信息"""
        if not self.resources:
            return ResourceStats(
                total_count=0,
                total_size=0,
                by_type={},
                by_domain={},
                cache_hit_rate=0.0,
                load_timing={}
            )
        
        total_size = sum(r.size for r in self.resources)
        
        # 按类型统计
        by_type = defaultdict(lambda: {"count": 0, "size": 0})
        for r in self.resources:
            by_type[r.resource_type]["count"] += 1
            by_type[r.resource_type]["size"] += r.size
        
        # 按域名统计
        by_domain = defaultdict(int)
        for r in self.resources:
            by_domain[r.domain] += 1
        
        # 计算缓存命中率（假设无法准确判断，设为0）
        cache_hit_rate = 0.0
        
        # 加载时序分析
        timestamps = [r.timestamp for r in self.resources]
        load_timing = {
            "first_resource": min(timestamps) if timestamps else 0,
            "last_resource": max(timestamps) if timestamps else 0,
            "load_span_ms": max(timestamps) - min(timestamps) if timestamps else 0
        }
        
        return ResourceStats(
            total_count=len(self.resources),
            total_size=total_size,
            by_type=dict(by_type),
            by_domain=dict(by_domain),
            cache_hit_rate=cache_hit_rate,
            load_timing=load_timing
        )
    
    def _analyze_performance(self) -> PerformanceImpact:
        """分析性能影响"""
        # 最大的资源
        largest = sorted(self.resources, key=lambda x: x.size, reverse=True)[:10]
        largest_resources = [
            {
                "url": r.url[:50],
                "type": r.resource_type,
                "size_kb": round(r.size / 1024, 2)
            }
            for r in largest
        ]
        
        # 最慢的资源（这里用文件大小作为代理，因为没有真实加载时间）
        slowest = sorted(self.resources, key=lambda x: x.size, reverse=True)[:10]
        slowest_resources = [
            {
                "url": r.url[:50],
                "type": r.resource_type,
                "estimated_time_ms": round(r.size / 1024 * 10, 2)  # 假设10KB/ms
            }
            for r in slowest
        ]
        
        # 渲染阻塞资源
        render_blocking = [
            r.url for r in self.resources
            if r.resource_type in ['stylesheet', 'script'] and r.size > 50000
        ][:10]
        
        # 优化建议
        suggestions = self._generate_optimization_suggestions()
        
        return PerformanceImpact(
            slowest_resources=slowest_resources,
            largest_resources=largest_resources,
            render_blocking=render_blocking,
            optimization_suggestions=suggestions
        )
    
    def _generate_optimization_suggestions(self) -> List[str]:
        """生成优化建议"""
        suggestions = []
        
        # 分析大文件
        large_files = [r for r in self.resources if r.size > 500000]  # > 500KB
        if large_files:
            suggestions.append(f"发现 {len(large_files)} 个大文件(>500KB)，建议压缩或分割")
        
        # 分析图片
        images = [r for r in self.resources if r.resource_type == 'image']
        total_image_size = sum(r.size for r in images)
        if total_image_size > 1024 * 1024:  # > 1MB
            suggestions.append(f"图片总大小 {total_image_size/1024/1024:.2f}MB，建议使用WebP格式或懒加载")
        
        # 分析CSS/JS
        css_js = [r for r in self.resources if r.resource_type in ['stylesheet', 'script']]
        if len(css_js) > 10:
            suggestions.append(f"CSS/JS文件数量较多({len(css_js)})，建议合并以减少请求数")
        
        # 分析字体
        fonts = [r for r in self.resources if r.resource_type == 'font']
        if len(fonts) > 3:
            suggestions.append(f"字体文件较多({len(fonts)})，建议只加载必要字重")
        
        return suggestions
    
    def _analyze_cdn(self) -> Dict[str, Any]:
        """分析CDN使用"""
        cdn_resources = []
        
        for r in self.resources:
            if any(cdn in r.domain.lower() for cdn in self.CDN_DOMAINS):
                cdn_resources.append(r)
        
        return {
            "cdn_resource_count": len(cdn_resources),
            "cdn_resource_size": sum(r.size for r in cdn_resources),
            "cdn_percentage": len(cdn_resources) / len(self.resources) * 100 if self.resources else 0,
            "cdn_domains": list(set(r.domain for r in cdn_resources))
        }
    
    def _analyze_third_party(self) -> Dict[str, Any]:
        """分析第三方资源"""
        # 定义常见第三方服务
        third_party_patterns = {
            'analytics': ['google-analytics', 'gtag', 'segment', 'mixpanel', 'amplitude'],
            'advertising': ['doubleclick', 'googleads', 'facebook', 'adsystem'],
            'social': ['facebook', 'twitter', 'linkedin', 'weibo'],
            'fonts': ['fonts.googleapis', 'fonts.gstatic'],
            'maps': ['maps.google', 'maps.googleapis'],
            'payment': ['stripe', 'paypal', 'alipay', 'wechatpay']
        }
        
        third_party = defaultdict(lambda: {"count": 0, "size": 0, "resources": []})
        
        for r in self.resources:
            url_lower = r.url.lower()
            for category, patterns in third_party_patterns.items():
                if any(p in url_lower for p in patterns):
                    third_party[category]["count"] += 1
                    third_party[category]["size"] += r.size
                    third_party[category]["resources"].append(r.url[:50])
                    break
        
        return {
            "categories": dict(third_party),
            "total_third_party": sum(1 for r in self.resources 
                                     if any(p in r.url.lower() 
                                           for patterns in third_party_patterns.values() 
                                           for p in patterns))
        }


if __name__ == "__main__":
    # 测试
    import sys
    if len(sys.argv) > 1:
        analyzer = ResourcesAnalyzer(sys.argv[1])
        result = analyzer.analyze()
        
        print("\n=== 资源分析结果 ===")
        print(f"总资源数: {result.stats.total_count}")
        print(f"总大小: {result.stats.total_size / 1024 / 1024:.2f} MB")
        
        print("\n=== 资源类型分布 ===")
        for rtype, data in result.stats.by_type.items():
            print(f"  {rtype}: {data['count']} 个, {data['size']/1024:.2f} KB")
        
        print("\n=== 优化建议 ===")
        for suggestion in result.performance.optimization_suggestions:
            print(f"  - {suggestion}")
