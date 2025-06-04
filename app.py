#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
电费自动提醒系统
主应用程序，包含Web界面和定时任务
"""

import os
import sqlite3
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import time
import json
import re
import shutil
import importlib
from bs4 import BeautifulSoup
from flask import Flask, render_template, jsonify, request, redirect, url_for
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
import logging

# 导入配置
try:
    import config
except ImportError:
    print("请先配置config.py文件，填写用户名、密码等信息")
    print("可以复制config.py.example为config.py并填写实际信息")
    exit(1)

# 检查配置是否已填写
if (hasattr(config, 'BUPT_USERNAME') and config.BUPT_USERNAME == "你的学号") or \
   (hasattr(config, 'EMAIL_USERNAME') and config.EMAIL_USERNAME == "你的邮箱@qq.com"):
    print("请先在config.py中填写实际的用户名、密码等信息！")
    print("当前配置文件中仍然是示例值，请修改为实际值")
    exit(1)

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('electric_monitor.log'),
        logging.StreamHandler()
    ]
)

app = Flask(__name__)
app.secret_key = 'electric_monitor_secret_key'

# 添加JSON过滤器
@app.template_filter('tojsonfilter')
def to_json_filter(value):
    return json.dumps(value, ensure_ascii=False)

class ElectricMonitor:
    def __init__(self):
        self.session = requests.Session()
        self.init_database()
        
    def init_database(self):
        """初始化数据库"""
        conn = sqlite3.connect('electric_data.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS electric_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                balance REAL,
                usage_today REAL,
                usage_month REAL,
                status TEXT,
                raw_data TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                alert_type TEXT,
                message TEXT,
                sent BOOLEAN DEFAULT 0
            )
        ''')
        
        conn.commit()
        conn.close()
        
    def login_bupt(self):
        """登录北邮统一身份认证"""
        try:
            # 获取登录页面
            login_url = "https://auth.bupt.edu.cn/authserver/login"
            response = self.session.get(login_url, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 新的登录页面结构：提取必要的隐藏字段
            type_input = soup.find('input', {'name': 'type'})
            execution_input = soup.find('input', {'name': 'execution'})
            _eventId_input = soup.find('input', {'name': '_eventId'})
            
            if not type_input or not execution_input or not _eventId_input:
                logging.error("无法找到登录所需的隐藏字段，页面结构可能已变化")
                # 保存页面内容用于调试
                with open('debug_login_page.html', 'w', encoding='utf-8') as f:
                    f.write(response.text)
                logging.info("登录页面内容已保存到debug_login_page.html")
                return False
            
            type_value = type_input.get('value', '') if type_input else '' # type: ignore
            execution = execution_input.get('value', '') if execution_input else '' # type: ignore
            _eventId = _eventId_input.get('value', '') if _eventId_input else '' # type: ignore # type: ignore
            
            # 登录数据 - 使用新的字段结构
            login_data = {
                'username': config.BUPT_USERNAME,
                'password': config.BUPT_PASSWORD,
                'type': type_value,
                'execution': execution,
                '_eventId': _eventId
            }
            
            # 提交登录
            response = self.session.post(login_url, data=login_data, timeout=10)
            
            if 'CAS Login' in response.text or '统一身份认证' in response.text:
                logging.error("登录失败，请检查用户名和密码")
                return False
            
            logging.info("登录成功")
            return True
            
        except Exception as e:
            logging.error(f"登录过程中出现错误: {str(e)}")
            return False
    
    def check_login_needed(self, response):
        """检查响应是否需要登录"""
        # 检查是否跳转到了登录页面
        if (response.status_code == 302 or 
            'auth.bupt.edu.cn' in response.url or
            'CAS Login' in response.text or
            '统一身份认证' in response.text or
            'login' in response.url.lower()):
            logging.info("检测到需要登录")
            return True
        return False
    
    def get_electric_data(self):
        """获取电费数据 - 智能登录检查"""
        try:
            # 先尝试直接访问电费查询页面，检查是否需要登录
            electric_url = "https://app.bupt.edu.cn/buptdf/wap/default/chong"
            response = self.session.get(electric_url, timeout=10, allow_redirects=True)
            
            logging.info(f"访问电费页面: 状态码={response.status_code}, URL={response.url}")
            
            # 检查是否被重定向到登录页面
            if self.check_login_needed(response):
                logging.info("需要登录，开始登录流程...")
                if not self.login_bupt():
                    logging.error("登录失败")
                    return None
                
                # 重新访问电费页面
                response = self.session.get(electric_url, timeout=10)
                if response.status_code != 200:
                    logging.error(f"登录后访问电费页面失败，状态码: {response.status_code}")
                    return None
                logging.info("登录成功，重新访问电费页面成功")
            else:
                logging.info("无需登录，直接查询电费数据")
            
            if response.status_code != 200:
                logging.error(f"访问电费页面失败，状态码: {response.status_code}")
                return None
            
            logging.info("开始查询电费数据...")
            
            # 配置查询参数
            area_id = getattr(config, 'AREA_ID', 2)  # 默认沙河校区
            apartment_id = getattr(config, 'APARTMENT_ID', '沙河校区雁北园A楼')
            floor_id = getattr(config, 'FLOOR_ID', '1层')
            room_number = getattr(config, 'ROOM_NUMBER', '190807009132')  # 需要在配置中设置实际房间号
            
            logging.info(f"查询参数: 校区ID={area_id}, 公寓={apartment_id}, 楼层={floor_id}, 房间号={room_number}")
            
            # 查询电费数据
            search_url = "https://app.bupt.edu.cn/buptdf/wap/default/search"
            response = self.session.post(search_url, data={
                'partmentId': apartment_id,
                'floorId': floor_id,
                'dromNumber': room_number,
                'areaid': area_id
            }, timeout=10)
            
            if response.status_code != 200:
                logging.error(f"电费查询接口访问失败，状态码: {response.status_code}")
                return None
            
            # 解析JSON响应
            try:
                electric_data = response.json()
                logging.info(f"收到电费数据响应: {electric_data}")
                
                if electric_data.get('e') != 0:
                    logging.error(f"电费查询失败: {electric_data.get('m', '未知错误')}")
                    return None
                
                # 提取数据
                raw_data = electric_data.get('d', {}).get('data', {})
                
                data = {
                    'balance': float(raw_data.get('surplus', 0)),  # 余额
                    'total_usage': float(raw_data.get('vTotal', 0)),  # 总用电量
                    'usage_today': None,  # 今日用电量（从原始数据无法直接获取，设为None）
                    'usage_month': None,  # 本月用电量（从原始数据无法直接获取，设为None）
                    'price': float(raw_data.get('price', 0.48)),  # 电价
                    'query_time': raw_data.get('time', ''),  # 查询时间
                    'apartment': raw_data.get('parName', ''),  # 公寓名称
                    'floor': raw_data.get('floorName', ''),  # 楼层
                    'status': 'success',
                    'raw_data': json.dumps(electric_data, ensure_ascii=False),
                    'timestamp': datetime.now()
                }
                
                logging.info(f"解析电费数据成功: 余额={data['balance']}元, 总用电={data['total_usage']}度, 电价={data['price']}元/度")
                
                # 计算今日和月度用电量
                data = self.calculate_usage_data(data)
                
                return data
                
            except json.JSONDecodeError as e:
                logging.error(f"电费数据JSON解析失败: {e}")
                logging.error(f"响应内容: {response.text[:500]}")
                return None
            except (ValueError, KeyError) as e:
                logging.error(f"电费数据解析错误: {e}")
                return None
            
        except Exception as e:
            logging.error(f"获取电费数据时出现错误: {str(e)}")
            return None
    
    def calculate_usage_data(self, data):
        """根据历史数据计算今日和月度用电量"""
        try:
            conn = sqlite3.connect('electric_data.db')
            cursor = conn.cursor()
            
            # 获取当天最早的记录，用于计算今日用电量
            cursor.execute('''
                SELECT * FROM electric_records
                WHERE timestamp >= datetime('now', 'localtime', 'start of day')
                AND balance IS NOT NULL
                ORDER BY timestamp ASC
                LIMIT 1
            ''')
            today_first = cursor.fetchone()
            
            # 获取本月最早的记录，用于计算月度用电量
            cursor.execute('''
                SELECT * FROM electric_records
                WHERE timestamp >= datetime('now', 'localtime', 'start of month')
                AND balance IS NOT NULL
                ORDER BY timestamp ASC
                LIMIT 1
            ''')
            month_first = cursor.fetchone()
            
            # 计算今日用电量和月度用电量
            if today_first and today_first[2] is not None and data['balance'] is not None:
                # 今日电费变化（消费为正值，充值为负值）
                today_usage = float(today_first[2]) - float(data['balance'])
                if today_usage > 0:  # 消费了电费，才计算为用电量
                    data['usage_today'] = today_usage / float(data['price']) if data['price'] > 0 else 0
            
            if month_first and month_first[2] is not None and data['balance'] is not None:
                # 月度电费变化（消费为正值，充值为负值）
                month_usage = float(month_first[2]) - float(data['balance']) 
                if month_usage > 0:  # 消费了电费，才计算为用电量
                    data['usage_month'] = month_usage / float(data['price']) if data['price'] > 0 else 0
            
            conn.close()
            
            logging.info(f"计算用电量：今日={data.get('usage_today')}度，本月={data.get('usage_month')}度")
            return data
        except Exception as e:
            logging.error(f"计算用电量时出错: {str(e)}")
            return data
    
    def save_data(self, data):
        """保存数据到数据库"""
        if not data:
            logging.warning("保存数据失败：数据为空")
            return
            
        try:
            conn = sqlite3.connect('electric_data.db')
            cursor = conn.cursor()
            
            # 使用当前系统时间
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # 确保数值型字段不为None，否则使用默认值
            balance = float(data.get('balance', 0)) if data.get('balance') is not None else 0.0
            usage_today = float(data.get('usage_today', 0)) if data.get('usage_today') is not None else None
            usage_month = float(data.get('usage_month', 0)) if data.get('usage_month') is not None else None
            
            cursor.execute('''
                INSERT INTO electric_records (timestamp, balance, usage_today, usage_month, status, raw_data)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                current_time,
                balance,
                usage_today,
                usage_month,
                data.get('status', 'success'),
                data.get('raw_data', '')
            ))
            
            conn.commit()
            conn.close()
            
            # 检查是否需要发送预警
            if balance < config.LOW_BALANCE_THRESHOLD:
                self.send_alert(balance)
        except Exception as e:
            logging.error(f"保存数据失败: {str(e)}")
            # 如果发生错误，尝试关闭数据库连接
            try:
                conn.close()
            except:
                pass
    
    def send_alert(self, balance):
        """发送低余额预警邮件"""
        try:
            # 检查是否已经发送过预警（24小时内）
            conn = sqlite3.connect('electric_data.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM alerts
                WHERE alert_type = 'low_balance'
                AND timestamp > datetime('now', 'localtime', '-24 hours')
                AND sent = 1
            ''')
            
            if cursor.fetchone():
                conn.close()
                logging.info("24小时内已发送过预警邮件，跳过")
                return
            
            # 获取邮箱列表
            alert_emails = []
            if hasattr(config, 'ALERT_EMAILS') and config.ALERT_EMAILS:
                alert_emails = config.ALERT_EMAILS
            elif hasattr(config, 'ALERT_EMAIL'):
                alert_emails = [config.ALERT_EMAIL] # type: ignore
            else:
                logging.error("未配置预警邮箱")
                return
            
            # 创建邮件内容
            body = f"""
            您好！
            
            您的电费余额不足，请及时充值：
            
            当前余额: {balance:.2f} 元
            预警阈值: {config.LOW_BALANCE_THRESHOLD} 元
            查询时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            
            请及时前往 https://app.bupt.edu.cn/buptdf/wap/default/chong 进行充值。
            
            ---
            电费自动提醒系统
            """
            
            # 连接SMTP服务器
            server = smtplib.SMTP(config.EMAIL_SMTP_SERVER, config.EMAIL_SMTP_PORT)
            server.starttls()
            server.login(config.EMAIL_USERNAME, config.EMAIL_PASSWORD)
            
            # 发送给每个邮箱
            sent_count = 0
            for email in alert_emails:
                try:
                    msg = MIMEMultipart()
                    msg['From'] = config.EMAIL_USERNAME
                    msg['To'] = email
                    msg['Subject'] = "⚠️ 电费余额不足预警"
                    msg.attach(MIMEText(body, 'plain', 'utf-8'))
                    
                    text = msg.as_string()
                    server.sendmail(config.EMAIL_USERNAME, email, text)
                    sent_count += 1
                    logging.info(f"预警邮件已发送到: {email}")
                except Exception as e:
                    logging.error(f"发送邮件到 {email} 失败: {str(e)}")
            
            server.quit()
            
            # 记录预警
            cursor.execute('''
                INSERT INTO alerts (alert_type, message, sent)
                VALUES (?, ?, ?)
            ''', ('low_balance', f'余额不足预警: {balance}元，已发送{sent_count}封邮件', 1))
            
            conn.commit()
            conn.close()
            
            logging.info(f"预警邮件发送完成，成功发送{sent_count}封邮件，当前余额: {balance}元")
            
        except Exception as e:
            logging.error(f"发送预警邮件时出现错误: {str(e)}")
    
    def get_recent_records(self, limit=20):
        """获取最近的记录"""
        conn = sqlite3.connect('electric_data.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM electric_records 
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (limit,))
        
        records = cursor.fetchall()
        conn.close()
        
        return records
    
    def get_statistics(self):
        """获取统计数据"""
        conn = sqlite3.connect('electric_data.db')
        cursor = conn.cursor()
        
        # 最新数据
        cursor.execute('''
            SELECT * FROM electric_records 
            WHERE balance IS NOT NULL 
            ORDER BY timestamp DESC 
            LIMIT 1
        ''')
        latest = cursor.fetchone()
        
        # 今日用电量
        cursor.execute('''
            SELECT usage_today FROM electric_records
            WHERE timestamp >= datetime('now', 'localtime', 'start of day')
            AND usage_today IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT 1
        ''')
        row = cursor.fetchone()
        today_usage = row[0] if row else None
        
        # 本月用电量
        cursor.execute('''
            SELECT usage_month FROM electric_records
            WHERE timestamp >= datetime('now', 'localtime', 'start of month')
            AND usage_month IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT 1
        ''')
        row = cursor.fetchone()
        month_usage = row[0] if row else None

        # 余额趋势（最近24小时，按小时统计）
        cursor.execute('''
            SELECT strftime('%Y-%m-%d %H:00:00', timestamp) as hour, AVG(balance) as avg_balance
            FROM electric_records
            WHERE timestamp > datetime('now', 'localtime', '-24 hours')
            AND balance IS NOT NULL
            GROUP BY strftime('%Y-%m-%d %H', timestamp)
            ORDER BY hour
        ''')
        balance_trend_hourly = cursor.fetchall()
        
        # 余额趋势（最近30天，按天统计）
        cursor.execute('''
            SELECT date(timestamp) as date, AVG(balance) as avg_balance
            FROM electric_records
            WHERE timestamp > datetime('now', 'localtime', '-30 days')
            AND balance IS NOT NULL
            GROUP BY date(timestamp)
            ORDER BY date
        ''')
        balance_trend_daily = cursor.fetchall()
        
        # 余额趋势（最近12个月，按月统计）
        cursor.execute('''
            SELECT strftime('%Y-%m', timestamp) as month, AVG(balance) as avg_balance
            FROM electric_records
            WHERE timestamp > datetime('now', 'localtime', '-12 months')
            AND balance IS NOT NULL
            GROUP BY strftime('%Y-%m', timestamp)
            ORDER BY month
        ''')
        balance_trend_monthly = cursor.fetchall()
        
        conn.close()
        
        return {
            'latest': latest,
            'today_usage': today_usage if today_usage is not None else 0.0,
            'month_usage': month_usage if month_usage is not None else 0.0,
            'balance_trend_hourly': balance_trend_hourly,
            'balance_trend_daily': balance_trend_daily,
            'balance_trend_monthly': balance_trend_monthly
        }

# 创建监控实例
monitor = ElectricMonitor()

# Web路由
@app.route('/')
def index():
    """主页"""
    stats = monitor.get_statistics()
    records = monitor.get_recent_records(10)
    return render_template('index.html', stats=stats, records=records)

@app.route('/api/stats')
def api_stats():
    """获取统计数据API"""
    stats = monitor.get_statistics()
    return jsonify(stats)

@app.route('/api/records')
def api_records():
    """获取记录数据API"""
    limit = request.args.get('limit', 20, type=int)
    records = monitor.get_recent_records(limit)
    return jsonify({'records': records})

@app.route('/api/check', methods=['POST'])
def api_check():
    """立即检查电费API"""
    try:
        # 直接获取电费数据，内部会智能检查是否需要登录
        data = monitor.get_electric_data()
        if data:
            monitor.save_data(data)
              # 检查是否需要发送预警
            if float(data['balance']) < config.LOW_BALANCE_THRESHOLD:
                monitor.send_alert(data['balance'])
            
            return jsonify({
                'success': True, 
                'message': '检查完成',
                'data': data
            })
        else:
            return jsonify({'success': False, 'message': '获取数据失败'})
    except Exception as e:
        logging.error(f"API检查失败: {str(e)}")
        return jsonify({'success': False, 'message': f'检查失败: {str(e)}'})

@app.route('/api/records', methods=['DELETE'])
def api_clear_records():
    """清空所有记录API"""
    try:
        conn = sqlite3.connect('electric_data.db')
        cursor = conn.cursor()
        cursor.execute('DELETE FROM electric_records')
        cursor.execute('DELETE FROM alerts')
        conn.commit()
        conn.close()
        
        logging.info("用户清空了所有记录")
        return jsonify({'success': True, 'message': '记录已清空'})
    except Exception as e:
        logging.error(f"清空记录失败: {str(e)}")
        return jsonify({'success': False, 'message': f'清空失败: {str(e)}'})

@app.route('/api/records/<int:record_id>', methods=['DELETE'])
def api_delete_record(record_id):
    """删除单条记录API"""
    try:
        conn = sqlite3.connect('electric_data.db')
        cursor = conn.cursor()
        cursor.execute('DELETE FROM electric_records WHERE id = ?', (record_id,))
        
        if cursor.rowcount > 0:
            conn.commit()
            conn.close()
            logging.info(f"用户删除了记录ID: {record_id}")
            return jsonify({'success': True, 'message': '记录已删除'})
        else:
            conn.close()
            return jsonify({'success': False, 'message': '记录不存在'})
    except Exception as e:
        logging.error(f"删除记录失败: {str(e)}")
        return jsonify({'success': False, 'message': f'删除失败: {str(e)}'})

@app.route('/api/config', methods=['GET'])
def api_get_config():
    """获取系统配置API"""
    try:
        # 读取当前配置
        config_data = {
            'threshold': getattr(config, 'LOW_BALANCE_THRESHOLD', 10.0),
            'emails': getattr(config, 'ALERT_EMAILS', [config.ALERT_EMAIL] if hasattr(config, 'ALERT_EMAIL') else []), # type: ignore
            'check_frequency': getattr(config, 'CHECK_FREQUENCY_MINUTES', 60)
        }
        return jsonify({'success': True, 'config': config_data})
    except Exception as e:
        logging.error(f"获取配置失败: {str(e)}")
        return jsonify({'success': False, 'message': f'获取配置失败: {str(e)}'})

@app.route('/api/config', methods=['POST'])
def api_save_config():
    """保存系统配置API"""
    try:
        data = request.get_json()
        
        # 验证数据
        if not data:
            return jsonify({'success': False, 'message': '无效的配置数据'})
        
        threshold = data.get('threshold', 10.0)
        emails = data.get('emails', [])
        check_frequency = data.get('check_frequency', 60)
        
        # 验证邮箱格式
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        valid_emails = []
        for email in emails:
            email = email.strip()
            if email and re.match(email_pattern, email):
                valid_emails.append(email)
        
        if not valid_emails:
            return jsonify({'success': False, 'message': '请至少配置一个有效的邮箱地址'})
        
        # 更新配置文件
        config_content = f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
电费自动提醒系统配置文件
"""

# 北邮统一身份认证账号
BUPT_USERNAME = "{getattr(config, 'BUPT_USERNAME', '')}"
BUPT_PASSWORD = "{getattr(config, 'BUPT_PASSWORD', '')}"

# 邮箱配置
EMAIL_USERNAME = "{getattr(config, 'EMAIL_USERNAME', '')}"
EMAIL_PASSWORD = "{getattr(config, 'EMAIL_PASSWORD', '')}"
EMAIL_SMTP_SERVER = "{getattr(config, 'EMAIL_SMTP_SERVER', 'smtp.qq.com')}"
EMAIL_SMTP_PORT = {getattr(config, 'EMAIL_SMTP_PORT', 587)}

# 提醒邮箱列表
ALERT_EMAILS = {repr(valid_emails)}

# 余额阈值（元）
LOW_BALANCE_THRESHOLD = {threshold}

# 检查频率（分钟）
CHECK_FREQUENCY_MINUTES = {check_frequency}

# Web服务配置
WEB_HOST = "{getattr(config, 'WEB_HOST', '0.0.0.0')}"
WEB_PORT = {getattr(config, 'WEB_PORT', 5000)}
DEBUG_MODE = {getattr(config, 'DEBUG_MODE', False)}
'''
        
        # 备份原配置文件
        import shutil
        shutil.copy('config.py', 'config.py.backup')
        
        # 写入新配置
        with open('config.py', 'w', encoding='utf-8') as f:
            f.write(config_content)
        
        # 重新加载配置模块
        import importlib
        importlib.reload(config)
        
        logging.info(f"配置已更新 - 阈值: {threshold}, 邮箱数量: {len(valid_emails)}, 检查频率: {check_frequency}分钟")
        return jsonify({'success': True, 'message': '配置保存成功'})
        
    except Exception as e:
        logging.error(f"保存配置失败: {str(e)}")
        return jsonify({'success': False, 'message': f'保存失败: {str(e)}'})

@app.route('/api/logs', methods=['GET'])
def api_get_logs():
    """获取系统日志API"""
    try:
        limit = request.args.get('limit', 50, type=int)
        level = request.args.get('level', 'all')
        
        # 读取日志文件
        log_file_path = 'electric_monitor.log'
        logs = []
        
        if os.path.exists(log_file_path):
            with open(log_file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            # 解析日志行并过滤
            for line in reversed(lines):  # 倒序读取，最新的在前
                line = line.strip()
                if not line:
                    continue
                    
                # 解析日志格式: 2025-06-01 13:51:03,514 - INFO - 消息内容
                import re
                log_pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - (\w+) - (.+)'
                match = re.match(log_pattern, line)
                
                if match:
                    timestamp, log_level, message = match.groups()
                    
                    # 根据级别过滤
                    if level != 'all' and log_level != level:
                        continue
                    
                    logs.append({
                        'timestamp': timestamp,
                        'level': log_level,
                        'message': message
                    })
                    
                    # 限制数量
                    if len(logs) >= limit:
                        break
        
        return jsonify({'success': True, 'logs': logs})
        
    except Exception as e:
        logging.error(f"获取日志失败: {str(e)}")
        return jsonify({'success': False, 'message': f'获取日志失败: {str(e)}'})

@app.route('/api/logs', methods=['DELETE'])
def api_clear_logs():
    """清空系统日志API"""
    try:
        log_file_path = 'electric_monitor.log'
        
        # 清空日志文件
        if os.path.exists(log_file_path):
            with open(log_file_path, 'w', encoding='utf-8') as f:
                f.write('')
        
        logging.info("系统日志已被用户清空")
        return jsonify({'success': True, 'message': '日志已清空'})
        
    except Exception as e:
        logging.error(f"清空日志失败: {str(e)}")
        return jsonify({'success': False, 'message': f'清空日志失败: {str(e)}'})

# 定时任务
def scheduled_check():
    """定时检查电费"""
    logging.info("开始定时检查电费...")
    try:
        # 直接获取电费数据，内部会智能检查是否需要登录
        data = monitor.get_electric_data()
        if data:
            monitor.save_data(data)
            logging.info(f"定时检查完成 - 余额: {data['balance']}元")
            
            # 检查是否需要发送预警
            if float(data['balance']) < config.LOW_BALANCE_THRESHOLD:
                monitor.send_alert(data['balance'])
        else:
            logging.error("定时检查失败 - 无法获取数据")
    except Exception as e:
        logging.error(f"定时检查出错: {str(e)}")



def setup_scheduler():
    """设置调度器，防止重复添加任务"""
    # 清除可能存在的旧任务
    for job in scheduler.get_jobs():
        if job.id == 'electric_check':
            scheduler.remove_job('electric_check')
    
    # 添加新任务，设置ID和配置参数
    scheduler.add_job(
        func=scheduled_check,
        trigger="cron",
        minute=0,  # 每小时整点执行
        id='electric_check',  # 设置唯一ID
        max_instances=1,  # 最多同时运行1个实例
        coalesce=True,  # 如果错过执行时间，只运行最新的一次
        misfire_grace_time=300  # 允许5分钟的延迟执行
    )
    
    logging.info("定时任务已设置：每小时整点检查电费")

    # 注册退出时关闭调度器
    atexit.register(lambda: scheduler.shutdown())

if __name__ == '__main__':
    # 创建模板目录
    os.makedirs('templates', exist_ok=True)
    
    # 设置定时任务调度器
    global scheduler
    scheduler = BackgroundScheduler()
    # 设置定时任务（只在主进程中设置）
    setup_scheduler()
    if not scheduler.running:
        scheduler.start()
        logging.info("定时任务调度器已启动")
    
    logging.info("电费监控系统启动中...")
    logging.info(f"Web界面地址: http://localhost:{config.WEB_PORT}")
    logging.info("请确保已在config.py中配置正确的用户名密码")

    # 打印scheduler的所有任务
    logging.info("当前调度器任务列表:")
    for job in scheduler.get_jobs():
        logging.info(f"任务ID: {job.id}, 下次执行时间: {job.next_run_time}, 触发器: {job.trigger}")
    
    # 在生产环境中关闭调试模式避免重复任务
    debug_mode = getattr(config, 'DEBUG_MODE', False)
    
    # 添加这个环境变量可以禁用Flask的自动重载器
    os.environ['FLASK_DEBUG'] = '0' if not debug_mode else '1'
    
    # 如果在调试模式下，添加警告
    if debug_mode:
        logging.warning("警告：调试模式已启用，可能导致定时任务重复初始化。生产环境请在config.py中设置DEBUG_MODE=False")
    
    app.run(host=config.WEB_HOST, port=config.WEB_PORT, debug=debug_mode, use_reloader=debug_mode)
