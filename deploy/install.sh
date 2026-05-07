#!/bin/bash
# Sentinel Learner Server 安装脚本
# 用于在服务端OpenClaw环境中部署

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印函数
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 欢迎信息
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║     Sentinel Learner Server - 服务端部署安装脚本              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# 检查root权限
if [ "$EUID" -ne 0 ]; then 
    print_error "请使用 sudo 运行此脚本"
    exit 1
fi

# 获取安装参数
INSTALL_DIR=${INSTALL_DIR:-"/opt/sentinel-learner"}
DATA_DIR=${DATA_DIR:-"/data/sentinel-learner"}
SHARED_MEMORY_PATH=${SHARED_MEMORY_PATH:-"/shared/openclaw"}
LLM_API_KEY=${LLM_API_KEY:-""}

print_info "安装目录: $INSTALL_DIR"
print_info "数据目录: $DATA_DIR"
print_info "共享Memory路径: $SHARED_MEMORY_PATH"

# 检查依赖
print_info "检查系统依赖..."

# 检查Docker
if ! command -v docker &> /dev/null; then
    print_warning "Docker未安装，正在安装..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    print_success "Docker安装完成"
else
    print_success "Docker已安装"
fi

# 检查Docker Compose
if ! command -v docker-compose &> /dev/null; then
    print_warning "Docker Compose未安装，正在安装..."
    curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
    print_success "Docker Compose安装完成"
else
    print_success "Docker Compose已安装"
fi

# 创建目录
print_info "创建目录结构..."
mkdir -p $INSTALL_DIR
mkdir -p $DATA_DIR/{tasks,output,logs}
mkdir -p $SHARED_MEMORY_PATH
mkdir -p /etc/sentinel-learner

# 复制安装文件
print_info "复制应用文件..."
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# 复制部署文件
cp -r $SCRIPT_DIR/* $INSTALL_DIR/
cp -r $SCRIPT_DIR/../src $INSTALL_DIR/
cp -r $SCRIPT_DIR/../config $INSTALL_DIR/

# 创建环境配置文件
print_info "创建环境配置..."
cat > $INSTALL_DIR/.env << EOF
# Sentinel Learner 环境配置
SENTINEL_LEARNER_MODE=server
SENTINEL_LEARNER_HOST=0.0.0.0
SENTINEL_LEARNER_PORT=8000

# 路径配置
TASK_STORAGE_PATH=$DATA_DIR/tasks
OUTPUT_PATH=$DATA_DIR/output
OPENCLAW_MEMORY_PATH=$SHARED_MEMORY_PATH/openclaw-memory-skill

# LLM配置
LLM_API_KEY=$LLM_API_KEY
LLM_BASE_URL=https://api.moonshot.cn/v1

# 任务配置
MAX_CONCURRENT_TASKS=4
TASK_TIMEOUT_SECONDS=300
EOF

print_success "环境配置已创建"

# 创建Systemd服务
print_info "创建Systemd服务..."
cat > /etc/systemd/system/sentinel-learner.service << EOF
[Unit]
Description=Sentinel Learner Server
Documentation=https://github.com/sentinel-learner
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=/usr/local/bin/docker-compose -f $INSTALL_DIR/docker-compose.yml up -d
ExecStop=/usr/local/bin/docker-compose -f $INSTALL_DIR/docker-compose.yml down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

# 重新加载Systemd
systemctl daemon-reload
systemctl enable sentinel-learner.service

print_success "Systemd服务已创建"

# 创建启动脚本
cat > /usr/local/bin/sentinel-learner << 'EOF'
#!/bin/bash
# Sentinel Learner 管理脚本

INSTALL_DIR="/opt/sentinel-learner"

case "$1" in
    start)
        echo "Starting Sentinel Learner..."
        cd $INSTALL_DIR && docker-compose up -d
        ;;
    stop)
        echo "Stopping Sentinel Learner..."
        cd $INSTALL_DIR && docker-compose down
        ;;
    restart)
        echo "Restarting Sentinel Learner..."
        cd $INSTALL_DIR && docker-compose restart
        ;;
    status)
        cd $INSTALL_DIR && docker-compose ps
        ;;
    logs)
        cd $INSTALL_DIR && docker-compose logs -f
        ;;
    update)
        echo "Updating Sentinel Learner..."
        cd $INSTALL_DIR && docker-compose pull && docker-compose up -d
        ;;
    shell)
        cd $INSTALL_DIR && docker-compose exec sentinel-learner /bin/bash
        ;;
    *)
        echo "Usage: sentinel-learner {start|stop|restart|status|logs|update|shell}"
        exit 1
        ;;
esac
EOF

chmod +x /usr/local/bin/sentinel-learner
print_success "管理脚本已创建"

# 构建Docker镜像
print_info "构建Docker镜像..."
cd $INSTALL_DIR
docker-compose build

print_success "Docker镜像构建完成"

# 设置权限
print_info "设置文件权限..."
chown -R 1000:1000 $DATA_DIR
chmod -R 755 $DATA_DIR
chmod -R 775 $SHARED_MEMORY_PATH

# 创建OpenClaw Memory Skill软链接（如果不存在）
if [ ! -d "$SHARED_MEMORY_PATH/openclaw-memory-skill" ]; then
    print_warning "OpenClaw Memory Skill未找到，请确保已部署"
    print_info "预期路径: $SHARED_MEMORY_PATH/openclaw-memory-skill"
fi

# 完成安装
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║              安装完成！                                       ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║                                                              ║"
echo "║  安装目录: $INSTALL_DIR"
echo "║  数据目录: $DATA_DIR"
echo "║  API地址:  http://localhost:8000                             ║"
echo "║  文档地址: http://localhost:8000/docs                        ║"
echo "║                                                              ║"
echo "║  管理命令:                                                   ║"
echo "║    sentinel-learner start    # 启动服务                     ║"
echo "║    sentinel-learner stop     # 停止服务                     ║"
echo "║    sentinel-learner status   # 查看状态                     ║"
echo "║    sentinel-learner logs     # 查看日志                     ║"
echo "║                                                              ║"
echo "║  系统服务:                                                   ║"
echo "║    systemctl start sentinel-learner                         ║"
echo "║    systemctl stop sentinel-learner                          ║"
echo "║    systemctl status sentinel-learner                        ║"
echo "║                                                              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

print_info "是否立即启动服务? (y/n)"
read -r response
if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
    sentinel-learner start
    print_success "服务已启动！"
    print_info "API文档: http://localhost:8000/docs"
fi
