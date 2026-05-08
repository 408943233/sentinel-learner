#!/bin/bash
#
# 创建完整安装包脚本
# 包含: 代码 + chi_sim.traineddata + yolov8s.pt
#

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  创建 Page Screenshot to HTML 安装包${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PACKAGE_NAME="page-screenshot-to-html-installer"
VERSION=$(date +"%Y%m%d")
OUTPUT_DIR="$PROJECT_DIR/dist"

# 依赖文件路径
CHI_SIM_DATA="/Users/gaoyiwei/Downloads/chi_sim.traineddata"
YOLO_MODEL="/Users/gaoyiwei/Downloads/yolov8s.pt"

echo -e "${BLUE}项目目录: $PROJECT_DIR${NC}"
echo -e "${BLUE}输出目录: $OUTPUT_DIR${NC}"
echo ""

# 检查依赖文件
echo -e "${YELLOW}检查依赖文件...${NC}"

missing_files=()

if [ ! -f "$CHI_SIM_DATA" ]; then
    missing_files+=("chi_sim.traineddata (应在 /Users/gaoyiwei/Downloads/chi_sim.traineddata)")
fi

if [ ! -f "$YOLO_MODEL" ]; then
    missing_files+=("yolov8s.pt (应在 /Users/gaoyiwei/Downloads/yolov8s.pt)")
fi

if [ ${#missing_files[@]} -ne 0 ]; then
    echo -e "${RED}错误: 以下依赖文件缺失:${NC}"
    for file in "${missing_files[@]}"; do
        echo "  - $file"
    done
    echo ""
    echo "请确保这些文件已下载到正确位置"
    exit 1
fi

echo -e "${GREEN}✓ 所有依赖文件已找到${NC}"
echo ""

# 创建输出目录
mkdir -p "$OUTPUT_DIR"

# 创建临时目录
TEMP_DIR=$(mktemp -d)
PACKAGE_DIR="$TEMP_DIR/$PACKAGE_NAME-$VERSION"
mkdir -p "$PACKAGE_DIR"

echo -e "${YELLOW}复制项目文件...${NC}"

# 复制代码文件
cp -r "$PROJECT_DIR/scripts" "$PACKAGE_DIR/"
cp -r "$PROJECT_DIR/SKILL.md" "$PACKAGE_DIR/" 2>/dev/null || true
cp -r "$PROJECT_DIR/INSTALL.md" "$PACKAGE_DIR/" 2>/dev/null || true
cp -r "$PROJECT_DIR/README.md" "$PACKAGE_DIR/" 2>/dev/null || true

# 复制依赖文件
echo -e "${YELLOW}复制依赖文件...${NC}"
mkdir -p "$PACKAGE_DIR/models"
cp "$YOLO_MODEL" "$PACKAGE_DIR/models/"
cp "$CHI_SIM_DATA" "$PACKAGE_DIR/models/"

# 创建安装脚本
echo -e "${YELLOW}创建安装脚本...${NC}"

cat > "$PACKAGE_DIR/install.sh" << 'INSTALL_EOF'
#!/bin/bash
#
# Page Screenshot to HTML - 安装脚本
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

INSTALL_DIR="${INSTALL_DIR:-/opt/page-screenshot-to-html}"
TESSDATA_DIR="${TESSDATA_DIR:-/usr/local/share/tessdata}"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Page Screenshot to HTML 安装程序${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 检查root权限
if [ "$EUID" -ne 0 ]; then
    echo -e "${YELLOW}注意: 使用sudo运行以获得最佳安装效果${NC}"
    echo ""
fi

# 创建安装目录
echo -e "${YELLOW}创建安装目录...${NC}"
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/output"

# 复制文件
echo -e "${YELLOW}复制程序文件...${NC}"
cp -r scripts "$INSTALL_DIR/"
cp -r models "$INSTALL_DIR/"

# 安装Tesseract数据文件
if [ -d "$TESSDATA_DIR" ]; then
    echo -e "${YELLOW}安装Tesseract中文语言包...${NC}"
    cp models/chi_sim.traineddata "$TESSDATA_DIR/"
    echo -e "${GREEN}✓ 已安装到 $TESSDATA_DIR${NC}"
else
    echo -e "${YELLOW}警告: Tesseract数据目录不存在 ($TESSDATA_DIR)${NC}"
    echo "请手动将 chi_sim.traineddata 复制到Tesseract数据目录"
fi

# 安装YOLO模型
YOLO_DEST="$INSTALL_DIR/scripts/yolov8s.pt"
if [ ! -f "$YOLO_DEST" ]; then
    echo -e "${YELLOW}安装YOLO模型...${NC}"
    cp models/yolov8s.pt "$YOLO_DEST"
fi

# 设置权限
chmod +x "$INSTALL_DIR/scripts/"*.sh
chmod +x "$INSTALL_DIR/scripts/"*.py

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  安装完成!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "安装位置: $INSTALL_DIR"
echo ""
echo "使用方法:"
echo "  cd $INSTALL_DIR"
echo "  python3 scripts/screenshot_to_html.py <图片路径>"
echo ""
echo "环境变量设置 (添加到 ~/.bashrc 或 ~/.zshrc):"
echo "  export PAGE_SCREENSHOT_HTML_HOME=$INSTALL_DIR"
echo ""
INSTALL_EOF

chmod +x "$PACKAGE_DIR/install.sh"

# 创建README
cat > "$PACKAGE_DIR/PACKAGE_README.md" << 'README_EOF'
# Page Screenshot to HTML - 安装包

## 包含内容

- `scripts/` - 主程序代码
- `models/` - 依赖模型文件
  - `yolov8s.pt` - YOLOv8目标检测模型
  - `chi_sim.traineddata` - Tesseract中文OCR数据
- `install.sh` - 安装脚本

## 安装步骤

1. 解压安装包
```bash
tar -xzf page-screenshot-to-html-installer-*.tar.gz
cd page-screenshot-to-html-installer-*
```

2. 运行安装脚本
```bash
sudo ./install.sh
```

3. 设置环境变量 (可选)
```bash
export PAGE_SCREENSHOT_HTML_HOME=/opt/page-screenshot-to-html
```

## 依赖要求

- Python 3.8+
- Tesseract OCR
- Chrome/Chromium浏览器
- 详见 INSTALL.md

## 使用方法

```bash
cd /opt/page-screenshot-to-html
python3 scripts/screenshot_to_html.py /path/to/screenshot.png
```

README_EOF

# 创建压缩包
echo -e "${YELLOW}创建压缩包...${NC}"
cd "$TEMP_DIR"
tar -czf "$OUTPUT_DIR/${PACKAGE_NAME}-${VERSION}.tar.gz" "$PACKAGE_NAME-$VERSION"

# 计算文件大小
PACKAGE_SIZE=$(du -h "$OUTPUT_DIR/${PACKAGE_NAME}-${VERSION}.tar.gz" | cut -f1)

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  安装包创建完成!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}包信息:${NC}"
echo "  名称: ${PACKAGE_NAME}-${VERSION}.tar.gz"
echo "  大小: $PACKAGE_SIZE"
echo "  位置: $OUTPUT_DIR/"
echo ""
echo -e "${BLUE}包含内容:${NC}"
echo "  ✓