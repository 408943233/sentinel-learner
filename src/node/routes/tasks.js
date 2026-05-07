/**
 * 任务管理路由
 */

const express = require('express');
const router = express.Router();
const path = require('path');
const fs = require('fs-extra');
const multer = require('multer');
const { v4: uuidv4 } = require('uuid');

// 任务存储目录
const TASKS_DIR = path.join(__dirname, '../../../output/collections');

// 确保目录存在
fs.ensureDirSync(TASKS_DIR);

// 文件上传配置
const storage = multer.diskStorage({
    destination: (req, file, cb) => {
        const taskId = req.params.taskId || uuidv4();
        const taskDir = path.join(TASKS_DIR, taskId);
        fs.ensureDirSync(taskDir);
        cb(null, taskDir);
    },
    filename: (req, file, cb) => {
        cb(null, file.originalname);
    }
});
const upload = multer({ storage });

// 获取所有任务
router.get('/', async (req, res) => {
    try {
        const tasks = [];
        const taskDirs = await fs.readdir(TASKS_DIR);
        
        for (const taskId of taskDirs) {
            const taskDir = path.join(TASKS_DIR, taskId);
            const stat = await fs.stat(taskDir);
            
            if (stat.isDirectory()) {
                const metadataPath = path.join(taskDir, 'metadata.json');
                let metadata = {};
                
                if (await fs.pathExists(metadataPath)) {
                    metadata = await fs.readJson(metadataPath);
                }
                
                tasks.push({
                    id: taskId,
                    ...metadata,
                    createdAt: stat.birthtime
                });
            }
        }
        
        res.json({ tasks });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// 获取单个任务
router.get('/:taskId', async (req, res) => {
    try {
        const { taskId } = req.params;
        const taskDir = path.join(TASKS_DIR, taskId);
        
        if (!await fs.pathExists(taskDir)) {
            return res.status(404).json({ error: '任务不存在' });
        }
        
        const metadataPath = path.join(taskDir, 'metadata.json');
        const metadata = await fs.pathExists(metadataPath) 
            ? await fs.readJson(metadataPath) 
            : {};
        
        // 获取任务文件列表
        const files = await fs.readdir(taskDir);
        
        res.json({
            id: taskId,
            ...metadata,
            files
        });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// 上传任务文件
router.post('/:taskId/upload', upload.array('files'), async (req, res) => {
    try {
        const { taskId } = req.params;
        const files = req.files.map(f => ({
            name: f.originalname,
            size: f.size,
            path: f.path
        }));
        
        res.json({
            taskId,
            uploaded: files.length,
            files
        });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// 删除任务
router.delete('/:taskId', async (req, res) => {
    try {
        const { taskId } = req.params;
        const taskDir = path.join(TASKS_DIR, taskId);
        
        if (!await fs.pathExists(taskDir)) {
            return res.status(404).json({ error: '任务不存在' });
        }
        
        await fs.remove(taskDir);
        res.json({ message: '任务已删除' });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

module.exports = router;
