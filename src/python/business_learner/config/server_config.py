"""
服务器部署配置
"""

import os
from pathlib import Path
from typing import Optional


class ServerConfig:
    """服务器配置"""
    
    # 运行模式
    MODE = os.getenv("BUSINESS_LEARNER_MODE", "local")  # local 或 server
    
    # 服务器配置（server模式）
    SERVER_HOST = os.getenv("BUSINESS_LEARNER_HOST", "0.0.0.0")
    SERVER_PORT = int(os.getenv("BUSINESS_LEARNER_PORT", "8000"))
    
    # 共享Memory路径（server模式）
    SERVER_MEMORY_PATH = os.getenv(
        "OPENCLAW_MEMORY_PATH", 
        "/shared/openclaw/openclaw-memory-skill"
    )
    
    # Task数据存储路径（server模式）
    TASK_STORAGE_PATH = os.getenv(
        "TASK_STORAGE_PATH",
        "/data/tasks"
    )
    
    # 处理配置
    MAX_CONCURRENT_TASKS = int(os.getenv("MAX_CONCURRENT_TASKS", "4"))
    TASK_TIMEOUT_SECONDS = int(os.getenv("TASK_TIMEOUT_SECONDS", "300"))
    
    # 日志配置
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_PATH = os.getenv("LOG_PATH", "/var/log/business-learner")
    
    # Redis配置（用于任务队列）
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB = int(os.getenv("REDIS_DB", "0"))
    
    @classmethod
    def is_server_mode(cls) -> bool:
        """是否为服务器模式"""
        return cls.MODE == "server"
    
    @classmethod
    def get_memory_path(cls) -> str:
        """获取memory路径"""
        if cls.is_server_mode():
            return cls.SERVER_MEMORY_PATH
        else:
            # 本地模式使用项目内的路径
            return "/Users/gaoyiwei/Documents/trae_projects/openclaw/openclaw-memory-skill"
    
    @classmethod
    def validate(cls) -> bool:
        """验证配置"""
        if cls.is_server_mode():
            # 服务器模式需要检查共享memory路径
            memory_path = Path(cls.SERVER_MEMORY_PATH)
            if not memory_path.exists():
                print(f"警告: 共享memory路径不存在: {memory_path}")
                return False
            
            # 检查是否有写入权限
            if not os.access(memory_path, os.W_OK):
                print(f"错误: 没有写入权限: {memory_path}")
                return False
        
        return True


# 开发环境配置
class DevelopmentConfig(ServerConfig):
    """开发环境配置"""
    MODE = "local"
    LOG_LEVEL = "DEBUG"


# 生产环境配置
class ProductionConfig(ServerConfig):
    """生产环境配置"""
    MODE = "server"
    LOG_LEVEL = "WARNING"
    MAX_CONCURRENT_TASKS = 8


# 配置映射
config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": ServerConfig
}


def get_config(env: Optional[str] = None):
    """获取配置"""
    env = env or os.getenv("BUSINESS_LEARNER_ENV", "default")
    return config_map.get(env, ServerConfig)
