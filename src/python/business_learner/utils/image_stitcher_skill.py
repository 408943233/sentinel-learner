"""
长图拼接模块 - 使用 image-stitch skill
"""

import os
import subprocess
from pathlib import Path
from typing import List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class StitchResult:
    """拼接结果"""
    success: bool
    output_path: Optional[str]
    error_message: str = ""
    error_status: str = ""  # 错误状态码: NO_OVERLAP_DETECTED, INSUFFICIENT_OVERLAP, LOW_SIMILARITY


class ImageStitcherSkill:
    """图像拼接器 - 调用 image-stitch skill"""
    
    def __init__(self, skill_path: Optional[str] = None):
        """
        初始化拼接器
        
        Args:
            skill_path: image-stitch skill 脚本路径，默认从环境变量 IMAGE_STITCH_SKILL_PATH 读取
        """
        # skill 路径（优先使用传入参数，其次环境变量，最后从settings读取）
        from ..config.settings import IMAGE_STITCH_SKILL_PATH
        if skill_path:
            self.skill_path = Path(skill_path)
        else:
            self.skill_path = Path(os.environ.get("IMAGE_STITCH_SKILL_PATH", IMAGE_STITCH_SKILL_PATH))
    
    def stitch_vertical(self, image_paths: List[str], 
                       output_path: Optional[str] = None) -> StitchResult:
        """
        垂直拼接多张图片
        
        Args:
            image_paths: 图片路径列表（按从上到下顺序）
            output_path: 输出路径（可选）
            
        Returns:
            拼接结果
        """
        if len(image_paths) < 2:
            return StitchResult(
                success=False,
                output_path=None,
                error_message="至少需要2张图片"
            )
        
        # 确保所有图片存在
        for path in image_paths:
            if not Path(path).exists():
                return StitchResult(
                    success=False,
                    output_path=None,
                    error_message=f"图片不存在: {path}"
                )
        
        # 创建临时目录存放图片
        import tempfile
        import shutil
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # 复制图片到临时目录（转换为png并按顺序命名）
            for i, img_path in enumerate(image_paths):
                src = Path(img_path)
                dst = temp_path / f"{i:04d}.png"
                # 读取并转换为png
                import cv2
                img = cv2.imread(str(src))
                if img is not None:
                    cv2.imwrite(str(dst), img)
            
            # 调用 image-stitch skill
            try:
                cmd = ["python3", str(self.skill_path), str(temp_path)]
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                
                # 解析 skill 的 JSON 输出
                try:
                    # 从 stdout 中提取最后一行 JSON
                    lines = result.stdout.strip().split('\n')
                    json_output = None
                    for line in reversed(lines):
                        line = line.strip()
                        if line.startswith('{') and line.endswith('}'):
                            try:
                                json_output = json.loads(line)
                                break
                            except:
                                continue
                    
                    if json_output and json_output.get('success'):
                        # skill 输出到 temp_path/stitched/result_stitched.png
                        stitched_dir = temp_path / "stitched"
                        skill_output = stitched_dir / "result_stitched.png"
                        
                        if skill_output.exists():
                            # 如果指定了输出路径，复制到目标位置
                            if output_path:
                                output_file = Path(output_path)
                                output_file.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(skill_output, output_file)
                                return StitchResult(
                                    success=True,
                                    output_path=str(output_file)
                                )
                            else:
                                return StitchResult(
                                    success=True,
                                    output_path=str(skill_output)
                                )
                        else:
                            return StitchResult(
                                success=False,
                                output_path=None,
                                error_message="Skill 未生成输出文件"
                            )
                    else:
                        # 拼接失败，提取错误信息
                        error_msg = json_output.get('error', '未知错误') if json_output else result.stderr
                        error_status = json_output.get('status', 'UNKNOWN') if json_output else 'UNKNOWN'
                        return StitchResult(
                            success=False,
                            output_path=None,
                            error_message=error_msg,
                            error_status=error_status
                        )
                except Exception as e:
                    return StitchResult(
                        success=False,
                        output_path=None,
                        error_message=f"解析 Skill 输出失败: {str(e)}"
                    )
                    
            except subprocess.TimeoutExpired:
                return StitchResult(
                    success=False,
                    output_path=None,
                    error_message="Skill 执行超时"
                )
            except Exception as e:
                return StitchResult(
                    success=False,
                    output_path=None,
                    error_message=f"执行错误: {str(e)}"
                )
    
    def create_page_long_screenshot(self, image_paths: List[str], 
                                    output_path: str) -> StitchResult:
        """
        创建页面长截图
        
        Args:
            image_paths: 图片路径列表
            output_path: 输出路径
            
        Returns:
            拼接结果
        """
        return self.stitch_vertical(image_paths, output_path)

