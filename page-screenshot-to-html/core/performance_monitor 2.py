"""
性能监控模块 - 收集性能指标和耗时统计
"""
import time
import functools
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from collections import defaultdict
import statistics


@dataclass
class Metric:
    """性能指标"""
    name: str
    count: int = 0
    total_time: float = 0.0
    min_time: float = float('inf')
    max_time: float = 0.0
    times: List[float] = field(default_factory=list)
    
    def add(self, duration: float):
        """添加一次测量"""
        self.count += 1
        self.total_time += duration
        self.min_time = min(self.min_time, duration)
        self.max_time = max(self.max_time, duration)
        self.times.append(duration)
        
        # 只保留最近100次记录
        if len(self.times) > 100:
            self.times = self.times[-100:]
    
    @property
    def avg_time(self) -> float:
        """平均耗时"""
        return self.total_time / self.count if self.count > 0 else 0.0
    
    @property
    def median_time(self) -> float:
        """中位数耗时"""
        if not self.times:
            return 0.0
        return statistics.median(self.times)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'count': self.count,
            'total_time': round(self.total_time, 2),
            'avg_time': round(self.avg_time, 3),
            'median_time': round(self.median_time, 3),
            'min_time': round(self.min_time, 3),
            'max_time': round(self.max_time, 3)
        }


class PerformanceMonitor:
    """性能监控器 - 单例模式"""
    _instance: Optional['PerformanceMonitor'] = None
    _initialized: bool = False
    
    def __new__(cls) -> 'PerformanceMonitor':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if PerformanceMonitor._initialized:
            return
        
        self.metrics: Dict[str, Metric] = defaultdict(lambda: Metric(""))
        self.enabled = True
        PerformanceMonitor._initialized = True
    
    def track_time(self, name: str) -> Callable:
        """装饰器：跟踪函数执行时间"""
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                if not self.enabled:
                    return func(*args, **kwargs)
                
                start_time = time.time()
                try:
                    return func(*args, **kwargs)
                finally:
                    duration = time.time() - start_time
                    self.record(name, duration)
            
            return wrapper
        return decorator
    
    def record(self, name: str, duration: float):
        """记录一次性能指标"""
        if not self.enabled:
            return
        
        if name not in self.metrics:
            self.metrics[name] = Metric(name)
        
        self.metrics[name].add(duration)
    
    def get_metric(self, name: str) -> Optional[Metric]:
        """获取指定指标"""
        return self.metrics.get(name)
    
    def get_all_metrics(self) -> Dict[str, Dict[str, Any]]:
        """获取所有指标"""
        return {name: metric.to_dict() for name, metric in self.metrics.items()}
    
    def print_report(self):
        """打印性能报告"""
        if not self.metrics:
            print("  📊 暂无性能数据")
            return
        
        print("\n" + "="*60)
        print("性能监控报告")
        print("="*60)
        
        for name, metric in sorted(self.metrics.items()):
            print(f"\n{name}:")
            print(f"  调用次数: {metric.count}")
            print(f"  总耗时: {metric.total_time:.2f}s")
            print(f"  平均耗时: {metric.avg_time:.3f}s")
            print(f"  中位数: {metric.median_time:.3f}s")
            print(f"  最小/最大: {metric.min_time:.3f}s / {metric.max_time:.3f}s")
        
        print("="*60)
    
    def reset(self):
        """重置所有指标"""
        self.metrics.clear()
    
    def enable(self):
        """启用监控"""
        self.enabled = True
    
    def disable(self):
        """禁用监控"""
        self.enabled = False


# 全局监控器实例
monitor = PerformanceMonitor()


class Timer:
    """上下文管理器：计时器"""
    
    def __init__(self, name: str, monitor_instance: Optional[PerformanceMonitor] = None):
        self.name = name
        self.monitor = monitor_instance or monitor
        self.start_time: Optional[float] = None
        self.duration: Optional[float] = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.duration = time.time() - self.start_time
        self.monitor.record(self.name, self.duration)
    
    def elapsed(self) -> float:
        """获取已流逝的时间"""
        if self.duration is not None:
            return self.duration
        if self.start_time is not None:
            return time.time() - self.start_time
        return 0.0
