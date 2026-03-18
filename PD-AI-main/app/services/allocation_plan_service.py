"""
动态分配方案服务 - 冶炼厂资源动态分配档案管理
"""
import logging
import json
from typing import List, Dict, Optional, Any
from datetime import date, datetime

import pymysql
from app.services.contract_service import get_db_config, get_conn

logger = logging.getLogger(__name__)

class AllocationPlanService:
    """动态分配方案服务类"""

    def __init__(self):
        self.table_name = "t_allocation_plan"

    def _get_connection(self):
        """内部辅助方法：获取数据库连接"""
        config = get_db_config()
        return get_conn(config)

    def _serialize_json(self, data: Any) -> Optional[str]:
        """辅助方法：将 Python 对象序列化为 JSON 字符串"""
        if data is None:
            return None
        if isinstance(data, str):
            # 如果已经是字符串，尝试解析再序列化以确保格式合法，或者直接返回
            try:
                json.loads(data)
                return data
            except:
                return data 
        return json.dumps(data, ensure_ascii=False)

    def _deserialize_json(self, row: Optional[Dict]) -> Optional[Dict]:
        """辅助方法：将行数据中的 JSON 字段反序列化为 Python 对象"""
        if not row:
            return None
        
        json_fields = ['plan_details', 'input_factors', 'expected_kpi']
        for field in json_fields:
            val = row.get(field)
            if val and isinstance(val, str):
                try:
                    row[field] = json.loads(val)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON in {field} for plan {row.get('plan_id')}")
                    row[field] = None # 或者保留原字符串
        return row

    def create_plan(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建新的分配方案（默认为草稿）"""
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)

            # 强制转换 JSON 字段为字符串
            plan_details = data.get('plan_details')
            if not plan_details:
                return {"success": False, "error": "plan_details is required."}
            
            sql = f"""
                INSERT INTO {self.table_name} 
                (biz_date, category_range, plan_details, input_factors, 
                 expected_kpi, status, creator, execute_log)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            params = (
                data.get('biz_date'),
                data.get('category_range'),
                self._serialize_json(plan_details),
                self._serialize_json(data.get('input_factors')),
                self._serialize_json(data.get('expected_kpi')),
                data.get('status', 0),  # 默认 0-草稿
                data.get('creator'),
                data.get('execute_log')
            )

            cursor.execute(sql, params)
            conn.commit()
            
            plan_id = cursor.lastrowid
            new_record = self._get_record_by_cursor(cursor, plan_id)
            
            return {"success": True, "data": new_record}

        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error creating allocation plan: {e}")
            return {"success": False, "error": str(e)}
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def update_plan_status(self, plan_id: int, new_status: int, operator: Optional[str] = None) -> Dict[str, Any]:
        """
        更新方案状态
        业务规则检查：
        - 草稿(0) -> 已发布(1)
        - 已发布(1) -> 执行中(2)
        - 执行中(2) -> 已完成(3) 或 已取消(4)
        - 其他非法流转拒绝
        """
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)

            # 1. 获取当前状态
            current_record = self._get_record_by_cursor(cursor, plan_id)
            if not current_record:
                return {"success": False, "error": f"Plan {plan_id} not found."}
            
            current_status = current_record['status']
            
            # 2. 简单的状态机校验 (可根据实际需求放宽或收紧)
            allowed_transitions = {
                0: [1, 4], # 草稿 -> 发布/取消
                1: [2, 4], # 发布 -> 执行/取消
                2: [3, 4], # 执行 -> 完成/取消
                3: [],     # 已完成不可变
                4: []      # 已取消不可变
            }
            
            if new_status not in allowed_transitions.get(current_status, []):
                return {
                    "success": False, 
                    "error": f"Invalid status transition from {current_status} to {new_status}."
                }

            # 3. 执行更新
            updates = ["status = %s"]
            params = [new_status]
            
            # 如果变为执行中，可以记录开始时间日志（可选）
            if new_status == 2:
                log_msg = f"Started execution by {operator or 'system'} at {datetime.now()}"
                # 追加日志而不是覆盖
                old_log = current_record.get('execute_log') or ""
                new_log = f"{old_log}\n{log_msg}" if old_log else log_msg
                updates.append("execute_log = %s")
                params.append(new_log)
            
            # 如果变为已完成，记录结束时间
            if new_status == 3:
                log_msg = f"Completed by {operator or 'system'} at {datetime.now()}"
                old_log = current_record.get('execute_log') or ""
                new_log = f"{old_log}\n{log_msg}" if old_log else log_msg
                updates.append("execute_log = %s")
                params.append(new_log)

            params.append(plan_id)
            sql = f"UPDATE {self.table_name} SET {', '.join(updates)} WHERE plan_id = %s"
            
            cursor.execute(sql, params)
            conn.commit()

            updated_record = self._get_record_by_cursor(cursor, plan_id)
            return {"success": True, "data": updated_record}

        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error updating plan status {plan_id}: {e}")
            return {"success": False, "error": str(e)}
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def update_plan_content(self, plan_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """更新方案内容（仅限草稿状态，或根据业务需求允许修改）"""
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)

            # 检查状态，通常只允许修改草稿
            current_record = self._get_record_by_cursor(cursor, plan_id)
            if not current_record:
                return {"success": False, "error": f"Plan {plan_id} not found."}
            
            if current_record['status'] != 0:
                # 如果业务允许修改非草稿，可移除此判断
                return {"success": False, "error": "Only drafts (status=0) can be modified."}

            updates = []
            params = []
            allowed_fields = ['category_range', 'plan_details', 'input_factors', 'expected_kpi', 'execute_log']
            
            for field in allowed_fields:
                if field in data and data[field] is not None:
                    updates.append(f"{field} = %s")
                    val = data[field]
                    if field in ['plan_details', 'input_factors', 'expected_kpi']:
                        val = self._serialize_json(val)
                    params.append(val)
            
            if not updates:
                return {"success": True, "data": current_record, "message": "No fields updated"}

            params.append(plan_id)
            sql = f"UPDATE {self.table_name} SET {', '.join(updates)} WHERE plan_id = %s"
            cursor.execute(sql, params)
            conn.commit()

            updated_record = self._get_record_by_cursor(cursor, plan_id)
            return {"success": True, "data": updated_record}

        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error updating plan content {plan_id}: {e}")
            return {"success": False, "error": str(e)}
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def get_plan_by_id(self, plan_id: int) -> Optional[Dict[str, Any]]:
        """根据 ID 获取单条记录"""
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            return self._get_record_by_cursor(cursor, plan_id)
        except Exception as e:
            logger.error(f"Error fetching plan {plan_id}: {e}")
            raise e
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def _get_record_by_cursor(self, cursor, plan_id: int) -> Optional[Dict[str, Any]]:
        """内部方法：查询并处理 JSON"""
        sql = f"SELECT * FROM {self.table_name} WHERE plan_id = %s"
        cursor.execute(sql, (plan_id,))
        row = cursor.fetchone()
        return self._deserialize_json(row)

    def list_plans(
        self, 
        page: int = 1, 
        page_size: int = 20,
        biz_date: Optional[date] = None,
        status: Optional[int] = None,
        creator: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None
    ) -> Dict[str, Any]:
        """分页查询方案列表"""
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)

            where_clauses = ["1=1"]
            params = []

            if biz_date:
                where_clauses.append("biz_date = %s")
                params.append(biz_date)
            if status is not None:
                where_clauses.append("status = %s")
                params.append(status)
            if creator:
                where_clauses.append("creator LIKE %s")
                params.append(f"%{creator}%")
            if date_from:
                where_clauses.append("biz_date >= %s")
                params.append(date_from)
            if date_to:
                where_clauses.append("biz_date <= %s")
                params.append(date_to)

            where_sql = " AND ".join(where_clauses)
            offset = (page - 1) * page_size

            # 查总数
            count_sql = f"SELECT COUNT(*) as total FROM {self.table_name} WHERE {where_sql}"
            cursor.execute(count_sql, params)
            total = cursor.fetchone()['total']

            # 查数据
            data_sql = f"""
                SELECT plan_id, biz_date, category_range, status, creator, create_time, execute_log
                FROM {self.table_name} 
                WHERE {where_sql}
                ORDER BY biz_date DESC, create_time DESC
                LIMIT %s OFFSET %s
            """
            # 注意：列表页通常不返回巨大的 JSON 字段以节省带宽，详情再查
            # 如果需要返回 JSON，去掉上面的字段限制，改为 SELECT *
            # 这里为了性能，列表只返回基础信息，如需 JSON 可在前端请求详情
            
            # 修正：为了保持风格一致，这里返回所有字段，但在大数据量时需注意
            data_sql_full = f"""
                SELECT * FROM {self.table_name} 
                WHERE {where_sql}
                ORDER BY biz_date DESC, create_time DESC
                LIMIT %s OFFSET %s
            """
            data_params = params + [page_size, offset]
            cursor.execute(data_sql_full, data_params)
            items = cursor.fetchall()

            # 批量处理 JSON
            processed_items = [self._deserialize_json(item) for item in items]

            return {
                "total": total,
                "items": processed_items,
                "page": page,
                "page_size": page_size
            }

        except Exception as e:
            logger.error(f"Error listing plans: {e}")
            raise e
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def delete_plan(self, plan_id: int) -> Dict[str, Any]:
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 简单检查状态
            check_cursor = conn.cursor(pymysql.cursors.DictCursor)
            record = self._get_record_by_cursor(check_cursor, plan_id)
            check_cursor.close()
            
            if not record:
                return {"success": False, "error": f"Plan {plan_id} not found."}
            
            if record['status'] not in [0, 4]: # 只允许删草稿或已取消
                 return {"success": False, "error": "Cannot delete a plan that is published or executing."}

            sql = f"DELETE FROM {self.table_name} WHERE plan_id = %s"
            cursor.execute(sql, (plan_id,))
            conn.commit()
            
            return {"success": True, "message": "Deleted successfully"}
            
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error deleting plan {plan_id}: {e}")
            return {"success": False, "error": str(e)}
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def export_plans(
        self, 
        ids: Optional[List[int]] = None, 
        date_from: Optional[date] = None, 
        date_to: Optional[date] = None,
        status: Optional[int] = None
    ) -> List[Dict]:
        """导出数据"""
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)

            where_clauses = ["1=1"]
            params = []

            if ids and len(ids) > 0:
                placeholders = ','.join(['%s'] * len(ids))
                where_clauses.append(f"plan_id IN ({placeholders})")
                params.extend(ids)
            if status is not None:
                where_clauses.append("status = %s")
                params.append(status)
            if date_from:
                where_clauses.append("biz_date >= %s")
                params.append(date_from)
            if date_to:
                where_clauses.append("biz_date <= %s")
                params.append(date_to)

            where_sql = " AND ".join(where_clauses)

            sql = f"""
                SELECT * FROM {self.table_name}
                WHERE {where_sql}
                ORDER BY biz_date DESC
            """
            
            cursor.execute(sql, params)
            items = cursor.fetchall()
            return [self._deserialize_json(item) for item in items]

        except Exception as e:
            logger.error(f"Error exporting plans: {e}")
            raise e
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

def get_allocation_plan_service() -> AllocationPlanService:
    return AllocationPlanService()