@echo off
chcp 65001 > nul
echo 🔋 电费自动提醒系统启动脚本
echo ==================================

REM 检查conda是否安装
where conda > nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 错误: 未找到conda，请先安装Anaconda或Miniconda
    pause
    exit /b 1
)

REM 激活conda环境
echo 📦 激活conda环境: electric_monitor
call conda activate electric_monitor
if %errorlevel% neq 0 (
    echo ❌ 错误: 无法激活conda环境，请确保已创建electric_monitor环境
    pause
    exit /b 1
)

REM 检查配置文件
if not exist "config.py" (
    echo ❌ 错误: 未找到config.py配置文件
    echo 请复制config.py.example为config.py并填写配置信息
    pause
    exit /b 1
)

echo 🚀 启动电费监控系统...
echo 📱 Web界面将在 http://localhost:5000 开启
echo ⏰ 系统将每小时自动检查电费情况
echo 📧 余额不足时将发送邮件到 nemo.yzx@bupt.edu.com
echo.
echo 按 Ctrl+C 停止服务
echo ==================================

REM 启动应用
python app.py

pause
