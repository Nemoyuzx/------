# 电费自动监控系统

一个自动监控北邮电费余额并发送预警邮件的系统，支持Web界面实时查看电费数据。

## ✨ 功能特性

- 🔐 **自动登录**: 自动登录北邮统一身份认证系统
- 📊 **实时监控**: 每小时自动检查电费余额和用电量  
- 📧 **邮件预警**: 余额不足时自动发送邮件通知
- 🌐 **Web界面**: 现代化的Web控制台，实时查看电费数据
- 📈 **数据分析**: 电费使用趋势图表和统计分析
- 💾 **数据存储**: SQLite数据库存储历史记录
- ⚙️ **简易配置**: 配置向导一键设置所有参数

## 📋 系统要求

- Python 3.9+
- Conda/Miniconda (推荐) 或 pip
- 网络连接（访问北邮网站）
- 邮箱账号（用于发送预警邮件）

## 🚀 快速部署

### 方法一：使用Conda（推荐）

```bash
# 1. 创建并激活虚拟环境
conda create -n electric_monitor python=3.9 -y
conda activate electric_monitor

# 2. 安装依赖
conda install flask requests beautifulsoup4 apscheduler lxml -y

# 3. 进入项目目录
cd "/Users/nemoyu/Desktop/电费自动提醒"

# 4. 配置系统
python setup_config.py

# 5. 启动服务
python app.py
```

### 方法二：使用pip

```bash
# 1. 创建虚拟环境
python3 -m venv electric_monitor
source electric_monitor/bin/activate  # macOS/Linux
# electric_monitor\Scripts\activate  # Windows

# 2. 安装依赖
pip install -r requirements.txt

# 3. 进入项目目录
cd "/Users/nemoyu/Desktop/电费自动提醒"

# 4. 配置系统
python setup_config.py

# 5. 启动服务
python app.py
```

### 方法三：一键启动

```bash
# macOS/Linux
chmod +x start.sh
./start.sh

# Windows
start.bat
```

## 🔧 配置说明

### 1. 基本配置

运行配置向导：
```bash
python setup_config.py
```

或手动编辑 `config.py`：
```python
# 北邮统一身份认证
BUPT_USERNAME = "你的学号"
BUPT_PASSWORD = "你的密码"

# 宿舍信息（当前配置：西土城校区学五楼5-801）
AREA_ID = 1  # 1=西土城, 2=沙河
APARTMENT_ID = "a3d3473047464fba9196e224659cc377"
FLOOR_ID = "8"
ROOM_NUMBER = "5-801"

# 邮件配置
EMAIL_SMTP_SERVER = "smtp.qq.com"
EMAIL_SMTP_PORT = 587
EMAIL_USERNAME = "你的邮箱@qq.com"
EMAIL_PASSWORD = "邮箱授权码"
ALERT_EMAIL = "接收预警的邮箱@qq.com"

# 预警设置
LOW_BALANCE_THRESHOLD = 10.0  # 余额低于10元时发送预警

# Web服务配置
WEB_HOST = "0.0.0.0"
WEB_PORT = 5100
```

### 2. 邮箱配置

**QQ邮箱（推荐）**:
1. 登录QQ邮箱设置
2. 开启SMTP服务
3. 生成授权码（不是QQ密码）
4. 填入配置文件

**其他邮箱**:
- 163邮箱: `smtp.163.com:25`
- Gmail: `smtp.gmail.com:587`
- 139邮箱: `smtp.139.com:25`

### 3. 宿舍配置

如需修改宿舍，使用房间查找工具：
```bash
python room_finder.py
```

或直接编辑 `config.py` 中的宿舍配置参数。

## 🌐 使用方法

### 启动系统

```bash
python app.py
```

### 访问Web界面

启动后在浏览器中访问：
```
http://localhost:5100
```

### Web界面功能

- **实时仪表盘**: 显示当前余额、今日用电、本月用电
- **趋势图表**: 余额变化趋势可视化
- **历史记录**: 详细的检查记录和数据
- **手动检查**: 点击按钮立即检查电费
- **状态监控**: 系统运行状态和最后更新时间

### API接口

- `GET /` - Web监控界面
- `GET /api/check` - 手动检查电费
- `GET /api/stats` - 获取统计数据
- `GET /api/records?limit=N` - 获取历史记录

## ⏰ 自动化功能

- **定时检查**: 每小时整点自动检查电费
- **低余额预警**: 余额低于设定阈值时发送邮件
- **数据存储**: 自动保存历史记录到SQLite数据库
- **日志记录**: 详细的运行日志记录

## 📁 项目结构

```
电费自动提醒/
├── app.py                    # 主应用程序
├── config.py                 # 配置文件（用户填写）
├── config.py.example         # 配置模板
├── setup_config.py           # 配置向导
├── room_finder.py            # 房间查找工具
├── requirements.txt          # Python依赖包列表
├── start.sh / start.bat      # 启动脚本
├── README.md                 # 说明文档
├── .gitignore                # Git忽略文件
├── templates/
│   └── index.html            # Web界面模板
├── electric_data.db          # SQLite数据库（自动创建）
└── electric_monitor.log      # 运行日志（自动创建）
```

## 🛠️ 常见问题

### 1. 登录失败
- 检查学号和密码是否正确
- 确认网络连接正常
- 查看日志文件 `electric_monitor.log`

### 2. 邮件发送失败
- 检查邮箱SMTP设置
- 确认授权码正确（不是邮箱密码）
- 检查网络防火墙设置

### 3. 端口被占用
```bash
# 查找占用端口的进程
lsof -i :5100

# 杀死进程
sudo kill -9 <PID>
```

### 4. 依赖安装失败
```bash
# 更新pip
pip install --upgrade pip

# 清除缓存
pip cache purge

# 重新安装
pip install -r requirements.txt
```

## 🔐 安全说明

- 配置文件 `config.py` 已加入 `.gitignore`，不会被提交到Git
- 敏感信息（密码、邮箱）请妥善保管
- 建议定期更换密码

## 📝 更新日志

### v1.0.0 (2025-06-01)
- ✅ 基础电费监控功能
- ✅ 邮件预警系统
- ✅ Web界面
- ✅ 数据存储和统计
- ✅ 配置向导
- ✅ 定时任务调度

## 🤝 贡献

欢迎提交Issues和Pull Requests来改进这个项目！

欢迎发送邮件到2099905168@qq.com进行交流

## 📄 许可证

GNU GENERAL PUBLIC LICENSE - Version 3, 29 June 2007

## ⚠️ 免责声明

本工具仅供学习和个人使用，请遵守相关网站的使用条款。使用本工具造成的任何后果由用户自行承担。
