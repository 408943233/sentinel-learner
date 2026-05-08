#!/bin/bash
# 推送 sentinel-learner 到 GitHub
# 请在本地终端运行此脚本

cd /Users/gaoyiwei/Documents/trae_projects/openclaw/sentinel-learner

echo "======================================"
echo "GitHub 推送脚本"
echo "======================================"
echo ""

echo "当前提交:"
git log --oneline -1
echo ""

echo "推送到 GitHub..."
git push origin main

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ 推送成功!"
else
    echo ""
    echo "❌ 推送失败"
    echo "请检查网络连接或手动推送"
fi

echo ""
echo "======================================"
