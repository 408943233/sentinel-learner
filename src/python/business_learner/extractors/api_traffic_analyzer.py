"""
API Traffic 分析器
分析数据流向和API调用链
"""

import json
from typing import List, Dict, Optional, Any, Set
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse, parse_qs


@dataclass
class APICall:
    """API调用"""
    timestamp: int
    method: str
    url: str
    status: int
    duration_ms: int
    request_size: int
    response_size: int
    resource_type: str
    initiator: str
    query_params: Dict[str, Any]
    response_data_type: str


@dataclass
class DataFlow:
    """数据流向"""
    source: str  # 发起方
    target: str  # 接收方（API端点）
    data_type: str  # 数据类型
    frequency: int  # 调用频次
    avg_response_time: float
    error_rate: float


@dataclass
class APITrafficResult:
    """API流量分析结果"""
    total_requests: int
    unique_endpoints: int
    api_calls: List[APICall]
    data_flows: List[DataFlow]
    endpoint_stats: Dict[str, Any]
    error_requests: List[APICall]
    timing_analysis: Dict[str, Any]
    domain_distribution: Dict[str, int]


class APITrafficAnalyzer:
    """API流量分析器"""
    
    def __init__(self, traffic_path: str):
        """
        初始化分析器
        
        Args:
            traffic_path: api_traffic.jsonl 文件路径
        """
        self.traffic_path = Path(traffic_path)
        self.api_calls: List[APICall] = []
    
    def analyze(self) -> APITrafficResult:
        """
        执行完整分析
        
        Returns:
            分析结果
        """
        print("  [API Traffic分析] 加载流量数据...")
        self._load_traffic()
        print(f"    共 {len(self.api_calls)} 个API调用")
        
        print("  [API Traffic分析] 分析数据流向...")
        data_flows = self._analyze_data_flows()
        print(f"    识别 {len(data_flows)} 个数据流向")
        
        print("  [API Traffic分析] 统计端点...")
        endpoint_stats = self._analyze_endpoints()
        
        print("  [API Traffic分析] 分析错误请求...")
        error_requests = [c for c in self.api_calls if c.status >= 400]
        print(f"    发现 {len(error_requests)} 个错误请求")
        
        print("  [API Traffic分析] 分析时序...")
        timing_analysis = self._analyze_timing()
        
        print("  [API Traffic分析] 分析域名分布...")
        domain_distribution = self._analyze_domains()
        
        return APITrafficResult(
            total_requests=len(self.api_calls),
            unique_endpoints=len(endpoint_stats),
            api_calls=self.api_calls,
            data_flows=data_flows,
            endpoint_stats=endpoint_stats,
            error_requests=error_requests,
            timing_analysis=timing_analysis,
            domain_distribution=domain_distribution
        )
    
    def _load_traffic(self):
        """加载API流量数据"""
        if not self.traffic_path.exists():
            return
        
        with open(self.traffic_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    
                    # 解析URL
                    url = record.get("url", "")
                    parsed = urlparse(url)
                    
                    # 提取查询参数
                    query_params = parse_qs(parsed.query)
                    query_params = {k: v[0] if len(v) == 1 else v for k, v in query_params.items()}
                    
                    call = APICall(
                        timestamp=record.get("timestamp", 0),
                        method=record.get("method", "GET"),
                        url=url,
                        status=record.get("status", 0),
                        duration_ms=record.get("duration", 0),
                        request_size=record.get("request_size", 0),
                        response_size=record.get("response_size", 0),
                        resource_type=record.get("resource_type", "xhr"),
                        initiator=record.get("initiator", ""),
                        query_params=query_params,
                        response_data_type=record.get("response_content_type", "")
                    )
                    self.api_calls.append(call)
                except:
                    continue
    
    def _analyze_data_flows(self) -> List[DataFlow]:
        """分析数据流向"""
        flows = {}
        
        for call in self.api_calls:
            # 提取端点路径
            parsed = urlparse(call.url)
            endpoint = f"{parsed.netloc}{parsed.path}"
            
            # 确定数据类型
            data_type = self._determine_data_type(call)
            
            # 创建流向键
            flow_key = (call.initiator or "page", endpoint, data_type)
            
            if flow_key not in flows:
                flows[flow_key] = {
                    "source": flow_key[0],
                    "target": flow_key[1],
                    "data_type": data_type,
                    "count": 0,
                    "total_time": 0,
                    "errors": 0
                }
            
            flows[flow_key]["count"] += 1
            flows[flow_key]["total_time"] += call.duration_ms
            if call.status >= 400:
                flows[flow_key]["errors"] += 1
        
        # 转换为DataFlow对象
        data_flows = []
        for flow_data in flows.values():
            data_flows.append(DataFlow(
                source=flow_data["source"],
                target=flow_data["target"],
                data_type=flow_data["data_type"],
                frequency=flow_data["count"],
                avg_response_time=flow_data["total_time"] / flow_data["count"],
                error_rate=flow_data["errors"] / flow_data["count"]
            ))
        
        # 按频次排序
        data_flows.sort(key=lambda x: x.frequency, reverse=True)
        
        return data_flows
    
    def _determine_data_type(self, call: APICall) -> str:
        """确定数据类型"""
        url = call.url.lower()
        content_type = call.response_data_type.lower()
        
        # 根据URL路径判断
        if any(kw in url for kw in ["user", "login", "auth", "session"]):
            return "authentication"
        elif any(kw in url for kw in ["product", "item", "goods", "sku"]):
            return "product_data"
        elif any(kw in url for kw in ["order", "cart", "checkout", "payment"]):
            return "order_data"
        elif any(kw in url for kw in ["search", "query", "filter"]):
            return "search_query"
        elif any(kw in url for kw in ["content", "article", "news", "post"]):
            return "content_data"
        elif any(kw in url for kw in ["config", "setting", "option"]):
            return "configuration"
        elif any(kw in url for kw in ["upload", "file", "image", "media"]):
            return "file_transfer"
        
        # 根据Content-Type判断
        if "json" in content_type:
            return "json_data"
        elif "xml" in content_type:
            return "xml_data"
        elif "html" in content_type:
            return "html_content"
        
        return "unknown"
    
    def _analyze_endpoints(self) -> Dict[str, Any]:
        """分析端点统计"""
        endpoints = {}
        
        for call in self.api_calls:
            parsed = urlparse(call.url)
            endpoint = f"{parsed.netloc}{parsed.path}"
            
            if endpoint not in endpoints:
                endpoints[endpoint] = {
                    "count": 0,
                    "methods": set(),
                    "status_codes": {},
                    "total_duration": 0,
                    "min_duration": float('inf'),
                    "max_duration": 0,
                    "total_request_size": 0,
                    "total_response_size": 0
                }
            
            ep = endpoints[endpoint]
            ep["count"] += 1
            ep["methods"].add(call.method)
            ep["status_codes"][call.status] = ep["status_codes"].get(call.status, 0) + 1
            ep["total_duration"] += call.duration_ms
            ep["min_duration"] = min(ep["min_duration"], call.duration_ms)
            ep["max_duration"] = max(ep["max_duration"], call.duration_ms)
            ep["total_request_size"] += call.request_size
            ep["total_response_size"] += call.response_size
        
        # 计算平均值并转换set
        for endpoint, stats in endpoints.items():
            stats["avg_duration"] = stats["total_duration"] / stats["count"]
            stats["methods"] = list(stats["methods"])
        
        return endpoints
    
    def _analyze_timing(self) -> Dict[str, Any]:
        """分析时序"""
        if not self.api_calls:
            return {}
        
        durations = [c.duration_ms for c in self.api_calls]
        
        return {
            "total_calls": len(durations),
            "avg_duration_ms": sum(durations) / len(durations),
            "min_duration_ms": min(durations),
            "max_duration_ms": max(durations),
            "p50_duration_ms": sorted(durations)[len(durations) // 2],
            "p95_duration_ms": sorted(durations)[int(len(durations) * 0.95)],
            "p99_duration_ms": sorted(durations)[int(len(durations) * 0.99)]
        }
    
    def _analyze_domains(self) -> Dict[str, int]:
        """分析域名分布"""
        domains = {}
        
        for call in self.api_calls:
            parsed = urlparse(call.url)
            domain = parsed.netloc
            domains[domain] = domains.get(domain, 0) + 1
        
        # 按频次排序
        return dict(sorted(domains.items(), key=lambda x: x[1], reverse=True))

