#!/bin/bash
#
# OpenClaw Skill 更新脚本
# 用于将本地skill更新到OpenClaw服务器
#

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 配置
SKILL_NAME="page-screenshot-to-html"
LOCAL_SKILL_DIR="/Users/gaoyiwei/Documents/trae_projects/openclaw/page-screenshot-to-html"
OPENCLAW_HOST="${OPENCLAW_HOST:-localhost}"
OPENCLAW_PORT="${OPENCLAW_PORT:-8080}"
OPENCLAW_API_KEY="${OPENCLAW_API_KEY:-}"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  OpenClaw Skill 更新工具${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 检查必要文件
echo -e "${YELLOW}检查必要文件...${NC}"

if [ ! -f "$LOCAL_SKILL_DIR/SKILL.md" ]; then
    echo -e "${RED}错误: SKILL.md 不存在${NC}"
    exit 1
fi

if [ ! -f "$LOCAL_SKILL_DIR/scripts/screenshot_to_html.py" ]; then
    echo -e "${RED}错误: 主脚本不存在${NC}"
    exit 1
fi

echo -e "${GREEN}✓ 文件检查通过${NC}"
echo ""

# 打包skill
echo -e "${YELLOW}打包Skill...${NC}"
TEMP_DIR=$(mktemp -d)
SKILL_PACKAGE="$TEMP_DIR/${SKILL_NAME}.tar.gz"

cd "$LOCAL_SKILL_DIR"
tar -czf "$SKILL_PACKAGE" \
    --exclude='*.pyc' \
    --exclude='__pycache__' \
    --exclude='.git' \
    --exclude='output/*.html' \
    --exclude='output/*.png' \
    --exclude='*.log' \
    .

echo -e "${GREEN}✓ Skill打包完成: $SKILL_PACKAGE${NC}"
echo ""

# 检查OpenClaw API密钥
if [ -z "$OPENCLAW_API_KEY" ]; then
    echo -e "${YELLOW}警告: OPENCLAW_API_KEY 未设置${NC}"
    echo "请设置环境变量: export OPENCLAW_API_KEY=your_api_key"
    echo ""
    read -p "请输入API Key (或直接回车跳过上传): " api_key
    if [ ! -z "$api_key" ]; then
        OPENCLAW_API_KEY="$api_key"
    fi
fi

# 上传到OpenClaw
if [ ! -z "$OPENCLAW_API_KEY" ]; then
    echo -e "${YELLOW}上传Skill到OpenClaw...${NC}"
    
    API_URL="http://${OPENCLAW_HOST}:${OPENCLAW_PORT}/api/v1/skills/${SKILL_NAME}/update"
    
    response=$(curl -s -w "\n%{http_code}" -X POST \
        -H "Authorization: Bearer $OPENCLAW_API_KEY" \
        -F "file=@$SKILL_PACKAGE" \
        "$API_URL" 2>/dev/null || echo "\n000")
    
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')
    
    if [ "$http_code" = "200" ]; then
        echo -e "${GREEN}✓ Skill更新成功!${NC}"
        echo "响应: $body"
    elif [ "$http_code" = "000" ]; then
        echo -e "${RED}✗ 无法连接到OpenClaw服务器${NC}"
        echo "请检查:"
        echo "  1. OpenClaw服务是否运行"
        echo "  2. OPENCLAW_HOST 和 OPENCLAW_PORT 设置是否正确"
        echo ""
        echo "当前设置:"
        echo "  HOST: $OPENCLAW_HOST"
        echo "  PORT: $OPENCLAW_PORT"
    else
        echo -e "${RED}✗ Skill更新失败 (HTTP $http_code)${NC}"
        echo "响应: $body"
    fi
else
    echo -e "${YELLOW}跳过上传，仅打包完成${NC}"
    echo "打包文件位置: $SKILL_PACKAGE"
fi

# 清理临时文件
rm -rf "$TEMP_DIR"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  更新流程完成${NC}"
echo -e "${GREEN}========================================${NC}"
