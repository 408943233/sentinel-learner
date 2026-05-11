"""
最终版增强学习引擎
整合所有功能：
- 全数据源分析（P0/P1/P2）
- 冲突检测与解决
- 时间对齐
- LLM深度理解
"""

import json
import time
from pathlib import Path
from typing import List, Dict, Optional, Any
from dataclasses import asdict

from ..extractors.enhanced_video_analyzer_fixed import EnhancedVideoAnalyzerFixed
from ..extractors.api_extractor import APIExtractor
from ..extractors.api_schema_extractor import APISchemaExtractor
from ..extractors.dom_extractor import DOMExtractor
from ..extractors.dom_parser import DOMParser
from ..extractors.manifest_analyzer import ManifestAnalyzer
from ..extractors.api_traffic_analyzer import APITrafficAnalyzer
from ..extractors.resources_analyzer import ResourcesAnalyzer
from ..extractors.logs_analyzer import LogsAnalyzer
from ..extractors.page_structure_extractor import PageStructureExtractor

from ..fusion.visual_text_fusion import VisualTextFusionEngine, VisualAnalysisResult, TextAnalysisResult
from ..fusion.conflict_resolver import ConflictResolver
from ..fusion.temporal_aligner import TemporalAligner

from ..llm.llm_integration import LLMIntegrationModule
from ..llm.business_understander import BusinessUnderstander

from ..storage.unified_memory_adapter import UnifiedMemoryAdapter

from ..utils.models import (
    TaskUnderstanding, PageUnderstanding, BusinessProcess,
    APIEntity, PageInfo
)
from ..utils.task_metadata import TaskMetadataManager, TaskStatus, TaskMetadata


class FinalBusinessLearningEngine:
    """最终版业务学习引擎"""
    
    def __init__(self, 
                 task_path: str,
                 mode: str = 'local',
                 server_memory_path: Optional[str] = None,
                 llm_api_key: Optional[str] = None):
        """
        初始化引擎
        
        Args:
            task_path: Task目录路径
            mode: 运行模式 ('local' 或 'server')
            server_memory_path: 服务器memory路径
            llm_api_key: LLM API密钥
        """
        self.task_path = Path(task_path)
        self.mode = mode
        self.llm_api_key = llm_api_key
        
        # 初始化元数据管理器
        self.metadata_manager = TaskMetadataManager(str(self.task_path))
        
        # 数据路径
        self.video_path = self.task_path / "video" / "raw_record.mp4"
        self.manifest_path = self.task_path / "training_manifest.jsonl"
        self.api_path = self.task_path / "network" / "api_responses.json"
        self.api_traffic_path = self.task_path / "network" / "api_traffic.jsonl"
        self.resources_dir = self.task_path / "network" / "resources"
        self.logs_dir = self.task_path / "logs"
        self.dom_dir = self.task_path / "dom"
        self.page_structure_path = self.task_path / "page_structure.json"
        self.rrweb_events_path = self.task_path / "dom" / "rrweb_events.json"
        self.browser_state_path = self.task_path / "sandbox" / "browser_state.json"
        self.lineage_path = self.task_path / "sandbox" / "lineage.json"
        
        # 输出路径
        self.output_dir = self.task_path / "analysis"
        self.output_dir.mkdir(exist_ok=True)
        
        # 初始化各模块
        self.video_analyzer: Optional[EnhancedVideoAnalyzerFixed] = None
        self.api_extractor: Optional[APIExtractor] = None
        self.dom_extractor: Optional[DOMExtractor] = None
        self.manifest_analyzer: Optional[ManifestAnalyzer] = None
        self.api_traffic_analyzer: Optional[APITrafficAnalyzer] = None
        self.resources_analyzer: Optional[ResourcesAnalyzer] = None
        self.logs_analyzer: Optional[LogsAnalyzer] = None
        
        self.fusion_engine = VisualTextFusionEngine(visual_weight=0.6, text_weight=0.4)
        self.conflict_resolver = ConflictResolver()
        self.temporal_aligner = TemporalAligner(tolerance_ms=500)
        self.understander = BusinessUnderstander()
        self.llm_module = LLMIntegrationModule(api_key=llm_api_key)
        
        # 存储适配器
        self.memory_adapter = UnifiedMemoryAdapter(
            mode=mode,
            server_memory_path=server_memory_path
        )
        
        # 结果
        self.task_result: Optional[TaskUnderstanding] = None
        self.metadata: Optional[TaskMetadata] = None
        
        # 中间结果
        self.all_analysis_results: Dict[str, Any] = {}
    
    def run(self, 
            use_llm_vision: bool = False,
            create_long_screenshots: bool = True) -> TaskUnderstanding:
        """
        运行完整学习流程（最终版）
        
        Args:
            use_llm_vision: 是否使用LLM视觉识别
            create_long_screenshots: 是否创建长截图
            
        Returns:
            任务理解结果
        """
        start_time = time.time()
        
        print("=" * 60)
        print("🚀 最终版业务学习引擎启动")
        print("=" * 60)
        
        # 加载元数据
        self.metadata = self.metadata_manager.load_or_create()
        print(f"\n📋 任务信息:")
        print(f"   Task ID: {self.metadata.task_id}")
        print(f"   Target System: {self.metadata.target_system.name}")
        print(f"   Recorded By: {self.metadata.recorder.user_id}")
        
        # 更新处理状态
        self.metadata_manager.update_processing_status(TaskStatus.PROCESSING)
        
        try:
            # ========== P0 核心数据分析 ==========
            print("\n" + "=" * 60)
            print("📊 P0 核心数据分析")
            print("=" * 60)
            
            # 1. Video分析
            print("\n[1/9] 🎥 Video分析（关键帧+长图）...")
            video_result = self._analyze_video(
                use_llm=use_llm_vision,
                create_long_screenshots=create_long_screenshots
            )
            self.all_analysis_results['video'] = video_result
            
            # 2. Manifest深度分析
            print("\n[2/9] 📜 Manifest深度分析（用户意图+流程）...")
            manifest_result = self._analyze_manifest()
            self.all_analysis_results['manifest'] = manifest_result
            
            # 3. API业务实体提取
            print("\n[3/9] 🔌 API业务实体提取...")
            api_entities = self._extract_api_entities()
            self.all_analysis_results['api_entities'] = api_entities
            
            # ========== P1 辅助数据分析 ==========
            print("\n" + "=" * 60)
            print("📊 P1 辅助数据分析")
            print("=" * 60)

            # 4. Page Structure 分析
            print("\n[4/9] 📄 Page Structure 分析...")
            page_structure_result = self._analyze_page_structure()
            self.all_analysis_results['page_structure'] = page_structure_result

            # 5. rrweb events 分析
            print("\n[5/9] 🎬 rrweb events 分析...")
            rrweb_result = self._analyze_rrweb_events()
            self.all_analysis_results['rrweb_events'] = rrweb_result

            # 6. Browser State 分析
            print("\n[6/9] 🍪 Browser State 分析...")
            browser_state_result = self._analyze_browser_state()
            self.all_analysis_results['browser_state'] = browser_state_result

            # 7. DOM结构分析
            print("\n[7/9] 🏗️ DOM结构分析...")
            dom_result = self._analyze_dom()
            self.all_analysis_results['dom'] = dom_result
            
            # 8. API流量分析
            print("\n[8/12] 🌊 API流量分析（数据流向）...")
            api_traffic_result = self._analyze_api_traffic()
            self.all_analysis_results['api_traffic'] = api_traffic_result

            # ========== P2 补充数据分析 ==========
            print("\n" + "=" * 60)
            print("📊 P2 补充数据分析")
            print("=" * 60)

            # 9. 静态资源分析
            print("\n[9/12] 📦 静态资源分析...")
            resources_result = self._analyze_resources()
            self.all_analysis_results['resources'] = resources_result

            # 10. 日志错误分析
            print("\n[10/12] 🐛 日志错误分析...")
            logs_result = self._analyze_logs()
            self.all_analysis_results['logs'] = logs_result

            # 11. Lineage 血缘分析
            print("\n[11/12] 🔗 Lineage 血缘分析...")
            lineage_result = self._analyze_lineage()
            self.all_analysis_results['lineage'] = lineage_result

            # ========== 融合与对齐 ==========
            print("\n" + "=" * 60)
            print("🔄 数据融合与对齐")
            print("=" * 60)

            # 12. 时间对齐
            print("\n[12/13] ⏱️ 时间对齐...")
            alignment_result = self._perform_temporal_alignment()
            self.all_analysis_results['alignment'] = alignment_result

            # 13. 冲突检测与解决
            print("\n[13/13] ⚖️ 冲突检测与解决...")
            conflict_result = self._resolve_conflicts()
            self.all_analysis_results['conflict_resolution'] = conflict_result
            
            # ========== 生成最终理解 ==========
            print("\n" + "=" * 60)
            print("🧠 生成业务理解")
            print("=" * 60)
            
            # 14. LLM深度理解（如果启用）
            if use_llm_vision and self.llm_api_key:
                print("\n[14] 🤖 LLM深度理解...")
                self._perform_llm_understanding()
            
            # 15. 生成最终任务理解
            print("\n[15] 📝 生成最终任务理解...")
            task = self._generate_final_understanding()
            
            # 12. 保存结果
            print("\n💾 保存结果...")
            self._save_comprehensive_results(task)
            
            # 13. 存储到知识图谱
            print("\n🗄️ 存储到知识图谱...")
            self._store_to_memory(task)
            
            # 更新成功状态
            duration = time.time() - start_time
            self.metadata_manager.update_processing_status(
                TaskStatus.COMPLETED,
                duration=duration
            )
            
            print("\n" + "=" * 60)
            print(f"✅ 分析完成！耗时: {duration:.1f}秒")
            print("=" * 60)
            
            return task
            
        except Exception as e:
            self.metadata_manager.update_processing_status(
                TaskStatus.FAILED,
                error_message=str(e)
            )
            print(f"\n❌ 分析失败: {e}")
            raise
    
    def _analyze_video(self, use_llm: bool = False,
                      create_long_screenshots: bool = True) -> Dict:
        """分析视频数据"""
        if not self.video_path.exists():
            print("  ⚠️ 视频文件不存在")
            return {}

        self.video_analyzer = EnhancedVideoAnalyzerFixed(
            str(self.video_path),
            str(self.manifest_path),
            api_key=self.llm_api_key
        )

        return self.video_analyzer.extract_and_analyze(
            output_dir=str(self.output_dir / "enhanced_final"),
            use_llm=use_llm and self.llm_api_key is not None,
            create_long_screenshots=create_long_screenshots
        )
    
    def _analyze_manifest(self) -> Dict:
        """深度分析manifest"""
        if not self.manifest_path.exists():
            print("  ⚠️ Manifest文件不存在")
            return {}
        
        self.manifest_analyzer = ManifestAnalyzer(str(self.manifest_path))
        result = self.manifest_analyzer.analyze()
        
        return {
            'total_events': result.total_events,
            'user_intents': [asdict(i) for i in result.user_intents],
            'business_flows': [self._flow_to_dict(f) for f in result.business_flows],
            'page_visits': result.page_visits,
            'interaction_patterns': result.interaction_patterns,
            'error_events': result.error_events
        }
    
    def _flow_to_dict(self, flow) -> Dict:
        """转换流程为字典"""
        return {
            'flow_id': flow.flow_id,
            'name': flow.name,
            'description': flow.description,
            'start_url': flow.start_url,
            'end_url': flow.end_url,
            'steps_count': len(flow.steps),
            'total_duration_ms': flow.total_duration_ms
        }
    
    def _extract_api_entities(self) -> Dict:
        """提取API业务实体和Schema"""
        if not self.api_path.exists():
            print("  ⚠️ API响应文件不存在")
            return {'entities': [], 'schemas': []}

        # 提取业务实体
        self.api_extractor = APIExtractor(str(self.api_path))
        entities = self.api_extractor.extract_entities()

        # 提取API Schema（深层解析）
        schema_extractor = APISchemaExtractor(str(self.api_path))
        schemas = schema_extractor.extract_schemas()

        # 打印统计信息
        schema_summary = schema_extractor.get_schema_summary(schemas)
        print(f"    业务实体: {len(entities)} 个")
        print(f"    API Schema: {len(schemas)} 个")
        print(f"    业务类型: {list(schema_summary['business_entities'].keys())}")

        return {
            'entities': entities,
            'schemas': schemas,
            'schema_summary': schema_summary,
            'openapi_spec': schema_extractor.export_openapi_spec(schemas)
        }
    
    def _analyze_dom(self) -> Dict:
        """分析DOM结构（包含页面结构和样式）"""
        if not self.dom_dir.exists():
            print("  ⚠️ DOM目录不存在")
            return {}

        # 查找所有snapshot文件
        snapshot_files = list(self.dom_dir.glob("snapshot_*.json"))
        if not snapshot_files:
            print("  ⚠️ 未找到DOM snapshot文件")
            return {}

        results = []
        page_structures = []
        full_snapshots = 0
        incremental_snapshots = 0

        for snapshot_file in snapshot_files:
            # 检查是否为 full snapshot (type 2)
            # 只有 full snapshot 才有完整的 DOM 树
            try:
                with open(snapshot_file, 'r', encoding='utf-8') as f:
                    snapshot_data = json.load(f)
                rrweb_event = snapshot_data.get('rrwebEvent', {})
                event_type = rrweb_event.get('type')

                # 统计 snapshot 类型
                if event_type == 2:
                    full_snapshots += 1
                elif event_type == 3:
                    incremental_snapshots += 1
                    continue  # 跳过增量 snapshot
                else:
                    continue  # 跳过其他类型
            except Exception as e:
                print(f"  ⚠️ 读取 snapshot 失败: {snapshot_file.name} - {e}")
                continue

            # 使用 DOMParser 进行完整的 DOM 分析
            parser = DOMParser(str(snapshot_file))
            snapshot = parser.parse()

            if snapshot:
                # 计算树深度
                tree_depth = self._calc_tree_depth(snapshot.root)

                # 提取布局信息
                layout_info = parser.extract_layout_info(snapshot)

                results.append({
                    'file': snapshot_file.name,
                    'page_info': {
                        'url': snapshot.url,
                        'title': snapshot.title,
                        'page_type': snapshot.page_type
                    },
                    'element_count': len(snapshot.elements_map),
                    'interactive_count': sum(1 for e in snapshot.elements_map.values() if e.is_interactive),
                    'tree_depth': tree_depth,
                    'has_structure': True,
                    'layout_info': layout_info,
                    'business_actions': layout_info.get('business_actions', [])
                })

        print(f"    Full snapshots: {full_snapshots}")
        print(f"    Incremental snapshots: {incremental_snapshots} (skipped)")
        if results:
            print(f"    Elements in first snapshot: {results[0]['element_count']}")
            print(f"    Interactive elements: {results[0]['interactive_count']}")

        return {
            'total_snapshots': len(results),
            'full_snapshots': full_snapshots,
            'incremental_snapshots': incremental_snapshots,
            'snapshots': results,
            'page_structures': page_structures
        }

    def _calc_tree_depth(self, node, depth=0) -> int:
        """计算DOM树深度"""
        if not node.children:
            return depth
        max_child_depth = 0
        for child in node.children:
            child_depth = self._calc_tree_depth(child, depth + 1)
            max_child_depth = max(max_child_depth, child_depth)
        return max_child_depth
    
    def _analyze_api_traffic(self) -> Dict:
        """分析API流量"""
        if not self.api_traffic_path.exists():
            print("  ⚠️ API流量文件不存在")
            return {}
        
        self.api_traffic_analyzer = APITrafficAnalyzer(str(self.api_traffic_path))
        result = self.api_traffic_analyzer.analyze()
        
        return {
            'total_requests': result.total_requests,
            'unique_endpoints': result.unique_endpoints,
            'error_count': len(result.error_requests),
            'domain_distribution': result.domain_distribution,
            'data_flows': [asdict(f) for f in result.data_flows[:10]],
            'timing_analysis': result.timing_analysis
        }
    
    def _analyze_resources(self) -> Dict:
        """分析静态资源"""
        if not self.resources_dir.exists():
            print("  ⚠️ Resources目录不存在")
            return {}
        
        self.resources_analyzer = ResourcesAnalyzer(str(self.resources_dir))
        result = self.resources_analyzer.analyze()
        
        return {
            'total_resources': result.stats.total_count,
            'total_size_mb': result.stats.total_size / 1024 / 1024,
            'by_type': result.stats.by_type,
            'cdn_usage': result.cdn_usage,
            'optimization_suggestions': result.performance.optimization_suggestions
        }
    
    def _analyze_page_structure(self) -> Dict:
        """分析 page_structure.json"""
        if not self.page_structure_path.exists():
            print("  ⚠️ page_structure.json 不存在")
            return {}

        try:
            with open(self.page_structure_path, 'r', encoding='utf-8') as f:
                page_structure = json.load(f)

            # 提取关键信息
            components = page_structure.get('components', [])
            layout_sections = page_structure.get('layoutSections', [])
            css_rules = page_structure.get('cssRules', [])
            responsive_breakpoints = page_structure.get('responsiveBreakpoints', [])

            # 统计信息
            component_types = {}
            for comp in components:
                comp_type = comp.get('type', 'unknown')
                component_types[comp_type] = component_types.get(comp_type, 0) + 1

            print(f"    组件数量: {len(components)}")
            print(f"    布局区块: {len(layout_sections)}")
            print(f"    CSS规则: {len(css_rules)}")
            print(f"    响应式断点: {len(responsive_breakpoints)}")

            return {
                'total_components': len(components),
                'total_layout_sections': len(layout_sections),
                'total_css_rules': len(css_rules),
                'responsive_breakpoints': responsive_breakpoints,
                'component_types': component_types,
                'components_summary': [
                    {'id': c.get('id'), 'type': c.get('type'), 'name': c.get('name')}
                    for c in components[:10]  # 只返回前10个
                ]
            }
        except Exception as e:
            print(f"  ⚠️ 读取 page_structure.json 失败: {e}")
            return {}

    def _analyze_rrweb_events(self) -> Dict:
        """分析 rrweb_events.json"""
        if not self.rrweb_events_path.exists():
            print("  ⚠️ rrweb_events.json 不存在")
            return {}

        try:
            with open(self.rrweb_events_path, 'r', encoding='utf-8') as f:
                events = json.load(f)

            if not isinstance(events, list):
                print("  ⚠️ rrweb_events.json 格式不正确")
                return {}

            # 统计事件类型
            event_types = {}
            timestamps = []

            for event in events:
                event_type = event.get('type')
                event_types[event_type] = event_types.get(event_type, 0) + 1
                if 'timestamp' in event:
                    timestamps.append(event['timestamp'])

            # 事件类型映射
            type_names = {
                0: 'DomContentLoaded',
                1: 'Load',
                2: 'FullSnapshot',
                3: 'IncrementalSnapshot',
                4: 'Meta',
                5: 'Custom'
            }

            event_summary = {type_names.get(k, f'Type_{k}'): v for k, v in event_types.items()}

            # 计算时间范围
            duration = 0
            if timestamps:
                duration = max(timestamps) - min(timestamps)

            print(f"    总事件数: {len(events)}")
            print(f"    Full snapshots: {event_types.get(2, 0)}")
            print(f"    Incremental snapshots: {event_types.get(3, 0)}")
            print(f"    录制时长: {duration/1000:.1f}s")

            return {
                'total_events': len(events),
                'event_types': event_summary,
                'duration_ms': duration,
                'duration_seconds': duration / 1000 if duration else 0
            }
        except Exception as e:
            print(f"  ⚠️ 读取 rrweb_events.json 失败: {e}")
            return {}

    def _analyze_browser_state(self) -> Dict:
        """分析 browser_state.json"""
        if not self.browser_state_path.exists():
            print("  ⚠️ browser_state.json 不存在")
            return {}

        try:
            with open(self.browser_state_path, 'r', encoding='utf-8') as f:
                browser_state = json.load(f)

            cookies = browser_state.get('cookies', [])
            local_storage = browser_state.get('localStorage', {})
            session_storage = browser_state.get('sessionStorage', {})

            # 分析 cookie 域名
            cookie_domains = set()
            for cookie in cookies:
                domain = cookie.get('domain', '')
                if domain:
                    cookie_domains.add(domain)

            # 分析 localStorage keys
            local_storage_keys = list(local_storage.keys())

            print(f"    Cookies: {len(cookies)} (domains: {len(cookie_domains)})")
            print(f"    LocalStorage: {len(local_storage_keys)} keys")
            print(f"    SessionStorage: {len(session_storage)} keys")

            return {
                'cookie_count': len(cookies),
                'cookie_domains': list(cookie_domains),
                'local_storage_keys': local_storage_keys,
                'local_storage_count': len(local_storage_keys),
                'session_storage_count': len(session_storage),
                'has_auth_cookies': any('auth' in c.get('name', '').lower() or
                                        'token' in c.get('name', '').lower()
                                        for c in cookies)
            }
        except Exception as e:
            print(f"  ⚠️ 读取 browser_state.json 失败: {e}")
            return {}

    def _analyze_logs(self) -> Dict:
        """分析日志"""
        if not self.logs_dir.exists():
            print("  ⚠️ Logs目录不存在")
            return {}

        self.logs_analyzer = LogsAnalyzer(str(self.logs_dir))
        result = self.logs_analyzer.analyze()

        return {
            'console_error_count': len(result.console_errors),
            'js_error_count': len(result.js_errors),
            'stability_score': result.system_health.stability_score,
            'error_patterns': [asdict(p) for p in result.error_patterns[:5]],
            'recommendations': result.recommendations
        }

    def _analyze_lineage(self) -> Dict:
        """分析 lineage.json（页面血缘关系）"""
        if not self.lineage_path.exists():
            print("  ⚠️ lineage.json 不存在")
            return {}

        try:
            with open(self.lineage_path, 'r', encoding='utf-8') as f:
                lineage_data = json.load(f)

            # 提取页面跳转关系
            page_transitions = lineage_data.get('page_transitions', [])
            navigation_graph = lineage_data.get('navigation_graph', {})
            entry_points = lineage_data.get('entry_points', [])

            # 分析跳转路径
            transition_summary = []
            for transition in page_transitions[:20]:  # 最多分析20个跳转
                summary = {
                    'from_page': transition.get('from_page', ''),
                    'to_page': transition.get('to_page', ''),
                    'trigger': transition.get('trigger', 'unknown'),
                    'timestamp': transition.get('timestamp', 0)
                }
                transition_summary.append(summary)

            # 分析导航图节点和边
            nodes = navigation_graph.get('nodes', [])
            edges = navigation_graph.get('edges', [])

            print(f"    页面跳转: {len(page_transitions)} 次")
            print(f"    导航节点: {len(nodes)} 个")
            print(f"    导航边: {len(edges)} 条")
            print(f"    入口点: {len(entry_points)} 个")

            return {
                'page_transition_count': len(page_transitions),
                'navigation_node_count': len(nodes),
                'navigation_edge_count': len(edges),
                'entry_points': entry_points,
                'transitions': transition_summary,
                'navigation_graph': {
                    'nodes': nodes[:10],  # 限制返回数量
                    'edges': edges[:20]
                }
            }
        except Exception as e:
            print(f"  ⚠️ 读取 lineage.json 失败: {e}")
            return {}

    def _perform_temporal_alignment(self) -> Dict:
        """执行时间对齐"""
        # 准备各源事件
        video_events = []
        manifest_events = []
        api_events = []
        
        if self.video_analyzer and self.video_analyzer.keyframes:
            video_events = [
                {
                    'timestamp': int(k.timestamp * 1000),
                    'event_type': k.event_type,
                    'data': k.event_data
                }
                for k in self.video_analyzer.keyframes
            ]
        
        if self.manifest_analyzer and self.manifest_analyzer.events:
            manifest_events = self.manifest_analyzer.events
        
        if self.api_traffic_analyzer and self.api_traffic_analyzer.api_calls:
            api_events = [
                {
                    'timestamp': c.timestamp,
                    'url': c.url,
                    'method': c.method
                }
                for c in self.api_traffic_analyzer.api_calls
            ]
        
        result = self.temporal_aligner.align(
            video_events=video_events,
            manifest_events=manifest_events,
            api_events=api_events
        )
        
        return {
            'aligned_event_count': len(result.aligned_events),
            'anchor_points': result.anchor_points,
            'drift_analysis': result.drift_analysis
        }
    
    def _resolve_conflicts(self) -> Dict:
        """检测并解决冲突"""
        # 准备各源数据
        data_sources = {}
        
        # 导入DataSource
        from ..fusion.conflict_resolver import DataSource
        
        # Video数据
        if self.video_analyzer:
            data_sources[DataSource.VIDEO] = {
                'keyframes_count': len(self.video_analyzer.keyframes),
                'long_screenshots': len(self.video_analyzer.page_sessions)
            }
        
        # Manifest数据
        if self.manifest_analyzer:
            data_sources[DataSource.MANIFEST] = {
                'total_events': len(self.manifest_analyzer.events),
                'flows': len(self.all_analysis_results.get('manifest', {}).get('business_flows', []))
            }
        
        # API数据
        if self.api_extractor:
            api_data = self.all_analysis_results.get('api_entities', {})
            entities = api_data.get('entities', []) if isinstance(api_data, dict) else []
            data_sources[DataSource.API] = {
                'entities': [e.__dict__ for e in entities]
            }
        
        # DOM数据
        if self.dom_extractor:
            dom_data = self.all_analysis_results.get('dom', {})
            data_sources[DataSource.DOM] = {
                'snapshots': len(dom_data)
            }
        
        result = self.conflict_resolver.detect_and_resolve(data_sources)
        
        return {
            'total_conflicts': result.total_conflicts,
            'resolved_conflicts': result.resolved_conflicts,
            'unresolved_count': len(result.unresolved_conflicts),
            'resolution_log': result.resolution_log
        }
    
    def _perform_llm_understanding(self):
        """执行LLM深度理解"""
        # 这里可以添加对manifest流程、API实体等的LLM分析
        pass
    
    def _generate_final_understanding(self) -> TaskUnderstanding:
        """生成最终理解"""
        # 构建页面理解
        pages = self._build_pages_from_all_sources()
        
        # 构建流程理解
        processes = self._build_processes_from_manifest()
        
        # 提取业务系统信息
        business_system = self._infer_business_system()
        business_domain = self._infer_business_domain()
        
        # 修复：api_entities 是字典，需要提取其中的 entities 列表
        api_entities_data = self.all_analysis_results.get('api_entities', {})
        if isinstance(api_entities_data, dict):
            entities = api_entities_data.get('entities', [])
        else:
            entities = api_entities_data if isinstance(api_entities_data, list) else []
        
        task = TaskUnderstanding(
            task_id=self.metadata.task_id,
            business_system=business_system,
            business_domain=business_domain,
            pages=pages,
            processes=processes,
            entities=entities
        )
        
        # 生成摘要
        task.key_findings = self._generate_key_findings()
        task.summary = self._generate_summary()
        
        self.task_result = task
        return task
    
    def _build_pages_from_all_sources(self) -> List[PageUnderstanding]:
        """从所有数据源构建页面理解"""
        pages = []
        
        # 从manifest的page_visits构建
        manifest_data = self.all_analysis_results.get('manifest', {})
        for visit in manifest_data.get('page_visits', []):
            # 创建页面理解
            page_info = PageInfo(
                url=visit.get('url', ''),
                title=visit.get('title', ''),
                page_type='unknown',
                business_domain=''
            )
            page = PageUnderstanding(
                page_info=page_info,
                visual_elements=[],
                api_entities=[],
                business_summary=''
            )
            pages.append(page)
        
        return pages
    
    def _build_processes_from_manifest(self) -> List[BusinessProcess]:
        """从manifest构建流程"""
        processes = []
        
        manifest_data = self.all_analysis_results.get('manifest', {})
        for flow_data in manifest_data.get('business_flows', []):
            from ..utils.models import UserAction
            
            process = BusinessProcess(
                name=flow_data.get('name', ''),
                description=flow_data.get('description', ''),
                start_page=flow_data.get('start_url', ''),
                end_page=flow_data.get('end_url', ''),
                steps=[]  # 简化处理
            )
            processes.append(process)
        
        return processes
    
    def _infer_business_system(self) -> str:
        """推断业务系统"""
        if self.metadata and self.metadata.target_system:
            return self.metadata.target_system.name
        
        # 从URL推断
        manifest_data = self.all_analysis_results.get('manifest', {})
        if manifest_data.get('page_visits'):
            url = manifest_data['page_visits'][0].get('url', '')
            if 'chinastock' in url:
                return '中国银河证券官网'
        
        return '未知系统'
    
    def _infer_business_domain(self) -> str:
        """推断业务领域"""
        return '金融证券'
    
    def _generate_key_findings(self) -> List[str]:
        """生成关键发现"""
        findings = []
        
        # 从各分析结果中提取关键发现
        manifest_data = self.all_analysis_results.get('manifest', {})
        if manifest_data.get('business_flows'):
            findings.append(f"识别 {len(manifest_data['business_flows'])} 个业务流程")
        
        api_entities = self.all_analysis_results.get('api_entities', [])
        if api_entities:
            findings.append(f"提取 {len(api_entities)} 个业务实体")
        
        conflict_data = self.all_analysis_results.get('conflict_resolution', {})
        if conflict_data.get('total_conflicts', 0) > 0:
            findings.append(f"解决 {conflict_data['resolved_conflicts']}/{conflict_data['total_conflicts']} 个数据冲突")
        
        logs_data = self.all_analysis_results.get('logs', {})
        if logs_data.get('stability_score', 100) < 80:
            findings.append(f"系统稳定性评分: {logs_data['stability_score']:.1f}/100")
        
        return findings
    
    def _generate_summary(self) -> str:
        """生成摘要"""
        parts = [
            f"## 业务系统分析报告",
            f"",
            f"**目标系统**: {self._infer_business_system()}",
            f"**业务领域**: {self._infer_business_domain()}",
            f"",
            f"### 数据覆盖",
            f"- Video分析: {'✅' if 'video' in self.all_analysis_results else '❌'}",
            f"- Manifest分析: {'✅' if 'manifest' in self.all_analysis_results else '❌'}",
            f"- API分析: {'✅' if 'api_entities' in self.all_analysis_results else '❌'}",
            f"- DOM分析: {'✅' if 'dom' in self.all_analysis_results else '❌'}",
            f"- 流量分析: {'✅' if 'api_traffic' in self.all_analysis_results else '❌'}",
            f"- 资源分析: {'✅' if 'resources' in self.all_analysis_results else '❌'}",
            f"- 日志分析: {'✅' if 'logs' in self.all_analysis_results else '❌'}",
            f"",
            f"### 关键发现"
        ]
        
        for finding in self._generate_key_findings():
            parts.append(f"- {finding}")
        
        return "\n".join(parts)
    
    def _save_comprehensive_results(self, task: TaskUnderstanding):
        """保存完整结果（包含原型Demo）"""
        result_file = self.output_dir / "final_comprehensive_analysis.json"

        # 自定义JSON序列化函数，处理dataclass对象
        def serialize_obj(obj):
            if hasattr(obj, '__dict__'):
                return obj.__dict__
            elif hasattr(obj, 'value'):
                return obj.value
            elif isinstance(obj, (set, frozenset)):
                return list(obj)
            elif isinstance(obj, bytes):
                return obj.decode('utf-8', errors='ignore')
            return str(obj)

        # 深度转换analysis_results中的所有dataclass对象
        def deep_convert(obj):
            if isinstance(obj, dict):
                return {k: deep_convert(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [deep_convert(item) for item in obj]
            elif hasattr(obj, '__dict__'):
                # 处理dataclass对象
                result = {}
                for k, v in obj.__dict__.items():
                    # 跳过私有属性和方法
                    if not k.startswith('_'):
                        result[k] = deep_convert(v)
                return result
            elif hasattr(obj, 'value'):
                # 处理枚举类型
                return obj.value
            elif isinstance(obj, (set, frozenset)):
                return list(obj)
            else:
                return obj

        # 转换analysis_results
        converted_results = deep_convert(self.all_analysis_results)

        result_dict = {
            "task_id": task.task_id,
            "business_system": task.business_system,
            "business_domain": task.business_domain,
            "metadata": {
                "recorded_by": self.metadata.recorder.user_id,
                "recorded_at": self.metadata.recorder.recorded_at,
                "target_system": self.metadata.target_system.name
            },
            "data_coverage": {
                "video_analyzed": 'video' in self.all_analysis_results,
                "manifest_analyzed": 'manifest' in self.all_analysis_results,
                "api_analyzed": 'api_entities' in self.all_analysis_results,
                "dom_analyzed": 'dom' in self.all_analysis_results,
                "api_traffic_analyzed": 'api_traffic' in self.all_analysis_results,
                "resources_analyzed": 'resources' in self.all_analysis_results,
                "logs_analyzed": 'logs' in self.all_analysis_results,
                "lineage_analyzed": 'lineage' in self.all_analysis_results
            },
            "analysis_results": converted_results,
            "pages": [
                {
                    "url": p.page_info.url,
                    "title": p.page_info.title,
                    "type": getattr(p.page_info, 'page_type', 'unknown')
                }
                for p in task.pages
            ],
            "processes": [
                {
                    "name": p.name,
                    "description": p.description,
                    "steps": len(p.steps)
                }
                for p in task.processes
            ],
            "key_findings": task.key_findings,
            "summary": task.summary
        }

        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result_dict, f, ensure_ascii=False, indent=2, default=serialize_obj)

        print(f"  ✅ 结果已保存: {result_file}")

        # 生成原型Demo
        self._generate_prototype_demo(task)

    def _generate_prototype_demo(self, task: TaskUnderstanding):
        """生成原型Demo HTML"""
        try:
            from ..generators.prototype_generator import PrototypeGenerator

            # 查找页面结构文件
            structure_file = self.output_dir / 'page_structure.json'

            if structure_file.exists():
                generator = PrototypeGenerator(str(structure_file))
                prototype_path = generator.generate(
                    output_path=str(self.output_dir),
                    title=task.pages[0].page_info.title if task.pages else 'Prototype Demo'
                )

                if prototype_path:
                    print(f"  ✅ 原型Demo已生成: {prototype_path}")
                else:
                    print("  ⚠️ 原型Demo生成失败")
            else:
                print("  ⚠️ 未找到页面结构文件，跳过原型生成")

        except Exception as e:
            print(f"  ⚠️ 生成原型Demo时出错: {e}")

    def _store_to_memory(self, task: TaskUnderstanding):
        """存储到知识图谱"""
        try:
            self.memory_adapter.store_task_knowledge(
                task_result=task,
                metadata_manager=self.metadata_manager
            )
            print("  ✅ 已存储到知识图谱")
        except Exception as e:
            print(f"  ⚠️ 存储到知识图谱失败: {e}")

