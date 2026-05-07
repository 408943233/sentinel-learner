"""
Logs 分析器
分析控制台错误和系统日志
"""

import json
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from pathlib import Path
from collections import defaultdict
import re


@dataclass
class ConsoleError:
    """控制台错误"""
    timestamp: int
    level: str  # error, warn, info
    message: str
    source: str
    line: int
    column: int
    stack_trace: str
    url: str
    error_type: str


@dataclass
class ErrorPattern:
    """错误模式"""
    pattern: str
    count: int
    first_seen: int
    last_seen: int
    affected_pages: List[str]
    severity: str


@dataclass
class SystemHealth:
    """系统健康度"""
    error_rate: float
    warning_rate: float
    critical_errors: int
    stability_score: float  # 0-100


@dataclass
class LogsAnalysisResult:
    """日志分析结果"""
    console_errors: List[ConsoleError]
    error_patterns: List[ErrorPattern]
    system_health: SystemHealth
    js_errors: List[Dict]  # JavaScript错误
    network_errors: List[Dict]  # 网络相关错误
    performance_issues: List[Dict]  # 性能问题
    recommendations: List[str]


class LogsAnalyzer:
    """日志分析器"""
    
    # 错误类型模式
    ERROR_PATTERNS = {
        'reference_error': r'ReferenceError|is not defined',
        'type_error': r'TypeError|Cannot read property',
        'syntax_error': r'SyntaxError|Unexpected token',
        'network_error': r'NetworkError|Failed to fetch|ERR_',
        'cors_error': r'CORS|Cross-Origin|Access-Control',
        'promise_rejection': r'UnhandledPromiseRejection|Promise',
        'null_undefined': r'null|undefined|cannot read',
        'timeout_error': r'Timeout|ETIMEDOUT',
        'resource_error': r'Resource|404|Not Found'
    }
    
    def __init__(self, logs_dir: str):
        """
        初始化分析器
        
        Args:
            logs_dir: logs目录路径
        """
        self.logs_dir = Path(logs_dir)
        self.console_errors: List[ConsoleError] = []
        self.js_errors: List[Dict] = []
    
    def analyze(self) -> LogsAnalysisResult:
        """
        执行完整分析
        
        Returns:
            分析结果
        """
        print("  [Logs分析] 加载控制台错误...")
        self._load_console_errors()
        print(f"    发现 {len(self.console_errors)} 个控制台错误")
        
        print("  [Logs分析] 加载JS错误...")
        self._load_js_errors()
        print(f"    发现 {len(self.js_errors)} 个JS错误")
        
        print("  [Logs分析] 分析错误模式...")
        error_patterns = self._analyze_error_patterns()
        print(f"    识别 {len(error_patterns)} 个错误模式")
        
        print("  [Logs分析] 评估系统健康度...")
        system_health = self._assess_system_health()
        
        print("  [Logs分析] 分类错误...")
        network_errors = self._extract_network_errors()
        performance_issues = self._extract_performance_issues()
        
        print("  [Logs分析] 生成建议...")
        recommendations = self._generate_recommendations(error_patterns)
        
        return LogsAnalysisResult(
            console_errors=self.console_errors,
            error_patterns=error_patterns,
            system_health=system_health,
            js_errors=self.js_errors,
            network_errors=network_errors,
            performance_issues=performance_issues,
            recommendations=recommendations
        )
    
    def _load_console_errors(self):
        """加载控制台错误"""
        errors_file = self.logs_dir / "console_errors.jsonl"
        
        if not errors_file.exists():
            return
        
        with open(errors_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    error = json.loads(line)
                    
                    console_error = ConsoleError(
                        timestamp=error.get("timestamp", 0),
                        level=error.get("level", "error"),
                        message=error.get("message", ""),
                        source=error.get("source", ""),
                        line=error.get("line", 0),
                        column=error.get("column", 0),
                        stack_trace=error.get("stack", ""),
                        url=error.get("url", ""),
                        error_type=self._classify_error(error.get("message", ""))
                    )
                    self.console_errors.append(console_error)
                except:
                    continue
    
    def _load_js_errors(self):
        """加载JS错误"""
        errors_file = self.logs_dir / "errors.json"
        
        if not errors_file.exists():
            return
        
        try:
            with open(errors_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    self.js_errors = data
                elif isinstance(data, dict):
                    self.js_errors = data.get("errors", [])
        except:
            pass
    
    def _classify_error(self, message: str) -> str:
        """分类错误类型"""
        message_lower = message.lower()
        
        for error_type, pattern in self.ERROR_PATTERNS.items():
            if re.search(pattern, message_lower):
                return error_type
        
        return 'unknown'
    
    def _analyze_error_patterns(self) -> List[ErrorPattern]:
        """分析错误模式"""
        patterns = defaultdict(lambda: {
            "count": 0,
            "first_seen": float('inf'),
            "last_seen": 0,
            "affected_pages": set(),
            "messages": []
        })
        
        for error in self.console_errors:
            error_type = error.error_type
            
            patterns[error_type]["count"] += 1
            patterns[error_type]["first_seen"] = min(
                patterns[error_type]["first_seen"], 
                error.timestamp
            )
            patterns[error_type]["last_seen"] = max(
                patterns[error_type]["last_seen"], 
                error.timestamp
            )
            patterns[error_type]["affected_pages"].add(error.url)
            patterns[error_type]["messages"].append(error.message[:100])
        
        # 转换为ErrorPattern对象
        error_patterns = []
        for pattern_name, data in patterns.items():
            # 确定严重程度
            severity = self._determine_severity(pattern_name, data["count"])
            
            error_patterns.append(ErrorPattern(
                pattern=pattern_name,
                count=data["count"],
                first_seen=data["first_seen"],
                last_seen=data["last_seen"],
                affected_pages=list(data["affected_pages"]),
                severity=severity
            ))
        
        # 按数量和严重程度排序
        error_patterns.sort(key=lambda x: (x.severity != 'critical', -x.count))
        
        return error_patterns
    
    def _determine_severity(self, error_type: str, count: int) -> str:
        """确定错误严重程度"""
        critical_types = ['reference_error', 'type_error', 'syntax_error']
        warning_types = ['network_error', 'cors_error', 'resource_error']
        
        if error_type in critical_types and count > 5:
            return 'critical'
        elif error_type in critical_types or count > 10:
            return 'high'
        elif error_type in warning_types:
            return 'medium'
        else:
            return 'low'
    
    def _assess_system_health(self) -> SystemHealth:
        """评估系统健康度"""
        total_errors = len(self.console_errors)
        
        # 统计各级别错误
        error_count = sum(1 for e in self.console_errors if e.level == 'error')
        warning_count = sum(1 for e in self.console_errors if e.level == 'warn')
        
        # 计算错误率（假设每100个事件）
        error_rate = error_count / max(total_errors, 1) * 100
        warning_rate = warning_count / max(total_errors, 1) * 100
        
        # 严重错误数
        critical_errors = sum(1 for e in self.console_errors 
                             if e.error_type in ['reference_error', 'type_error'])
        
        # 计算稳定性分数 (0-100)
        stability_score = 100
        stability_score -= error_count * 2  # 每个错误扣2分
        stability_score -= warning_count * 0.5  # 每个警告扣0.5分
        stability_score -= critical_errors * 10  # 严重错误额外扣分
        stability_score = max(0, stability_score)
        
        return SystemHealth(
            error_rate=error_rate,
            warning_rate=warning_rate,
            critical_errors=critical_errors,
            stability_score=stability_score
        )
    
    def _extract_network_errors(self) -> List[Dict]:
        """提取网络相关错误"""
        network_errors = []
        
        for error in self.console_errors:
            if error.error_type in ['network_error', 'cors_error', 'resource_error']:
                network_errors.append({
                    "timestamp": error.timestamp,
                    "message": error.message[:100],
                    "url": error.url,
                    "source": error.source,
                    "type": error.error_type
                })
        
        return network_errors
    
    def _extract_performance_issues(self) -> List[Dict]:
        """提取性能问题"""
        performance_issues = []
        
        # 查找性能相关的错误/警告
        performance_keywords = ['slow', 'performance', 'timeout', 'memory', 'lag']
        
        for error in self.console_errors:
            if any(kw in error.message.lower() for kw in performance_keywords):
                performance_issues.append({
                    "timestamp": error.timestamp,
                    "message": error.message[:100],
                    "url": error.url,
                    "type": "performance"
                })
        
        return performance_issues
    
    def _generate_recommendations(self, patterns: List[ErrorPattern]) -> List[str]:
        """生成优化建议"""
        recommendations = []
        
        # 根据错误模式生成建议
        for pattern in patterns:
            if pattern.pattern == 'reference_error':
                recommendations.append(
                    f"发现 {pattern.count} 个引用错误，建议检查变量定义和脚本加载顺序"
                )
            elif pattern.pattern == 'type_error':
                recommendations.append(
                    f"发现 {pattern.count} 个类型错误，建议添加类型检查和空值保护"
                )
            elif pattern.pattern == 'cors_error':
                recommendations.append(
                    f"发现 {pattern.count} 个跨域错误，建议配置CORS策略或代理"
                )
            elif pattern.pattern == 'network_error':
                recommendations.append(
                    f"发现 {pattern.count} 个网络错误，建议添加错误重试机制"
                )
            elif pattern.pattern == 'promise_rejection':
                recommendations.append(
                    f"发现 {pattern.count} 个未处理的Promise拒绝，建议添加.catch()处理"
                )
        
        # 根据系统健康度生成建议
        critical_count = sum(1 for p in patterns if p.severity == 'critical')
        if critical_count > 0:
            recommendations.insert(0, f"发现 {critical_count} 个严重错误模式，建议优先修复")
        
        return recommendations


if __name__ == "__main__":
    # 测试
    import sys
    if len(sys.argv) > 1:
        analyzer = LogsAnalyzer(sys.argv[1])
        result = analyzer.analyze()
        
        print("\n=== 日志分析结果 ===")
        print(f"控制台错误数: {len(result.console_errors)}")
        print(f"JS错误数: {len(result.js_errors)}")
        print(f"系统健康度: {result.system_health.stability_score:.1f}/100")
        
        print("\n=== 错误模式 ===")
        for pattern in result.error_patterns[:5]:
            print(f"  [{pattern.severity}] {pattern.pattern}: {pattern.count} 次")
        
        print("\n=== 优化建议 ===")
        for rec in result.recommendations[:5]:
            print(f"  - {rec}")
