# services/matching_service.py
import json
import re
from typing import Dict, Any, Optional, List
from datetime import datetime
import logging

from core.database import get_conn
from services.coze_service import coze_service

logger = logging.getLogger(__name__)


class OrderData:
    """订单数据类"""
    
    def __init__(self, **kwargs):
        self.plate_number: Optional[str] = kwargs.get('plate_number')
        self.driver_name: Optional[str] = kwargs.get('driver_name')
        self.id_card: Optional[str] = kwargs.get('id_card')
        self.phone: Optional[str] = kwargs.get('phone')
        self.category: Optional[str] = kwargs.get('category')
        self.has_waybill: Optional[str] = kwargs.get('has_waybill')

    def is_complete(self) -> bool:
        """检查6个字段是否都存在"""
        return all([
            self.plate_number, self.driver_name, self.id_card,
            self.phone, self.category, self.has_waybill
        ])

    def get_missing_fields(self) -> List[str]:
        """获取缺失的字段名"""
        missing = []
        field_map = {
            "plate_number": "车号",
            "driver_name": "司机姓名",
            "id_card": "身份证号",
            "phone": "司机电话",
            "category": "品类",
            "has_waybill": "联单状态"
        }
        for key, name in field_map.items():
            if not getattr(self, key):
                missing.append(name)
        return missing

    def normalize(self):
        """执行数据清洗和映射"""
        # 品类映射规则
        category_map = {
            "电动": "电动车",
            "黑皮": "黑皮",
            "新能源": "新能源",
            "通信": "通信",
            "摩托车": "摩托车",
            "大白": "大白"
        }
        if self.category:
            for k, v in category_map.items():
                if k in self.category:
                    self.category = v
                    break

        # 联单状态映射规则
        waybill_map = {
            "带": "带",
            "有": "带",
            "自带": "带",
            "有联单": "带",
            "无": "不带",
            "没有": "不带",
            "无联单": "不带"
        }
        if self.has_waybill:
            for k, v in waybill_map.items():
                if k in self.has_waybill:
                    self.has_waybill = v
                    break
            if not self.has_waybill:
                self.has_waybill = "不带"

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'plate_number': self.plate_number,
            'driver_name': self.driver_name,
            'id_card': self.id_card,
            'phone': self.phone,
            'category': self.category,
            'has_waybill': self.has_waybill
        }


class MatchingService:
    """匹配服务 - 处理报单匹配逻辑"""
    
    def __init__(self):
        # 可以使用Redis替代内存存储
        self.conversation_state: Dict[int, Dict[str, Any]] = {}
    
    async def extract_info_with_coze(self, message: str) -> OrderData:
        """调用Coze提取结构化信息"""
        try:
            # 构建提示词
            prompt = f"""
            你是一个物流报单助手。请从用户的这句话中提取以下6个字段：车号、司机姓名、身份证号、司机电话、品类、联单状态。
            用户消息：{message}

            要求：
            1. 只返回标准的 JSON 格式，不要包含 markdown 标记
            2. 如果某个字段没提到，该字段值为 null
            3. 字段名必须使用英文：plate_number, driver_name, id_card, phone, category, has_waybill
            4. 联单状态(has_waybill)只提取为 '带' 或 '不带' 两种值：
               - 如果用户提到"有联单"、"自带联单"、"有"等，返回 "带"
               - 如果用户提到"无联单"、"没有联单"、"无"等，返回 "不带"
               - 不确定时返回 null

            示例输出：{{"plate_number": "冀A013TJ", "driver_name": "黄立军", "id_card": "132325197104084410", "phone": "13803364825", "category": "电动", "has_waybill": "带"}}
            """
            
            # 调用Coze服务
            response = await coze_service.chat_sync(prompt, "extract_" + str(hash(message)))
            
            # 清理JSON
            response = re.sub(r'```json|```', '', response).strip()
            data = json.loads(response)
            
            return OrderData(**data)
            
        except Exception as e:
            logger.error(f"Coze提取失败: {e}")
            return OrderData()
    
    def generate_missing_hint(self, missing_fields: List[str]) -> str:
        """生成缺失字段提示"""
        hint_parts = []
        for field in missing_fields:
            if field == "品类":
                hint_parts.append("“品类”（可选：电动/黑皮/新能源/通信/摩托车/大白）")
            elif field == "联单状态":
                hint_parts.append("“联单状态”（请回复：带 或 不带）")
            else:
                hint_parts.append(f"“{field}”")

        if len(hint_parts) == 1:
            return f"请补充{hint_parts[0]}信息。"
        else:
            last = hint_parts.pop()
            return f"请补充{', '.join(hint_parts)}和{last}信息。"
    
    async def process_chat_message(self, user_id: int, message: str) -> dict:
        """处理聊天消息"""
        # 1. 获取或初始化当前用户状态
        current_data = self.conversation_state.get(user_id, {})
        temp_order = OrderData(**current_data)
        
        # 2. 调用Coze提取新信息
        new_info = await self.extract_info_with_coze(message)
        
        # 3. 合并信息
        for field in ['plate_number', 'driver_name', 'id_card', 'phone', 'category', 'has_waybill']:
            val = getattr(new_info, field)
            if val:
                setattr(temp_order, field, val)
        
        # 更新状态
        self.conversation_state[user_id] = temp_order.to_dict()
        
        # 4. 校验完整性
        if not temp_order.is_complete():
            missing = temp_order.get_missing_fields()
            hint_text = self.generate_missing_hint(missing)
            missing_str = "、".join(missing)
            
            return {
                "type": "incomplete",
                "message": f"收到部分信息。还缺少：{missing_str}。\n\n{hint_text}",
                "data": temp_order.to_dict()
            }
        
        # 5. 信息完整 -> 数据清洗
        temp_order.normalize()
        self.conversation_state[user_id] = temp_order.to_dict()
        
        # 6. 生成确认表格
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        table_md = f"""
### 报单信息确认
| 报单日期 | 司机电话 | 司机姓名 | 车号 | 品类 | 联单状态 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| {current_date} | {temp_order.phone} | {temp_order.driver_name} | {temp_order.plate_number} | {temp_order.category} | {temp_order.has_waybill} |

✅ 信息已完整。请回复 **“确认”** 提交报单，或回复 **“取消”** 重新填写。
        """
        
        return {
            "type": "complete",
            "message": table_md,
            "data": temp_order.to_dict()
        }
    
    async def confirm_order(self, user_id: int) -> dict:
        """用户确认后将数据写入数据库"""
        if user_id not in self.conversation_state:
            return {"success": False, "msg": "❌ 没有找到待确认的订单信息"}
        
        data = self.conversation_state[user_id]
        
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO orders 
                        (user_id, plate_number, driver_name, id_card, phone, category, has_waybill, status, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        user_id,
                        data['plate_number'],
                        data['driver_name'],
                        data['id_card'],
                        data['phone'],
                        data['category'],
                        data['has_waybill'],
                        'confirmed',
                        datetime.now()
                    ))
                    
                    order_id = cur.lastrowid
                    conn.commit()
                    
                    # 清除会话状态
                    del self.conversation_state[user_id]
                    
                    return {"success": True, "msg": f"✅ 报单成功！单号：{order_id}"}
                    
        except Exception as e:
            logger.error(f"数据库写入失败: {e}")
            return {"success": False, "msg": f"❌ 数据库写入失败：{str(e)}"}
    
    def cancel_order(self, user_id: int) -> dict:
        """取消当前报单"""
        if user_id in self.conversation_state:
            del self.conversation_state[user_id]
            return {"success": True, "msg": "🗑️ 已取消当前报单，请重新开始。"}
        return {"success": False, "msg": "当前没有进行中的报单。"}
    
    async def find_matching_booking(self, content_json: Dict, user_id: int, doc_type: str) -> List[Dict]:
        """查找匹配的报单"""
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    # 根据单据类型提取关键字段
                    if doc_type == 'weighbridge':
                        # 磅单：用车号匹配
                        vehicle_no = content_json.get('vehicle_no')
                        if vehicle_no:
                            cur.execute("""
                                SELECT id, plate_number, driver_name, category, created_at
                                FROM orders
                                WHERE user_id = %s AND plate_number LIKE %s
                                ORDER BY created_at DESC
                                LIMIT 5
                            """, (user_id, f"%{vehicle_no}%"))
                    
                    elif doc_type == 'manifest':
                        # 联单：用司机姓名或车牌匹配
                        p1 = content_json.get('part1', {})
                        p2 = content_json.get('part2', {})
                        
                        driver = p2.get('driver')
                        vehicle = p2.get('vehicle_plate')
                        
                        if driver or vehicle:
                            sql = "SELECT id, plate_number, driver_name, category, created_at FROM orders WHERE user_id = %s"
                            params = [user_id]
                            
                            if driver:
                                sql += " AND driver_name LIKE %s"
                                params.append(f"%{driver}%")
                            
                            if vehicle:
                                sql += " AND plate_number LIKE %s"
                                params.append(f"%{vehicle}%")
                            
                            sql += " ORDER BY created_at DESC LIMIT 5"
                            cur.execute(sql, tuple(params))
                    
                    rows = cur.fetchall()
                    
                    candidates = []
                    for row in rows:
                        candidates.append({
                            "booking_id": row['id'],
                            "plate_number": row['plate_number'],
                            "driver_name": row['driver_name'],
                            "category": row['category'],
                            "created_at": row['created_at'].isoformat() if row['created_at'] else None,
                            "match_score": 0.8  # 可以计算实际匹配度
                        })
                    
                    return candidates
                    
        except Exception as e:
            logger.error(f"查找匹配报单失败: {e}")
            return []


# 创建单例
matching_service = MatchingService()