#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
房间查询助手 - 帮助用户找到自己的宿舍信息
使用方法: python room_finder.py
"""

import requests
from bs4 import BeautifulSoup
import config
import json

class RoomFinder:
    def __init__(self):
        self.session = requests.Session()
    
    def login(self):
        """登录系统"""
        try:
            print("正在登录...")
            login_url = "https://auth.bupt.edu.cn/authserver/login"
            response = self.session.get(login_url, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            type_input = soup.find('input', {'name': 'type'})
            execution_input = soup.find('input', {'name': 'execution'})
            _eventId_input = soup.find('input', {'name': '_eventId'})
            
            if not type_input or not execution_input or not _eventId_input:
                print("❌ 登录页面结构异常")
                return False
            
            login_data = {
                'username': config.BUPT_USERNAME,
                'password': config.BUPT_PASSWORD,
                'type': type_input.get('value', ''), # type: ignore
                'execution': execution_input.get('value', ''), # type: ignore
                '_eventId': _eventId_input.get('value', '') # type: ignore
            }
            
            response = self.session.post(login_url, data=login_data, timeout=10)
            
            if 'CAS Login' in response.text:
                print("❌ 登录失败，请检查用户名和密码")
                return False
            
            print("✅ 登录成功")
            
            # 访问电费页面
            electric_url = "https://app.bupt.edu.cn/buptdf/wap/default/chong"
            response = self.session.get(electric_url, timeout=10)
            
            if response.status_code == 200:
                print("✅ 电费页面访问成功")
                return True
            else:
                print(f"❌ 电费页面访问失败: {response.status_code}")
                return False
            
        except Exception as e:
            print(f"❌ 登录过程出错: {e}")
            return False
    
    def get_areas(self):
        """获取校区列表"""
        areas = [
            {'id': 1, 'name': '西土城'},
            {'id': 2, 'name': '沙河'}
        ]
        return areas
    
    def get_apartments(self, area_id):
        """获取公寓列表"""
        try:
            url = "https://app.bupt.edu.cn/buptdf/wap/default/part"
            response = self.session.post(url, data={'areaid': area_id}, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('e') == 0:
                    return data['d']['data']
            return []
        except Exception as e:
            print(f"获取公寓数据出错: {e}")
            return []
    
    def get_floors(self, area_id, apartment_id):
        """获取楼层列表"""
        try:
            url = "https://app.bupt.edu.cn/buptdf/wap/default/floor"
            response = self.session.post(url, data={
                'partmentId': apartment_id,
                'areaid': area_id
            }, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('e') == 0:
                    return data['d']['data']
            return []
        except Exception as e:
            print(f"获取楼层数据出错: {e}")
            return []
    
    def get_rooms(self, area_id, apartment_id, floor_id):
        """获取房间列表"""
        try:
            url = "https://app.bupt.edu.cn/buptdf/wap/default/drom"
            response = self.session.post(url, data={
                'partmentId': apartment_id,
                'floorId': floor_id,
                'areaid': area_id
            }, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('e') == 0:
                    return data['d']['data']
            return []
        except Exception as e:
            print(f"获取房间数据出错: {e}")
            return []
    
    def search_room_by_name(self, target_room_name):
        """通过房间名搜索房间信息"""
        print(f"\n🔍 正在搜索房间: {target_room_name}")
        
        areas = self.get_areas()
        found_rooms = []
        
        for area in areas:
            print(f"\n检查校区: {area['name']}")
            apartments = self.get_apartments(area['id'])
            
            for apartment in apartments:
                print(f"  检查公寓: {apartment['partmentName']}")
                floors = self.get_floors(area['id'], apartment['partmentId'])
                
                for floor in floors:
                    print(f"    检查楼层: {floor['floorName']}")
                    rooms = self.get_rooms(area['id'], apartment['partmentId'], floor['floorId'])
                    
                    for room in rooms:
                        if target_room_name.lower() in room['dromName'].lower():
                            found_rooms.append({
                                'area_id': area['id'],
                                'area_name': area['name'],
                                'apartment_id': apartment['partmentId'],
                                'apartment_name': apartment['partmentName'],
                                'floor_id': floor['floorId'],
                                'floor_name': floor['floorName'],
                                'room_number': room['dromNum'],
                                'room_name': room['dromName']
                            })
                            print(f"      ✅ 找到匹配房间: {room['dromName']} (编号: {room['dromNum']})")
        
        return found_rooms
    
    def interactive_search(self):
        """交互式搜索"""
        print("\n=== 电费查询房间信息配置助手 ===")
        print("本工具帮助您找到宿舍房间的配置信息")
        
        while True:
            print("\n请选择操作:")
            print("1. 通过房间名搜索 (如: A楼102, S2楼301)")
            print("2. 浏览所有房间")
            print("3. 退出")
            
            choice = input("\n请输入选项 (1-3): ").strip()
            
            if choice == "1":
                room_name = input("请输入房间名 (如: A楼102): ").strip()
                if room_name:
                    found_rooms = self.search_room_by_name(room_name)
                    
                    if found_rooms:
                        print(f"\n✅ 找到 {len(found_rooms)} 个匹配的房间:")
                        for i, room in enumerate(found_rooms, 1):
                            print(f"\n{i}. {room['room_name']}")
                            print(f"   校区: {room['area_name']} (ID: {room['area_id']})")
                            print(f"   公寓: {room['apartment_name']}")
                            print(f"   楼层: {room['floor_name']}")
                            print(f"   房间编号: {room['room_number']}")
                            print(f"   配置代码:")
                            print(f"   AREA_ID = {room['area_id']}")
                            print(f"   APARTMENT_ID = \"{room['apartment_id']}\"")
                            print(f"   FLOOR_ID = \"{room['floor_id']}\"")
                            print(f"   ROOM_NUMBER = \"{room['room_number']}\"")
                        
                        # 询问是否测试电费查询
                        if len(found_rooms) == 1:
                            test = input(f"\n是否测试查询 {found_rooms[0]['room_name']} 的电费数据? (y/n): ").strip().lower()
                            if test == 'y':
                                self.test_electric_query(found_rooms[0])
                    else:
                        print(f"❌ 未找到匹配的房间: {room_name}")
                
            elif choice == "2":
                self.browse_all_rooms()
                
            elif choice == "3":
                print("退出程序")
                break
                
            else:
                print("❌ 无效选项，请重新选择")
    
    def browse_all_rooms(self):
        """浏览所有房间"""
        areas = self.get_areas()
        
        for area in areas:
            print(f"\n校区: {area['name']} (ID: {area['id']})")
            apartments = self.get_apartments(area['id'])
            
            for apartment in apartments[:3]:  # 限制显示前3个公寓
                print(f"  公寓: {apartment['partmentName']}")
                floors = self.get_floors(area['id'], apartment['partmentId'])
                
                for floor in floors[:2]:  # 限制显示前2个楼层
                    print(f"    楼层: {floor['floorName']}")
                    rooms = self.get_rooms(area['id'], apartment['partmentId'], floor['floorId'])
                    
                    for room in rooms[:5]:  # 限制显示前5个房间
                        print(f"      房间: {room['dromName']} (编号: {room['dromNum']})")
                
                if len(floors) > 2:
                    print(f"    ... 还有 {len(floors) - 2} 个楼层")
            
            if len(apartments) > 3:
                print(f"  ... 还有 {len(apartments) - 3} 个公寓")
    
    def test_electric_query(self, room_info):
        """测试电费查询"""
        try:
            print(f"\n🔍 测试查询 {room_info['room_name']} 的电费数据...")
            
            url = "https://app.bupt.edu.cn/buptdf/wap/default/search"
            response = self.session.post(url, data={
                'partmentId': room_info['apartment_id'],
                'floorId': room_info['floor_id'],
                'dromNumber': room_info['room_number'],
                'areaid': room_info['area_id']
            }, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                print(f"查询结果: {data}")
                
                if data.get('e') == 0:
                    electric_data = data.get('d', {}).get('data', {})
                    print(f"✅ 查询成功!")
                    print(f"   余额: {electric_data.get('surplus', 'N/A')} 元")
                    print(f"   总用电量: {electric_data.get('vTotal', 'N/A')} 度")
                    print(f"   电价: {electric_data.get('price', 'N/A')} 元/度")
                    print(f"   查询时间: {electric_data.get('time', 'N/A')}")
                else:
                    print(f"❌ 查询失败: {data.get('m', '未知错误')}")
            else:
                print(f"❌ 查询接口访问失败: {response.status_code}")
                
        except Exception as e:
            print(f"❌ 测试查询出错: {e}")

def main():
    finder = RoomFinder()
    
    if finder.login():
        finder.interactive_search()
    else:
        print("❌ 登录失败，请检查配置文件中的用户名和密码")

if __name__ == "__main__":
    main()
