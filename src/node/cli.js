#!/usr/bin/env node
/**
 * Sentinel Learner CLI
 * 命令行工具用于学习任务和分析
 */

const { Command } = require('commander');
const chalk = require('chalk');
const ora = require('ora');
const path = require('path');
const { execSync } = require('child_process');

const program = new Command();

program
    .name('sentinel-learner')
    .description('Sentinel Browser 录制任务的学习与分析系统')
    .version('1.0.0');

// learn 命令 - 学习任务
program
    .command('learn')
    .description('学习一个录制任务')
    .option('-t, --task <path>', '任务目录路径')
    .option('-o, --output <path>', '输出目录', './output')
    .action(async (options) => {
        const spinner = ora('正在启动学习引擎...').start();
        
        try {
            const taskPath = options.task;
            if (!taskPath) {
                spinner.fail('请提供任务目录路径: --task <path>');
                process.exit(1);
            }
            
            spinner.text = `正在学习任务: ${taskPath}`;
            
            // 调用 Python 学习引擎
            const pythonScript = path.join(__dirname, '../python/business_learner/cli.py');
            const cmd = `python3 "${pythonScript}" learn --task "${taskPath}" --output "${options.output}"`;
            
            execSync(cmd, { stdio: 'inherit' });
            
            spinner.succeed('学习任务完成！');
        } catch (error) {
            spinner.fail(`学习失败: ${error.message}`);
            process.exit(1);
        }
    });

// mock 命令 - 启动模拟服务
program
    .command('mock')
    .description('启动API模拟服务')
    .option('-p, --port <port>', '服务端口', '3002')
    .option('-c, --config <path>', '配置文件路径')
    .action(async (options) => {
        console.log(chalk.blue(`启动模拟服务在端口 ${options.port}...`));
        
        // 这里可以启动mock服务器
        const mockServer = require('./mock/server');
        await mockServer.start(options.port, options.config);
    });

// evaluate 命令 - 评估学习结果
program
    .command('evaluate')
    .description('评估学习结果')
    .option('-t, --task <path>', '任务目录路径')
    .option('-r, --report <path>', '报告输出路径')
    .action(async (options) => {
        const spinner = ora('正在评估学习结果...').start();
        
        try {
            // 调用评估逻辑
            spinner.succeed('评估完成！');
        } catch (error) {
            spinner.fail(`评估失败: ${error.message}`);
            process.exit(1);
        }
    });

program.parse();
