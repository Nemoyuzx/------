#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置向导 - 帮助用户设置实际凭据
"""

import os
import shutil
import getpass

def setup_config():
    """配置向导"""
    print("=" * 60)
    print("              电费监控系统配置向导")
    print("=" * 60)
    print()
    
    # 检查配置文件
    config_file = "config.py"
    example_file = "config.py.example"
    
    if not os.path.exists(example_file):
        print(f"❌ 找不到模板文件 {example_file}")
        return False
    
    if os.path.exists(config_file):
        choice = input(f"配置文件 {config_file} 已存在，是否覆盖？ (y/N): ").strip().lower()
        if choice != 'y':
            print("配置取消")
            return False
        
        # 备份现有配置
        backup_file = f"{config_file}.backup"
        shutil.copy2(config_file, backup_file)
        print(f"已备份现有配置到 {backup_file}")
    
    print("请填写以下配置信息：")
    print()
    
    # 收集用户输入
    config_data = {}
    
    # 北邮账号信息
    print("1. 北邮统一身份认证信息")
    config_data['BUPT_USERNAME'] = input("   学号: ").strip()
    config_data['BUPT_PASSWORD'] = getpass.getpass("   密码: ").strip()
    print()
    
    # 邮箱信息
    print("2. 邮件发送配置")
    print("   注意：如使用QQ邮箱，密码应为授权码，不是QQ密码")
    config_data['EMAIL_USERNAME'] = input("   发送邮箱: ").strip()
    config_data['EMAIL_PASSWORD'] = getpass.getpass("   邮箱密码/授权码: ").strip()
    config_data['ALERT_EMAIL'] = input("   接收预警邮箱 [默认: nemo.yzx@bupt.edu.com]: ").strip()
    
    if not config_data['ALERT_EMAIL']:
        config_data['ALERT_EMAIL'] = "nemo.yzx@bupt.edu.com"
    
    # SMTP服务器设置
    email_domain = config_data['EMAIL_USERNAME'].split('@')[-1].lower()
    if 'qq.com' in email_domain:
        smtp_server = "smtp.qq.com"
        smtp_port = 587
    elif '163.com' in email_domain:
        smtp_server = "smtp.163.com"
        smtp_port = 25
    elif '126.com' in email_domain:
        smtp_server = "smtp.126.com"
        smtp_port = 25
    elif 'gmail.com' in email_domain:
        smtp_server = "smtp.gmail.com"
        smtp_port = 587
    else:
        smtp_server = input("   SMTP服务器: ").strip()
        smtp_port = int(input("   SMTP端口: ").strip())
    
    config_data['EMAIL_SMTP_SERVER'] = smtp_server
    config_data['EMAIL_SMTP_PORT'] = smtp_port
    print(f"   自动检测SMTP: {smtp_server}:{smtp_port}")
    print()
    
    # 其他设置
    print("3. 其他设置")
    threshold = input("   余额预警阈值（元）[默认: 10.0]: ").strip()
    config_data['LOW_BALANCE_THRESHOLD'] = float(threshold) if threshold else 10.0
    
    port = input("   Web服务端口 [默认: 5000]: ").strip()
    config_data['WEB_PORT'] = int(port) if port else 5000
    print()
    
    # 确认配置
    print("配置信息确认：")
    print(f"学号: {config_data['BUPT_USERNAME']}")
    print(f"发送邮箱: {config_data['EMAIL_USERNAME']}")
    print(f"接收邮箱: {config_data['ALERT_EMAIL']}")
    print(f"SMTP服务器: {config_data['EMAIL_SMTP_SERVER']}:{config_data['EMAIL_SMTP_PORT']}")
    print(f"预警阈值: {config_data['LOW_BALANCE_THRESHOLD']} 元")
    print(f"Web端口: {config_data['WEB_PORT']}")
    print()
    
    confirm = input("确认无误并保存配置？ (Y/n): ").strip().lower()
    if confirm == 'n':
        print("配置取消")
        return False
    
    # 生成配置文件
    config_content = f"""# 配置文件 - 电费自动提醒系统
# 自动生成于 {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

# 北邮统一身份认证用户名和密码
BUPT_USERNAME = "{config_data['BUPT_USERNAME']}"
BUPT_PASSWORD = "{config_data['BUPT_PASSWORD']}"

# 邮件发送配置
EMAIL_SMTP_SERVER = "{config_data['EMAIL_SMTP_SERVER']}"
EMAIL_SMTP_PORT = {config_data['EMAIL_SMTP_PORT']}
EMAIL_USERNAME = "{config_data['EMAIL_USERNAME']}"
EMAIL_PASSWORD = "{config_data['EMAIL_PASSWORD']}"
ALERT_EMAIL = "{config_data['ALERT_EMAIL']}"

# 电费预警阈值（元）
LOW_BALANCE_THRESHOLD = {config_data['LOW_BALANCE_THRESHOLD']}

# Web服务配置
WEB_HOST = "0.0.0.0"
WEB_PORT = {config_data['WEB_PORT']}
DEBUG_MODE = True
"""
    
    # 保存配置文件
    with open(config_file, 'w', encoding='utf-8') as f:
        f.write(config_content)
    
    print(f"✅ 配置已保存到 {config_file}")
    print()
    
    # 测试配置
    test_choice = input("是否测试配置？ (Y/n): ").strip().lower()
    if test_choice != 'n':
        test_configuration()
    
    return True

def test_configuration():
    """测试配置"""
    print()
    print("测试配置...")
    
    try:
        import config
        print("✅ 配置文件加载成功")
        
        # 测试必要字段
        required_fields = ['BUPT_USERNAME', 'BUPT_PASSWORD', 'EMAIL_USERNAME', 'EMAIL_PASSWORD']
        for field in required_fields:
            if hasattr(config, field) and getattr(config, field):
                print(f"✅ {field} 已配置")
            else:
                print(f"❌ {field} 未配置或为空")
        
        print()
        print("配置测试完成！")
        print("现在可以运行主程序了：")
        print("  python app.py")
        
    except Exception as e:
        print(f"❌ 配置测试失败: {str(e)}")

def show_usage():
    """显示使用说明"""
    print()
    print("=" * 60)
    print("使用说明:")
    print("1. 配置完成后，运行主程序：python app.py")
    print("2. 在浏览器中访问 http://localhost:端口号")
    print("3. 系统会每小时自动检查电费")
    print("4. 余额不足时会自动发送邮件预警")
    print()
    print("如需修改配置，重新运行此脚本即可")
    print("=" * 60)

if __name__ == "__main__":
    if setup_config():
        show_usage()
    else:
        print("配置失败或取消")
