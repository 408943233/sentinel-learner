#!/usr/bin/env python3
"""
Sentinel Learner Server
服务端API服务
"""

import os
import sys
import json
import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks, File, UploadFile, Form
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, Field
import uvicorn

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from business_learner.core.final_engine import FinalBusinessLearningEngine
from business_learner.utils.task_metadata import TaskMetadataManager
from business_learner.storage.unified_memory_adapter import UnifiedMemoryAdapter


# ============== 数据模型 ==============

class TaskSubmitRequest(BaseModel):
    """任务提交请求"""
    task_id: str = Field(..., description="任务ID")
    task_name: Optional[str] = Field(None, description="任务名称")
    description: Optional[str] = Field(None, description="任务描述")
    use_llm_vision: bool = Field(True, description="是否使用LLM视觉分析")
    create_long_screenshots: bool = Field(True, description="是否创建长截图")


class TaskStatusResponse(BaseModel):
    """任务状态响应"""
    task_id: str
    status: str  # pending, processing, completed, failed
    progress: float = Field(0.0, ge=0.0, le=100.0)
    message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    result_path: Optional[str] = None


class SystemInfoResponse(BaseModel):
    """系统信息响应"""
    version: str
    mode: str
    memory_path: str
    task_count: int
    active_tasks: int


# ============== 全局状态 ==============

class ServerState:
    """服务器状态管理"""
    def __init__(self):
        self.tasks: Dict[str, Dict] = {}
        self.active_tasks: int = 0
        self.max_concurrent = int(os.getenv('MAX_CONCURRENT_TASKS', '4'))
        self.task_storage_path = Path(os.getenv('TASK_STORAGE_PATH', '/app/data/tasks'))
        self.output_path = Path(os.getenv('OUTPUT_PATH', '/app/data/output'))
        self.memory_path = os.getenv('OPENCLAW_MEMORY_PATH', '/shared/openclaw-memory-skill')
        
    def get_task_status(self, task_id: str) -> Optional[Dict]:
        return self.tasks.get(task_id)
    
    def update_task(self, task_id: str, **kwargs):
        if task_id in self.tasks:
            self.tasks[task_id].update(kwargs)
            self.tasks[task_id]['updated_at'] = datetime.now()


server_state = ServerState()


# ============== 生命周期管理 ==============

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    print("🚀 Starting Sentinel Learner Server...")
    
    # 确保目录存在
    server_state.task_storage_path.mkdir(parents=True, exist_ok=True)
    server_state.output_path.mkdir(parents=True, exist_ok=True)
    
    # 检查Memory连接
    memory_adapter = UnifiedMemoryAdapter(
        mode="server",
        server_memory_path=server_state.memory_path
    )
    print(f"✅ Connected to OpenClaw Memory: {server_state.memory_path}")
    
    yield
    
    # 关闭时
    print("🛑 Shutting down Sentinel Learner Server...")


# ============== FastAPI应用 ==============

app = FastAPI(
    title="Sentinel Learner API",
    description="智能业务学习系统服务端API",
    version="2.0.0",
    lifespan=lifespan
)


# ============== API端点 ==============

@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0"
    }


@app.get("/api/v1/info", response_model=SystemInfoResponse)
async def get_system_info():
    """获取系统信息"""
    return SystemInfoResponse(
        version="2.0.0",
        mode="server",
        memory_path=server_state.memory_path,
        task_count=len(server_state.tasks),
        active_tasks=server_state.active_tasks
    )


@app.post("/api/v1/tasks", response_model=TaskStatusResponse)
async def submit_task(
    request: TaskSubmitRequest,
    background_tasks: BackgroundTasks
):
    """提交学习任务"""
    task_id = request.task_id
    
    # 检查任务是否已存在
    if task_id in server_state.tasks:
        raise HTTPException(status_code=409, detail=f"Task {task_id} already exists")
    
    # 检查并发限制
    if server_state.active_tasks >= server_state.max_concurrent:
        raise HTTPException(
            status_code=503, 
            detail=f"Server busy. Active tasks: {server_state.active_tasks}/{server_state.max_concurrent}"
        )
    
    # 检查任务数据是否存在
    task_path = server_state.task_storage_path / f"task_{task_id}"
    if not task_path.exists():
        raise HTTPException(
            status_code=404, 
            detail=f"Task data not found at {task_path}"
        )
    
    # 创建任务记录
    now = datetime.now()
    server_state.tasks[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "progress": 0.0,
        "message": "Task queued",
        "created_at": now,
        "updated_at": now,
        "result_path": None
    }
    
    # 后台执行
    background_tasks.add_task(
        process_task,
        task_id=task_id,
        use_llm_vision=request.use_llm_vision,
        create_long_screenshots=request.create_long_screenshots
    )
    
    return TaskStatusResponse(**server_state.tasks[task_id])


@app.post("/api/v1/tasks/upload")
async def upload_task(
    task_file: UploadFile = File(...),
    task_id: str = Form(...),
    use_llm_vision: bool = Form(True),
    background_tasks: BackgroundTasks = None
):
    """上传并处理任务"""
    # 保存上传的文件
    task_dir = server_state.task_storage_path / f"task_{task_id}"
    task_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = task_dir / task_file.filename
    with open(file_path, "wb") as f:
        content = await task_file.read()
        f.write(content)
    
    # 解压如果是压缩文件
    if task_file.filename.endswith('.zip'):
        import zipfile
        with zipfile.ZipFile(file_path, 'r') as zip_ref:
            zip_ref.extractall(task_dir)
        file_path.unlink()  # 删除zip文件
    
    # 提交任务
    request = TaskSubmitRequest(
        task_id=task_id,
        use_llm_vision=use_llm_vision
    )
    
    return await submit_task(request, background_tasks)


@app.get("/api/v1/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """获取任务状态"""
    task = server_state.get_task_status(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
    return TaskStatusResponse(**task)


@app.get("/api/v1/tasks")
async def list_tasks(
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    """列出所有任务"""
    tasks = list(server_state.tasks.values())
    
    if status:
        tasks = [t for t in tasks if t['status'] == status]
    
    total = len(tasks)
    tasks = tasks[offset:offset + limit]
    
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "tasks": tasks
    }


@app.get("/api/v1/tasks/{task_id}/result")
async def get_task_result(task_id: str):
    """获取任务结果"""
    task = server_state.get_task_status(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
    if task['status'] != 'completed':
        raise HTTPException(
            status_code=400, 
            detail=f"Task not completed. Current status: {task['status']}"
        )
    
    result_path = Path(task['result_path'])
    if not result_path.exists():
        raise HTTPException(status_code=404, detail="Result file not found")
    
    return FileResponse(result_path)


@app.delete("/api/v1/tasks/{task_id}")
async def delete_task(task_id: str):
    """删除任务"""
    if task_id not in server_state.tasks:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
    # 如果任务正在运行，不能删除
    if server_state.tasks[task_id]['status'] == 'processing':
        raise HTTPException(status_code=400, detail="Cannot delete running task")
    
    del server_state.tasks[task_id]
    
    return {"message": f"Task {task_id} deleted"}


# ============== 后台任务处理 ==============

async def process_task(
    task_id: str,
    use_llm_vision: bool,
    create_long_screenshots: bool
):
    """处理任务"""
    try:
        server_state.active_tasks += 1
        server_state.update_task(
            task_id,
            status="processing",
            progress=10.0,
            message="Initializing learning engine..."
        )
        
        # 查找任务目录
        task_dirs = list(server_state.task_storage_path.glob(f"task_*{task_id}*"))
        if not task_dirs:
            raise Exception(f"Task directory not found for {task_id}")
        
        task_path = task_dirs[0]
        
        server_state.update_task(
            task_id,
            progress=20.0,
            message="Loading task data..."
        )
        
        # 创建学习引擎
        engine = FinalBusinessLearningEngine(str(task_path))
        
        server_state.update_task(
            task_id,
            progress=30.0,
            message="Analyzing video and data..."
        )
        
        # 执行学习
        result = engine.run(
            use_llm_vision=use_llm_vision,
            create_long_screenshots=create_long_screenshots
        )
        
        server_state.update_task(
            task_id,
            progress=80.0,
            message="Storing knowledge to memory..."
        )
        
        # 结果文件路径
        result_file = task_path / "analysis" / "final_comprehensive_analysis.json"
        
        server_state.update_task(
            task_id,
            status="completed",
            progress=100.0,
            message="Task completed successfully",
            result_path=str(result_file) if result_file.exists() else None
        )
        
        print(f"✅ Task {task_id} completed")
        
    except Exception as e:
        server_state.update_task(
            task_id,
            status="failed",
            message=f"Error: {str(e)}"
        )
        print(f"❌ Task {task_id} failed: {e}")
        
    finally:
        server_state.active_tasks -= 1


# ============== 启动入口 ==============

if __name__ == "__main__":
    host = os.getenv('SENTINEL_LEARNER_HOST', '0.0.0.0')
    port = int(os.getenv('SENTINEL_LEARNER_PORT', '8000'))
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║           Sentinel Learner Server v2.0.0                     ║
╠══════════════════════════════════════════════════════════════╣
║  API Documentation: http://{host}:{port}/docs                 ║
║  Health Check:      http://{host}:{port}/health               ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    uvicorn.run(
        "server:app",
        host=host,
        port=port,
        reload=False,
        workers=1
    )
