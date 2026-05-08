#!/bin/bash
# 推送 sentinel-learner 到 GitHub

cd /Users/gaoyiwei/Documents/trae_projects/openclaw/sentinel-learner

echo "当前状态:"
git status

echo ""
echo "最近的提交:"
git log --oneline -3

echo ""
echo "推送到 GitHub..."
git push origin main

echo ""
echo "完成!"
