/**
 * Mock API 路由
 */

const express = require('express');
const router = express.Router();
const path = require('path');
const fs = require('fs-extra');

// Mock 数据存储目录
const MOCK_DIR = path.join(__dirname, '../../../output/mock-apis');
fs.ensureDirSync(MOCK_DIR);

// 动态路由处理器
router.all('*', async (req, res) => {
    try {
        // 从请求路径生成mock文件名
        const mockPath = req.path.replace(/\//g, '_');
        const mockFile = path.join(MOCK_DIR, `${mockPath}.json`);
        
        // 检查是否有预设的mock数据
        if (await fs.pathExists(mockFile)) {
            const mockData = await fs.readJson(mockFile);
            return res.json(mockData);
        }
        
        // 返回默认响应
        res.json({
            success: true,
            message: 'Mock响应',
            path: req.path,
            method: req.method,
            timestamp: new Date().toISOString()
        });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

module.exports = router;
