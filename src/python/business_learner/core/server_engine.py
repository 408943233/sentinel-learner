"""
服务器版业务学习引擎
支持完整的元数据管理和多Task知识融合
"""

import json
import time
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import asdict
from datetime import datetime

from ..utils.models import TaskUnderstanding, PageUnderstanding, BusinessProcess
from ..utils.task_metadata import (
    TaskMetadataManager, TaskMetadata, TaskStatus
)
from ..extractors.enhanced_video_analyzer_fixed import EnhancedVideoAnalyzerFixed
from ..extractors.api_extractor import APIExtractor
from ..extractors.dom_extractor import DOMExtractor
from ..fusion.fusion_engine import FusionEngine
from ..llm.business_understander import BusinessUnderstander
from ..storage.unified_memory_adapter import UnifiedMemoryAdapter


class ServerBusinessLearningEngine:
    """服务器版业务学习引擎"""
    
    def __init__(self, task_path: str, mode: str = "local", 
                 server_memory_path: Optional[str] = None):
        """
        初始化引擎
        
        Args:
            task_path: task数据目录路径
            mode: 运行模式 ('local' 或 'server')
            server_memory_path: 服务器memory路径（server模式）
        """
        self.task_path = Path(task_path)
        self.mode = mode
        
        # 初始化元数据管理器
        self.metadata_manager = TaskMetadataManager(str(self.task_path))
        
        # 数据路径
        self.video_path = self.task_path / "video" / "raw_record.mp4"
        self.manifest_path = self.task_path / "training_manifest.jsonl"
        self.api_path = self.task_path / "network" / "api_responses.json"
        self.dom_dir = self.task_path / "dom"
        
        # 输出路径
        self.output_dir = self.task_path / "analysis"
        self.output_dir.mkdir(exist_ok=True)
        
        # 初始化各模块
        self.video_analyzer = None
        self.api_extractor = None
        self.fusion_engine = FusionEngine()
        self.understander = BusinessUnderstander()
        
        # 初始化存储适配器
        self.memory_adapter = UnifiedMemoryAdapter(
            mode=mode,
            server_memory_path=server_memory_path
        )
        
        # 结果
        self.task_result: Optional[TaskUnderstanding] = None
        self.metadata: Optional[TaskMetadata] = None
    
    def run(self) -> TaskUnderstanding:
        """
        运行完整学习流程
        
        Returns:
            任务理解结果
        """
        start_time = time.time()
        
        # 加载元数据
        self.metadata = self.metadata_manager.load_metadata()
        if not self.metadata:
            raise ValueError(f"无法加载Task元数据: {self.task_path}")
        
        print("\n" + "="*70)
        print(f" Business Learning Engine (Server Mode: {self.mode})")
        print("="*70)
        print(f"\nTask: {self.metadata.task_name}")
        print(f"Target System: {self.metadata.target_system.name}")
        print(f"Recorded By: {self.metadata.recorder.user_id}")
        print(f"Recorded At: {self.metadata.recorder.recorded_at}")
        
        # 更新处理状态
        self.metadata_manager.update_processing_status(TaskStatus.PROCESSING)
        
        try:
            # 1. 提取API实体
            print("\n[1/5] 提取API业务实体...")
            api_entities = self._extract_api_entities()
            
            # 2. 分析视频
            print("\n[2/5] 分析视频关键帧...")
            keyframes = self._analyze_video()
            
            # 3. 解析DOM
            print("\n[3/5] 解析DOM结构...")
            dom_results = self._parse_dom_snapshots()
            
            # 4. 融合数据
            print("\n[4/5] 融合多源数据...")
            pages = self._fuse_data(keyframes, api_entities, dom_results)
            
            # 5. 提取流程
            print("\n[5/5] 提取业务流程...")
            processes = self._extract_processes()
            
            # 6. 生成理解
            print("\n[6/5] 生成业务理解...")
            task = self._generate_understanding(pages, processes, api_entities)
            
            # 7. 保存结果
            self._save_results(task)
            
            # 8. 存储到知识图谱
            self._store_to_memory(task)
            
            # 更新成功状态
            duration = time.time() - start_time
            self.metadata_manager.update_processing_status(
                TaskStatus.COMPLETED,
                duration=duration
            )
            
            print("\n" + "="*70)
            print(" 学习完成!")
            print(f" 处理耗时: {duration:.2f}秒")
            print("="*70)
            
            self.task_result = task
            return task
            
        except Exception as e:
            # 更新失败状态
            self.metadata_manager.update_processing_status(
                TaskStatus.FAILED,
                error_message=str(e)
            )
            raise
    
    def _extract_api_entities(self) -> List:
        """提取API实体"""
        if not self.api_path.exists():
            print("  [跳过] API响应文件不存在")
            return []
        
        self.api_extractor = APIExtractor(str(self.api_path))
        entities = self.api_extractor.extract_entities()
        
        summary = self.api_extractor.get_entity_summary(entities)
        print(f"  提取 {len(entities)} 个实体:")
        for et, info in summary.items():
            print(f"    - {et}: {info['count']} 个")
        
        return entities
    
    def _analyze_video(self) -> List:
        """分析视频"""
        if not self.video_path.exists():
            print("  [跳过] 视频文件不存在")
            return []
        
        keyframes_dir = self.output_dir / "keyframes"
        
        self.video_analyzer = EnhancedVideoAnalyzerFixed(
            str(self.video_path),
            str(self.manifest_path)
        )
        
        result = self.video_analyzer.analyze(
            use_llm=False,
            create_long_screenshots=True
        )
        keyframes = result.get('keyframes', [])
        
        print(f"  提取 {len(keyframes)} 个关键帧")
        return keyframes
    
    def _parse_dom_snapshots(self) -> Dict:
        """解析DOM快照"""
        results = {}
        
        if not self.dom_dir.exists():
            print("  [跳过] DOM目录不存在")
            return results
        
        snapshot_files = list(self.dom_dir.glob("snapshot_*.json"))
        
        for snapshot_file in snapshot_files:
            extractor = DOMExtractor(str(snapshot_file))
            page_info = extractor.extract_page_info()
            elements = extractor.extract_elements()
            interactive = extractor.extract_interactive_elements()
            
            results[snapshot_file.stem] = {
                "page_info": page_info,
                "elements": elements,
                "interactive": interactive
            }
        
        print(f"  解析 {len(results)} 个DOM快照")
        return results
    
    def _fuse_data(self, keyframes, api_entities, dom_results) -> List[PageUnderstanding]:
        """融合数据"""
        pages = []
        
        for snapshot_name, dom_data in dom_results.items():
            page_info = dom_data.get("page_info")
            if not page_info:
                continue
            
            related_entities = [
                e for e in api_entities
                if self._is_entity_related(e, page_info)
            ]
            
            related_keyframes = [
                k for k in keyframes
                if self._is_keyframe_related(k, page_info)
            ]
            
            visual_elements = self.video_analyzer.analyze_visual_elements(related_keyframes) if self.video_analyzer else []
            
            page_understanding = self.fusion_engine.fuse_page_data(
                page_info=page_info,
                visual_elements=visual_elements,
                api_entities=related_entities,
                dom_elements=dom_data.get("interactive", [])
            )
            
            understanding = self.understander.understand_page(page_understanding)
            page_understanding.business_summary = understanding.get("purpose", "")
            page_understanding.functionality = understanding.get("key_functions", [])
            
            pages.append(page_understanding)
        
        print(f"  融合 {len(pages)} 个页面")
        return pages
    
    def _is_entity_related(self, entity, page_info) -> bool:
        """判断实体是否与页面相关"""
        type_mapping = {
            'recruitment': 'recruitment',
            'announcement': 'announcement',
            'product': 'product'
        }
        entity_page_type = type_mapping.get(entity.entity_type)
        return entity_page_type == page_info.page_type if entity_page_type else False
    
    def _is_keyframe_related(self, keyframe, page_info) -> bool:
        """判断关键帧是否与页面相关"""
        return True
    
    def _extract_processes(self) -> List[BusinessProcess]:
        """提取业务流程"""
        processes = []
        
        if not self.manifest_path.exists():
            return processes
        
        from ..utils.models import UserAction
        
        events = []
        with open(self.manifest_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    events.append(event)
                except:
                    continue

        from ..extractors.manifest_analyzer import ManifestAnalyzer
        events = ManifestAnalyzer._normalize_event_format(events)

        current_process = None
        
        for event in events:
            action = event.get('event_details', {}).get('action')
            url = event.get('window_context', {}).get('url', '')
            timestamp = event.get('timestamp', 0)
            semantic = event.get('event_details', {}).get('semantic_label', '')
            
            if action == 'page-load':
                if current_process is None:
                    current_process = BusinessProcess(
                        name=f"流程_{len(processes)+1}",
                        description="用户操作流程",
                        start_page=url
                    )
                else:
                    current_process.end_page = url
                    
            elif action in ['click', 'scroll'] and current_process:
                step = UserAction(
                    timestamp=timestamp,
                    action_type=action,
                    target=semantic,
                    semantic_label=semantic
                )
                current_process.steps.append(step)
        
        if current_process and current_process.steps:
            processes.append(current_process)
        
        print(f"  提取 {len(processes)} 个业务流程")
        return processes
    
    def _generate_understanding(self, pages, processes, entities) -> TaskUnderstanding:
        """生成业务理解"""
        business_system = self.metadata.target_system.name
        business_domain = self.metadata.target_system.domain
        
        task = TaskUnderstanding(
            task_id=self.metadata.task_id,
            business_system=business_system,
            business_domain=business_domain,
            pages=pages,
            processes=processes,
            entities=entities
        )
        
        task.key_findings = self.understander.identify_key_findings(task)
        task.summary = self.understander.generate_task_summary(task)
        
        return task
    
    def _save_results(self, task: TaskUnderstanding):
        """保存结果"""
        result_file = self.output_dir / "business_understanding.json"
        
        result_dict = {
            "task_id": task.task_id,
            "business_system": task.business_system,
            "business_domain": task.business_domain,
            "created_at": task.created_at,
            "metadata": {
                "recorded_by": self.metadata.recorder.user_id,
                "recorded_at": self.metadata.recorder.recorded_at,
                "target_system": self.metadata.target_system.name
            },
            "pages": [
                {
                    "url": p.page_info.url,
                    "title": p.page_info.title,
                    "type": p.page_info.page_type,
                    "confidence": p.overall_confidence.value,
                    "functionality": p.functionality,
                    "entities_count": len(p.api_entities)
                }
                for p in task.pages
            ],
            "processes": [
                {
                    "name": p.name,
                    "steps": len(p.steps),
                    "start": p.start_page,
                    "end": p.end_page
                }
                for p in task.processes
            ],
            "key_findings": task.key_findings,
            "summary": task.summary
        }
        
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result_dict, f, ensure_ascii=False, indent=2)
        
        report_file = self.output_dir / "business_report.md"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(task.summary)
        
        print(f"\n  结果已保存:")
        print(f"    - {result_file}")
        print(f"    - {report_file}")
    
    def _store_to_memory(self, task: TaskUnderstanding):
        """存储到知识图谱"""
        print("\n  存储到知识图谱...")
        
        try:
            self.memory_adapter.store_task_knowledge(
                task_result=task,
                metadata_manager=self.metadata_manager
            )
            print("  存储完成")
            
        except Exception as e:
            print(f"  [警告] 存储失败: {e}")
    
    def get_system_summary(self) -> Dict:
        """获取目标系统的知识摘要"""
        if not self.metadata:
            return {}
        
        return self.memory_adapter.get_system_knowledge_summary(
            self.metadata.target_system.name
        )

