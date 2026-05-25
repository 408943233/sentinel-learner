"""
Prototype Builder 核心
整合多源重建策略和降级机制
"""

import time
from typing import Optional, List, Dict, Any
from pathlib import Path

from ..core.build_result import BuildResult, DataSource, BuildQuality
from ..evaluators.visual_evaluator import VisualEvaluator
from ..reconstructors.dom_reconstructor import DOMReconstructor
from ..reconstructors.resource_reconstructor import ResourceReconstructor


class PrototypeBuilder:
    """
    原型构建器
    
    重建策略（按优先级）：
    1. DOM 快照重建（最精确，预期 90-98%）
    2. 资源文件重建（次选，预期 80-90%）
    3. 视频关键帧重建（备选，预期 60-75%）
    4. 失败返回
    
    降级策略：
    - 如果当前策略质量 < 85%，自动降级到下一策略
    - 如果所有策略都失败，返回失败结果
    """
    
    def __init__(self, target_score: float = 0.95):
        """
        初始化构建器
        
        Args:
            target_score: 目标质量分数（默认 0.95）
        """
        self.target_score = target_score
        self.min_acceptable_score = 0.85  # 降级阈值
        
        # 初始化组件
        self.dom_reconstructor = DOMReconstructor()
        self.resource_reconstructor = ResourceReconstructor()
        self.evaluator = VisualEvaluator()
        
        # 重建策略链
        self.reconstruction_chain = [
            (DataSource.DOM_SNAPSHOT, self._try_dom_reconstruction),
            (DataSource.RESOURCE_FILES, self._try_resource_reconstruction),
            # (DataSource.VIDEO_KEYFRAME, self._try_video_reconstruction),  # 暂不实现
        ]
    
    def build(self, 
              task_path: str, 
              output_dir: str,
              original_screenshot: Optional[str] = None) -> BuildResult:
        """
        构建原型
        
        Args:
            task_path: task 目录路径
            output_dir: 输出目录
            original_screenshot: 原始页面截图路径（用于质量评估）
            
        Returns:
            构建结果
        """
        task_path = Path(task_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        task_id = task_path.name
        
        print(f"[PrototypeBuilder] 开始构建原型: {task_id}")
        print(f"  目标分数: {self.target_score}")
        
        # 尝试每种重建策略
        last_result = None
        
        for source_type, reconstruct_func in self.reconstruction_chain:
            print(f"\n  尝试策略: {source_type.value}")
            
            # 执行重建
            result = reconstruct_func(task_path, output_dir)
            last_result = result
            
            if not result.is_success():
                print(f"    ❌ 重建失败: {result.error_message}")
                continue
            
            print(f"    ✅ 重建成功: {result.output_path}")
            
            # 如果有原始截图，进行质量评估
            if original_screenshot and Path(original_screenshot).exists():
                print(f"    进行质量评估...")
                quality = self.evaluator.evaluate(
                    Path(original_screenshot),
                    result.output_path
                )
                result.quality = quality
                
                print(f"    质量评分:")
                print(f"      - SSIM: {quality.ssim_score:.3f}")
                print(f"      - 布局: {quality.layout_score:.3f}")
                print(f"      - 元素: {quality.element_score:.3f}")
                print(f"      - 样式: {quality.style_score:.3f}")
                print(f"      - 综合: {quality.overall_score:.3f}")
                print(f"      - 等级: {quality.evaluate_quality().value}")
                
                # 检查是否达到目标
                if result.meets_target(self.target_score):
                    print(f"    ✅ 达到目标分数！")
                    return result
                
                # 检查是否可接受（不降级）
                if quality.overall_score >= self.min_acceptable_score:
                    print(f"    ⚠️ 未达到目标，但可接受（≥{self.min_acceptable_score}）")
                    return result
                
                # 需要降级
                print(f"    ⬇️ 质量不足，降级到下一策略")
                result.downgrade_from = source_type
                result.downgrade_reason = f"质量分数 {quality.overall_score:.3f} < 阈值 {self.min_acceptable_score}"
            else:
                # 没有原始截图，无法评估，假设成功
                print(f"    ⚠️ 无原始截图，跳过质量评估")
                return result
        
        # 所有策略都失败或质量不足
        if last_result:
            print(f"\n  ❌ 所有策略均未能达到目标")
            return last_result
        
        # 完全失败
        return BuildResult(
            task_id=task_id,
            source=DataSource.FAILED,
            error_message="所有重建策略均失败"
        )
    
    def _try_dom_reconstruction(self, 
                               task_path: Path, 
                               output_dir: Path) -> BuildResult:
        """尝试 DOM 快照重建"""
        return self.dom_reconstructor.reconstruct(
            str(task_path),
            str(output_dir),
            self.target_score
        )
    
    def _try_resource_reconstruction(self, 
                                    task_path: Path, 
                                    output_dir: Path) -> BuildResult:
        """尝试资源文件重建"""
        return self.resource_reconstructor.reconstruct(
            str(task_path),
            str(output_dir),
            self.target_score
        )
    
    def batch_build(self,
                   task_paths: List[str],
                   output_base_dir: str,
                   original_screenshots: Optional[Dict[str, str]] = None) -> Dict[str, BuildResult]:
        """
        批量构建原型
        
        Args:
            task_paths: task 目录路径列表
            output_base_dir: 基础输出目录
            original_screenshots: task_id 到截图路径的映射
            
        Returns:
            task_id 到构建结果的映射
        """
        results = {}
        output_base = Path(output_base_dir)
        
        for i, task_path in enumerate(task_paths):
            task_path_obj = Path(task_path)
            task_id = task_path_obj.name
            
            print(f"\n{'='*60}")
            print(f"批量构建 [{i+1}/{len(task_paths)}]: {task_id}")
            print(f"{'='*60}")
            
            # 每个 task 单独的输出目录
            task_output_dir = output_base / task_id
            
            # 获取对应的原始截图
            screenshot = None
            if original_screenshots:
                screenshot = original_screenshots.get(task_id)
            
            # 构建
            result = self.build(task_path, str(task_output_dir), screenshot)
            results[task_id] = result
            
            # 统计
            success_count = sum(1 for r in results.values() if r.is_success())
            target_met_count = sum(1 for r in results.values() if r.meets_target(self.target_score))
            
            print(f"\n  进度: {success_count}/{len(results)} 成功, {target_met_count}/{len(results)} 达到目标")
        
        # 最终统计
        print(f"\n{'='*60}")
        print(f"批量构建完成")
        print(f"{'='*60}")
        print(f"  总数: {len(results)}")
        print(f"  成功: {sum(1 for r in results.values() if r.is_success())}")
        print(f"  达到目标 (≥{self.target_score}): {sum(1 for r in results.values() if r.meets_target(self.target_score))}")
        print(f"  降级: {sum(1 for r in results.values() if r.downgrade_from)}")
        print(f"  失败: {sum(1 for r in results.values() if not r.is_success())}")
        
        return results
    
    def get_build_report(self, results: Dict[str, BuildResult]) -> Dict[str, Any]:
        """
        生成构建报告
        
        Args:
            results: 构建结果字典
            
        Returns:
            报告字典
        """
        total = len(results)
        successful = [r for r in results.values() if r.is_success()]
        failed = [r for r in results.values() if not r.is_success()]
        target_met = [r for r in results.values() if r.meets_target(self.target_score)]
        downgraded = [r for r in results.values() if r.downgrade_from]
        
        # 质量统计
        quality_scores = [r.quality.overall_score for r in successful if r.quality.overall_score > 0]
        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0
        
        # 数据源统计
        source_counts = {}
        for r in successful:
            source = r.source.value
            source_counts[source] = source_counts.get(source, 0) + 1
        
        return {
            'summary': {
                'total': total,
                'successful': len(successful),
                'failed': len(failed),
                'target_met': len(target_met),
                'target_rate': len(target_met) / total if total > 0 else 0,
                'downgraded': len(downgraded),
                'average_quality': avg_quality
            },
            'by_source': source_counts,
            'quality_distribution': {
                'excellent': len([r for r in successful if r.quality.evaluate_quality() == BuildQuality.EXCELLENT]),
                'good': len([r for r in successful if r.quality.evaluate_quality() == BuildQuality.GOOD]),
                'acceptable': len([r for r in successful if r.quality.evaluate_quality() == BuildQuality.ACCEPTABLE]),
                'poor': len([r for r in successful if r.quality.evaluate_quality() == BuildQuality.POOR])
            },
            'failed_tasks': [
                {'task_id': r.task_id, 'error': r.error_message}
                for r in failed
            ],
            'downgraded_tasks': [
                {
                    'task_id': r.task_id,
                    'from': r.downgrade_from.value if r.downgrade_from else None,
                    'reason': r.downgrade_reason
                }
                for r in downgraded
            ]
        }
