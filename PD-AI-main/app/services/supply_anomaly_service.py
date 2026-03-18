"""
供应异常服务 - 冶炼厂供应异常档案管理
"""
import logging
import json
from typing import List, Dict, Optional, Any
from datetime import date, datetime
from decimal import Decimal

import pymysql
from app.services.contract_service import get_db_config, get_conn

logger = logging.getLogger(__name__)

class SupplyAnomalyService:
    """供应异常记录服务类"""

    def __init__(self):
        self.table_name = "t_supply_anomaly"

    def _get_connection(self):
        """内部辅助方法：获取数据库连接"""
        config = get_db_config()
        return get_conn(config)

    def create_anomaly(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建新的供应异常记录"""
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)

            # 处理 JSON 字段：如果传入的是列表/字典，确保它是合法的，PyMySQL 通常会自动序列化
            # 为了保险，如果是字符串则直接传，如果是对象则保留让驱动处理
            rec_actions = data.get('recommended_actions')
            
            sql = f"""
                INSERT INTO {self.table_name} 
                (category_code, supplier_code, supplier_name, anomaly_type, 
                 description, impact_scope, duration_days, status, 
                 recommended_actions, handler)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            params = (
                data.get('category_code'),
                data.get('supplier_code'),
                data.get('supplier_name'),
                data.get('anomaly_type'),
                data.get('description'),
                data.get('impact_scope'),
                data.get('duration_days'),
                data.get('status', 0),  # 默认 0-待处理
                json.dumps(rec_actions) if rec_actions else None, # 显式转为 JSON 字符串以防驱动不支持
                data.get('handler')
            )

            cursor.execute(sql, params)
            conn.commit()
            
            anomaly_id = cursor.lastrowid
            new_record = self._get_record_by_cursor(cursor, anomaly_id)
            
            return {"success": True, "data": new_record}

        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error creating supply anomaly: {e}")
            return {"success": False, "error": str(e)}
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def update_anomaly_status(self, anomaly_id: int, status: int, handler: Optional[str] = None) -> Dict[str, Any]:
        """
        更新异常处理状态
        如果状态变为 2(已解决)，自动记录 resolve_time
        """
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)

            updates = ["status = %s"]
            params = [status]

            if handler:
                updates.append("handler = %s")
                params.append(handler)

            if status == 2:
                # 状态变为已解决，自动记录解决时间
                updates.append("resolve_time = NOW()")
            elif status != 2:
                # 如果从已解决变回其他状态，清空解决时间（可选逻辑，视业务需求而定）
                # updates.append("resolve_time = NULL") 
                pass

            params.append(anomaly_id)
            sql = f"UPDATE {self.table_name} SET {', '.join(updates)} WHERE anomaly_id = %s"

            cursor.execute(sql, params)
            conn.commit()

            if cursor.rowcount == 0:
                record = self._get_record_by_cursor(cursor, anomaly_id)
                if not record:
                    return {"success": False, "error": f"Anomaly record with id {anomaly_id} not found."}
                return {"success": True, "data": record}
            
            updated_record = self._get_record_by_cursor(cursor, anomaly_id)
            return {"success": True, "data": updated_record}

        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error updating anomaly {anomaly_id}: {e}")
            return {"success": False, "error": str(e)}
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def update_anomaly_details(self, anomaly_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """更新异常详细信息（如描述、影响范围、推荐动作等）"""
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)

            updates = []
            params = []
            # 允许更新的字段
            allowed_fields = ['description', 'impact_scope', 'duration_days', 'recommended_actions', 'supplier_name']
            
            for field in allowed_fields:
                if field in data and data[field] is not None:
                    updates.append(f"{field} = %s")
                    val = data[field]
                    if field == 'recommended_actions':
                        val = json.dumps(val) if isinstance(val, (list, dict)) else val
                    params.append(val)
            
            if not updates:
                record = self._get_record_by_cursor(cursor, anomaly_id)
                if not record:
                     return {"success": False, "error": f"Anomaly record with id {anomaly_id} not found."}
                return {"success": True, "data": record}

            params.append(anomaly_id)
            sql = f"UPDATE {self.table_name} SET {', '.join(updates)} WHERE anomaly_id = %s"

            cursor.execute(sql, params)
            conn.commit()

            if cursor.rowcount == 0:
                record = self._get_record_by_cursor(cursor, anomaly_id)
                if not record:
                    return {"success": False, "error": f"Anomaly record with id {anomaly_id} not found."}
                return {"success": True, "data": record}
            
            updated_record = self._get_record_by_cursor(cursor, anomaly_id)
            return {"success": True, "data": updated_record}

        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error updating anomaly details {anomaly_id}: {e}")
            return {"success": False, "error": str(e)}
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def get_anomaly_by_id(self, anomaly_id: int) -> Optional[Dict[str, Any]]:
        """根据 ID 获取单条记录"""
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            return self._get_record_by_cursor(cursor, anomaly_id)
        except Exception as e:
            logger.error(f"Error fetching anomaly {anomaly_id}: {e}")
            raise e
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def _get_record_by_cursor(self, cursor, anomaly_id: int) -> Optional[Dict[str, Any]]:
        """内部方法：利用现有 cursor 查询"""
        sql = f"SELECT * FROM {self.table_name} WHERE anomaly_id = %s"
        cursor.execute(sql, (anomaly_id,))
        row = cursor.fetchone()
        
        # 确保 JSON 字段被正确解析 (如果驱动返回的是字符串)
        if row and row.get('recommended_actions'):
            try:
                if isinstance(row['recommended_actions'], str):
                    row['recommended_actions'] = json.loads(row['recommended_actions'])
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON in recommended_actions for anomaly {anomaly_id}")
                
        return row

    def list_anomalies(
        self, 
        page: int = 1, 
        page_size: int = 20,
        category_code: Optional[str] = None,
        supplier_code: Optional[str] = None,
        anomaly_type: Optional[str] = None,
        status: Optional[int] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        fuzzy_keywords: Optional[str] = None
    ) -> Dict[str, Any]:
        """分页查询异常列表"""
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
            if supplier_code:
                where_clauses.append("supplier_code = %s")
                params.append(supplier_code)
            if anomaly_type:
                where_clauses.append("anomaly_type = %s")
                params.append(anomaly_type)
            if status is not None:
                where_clauses.append("status = %s")
                params.append(status)
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
                    # 搜索供应商名称、异常描述、影响范围
                    keyword_conditions.append("(supplier_name LIKE %s OR description LIKE %s OR impact_scope LIKE %s)")
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

            # 批量处理 JSON 字段
            for item in items:
                if item.get('recommended_actions') and isinstance(item['recommended_actions'], str):
                    try:
                        item['recommended_actions'] = json.loads(item['recommended_actions'])
                    except:
                        pass

            return {
                "total": total,
                "items": items,
                "page": page,
                "page_size": page_size
            }

        except Exception as e:
            logger.error(f"Error listing anomalies: {e}")
            raise e
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def delete_anomaly(self, anomaly_id: int) -> Dict[str, Any]:
        """删除异常记录"""
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            sql = f"DELETE FROM {self.table_name} WHERE anomaly_id = %s"
            cursor.execute(sql, (anomaly_id,))
            conn.commit()
            
            if cursor.rowcount == 0:
                check_cursor = conn.cursor(pymysql.cursors.DictCursor)
                exists = self._get_record_by_cursor(check_cursor, anomaly_id)
                check_cursor.close()
                if not exists:
                    return {"success": False, "error": f"Anomaly record with id {anomaly_id} not found."}
                return {"success": False, "error": "Failed to delete record."}
                
            return {"success": True, "message": "Deleted successfully"}
            
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error deleting anomaly {anomaly_id}: {e}")
            return {"success": False, "error": str(e)}
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def export_anomalies(
        self, 
        ids: Optional[List[int]] = None, 
        date_from: Optional[date] = None, 
        date_to: Optional[date] = None,
        category_code: Optional[str] = None,
        supplier_code: Optional[str] = None
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
                where_clauses.append(f"anomaly_id IN ({placeholders})")
                params.extend(ids)
            
            if category_code:
                where_clauses.append("category_code = %s")
                params.append(category_code)
            if supplier_code:
                where_clauses.append("supplier_code = %s")
                params.append(supplier_code)

            if date_from:
                where_clauses.append("DATE(create_time) >= %s")
                params.append(date_from)
            if date_to:
                where_clauses.append("DATE(create_time) <= %s")
                params.append(date_to)

            where_sql = " AND ".join(where_clauses)

            sql = f"""
                SELECT 
                    anomaly_id, category_code, supplier_code, supplier_name, 
                    anomaly_type, description, impact_scope, duration_days, 
                    status, recommended_actions, handler, create_time, resolve_time
                FROM {self.table_name}
                WHERE {where_sql}
                ORDER BY create_time DESC
            """
            
            cursor.execute(sql, params)
            items = cursor.fetchall()
            
            # 处理 JSON
            for item in items:
                if item.get('recommended_actions') and isinstance(item['recommended_actions'], str):
                    try:
                        item['recommended_actions'] = json.loads(item['recommended_actions'])
                    except:
                        pass
                        
            return items

        except Exception as e:
            logger.error(f"Error exporting anomalies: {e}")
            raise e
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

def get_supply_anomaly_service() -> SupplyAnomalyService:
    return SupplyAnomalyService()