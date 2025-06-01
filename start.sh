#!/bin/bash

# 电费监控系统启动脚本

echo "🔋 电费自动提醒系统启动脚本"
echo "=================================="

# 检查conda环境
if ! command -v conda &> /dev/null; then
    echo "❌ 错误: 未找到conda，请先安装Anaconda或Miniconda"
    exit 1
fi

# 激活conda环境
echo "📦 激活conda环境: electric_monitor"
source $(conda info --base)/etc/profile.d/conda.sh
conda activate electric_monitor

if [ $? -ne 0 ]; then
    echo "❌ 错误: 无法激活conda环境，请确保已创建electric_monitor环境"
    exit 1
fi

# 检查配置文件
if [ ! -f "config.py" ]; then
    echo "❌ 错误: 未找到config.py配置文件"
    echo "请复制config.py.example为config.py并填写配置信息"
    exit 1
fi

# 检查配置是否完整
if grep -q "你的学号\|你的密码\|你的邮箱" config.py; then
    echo "⚠️  警告: config.py中还有未配置的项目，请检查并修改："
    echo "   - BUPT_USERNAME (北邮学号)"
    echo "   - BUPT_PASSWORD (北邮密码)" 
    echo "   - EMAIL_USERNAME (发送邮件的邮箱)"
    echo "   - EMAIL_PASSWORD (邮箱授权码)"
    echo ""
    read -p "是否继续启动？(y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "🚀 启动电费监控系统..."
echo "📱 Web界面将在 http://localhost:5000 开启"
echo "⏰ 系统将每小时自动检查电费情况"
echo "📧 余额不足时将发送邮件到 nemo.yzx@bupt.edu.com"
echo ""
echo "按 Ctrl+C 停止服务"
echo "=================================="

# 启动应用
python app.py
