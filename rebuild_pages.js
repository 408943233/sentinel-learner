const PageReconstructor = require('./sentinel-learner/src/node/page-reconstructor');
const path = require('path');

async function rebuild() {
  const reconstructor = new PageReconstructor({
    outputDir: './sentinel-learner/output/reconstructed',
    mockServerUrl: 'http://localhost:8090'
  });

  try {
    await reconstructor.reconstructFromTask(
      path.join(__dirname, 'output/collections/task_11_www.chinastock.com.cn_1778034751731')
    );
    console.log('页面重建完成！');
  } catch (err) {
    console.error('重建失败:', err);
  }
}

rebuild();
