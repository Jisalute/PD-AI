"""
预测服务 - 冶炼厂预测档案管理
"""
import logging
from typing import List, Dict, Optional, Any
from decimal import Decimal
from datetime import date, datetime

import pymysql
from app.services.contract_service import get_db_config, get_conn

logger = logging.getLogger(__name__)

class PredictionService:
    """预测每日配运量服务类"""

    def __init__(self):
        self.table_name = "t_prediction_result"

    def _get_connection(self):
        """内部辅助方法：获取数据库连接"""
        config = get_db_config()
        return get_conn(config)

    def create_prediction(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建新的预测记录"""
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)

            sql = f"""
                INSERT INTO {self.table_name} 
                (biz_date, category_code, predicted_value, rec_interval_start, rec_interval_end, operator, remarks)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            params = (
                data.get('biz_date'),
                data.get('category_code'),
                data.get('predicted_value'),
                data.get('rec_interval_start'),
                data.get('rec_interval_end'),
                data.get('operator'),
                data.get('remarks')
            )

            cursor.execute(sql, params)
            conn.commit()
            
            predict_id = cursor.lastrowid
            
            # 获取刚创建的详情
            new_record = self._get_record_by_cursor(cursor, predict_id)

            return {"success": True, "data": new_record}

        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error creating prediction: {e}")
            return {"success": False, "error": str(e)}
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def update_prediction(self, predict_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """更新预测记录"""
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)

            updates = []
            params = []
            allowed_fields = ['adjusted_value', 'adjust_reason', 'status', 'remarks', 'operator']
            
            for field in allowed_fields:
                if field in data and data[field] is not None:
                    updates.append(f"{field} = %s")
                    params.append(data[field])
            
            if not updates:
                record = self._get_record_by_cursor(cursor, predict_id)
                if not record:
                     return {"success": False, "error": f"Prediction record with id {predict_id} not found."}
                return {"success": True, "data": record}

            params.append(predict_id)
            sql = f"UPDATE {self.table_name} SET {', '.join(updates)} WHERE predict_id = %s"

            cursor.execute(sql, params)
            conn.commit()

            if cursor.rowcount == 0:
                record = self._get_record_by_cursor(cursor, predict_id)
                if not record:
                    return {"success": False, "error": f"Prediction record with id {predict_id} not found."}
                return {"success": True, "data": record}
            
            updated_record = self._get_record_by_cursor(cursor, predict_id)
            return {"success": True, "data": updated_record}

        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error updating prediction {predict_id}: {e}")
            return {"success": False, "error": str(e)}
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def get_prediction_by_id(self, predict_id: int) -> Optional[Dict[str, Any]]:
        """根据 ID 获取单条记录 (路由层直接用它，不需要包装 success)"""
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            return self._get_record_by_cursor(cursor, predict_id)
        except Exception as e:
            logger.error(f"Error fetching prediction {predict_id}: {e}")
            raise e
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def _get_record_by_cursor(self, cursor, predict_id: int) -> Optional[Dict[str, Any]]:
        """内部方法：利用现有 cursor 查询"""
        sql = f"SELECT * FROM {self.table_name} WHERE predict_id = %s"
        cursor.execute(sql, (predict_id,))
        return cursor.fetchone()

    def list_predictions(
        self, 
        page: int = 1, 
        page_size: int = 20,
        biz_date_from: Optional[date] = None,
        biz_date_to: Optional[date] = None,
        category_code: Optional[str] = None,
        status: Optional[int] = None,
        fuzzy_keywords: Optional[str] = None
    ) -> Dict[str, Any]:
        """分页查询预测列表 (直接返回字典，路由层直接返回)"""
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)

            where_clauses = ["1=1"]
            params = []

            if biz_date_from:
                where_clauses.append("biz_date >= %s")
                params.append(biz_date_from)
            if biz_date_to:
                where_clauses.append("biz_date <= %s")
                params.append(biz_date_to)
            if category_code:
                where_clauses.append("category_code = %s")
                params.append(category_code)
            if status is not None:
                where_clauses.append("status = %s")
                params.append(status)
            
            if fuzzy_keywords:
                keywords = fuzzy_keywords.split()
                keyword_conditions = []
                for kw in keywords:
                    keyword_conditions.append("(operator LIKE %s OR remarks LIKE %s)")
                    params.extend([f"%{kw}%", f"%{kw}%"])
                if keyword_conditions:
                    where_clauses.append(f"({' AND '.join(keyword_conditions)})")

            where_sql = " AND ".join(where_clauses)
            offset = (page - 1) * page_size

            count_sql = f"SELECT COUNT(*) as total FROM {self.table_name} WHERE {where_sql}"
            cursor.execute(count_sql, params)
            total = cursor.fetchone()['total']

            data_sql = f"""
                SELECT * FROM {self.table_name} 
                WHERE {where_sql}
                ORDER BY biz_date DESC, create_time DESC
                LIMIT %s OFFSET %s
            """
            data_params = params + [page_size, offset]
            cursor.execute(data_sql, data_params)
            items = cursor.fetchall()

            # 直接返回结构，路由层直接 return
            return {
                "total": total,
                "items": items,
                "page": page,
                "page_size": page_size
            }

        except Exception as e:
            logger.error(f"Error listing predictions: {e}")
            raise e
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def delete_prediction(self, predict_id: int) -> Dict[str, Any]:
        """删除预测记录"""
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            sql = f"DELETE FROM {self.table_name} WHERE predict_id = %s"
            cursor.execute(sql, (predict_id,))
            conn.commit()
            
            if cursor.rowcount == 0:
                # 检查是否存在
                check_cursor = conn.cursor(pymysql.cursors.DictCursor)
                exists = self._get_record_by_cursor(check_cursor, predict_id)
                check_cursor.close()
                
                if not exists:
                    return {"success": False, "error": f"Prediction record with id {predict_id} not found."}
                return {"success": False, "error": "Failed to delete record."}
                
            return {"success": True, "message": "Deleted successfully"}
            
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error deleting prediction {predict_id}: {e}")
            return {"success": False, "error": str(e)}
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    # 预留导出方法，防止路由报错
    def export_predictions(self, ids: Optional[List[int]] = None, date_from: Optional[date] = None, date_to: Optional[date] = None) -> List[Dict]:
        """简单实现导出逻辑，实际可根据需求完善"""

        return [] 

def get_prediction_service() -> PredictionService:
    return PredictionService()