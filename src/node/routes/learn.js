/**
 * 学习引擎路由
 */

const express = require('express');
const router = express.Router();
const { exec } = require('child_process');
const path = require('path');
const util = require('util');

const execPromise = util.promisify(exec);

// 启动学习任务
router.post('/start', async (req, res) => {
    try {
        const { taskId, options = {} } = req.body;
        
        if (!taskId) {
            return res.status(400).json({ error: '请提供任务ID' });
        }
        
        const taskPath = path.join(__dirname, '../../../output/collections', taskId);
        const pythonScript = path.join(__dirname, '../../python/business_learner/cli.py');
        
        const cmd = `python3 "${pythonScript}" learn --task "${taskPath}"`;
        
        // 异步执行学习命令
        exec(cmd, (error, stdout, stderr) => {
            if (error) {
                console.error('学习失败:', error);
            }
        });
        
        res.json({
            taskId,
            status: 'started',
            message: '学习任务已启动'
        });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// 获取学习状态
router.get('/status/:taskId', async (req, res) => {
    try {
        const { taskId } = req.params;
        
        // 检查输出目录是否存在结果
        const outputPath = path.join(__dirname, '../../../output/collections', taskId, 'output');
        const fs = require('fs-extra');
        
        const exists = await fs.pathExists(outputPath);
        
        res.json({
            taskId,
            status: exists ? 'completed' : 'processing'
        });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// 获取学习结果
router.get('/result/:taskId', async (req, res) => {
    try {
        const { taskId } = req.params;
        const outputPath = path.join(__dirname, '../../../output/collections', taskId, 'output');
        const fs = require('fs-extra');
        
        if (!await fs.pathExists(outputPath)) {
            return res.status(404).json({ error: '学习结果不存在' });
        }
        
        // 读取所有结果文件
        const files = await fs.readdir(outputPath);
        const results = {};
        
        for (const file of files) {
            if (file.endsWith('.json')) {
                const content = await fs.readJson(path.join(outputPath, file));
                results[file.replace('.json', '')] = content;
            }
        }
        
        res.json({
            taskId,
            results
        });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

module.exports = router;
