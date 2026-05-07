/**
 * Sentinel Learner - Node.js 入口
 * 提供API服务和任务管理
 */

const express = require('express');
const cors = require('cors');
const bodyParser = require('body-parser');
const path = require('path');
const fs = require('fs-extra');

// 路由
const taskRoutes = require('./routes/tasks');
const learnRoutes = require('./routes/learn');
const mockRoutes = require('./routes/mock');

const app = express();
const PORT = process.env.PORT || 3001;

// 中间件
app.use(cors());
app.use(bodyParser.json({ limit: '50mb' }));
app.use(bodyParser.urlencoded({ extended: true, limit: '50mb' }));

// 静态文件
app.use('/output', express.static(path.join(__dirname, '../../output')));

// 路由
app.use('/api/tasks', taskRoutes);
app.use('/api/learn', learnRoutes);
app.use('/api/mock', mockRoutes);

// 健康检查
app.get('/health', (req, res) => {
    res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// 启动服务器
app.listen(PORT, () => {
    console.log(`Sentinel Learner API 服务运行在端口 ${PORT}`);
    console.log(`API文档: http://localhost:${PORT}/api/docs`);
});

module.exports = app;
