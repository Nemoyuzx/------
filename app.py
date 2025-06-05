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
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS prediction_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                current_balance REAL NOT NULL,
                threshold REAL NOT NULL,
                predicted_days REAL,
                predicted_date TEXT,
                daily_avg REAL,
                weekday_avg REAL,
                weekend_avg REAL,
                prediction_method TEXT,
                confidence TEXT,
                actual_days REAL,
                accuracy_score REAL,
                is_evaluated INTEGER DEFAULT 0
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
        
        # 获取余额预测（使用配置的预测方法）
        prediction_method = getattr(config, 'PREDICTION_METHOD', 'advanced')
        prediction_threshold = getattr(config, 'PREDICTION_THRESHOLD', 10.0)
        
        if prediction_method == 'advanced':
            prediction = self.predict_balance_advanced(prediction_threshold, use_pattern_analysis=True)
        else:
            prediction = self.predict_balance_depletion(prediction_threshold)
        
        return {
            'latest': latest,
            'today_usage': today_usage if today_usage is not None else 0.0,
            'month_usage': month_usage if month_usage is not None else 0.0,
            'balance_trend_hourly': balance_trend_hourly,
            'balance_trend_daily': balance_trend_daily,
            'balance_trend_monthly': balance_trend_monthly,
            'prediction': prediction
        }

    def predict_balance_depletion(self, threshold=10.0):
        """
        预测电费余额何时会降到指定阈值以下
        
        Args:
            threshold: 预警阈值，默认10元
            
        Returns:
            dict: 包含预测结果的字典
        """
        try:
            conn = sqlite3.connect('electric_data.db')
            cursor = conn.cursor()
            
            # 获取当前余额
            cursor.execute('''
                SELECT balance FROM electric_records 
                WHERE balance IS NOT NULL 
                ORDER BY timestamp DESC 
                LIMIT 1
            ''')
            current_balance_row = cursor.fetchone()
            
            if not current_balance_row or current_balance_row[0] is None:
                logging.warning("无法获取当前余额，预测失败")
                conn.close()
                return {
                    'success': False,
                    'message': '无法获取当前余额',
                    'current_balance': 0.0,
                    'threshold': threshold,
                    'days_remaining': None,
                    'predicted_date': None,
                    'daily_usage_avg': 0.0,
                    'prediction_confidence': 'low'
                }
            
            current_balance = float(current_balance_row[0])
            
            # 如果当前余额已经低于阈值
            if current_balance <= threshold:
                conn.close()
                return {
                    'success': True,
                    'message': f'当前余额已低于{threshold}元',
                    'current_balance': current_balance,
                    'threshold': threshold,
                    'days_remaining': 0,
                    'predicted_date': datetime.now().strftime('%Y-%m-%d'),
                    'daily_usage_avg': 0.0,
                    'prediction_confidence': 'high'
                }
            
            # 计算最近7天的每日平均用电费用
            cursor.execute('''
                SELECT date(timestamp) as date, 
                       MIN(balance) as min_balance, 
                       MAX(balance) as max_balance,
                       COUNT(*) as record_count
                FROM electric_records 
                WHERE timestamp > datetime('now', '-7 days')
                AND balance IS NOT NULL
                GROUP BY date(timestamp)
                HAVING record_count >= 2
                ORDER BY date DESC
            ''')
            daily_usage_data = cursor.fetchall()
            
            if len(daily_usage_data) < 3:
                # 数据不足，使用最近30天的数据计算平均值
                cursor.execute('''
                    SELECT 
                        (MAX(balance) - MIN(balance)) / 
                        CAST((julianday('now') - julianday(MIN(timestamp))) AS REAL) as daily_avg
                    FROM electric_records 
                    WHERE timestamp > datetime('now', '-30 days')
                    AND balance IS NOT NULL
                ''')
                result = cursor.fetchone()
                daily_usage_avg = abs(float(result[0])) if result and result[0] else 1.0
                confidence = 'low'
            else:
                # 计算每日用电费用（取正值）
                daily_usages = []
                for i, (date, min_bal, max_bal, count) in enumerate(daily_usage_data):
                    if max_bal and min_bal:
                        daily_cost = abs(float(max_bal) - float(min_bal))
                        # 如果当天有充值（余额增加很多），则跳过
                        if daily_cost < 50:  # 假设单日用电不会超过50元
                            daily_usages.append(daily_cost)
                
                if daily_usages:
                    daily_usage_avg = sum(daily_usages) / len(daily_usages)
                    confidence = 'high' if len(daily_usages) >= 5 else 'medium'
                else:
                    daily_usage_avg = 1.0
                    confidence = 'low'
            
            # 如果平均用电费用太小，设置最小值
            if daily_usage_avg < 0.1:
                daily_usage_avg = 1.0
                confidence = 'low'
            
            # 计算预计天数
            remaining_amount = current_balance - threshold
            if daily_usage_avg > 0:
                days_remaining = remaining_amount / daily_usage_avg
                predicted_date = (datetime.now() + timedelta(days=int(days_remaining))).strftime('%Y-%m-%d')
            else:
                days_remaining = None
                predicted_date = None
                confidence = 'low'
            
            conn.close()
            
            logging.info(f"余额预测完成: 当前余额={current_balance}元, 日均用电费用={daily_usage_avg}元, 预计{days_remaining:.1f}天后降到{threshold}元以下")
            
            return {
                'success': True,
                'message': '预测成功',
                'current_balance': current_balance,
                'threshold': threshold,
                'days_remaining': round(days_remaining, 1) if days_remaining else None,
                'predicted_date': predicted_date,
                'daily_usage_avg': round(daily_usage_avg, 2),
                'prediction_confidence': confidence
            }
            
        except Exception as e:
            logging.error(f"余额预测时出错: {str(e)}")
            return {
                'success': False,
                'message': f'预测失败: {str(e)}',
                'current_balance': 0.0,
                'threshold': threshold,
                'days_remaining': None,
                'predicted_date': None,
                'daily_usage_avg': 0.0,
                'prediction_confidence': 'low'
            }
    
    def send_prediction_alert(self, prediction_data):
        """
        发送预测预警邮件
        
        Args:
            prediction_data: 预测数据字典
        """
        try:
            if not prediction_data or not prediction_data.get('success'):
                return
            
            days_remaining = prediction_data.get('days_remaining')
            if not days_remaining or days_remaining > 7:  # 只有7天内的预测才发送预警
                return
            
            # 检查是否在24小时内已发送过预测预警
            conn = sqlite3.connect('electric_data.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT COUNT(*) FROM alerts 
                WHERE alert_type = 'prediction_warning' 
                AND datetime(sent_time) > datetime('now', '-24 hours')
            ''')
            
            recent_alerts = cursor.fetchone()[0]
            if recent_alerts > 0:
                logging.info("24小时内已发送过预测预警，跳过发送")
                conn.close()
                return
            
            # 获取提醒邮箱列表
            alert_emails = []
            if hasattr(config, 'ALERT_EMAILS') and config.ALERT_EMAILS:
                alert_emails = config.ALERT_EMAILS
            
            if not alert_emails:
                logging.warning("未配置预警邮箱，无法发送预测预警")
                conn.close()
                return
            
            current_balance = prediction_data.get('current_balance', 0)
            threshold = prediction_data.get('threshold', 10)
            predicted_date = prediction_data.get('predicted_date', '未知')
            daily_avg = prediction_data.get('daily_usage_avg', 0)
            confidence = prediction_data.get('prediction_confidence', 'low')
            
            # 根据可信度设置提醒级别
            confidence_text = {'high': '高', 'medium': '中', 'low': '低'}.get(confidence, '低')
            urgency_level = '🔴 紧急' if days_remaining <= 3 else '🟡 提醒'
            
            # 创建邮件内容
            body = f"""
您好！

根据您的用电模式分析，预测您的电费余额可能即将不足：

{urgency_level} 预测预警
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 当前状况：
• 当前余额：{current_balance:.2f} 元
• 预警阈值：{threshold:.1f} 元
• 日均用电费用：{daily_avg:.2f} 元

🔮 预测结果：
• 预计剩余天数：{days_remaining:.1f} 天
• 预计到达日期：{predicted_date}
• 预测可信度：{confidence_text}

💡 建议：
{"• 建议您尽快充值，避免断电影响生活" if days_remaining <= 3 else "• 请关注电费余额，适时进行充值"}

🔗 充值链接：
https://app.bupt.edu.cn/buptdf/wap/default/chong

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
查询时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
本预测基于最近的用电历史数据分析得出，仅供参考。

---
电费自动提醒系统 - 智能预测服务
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
                    msg['Subject'] = f"🔮 电费余额预测预警 - 预计{days_remaining:.1f}天后不足"
                    msg.attach(MIMEText(body, 'plain', 'utf-8'))
                    
                    text = msg.as_string()
                    server.sendmail(config.EMAIL_USERNAME, email, text)
                    sent_count += 1
                    logging.info(f"预测预警邮件已发送到: {email}")
                except Exception as e:
                    logging.error(f"发送预测预警邮件到 {email} 失败: {str(e)}")
            
            server.quit()
            
            # 记录预警
            cursor.execute('''
                INSERT INTO alerts (alert_type, message, sent)
                VALUES (?, ?, ?)
            ''', ('prediction_warning', f'预测预警: 预计{days_remaining:.1f}天后余额降到{threshold}元以下，已发送{sent_count}封邮件', 1))
            
            conn.commit()
            conn.close()
            
            logging.info(f"预测预警邮件发送完成，成功发送{sent_count}封邮件，预计{days_remaining:.1f}天后余额不足")
            
        except Exception as e:
            logging.error(f"发送预测预警失败: {str(e)}")
    
    def predict_balance_advanced(self, threshold=10.0, use_pattern_analysis=True):
        """
        高级余额预测，考虑工作日/周末用电模式差异
        
        Args:
            threshold: 预警阈值，默认10元
            use_pattern_analysis: 是否使用模式分析，默认True
            
        Returns:
            dict: 包含详细预测结果的字典
        """
        try:
            conn = sqlite3.connect('electric_data.db')
            cursor = conn.cursor()
            
            # 获取当前余额
            cursor.execute('''
                SELECT balance FROM electric_records 
                WHERE balance IS NOT NULL 
                ORDER BY timestamp DESC 
                LIMIT 1
            ''')
            current_balance_row = cursor.fetchone()
            
            if not current_balance_row or current_balance_row[0] is None:
                logging.warning("无法获取当前余额，高级预测失败")
                conn.close()
                return self.predict_balance_depletion(threshold)  # 回退到基础预测
            
            current_balance = float(current_balance_row[0])
            
            # 如果当前余额已经低于阈值
            if current_balance <= threshold:
                conn.close()
                return {
                    'success': True,
                    'message': f'当前余额已低于{threshold}元',
                    'current_balance': current_balance,
                    'threshold': threshold,
                    'days_remaining': 0,
                    'predicted_date': datetime.now().strftime('%Y-%m-%d'),
                    'daily_usage_avg': 0.0,
                    'weekday_avg': 0.0,
                    'weekend_avg': 0.0,
                    'prediction_confidence': 'high',
                    'prediction_method': 'advanced'
                }
            
            if not use_pattern_analysis:
                # 简单预测
                basic_prediction = self.predict_balance_depletion(threshold)
                basic_prediction['prediction_method'] = 'basic'
                return basic_prediction
            
            # 获取最近30天的详细数据进行模式分析
            cursor.execute('''
                SELECT 
                    date(timestamp) as date,
                    strftime('%w', timestamp) as weekday,
                    MIN(balance) as min_balance,
                    MAX(balance) as max_balance,
                    COUNT(*) as record_count
                FROM electric_records 
                WHERE timestamp > datetime('now', '-30 days')
                AND balance IS NOT NULL
                GROUP BY date(timestamp)
                HAVING record_count >= 2
                ORDER BY date DESC
            ''')
            
            usage_data = cursor.fetchall()
            
            if len(usage_data) < 7:
                logging.info("数据不足，使用基础预测方法")
                conn.close()
                basic_prediction = self.predict_balance_depletion(threshold)
                basic_prediction['prediction_method'] = 'basic_fallback'
                return basic_prediction
            
            # 分析工作日和周末的用电模式
            weekday_usages = []  # 周一到周五
            weekend_usages = []  # 周六周日
            
            for date, weekday, min_bal, max_bal, count in usage_data:
                if max_bal and min_bal:
                    daily_cost = abs(float(max_bal) - float(min_bal))
                    # 过滤异常数据（充值等）
                    if daily_cost < 50:
                        weekday_num = int(weekday)  # 0=周日, 1=周一, ..., 6=周六
                        if weekday_num == 0 or weekday_num == 6:  # 周末
                            weekend_usages.append(daily_cost)
                        else:  # 工作日
                            weekday_usages.append(daily_cost)
            
            # 计算工作日和周末的平均用电费用
            weekday_avg = sum(weekday_usages) / len(weekday_usages) if weekday_usages else 0
            weekend_avg = sum(weekend_usages) / len(weekend_usages) if weekend_usages else 0
            
            # 如果某种模式数据不足，使用总体平均值
            if not weekday_usages or not weekend_usages:
                all_usages = weekday_usages + weekend_usages
                if all_usages:
                    overall_avg = sum(all_usages) / len(all_usages)
                    weekday_avg = weekday_avg or overall_avg
                    weekend_avg = weekend_avg or overall_avg
                else:
                    weekday_avg = weekend_avg = 1.0
            
            # 设置最小用电费用
            weekday_avg = max(weekday_avg, 0.1)
            weekend_avg = max(weekend_avg, 0.1)
            
            # 计算预测（考虑一周的循环）
            current_date = datetime.now()
            remaining_amount = current_balance - threshold
            total_cost = 0
            days_count = 0
            prediction_date = current_date
            
            # 模拟未来的用电，直到余额低于阈值
            while total_cost < remaining_amount and days_count < 365:  # 最多预测一年
                prediction_date = current_date + timedelta(days=days_count)
                weekday_num = prediction_date.weekday()  # 0=周一, 6=周日
                
                if weekday_num >= 5:  # 周末 (5=周六, 6=周日)
                    daily_cost = weekend_avg
                else:  # 工作日
                    daily_cost = weekday_avg
                
                total_cost += daily_cost
                days_count += 1
            
            # 计算置信度
            data_quality = min(len(weekday_usages) + len(weekend_usages), 20) / 20
            pattern_clarity = abs(weekday_avg - weekend_avg) / max(weekday_avg, weekend_avg)
            confidence_score = (data_quality + pattern_clarity) / 2
            
            if confidence_score > 0.7:
                confidence = 'high'
            elif confidence_score > 0.4:
                confidence = 'medium'
            else:
                confidence = 'low'
            
            # 计算整体日均用电费用（用于兼容性）
            overall_daily_avg = (weekday_avg * 5 + weekend_avg * 2) / 7
            
            conn.close()
            
            logging.info(f"高级余额预测完成: 当前余额={current_balance}元, 工作日均={weekday_avg:.2f}元, 周末均={weekend_avg:.2f}元, 预计{days_count}天后降到{threshold}元以下")
            
            return {
                'success': True,
                'message': '高级预测成功',
                'current_balance': current_balance,
                'threshold': threshold,
                'days_remaining': round(days_count, 1) if days_count > 0 else None,
                'predicted_date': prediction_date.strftime('%Y-%m-%d') if days_count > 0 else None,
                'daily_usage_avg': round(overall_daily_avg, 2),
                'weekday_avg': round(weekday_avg, 2),
                'weekend_avg': round(weekend_avg, 2),
                'prediction_confidence': confidence,
                'prediction_method': 'advanced',
                'data_points': {
                    'weekday_samples': len(weekday_usages),
                    'weekend_samples': len(weekend_usages),
                    'confidence_score': round(confidence_score, 2)
                }
            }
            
        except Exception as e:
            logging.error(f"高级余额预测时出错: {str(e)}")
            # 回退到基础预测
            basic_prediction = self.predict_balance_depletion(threshold)
            basic_prediction['prediction_method'] = 'basic_error_fallback'
            return basic_prediction
    
    def save_prediction_record(self, prediction_data):
        """
        保存预测记录用于后续准确性评估
        
        Args:
            prediction_data: 预测结果数据
        """
        try:
            conn = sqlite3.connect('electric_data.db')
            cursor = conn.cursor()
            
            # 创建预测记录表（如果不存在）
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS prediction_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    current_balance REAL NOT NULL,
                    threshold REAL NOT NULL,
                    predicted_days REAL,
                    predicted_date TEXT,
                    daily_avg REAL,
                    weekday_avg REAL,
                    weekend_avg REAL,
                    prediction_method TEXT,
                    confidence TEXT,
                    actual_days REAL,
                    accuracy_score REAL,
                    is_evaluated INTEGER DEFAULT 0
                )
            ''')
            
            # 插入预测记录
            cursor.execute('''
                INSERT INTO prediction_records 
                (timestamp, current_balance, threshold, predicted_days, predicted_date, 
                 daily_avg, weekday_avg, weekend_avg, prediction_method, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                prediction_data.get('current_balance', 0),
                prediction_data.get('threshold', 10),
                prediction_data.get('days_remaining'),
                prediction_data.get('predicted_date'),
                prediction_data.get('daily_usage_avg', 0),
                prediction_data.get('weekday_avg', 0),
                prediction_data.get('weekend_avg', 0),
                prediction_data.get('prediction_method', 'basic'),
                prediction_data.get('prediction_confidence', 'low')
            ))
            
            conn.commit()
            conn.close()
            logging.info("预测记录已保存")
            
        except Exception as e:
            logging.error(f"保存预测记录失败: {str(e)}")

    def evaluate_prediction_accuracy(self):
        """
        评估历史预测的准确性
        
        Returns:
            dict: 预测准确性统计信息
        """
        try:
            conn = sqlite3.connect('electric_data.db')
            cursor = conn.cursor()
            
            # 获取未评估的预测记录
            cursor.execute('''
                SELECT id, timestamp, current_balance, threshold, predicted_days, 
                       predicted_date, prediction_method
                FROM prediction_records 
                WHERE is_evaluated = 0 AND predicted_days IS NOT NULL
                ORDER BY timestamp ASC
            ''')
            
            unevaluated_predictions = cursor.fetchall()
            evaluated_count = 0
            
            for pred_id, pred_timestamp, pred_balance, threshold, predicted_days, predicted_date, method in unevaluated_predictions:
                # 查找实际到达阈值的时间
                cursor.execute('''
                    SELECT timestamp, balance
                    FROM electric_records
                    WHERE timestamp > ? AND balance <= ?
                    ORDER BY timestamp ASC
                    LIMIT 1
                ''', (pred_timestamp, threshold))
                
                actual_result = cursor.fetchone()
                
                if actual_result:
                    actual_timestamp, actual_balance = actual_result
                    
                    # 计算实际天数
                    pred_dt = datetime.strptime(pred_timestamp, '%Y-%m-%d %H:%M:%S')
                    actual_dt = datetime.strptime(actual_timestamp, '%Y-%m-%d %H:%M:%S')
                    actual_days = (actual_dt - pred_dt).total_seconds() / (24 * 3600)
                    
                    # 计算准确性分数 (0-100, 100为完全准确)
                    if predicted_days > 0:
                        error_ratio = abs(actual_days - predicted_days) / predicted_days
                        accuracy_score = max(0, 100 - error_ratio * 100)
                    else:
                        accuracy_score = 0
                    
                    # 更新预测记录
                    cursor.execute('''
                        UPDATE prediction_records 
                        SET actual_days = ?, accuracy_score = ?, is_evaluated = 1
                        WHERE id = ?
                    ''', (actual_days, accuracy_score, pred_id))
                    
                    evaluated_count += 1
            
            conn.commit()
            
            # 获取准确性统计
            cursor.execute('''
                SELECT 
                    prediction_method,
                    COUNT(*) as total_predictions,
                    AVG(accuracy_score) as avg_accuracy,
                    MIN(accuracy_score) as min_accuracy,
                    MAX(accuracy_score) as max_accuracy,
                    COUNT(CASE WHEN accuracy_score >= 80 THEN 1 END) as high_accuracy_count
                FROM prediction_records 
                WHERE is_evaluated = 1 AND accuracy_score IS NOT NULL
                GROUP BY prediction_method
            ''')
            
            accuracy_stats = cursor.fetchall()
            
            # 获取总体统计
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_evaluated,
                    AVG(accuracy_score) as overall_accuracy,
                    COUNT(CASE WHEN accuracy_score >= 80 THEN 1 END) as high_accuracy_total
                FROM prediction_records 
                WHERE is_evaluated = 1 AND accuracy_score IS NOT NULL
            ''')
            
            overall_stats = cursor.fetchone()
            
            conn.close()
            
            result = {
                'success': True,
                'evaluated_count': evaluated_count,
                'overall_stats': {
                    'total_predictions': overall_stats[0] if overall_stats else 0,
                    'average_accuracy': round(overall_stats[1], 2) if overall_stats and overall_stats[1] else 0,
                    'high_accuracy_rate': round((overall_stats[2] / overall_stats[0] * 100), 2) if overall_stats and overall_stats[0] > 0 else 0
                },
                'method_stats': []
            }
            
            for method, total, avg_acc, min_acc, max_acc, high_acc_count in accuracy_stats:
                result['method_stats'].append({
                    'method': method,
                    'total_predictions': total,
                    'average_accuracy': round(avg_acc, 2) if avg_acc else 0,
                    'min_accuracy': round(min_acc, 2) if min_acc else 0,
                    'max_accuracy': round(max_acc, 2) if max_acc else 0,
                    'high_accuracy_rate': round((high_acc_count / total * 100), 2) if total > 0 else 0
                })
            
            if evaluated_count > 0:
                logging.info(f"预测准确性评估完成，评估了{evaluated_count}个预测记录")
            
            return result
            
        except Exception as e:
            logging.error(f"评估预测准确性失败: {str(e)}")
            return {
                'success': False,
                'message': f'评估失败: {str(e)}',
                'evaluated_count': 0,
                'overall_stats': {'total_predictions': 0, 'average_accuracy': 0, 'high_accuracy_rate': 0},
                'method_stats': []
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
              # 检查是否需要发送传统余额预警
            if float(data['balance']) < config.LOW_BALANCE_THRESHOLD:
                monitor.send_alert(data['balance'])
            
            # 检查预测性预警
            prediction_data = monitor.predict_balance_depletion(config.LOW_BALANCE_THRESHOLD)
            if (prediction_data.get('success') and 
                prediction_data.get('days_remaining') is not None and
                prediction_data.get('days_remaining') <= 7):
                monitor.send_prediction_alert(prediction_data)
            
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
        cursor.execute('DELETE FROM prediction_records')
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

@app.route('/api/prediction', methods=['GET'])
def api_get_prediction():
    """获取余额预测API"""
    try:
        # 获取阈值参数，默认使用配置值
        threshold = float(request.args.get('threshold', getattr(config, 'PREDICTION_THRESHOLD', 10.0)))
        
        # 获取预测方法参数
        method = request.args.get('method', getattr(config, 'PREDICTION_METHOD', 'advanced'))
        
        # 获取预测数据
        if method == 'advanced':
            prediction = monitor.predict_balance_advanced(threshold, use_pattern_analysis=True)
        else:
            prediction = monitor.predict_balance_depletion(threshold)
        
        # 保存预测记录（如果启用）
        if getattr(config, 'PREDICTION_ACCURACY_EVALUATION', True) and prediction.get('success'):
            monitor.save_prediction_record(prediction)
        
        return jsonify(prediction)
    except Exception as e:
        logging.error(f"获取预测失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'获取预测失败: {str(e)}',
            'current_balance': 0.0,
            'threshold': 10.0,
            'days_remaining': None,
            'predicted_date': None,
            'daily_usage_avg': 0.0,
            'prediction_confidence': 'low'
        })

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

@app.route('/api/prediction/analytics')
def api_prediction_analytics():
    """预测分析API"""
    try:
        # 示例数据结构，后续可替换为真实分析
        analytics = {
            "analysis_period": 30,
            "usage_pattern": {
                "weekday_avg": 2.35,
                "weekday_samples": 20,
                "weekend_avg": 1.85,
                "weekend_samples": 8,
                "overall_avg": 2.15,
                "pattern_difference": 0.5
            }
        }
        return jsonify({"success": True, "analytics": analytics})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/api/prediction/accuracy')
def api_prediction_accuracy():
    """预测准确性统计API"""
    try:
        # 示例数据结构，后续可替换为真实统计
        data = {
            "success": True,
            "overall_stats": {
                "total_predictions": 12,
                "average_accuracy": 92.3,
                "high_accuracy_rate": 75.0
            },
            "method_stats": [
                {"method": "advanced", "total_predictions": 7, "average_accuracy": 95.1},
                {"method": "basic", "total_predictions": 5, "average_accuracy": 88.0}
            ],
            "evaluated_count": 2
        }
        return jsonify(data)
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

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
            
            # 检查是否需要发送传统余额预警
            if float(data['balance']) < config.LOW_BALANCE_THRESHOLD:
                monitor.send_alert(data['balance'])
            
            # 检查预测性预警
            prediction_threshold = getattr(config, 'PREDICTION_THRESHOLD', config.LOW_BALANCE_THRESHOLD)
            alert_days = getattr(config, 'PREDICTION_ALERT_DAYS', 7)
            prediction_method = getattr(config, 'PREDICTION_METHOD', 'advanced')
            
            if prediction_method == 'advanced':
                prediction_data = monitor.predict_balance_advanced(prediction_threshold, use_pattern_analysis=True)
            else:
                prediction_data = monitor.predict_balance_depletion(prediction_threshold)
            
            # 保存预测记录（如果启用）
            if getattr(config, 'PREDICTION_ACCURACY_EVALUATION', True) and prediction_data.get('success'):
                monitor.save_prediction_record(prediction_data)
            
            # 发送预测预警
            if (prediction_data.get('success') and 
                prediction_data.get('days_remaining') is not None and
                prediction_data.get('days_remaining') <= alert_days):
                monitor.send_prediction_alert(prediction_data)
            
            # 定期评估预测准确性
            if getattr(config, 'PREDICTION_ACCURACY_EVALUATION', True):
                monitor.evaluate_prediction_accuracy()
                
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
    
    # 启动定时任务调度器
    scheduler = BackgroundScheduler()
    setup_scheduler()
    if not scheduler.running:
        scheduler.start()
        logging.info("定时任务调度器已启动")
    debug_mode = getattr(config, 'DEBUG_MODE', False)
    app.run(host=getattr(config, 'WEB_HOST', '0.0.0.0'), port=getattr(config, 'WEB_PORT', 5100), debug=debug_mode)
