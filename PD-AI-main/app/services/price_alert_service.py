"""
价格预警服务
"""
import logging
from typing import List, Dict, Optional, Any
from datetime import date, datetime
from decimal import Decimal

import pymysql
from app.services.contract_service import get_db_config, get_conn

logger = logging.getLogger(__name__)

class PriceAlertService:
    """价格预警记录服务类"""

    def __init__(self):
        self.table_name = "t_price_alert"

    def _get_connection(self):
        """内部辅助方法：获取数据库连接"""
        config = get_db_config()
        return get_conn(config)

    def create_alert(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建新的预警记录"""
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)

            sql = f"""
                INSERT INTO {self.table_name} 
                (rule_id, rule_name, category_code, current_price, threshold_value, 
                 trigger_reason, level, status, confirm_user, confirm_time, remarks)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            # 注意：create_time 由数据库默认值生成
            params = (
                data.get('rule_id'),
                data.get('rule_name'),
                data.get('category_code'),
                data.get('current_price'),
                data.get('threshold_value'),
                data.get('trigger_reason'),
                data.get('level'),
                data.get('status', 0),  # 默认 0-未确认
                data.get('confirm_user'),
                data.get('confirm_time'),
                data.get('remarks')
            )

            cursor.execute(sql, params)
            conn.commit()
            
            alert_id = cursor.lastrowid
            new_record = self._get_record_by_cursor(cursor, alert_id)
            
            return {"success": True, "data": new_record}

        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error creating price alert: {e}")
            return {"success": False, "error": str(e)}
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def update_alert_status(self, alert_id: int, status: int, confirm_user: Optional[str] = None) -> Dict[str, Any]:
        """
        更新预警状态（核心业务：确认或关闭预警）
        如果状态变为 1(已确认)，自动记录确认时间
        """
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)

            updates = ["status = %s"]
            params = [status]

            if status == 1 and confirm_user:
                updates.append("confirm_user = %s")
                updates.append("confirm_time = NOW()")
                params.extend([confirm_user])
            elif confirm_user:
                # 即使不自动设时间，也允许手动更新确认人
                updates.append("confirm_user = %s")
                params.append(confirm_user)

            params.append(alert_id)
            sql = f"UPDATE {self.table_name} SET {', '.join(updates)} WHERE alert_id = %s"

            cursor.execute(sql, params)
            conn.commit()

            if cursor.rowcount == 0:
                # 检查是否存在
                record = self._get_record_by_cursor(cursor, alert_id)
                if not record:
                    return {"success": False, "error": f"Alert record with id {alert_id} not found."}
                return {"success": True, "data": record}
            
            updated_record = self._get_record_by_cursor(cursor, alert_id)
            return {"success": True, "data": updated_record}

        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error updating alert {alert_id}: {e}")
            return {"success": False, "error": str(e)}
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def get_alert_by_id(self, alert_id: int) -> Optional[Dict[str, Any]]:
        """根据 ID 获取单条记录"""
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            return self._get_record_by_cursor(cursor, alert_id)
        except Exception as e:
            logger.error(f"Error fetching alert {alert_id}: {e}")
            raise e
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def _get_record_by_cursor(self, cursor, alert_id: int) -> Optional[Dict[str, Any]]:
        """内部方法：利用现有 cursor 查询"""
        sql = f"SELECT * FROM {self.table_name} WHERE alert_id = %s"
        cursor.execute(sql, (alert_id,))
        return cursor.fetchone()

    def list_alerts(
        self, 
        page: int = 1, 
        page_size: int = 20,
        category_code: Optional[str] = None,
        status: Optional[int] = None,
        level: Optional[int] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        fuzzy_keywords: Optional[str] = None
    ) -> Dict[str, Any]:
        """分页查询预警列表"""
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)

            where_clauses = ["1=1"]
            params = []

            if category_code:
                where_clauses.append("category_code = %s")
                params.append(category_code)
            if status is not None:
                where_clauses.append("status = %s")
                params.append(status)
            if level is not None:
                where_clauses.append("level = %s")
                params.append(level)
            if date_from:
                where_clauses.append("DATE(create_time) >= %s")
                params.append(date_from)
            if date_to:
                where_clauses.append("DATE(create_time) <= %s")
                params.append(date_to)
            
            if fuzzy_keywords:
                keywords = fuzzy_keywords.split()
                keyword_conditions = []
                for kw in keywords:
                    keyword_conditions.append("(rule_name LIKE %s OR trigger_reason LIKE %s OR confirm_user LIKE %s)")
                    params.extend([f"%{kw}%", f"%{kw}%", f"%{kw}%"])
                if keyword_conditions:
                    where_clauses.append(f"({' AND '.join(keyword_conditions)})")

            where_sql = " AND ".join(where_clauses)
            offset = (page - 1) * page_size

            # 查总数
            count_sql = f"SELECT COUNT(*) as total FROM {self.table_name} WHERE {where_sql}"
            cursor.execute(count_sql, params)
            total = cursor.fetchone()['total']

            # 查数据
            data_sql = f"""
                SELECT * FROM {self.table_name} 
                WHERE {where_sql}
                ORDER BY create_time DESC
                LIMIT %s OFFSET %s
            """
            data_params = params + [page_size, offset]
            cursor.execute(data_sql, data_params)
            items = cursor.fetchall()

            return {
                "total": total,
                "items": items,
                "page": page,
                "page_size": page_size
            }

        except Exception as e:
            logger.error(f"Error listing alerts: {e}")
            raise e
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def delete_alert(self, alert_id: int) -> Dict[str, Any]:
        """删除预警记录（通常只有管理员权限）"""
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            sql = f"DELETE FROM {self.table_name} WHERE alert_id = %s"
            cursor.execute(sql, (alert_id,))
            conn.commit()
            
            if cursor.rowcount == 0:
                check_cursor = conn.cursor(pymysql.cursors.DictCursor)
                exists = self._get_record_by_cursor(check_cursor, alert_id)
                check_cursor.close()
                if not exists:
                    return {"success": False, "error": f"Alert record with id {alert_id} not found."}
                return {"success": False, "error": "Failed to delete record."}
                
            return {"success": True, "message": "Deleted successfully"}
            
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error deleting alert {alert_id}: {e}")
            return {"success": False, "error": str(e)}
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def export_alerts(
        self, 
        ids: Optional[List[int]] = None, 
        date_from: Optional[date] = None, 
        date_to: Optional[date] = None,
        category_code: Optional[str] = None
    ) -> List[Dict]:
        """导出数据（不分页）"""
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)

            where_clauses = ["1=1"]
            params = []

            if ids and len(ids) > 0:
                placeholders = ','.join(['%s'] * len(ids))
                where_clauses.append(f"alert_id IN ({placeholders})")
                params.extend(ids)
            
            if category_code:
                where_clauses.append("category_code = %s")
                params.append(category_code)

            if date_from:
                where_clauses.append("DATE(create_time) >= %s")
                params.append(date_from)
            if date_to:
                where_clauses.append("DATE(create_time) <= %s")
                params.append(date_to)

            where_sql = " AND ".join(where_clauses)

            sql = f"""
                SELECT 
                    alert_id, rule_id, rule_name, category_code, current_price, 
                    threshold_value, trigger_reason, level, status, 
                    confirm_user, confirm_time, create_time
                FROM {self.table_name}
                WHERE {where_sql}
                ORDER BY create_time DESC
            """
            
            cursor.execute(sql, params)
            return cursor.fetchall()

        except Exception as e:
            logger.error(f"Error exporting alerts: {e}")
            raise e
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

def get_price_alert_service() -> PriceAlertService:
    return PriceAlertService()