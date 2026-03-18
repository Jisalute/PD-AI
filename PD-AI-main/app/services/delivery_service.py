"""
销售台账/报货订单服务
"""
import logging
import os
import re
import shutil
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

from app.services.contract_service import get_conn
from app.services.customer_service import CustomerService

logger = logging.getLogger(__name__)

UPLOAD_DIR = Path("uploads/delivery_orders")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class DeliveryService:
    """报货订单服务"""

    def _determine_source_type(self, has_order: str, uploaded_by: str = None) -> str:
        """
        确定来源类型
        - 有联单 -> 司机
        - 无联单 -> 公司
        - 公司人员上传有联单 -> 可指定为公司
        """
        if has_order == '有':
            # 有联单默认司机，除非明确指定公司上传
            if uploaded_by == '公司':
                return '公司'
            return '司机'
        else:
            # 无联单默认公司
            return '公司'

    def _calculate_price(self, factory_name: str, product_name: str, quantity: Decimal) -> tuple:
        """
        关联合同计算价格
        返回: (contract_no, unit_price, total_amount)
        """
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    # 1. 查找客户ID
                    cur.execute(
                        "SELECT id FROM pd_customers WHERE smelter_name = %s",
                        (factory_name,)
                    )
                    customer = cur.fetchone()
                    if not customer:
                        return None, None, None

                    # 2. 查找生效中的合同
                    cur.execute("""
                        SELECT contract_no, unit_price 
                        FROM pd_contracts 
                        WHERE smelter_company = %s 
                        AND status = '生效中'
                        AND contract_date <= CURDATE()
                        AND (end_date IS NULL OR end_date >= CURDATE())
                        ORDER BY created_at DESC
                        LIMIT 1
                    """, (factory_name,))

                    contract = cur.fetchone()
                    if not contract:
                        return None, None, None

                    contract_no, unit_price = contract
                    if unit_price and quantity:
                        total = Decimal(str(unit_price)) * Decimal(str(quantity))
                    else:
                        total = None

                    return contract_no, float(unit_price) if unit_price else None, float(total) if total else None

        except Exception as e:
            logger.error(f"计算价格失败: {e}")
            return None, None, None

    def create_delivery(self, data: Dict, image_file: bytes = None, current_user: str = "system") -> Dict[str, Any]:
        """创建报货订单"""
        try:
            # 处理来源类型
            has_order = data.get('has_delivery_order', '无')
            uploaded_by = data.get('uploaded_by')  # 前端可传'公司'表示公司人员上传
            source_type = self._determine_source_type(has_order, uploaded_by)
            data['source_type'] = source_type

            # 发货人默认为当前操作人
            if not data.get('shipper'):
                data['shipper'] = current_user

            # 计算价格（如果有关联工厂和品种）
            contract_no = None
            unit_price = None
            total_amount = None

            if data.get('target_factory_name') and data.get('product_name') and data.get('quantity'):
                contract_no, unit_price, total_amount = self._calculate_price(
                    data['target_factory_name'],
                    data['product_name'],
                    Decimal(str(data['quantity']))
                )

            # 处理图片上传
            image_path = None
            if image_file and has_order == '有':
                # 保存联单图片
                file_ext = ".jpg"
                safe_name = re.sub(r'[^\w\-]', '_', str(data.get('vehicle_no', 'unknown')))
                filename = f"order_{safe_name}_{datetime.now().strftime('%Y%m%d%H%M%S')}{file_ext}"
                file_path = UPLOAD_DIR / filename

                with open(file_path, "wb") as f:
                    f.write(image_file)

                image_path = str(file_path)

            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO pd_deliveries 
                        (report_date, delivery_time, warehouse, target_factory_id, target_factory_name,
                         product_name, quantity, vehicle_no, driver_name, driver_phone, driver_id_card,
                         has_delivery_order, delivery_order_image, source_type,
                         shipper, payee, service_fee, contract_no, contract_unit_price, total_amount, status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        data.get('report_date'),
                        data.get('delivery_time'),
                        data.get('warehouse'),
                        data.get('target_factory_id'),
                        data.get('target_factory_name'),
                        data.get('product_name'),
                        data.get('quantity'),
                        data.get('vehicle_no'),
                        data.get('driver_name'),
                        data.get('driver_phone'),
                        data.get('driver_id_card'),
                        has_order,
                        image_path,
                        source_type,
                        data.get('shipper'),
                        data.get('payee'),
                        data.get('service_fee', 0),
                        contract_no,
                        unit_price,
                        total_amount,
                        data.get('status', '待确认')
                    ))

                    delivery_id = cur.lastrowid

                    return {
                        "success": True,
                        "message": "报货订单创建成功",
                        "data": {
                            "id": delivery_id,
                            "contract_no": contract_no,
                            "contract_unit_price": unit_price,
                            "total_amount": total_amount,
                            "source_type": source_type
                        }
                    }

        except Exception as e:
            logger.error(f"创建报货订单失败: {e}")
            return {"success": False, "error": str(e)}

    def update_delivery(self, delivery_id: int, data: Dict, image_file: bytes = None, current_user: str = "system") -> \
    Dict[str, Any]:
        """更新报货订单"""
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    # 检查是否存在
                    cur.execute("SELECT * FROM pd_deliveries WHERE id = %s", (delivery_id,))
                    old = cur.fetchone()
                    if not old:
                        return {"success": False, "error": "订单不存在"}

                    old_data = dict(zip([desc[0] for desc in cur.description], old))

                    # 处理来源类型（如果修改了联单状态）
                    has_order = data.get('has_delivery_order', old_data['has_delivery_order'])
                    if 'has_delivery_order' in data or 'uploaded_by' in data:
                        uploaded_by = data.get('uploaded_by')
                        data['source_type'] = self._determine_source_type(has_order, uploaded_by)

                    # 重新计算价格（如果关键字段变了）
                    factory = data.get('target_factory_name', old_data['target_factory_name'])
                    product = data.get('product_name', old_data['product_name'])
                    qty = data.get('quantity', old_data['quantity'])

                    if (data.get('target_factory_name') or data.get('product_name') or data.get('quantity')):
                        contract_no, unit_price, total_amount = self._calculate_price(
                            factory, product, Decimal(str(qty)) if qty else Decimal('0')
                        )
                        data['contract_no'] = contract_no
                        data['contract_unit_price'] = unit_price
                        data['total_amount'] = total_amount

                    # 处理新图片
                    if image_file and has_order == '有':
                        # 删除旧图片
                        if old_data.get('delivery_order_image') and os.path.exists(old_data['delivery_order_image']):
                            os.remove(old_data['delivery_order_image'])

                        # 保存新图片
                        safe_name = re.sub(r'[^\w\-]', '_', str(data.get('vehicle_no', old_data['vehicle_no'])))
                        filename = f"order_{safe_name}_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
                        file_path = UPLOAD_DIR / filename

                        with open(file_path, "wb") as f:
                            f.write(image_file)

                        data['delivery_order_image'] = str(file_path)

                    # 构建更新SQL
                    fields = [
                        'report_date', 'delivery_time', 'warehouse', 'target_factory_id', 'target_factory_name',
                        'product_name', 'quantity', 'vehicle_no', 'driver_name', 'driver_phone', 'driver_id_card',
                        'has_delivery_order', 'delivery_order_image', 'source_type',
                        'shipper', 'payee', 'service_fee', 'contract_no', 'contract_unit_price', 'total_amount',
                        'status'
                    ]

                    update_fields = []
                    params = []
                    for f in fields:
                        if f in data:
                            update_fields.append(f"{f} = %s")
                            params.append(data[f])

                    if not update_fields:
                        return {"success": False, "error": "没有要更新的字段"}

                    params.append(delivery_id)
                    sql = f"UPDATE pd_deliveries SET {', '.join(update_fields)} WHERE id = %s"
                    cur.execute(sql, tuple(params))

                    return {"success": True, "message": "更新成功"}

        except Exception as e:
            logger.error(f"更新报货订单失败: {e}")
            return {"success": False, "error": str(e)}

    def get_delivery(self, delivery_id: int) -> Optional[Dict]:
        """获取订单详情"""
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM pd_deliveries WHERE id = %s", (delivery_id,))
                    row = cur.fetchone()
                    if not row:
                        return None

                    columns = [desc[0] for desc in cur.description]
                    data = dict(zip(columns, row))

                    # 转换时间格式
                    for key in ['report_date', 'delivery_time', 'created_at', 'updated_at']:
                        if data.get(key):
                            data[key] = str(data[key])

                    return data

        except Exception as e:
            logger.error(f"查询订单失败: {e}")
            return None

    def list_deliveries(
            self,
            exact_factory_name: str = None,
            exact_status: str = None,
            exact_vehicle_no: str = None,
            exact_driver_name: str = None,
            exact_driver_phone: str = None,
            fuzzy_keywords: str = None,
            date_from: str = None,
            date_to: str = None,
            page: int = 1,
            page_size: int = 20
    ) -> Dict[str, Any]:
        """查询订单列表"""
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    where_clauses = []
                    params = []

                    if exact_factory_name:
                        where_clauses.append("target_factory_name = %s")
                        params.append(exact_factory_name)

                    if exact_status:
                        where_clauses.append("status = %s")
                        params.append(exact_status)

                    if exact_vehicle_no:
                        where_clauses.append("vehicle_no = %s")
                        params.append(exact_vehicle_no)

                    if exact_driver_name:
                        where_clauses.append("driver_name = %s")
                        params.append(exact_driver_name)

                    if exact_driver_phone:
                        where_clauses.append("driver_phone = %s")
                        params.append(exact_driver_phone)

                    if fuzzy_keywords:
                        tokens = [t for t in fuzzy_keywords.split() if t]
                        or_clauses = []
                        for token in tokens:
                            like = f"%{token}%"
                            or_clauses.append(
                                "(vehicle_no LIKE %s OR driver_name LIKE %s OR driver_phone LIKE %s "
                                "OR target_factory_name LIKE %s OR product_name LIKE %s)"
                            )
                            params.extend([like, like, like, like, like])
                        if or_clauses:
                            where_clauses.append("(" + " OR ".join(or_clauses) + ")")

                    if date_from:
                        where_clauses.append("report_date >= %s")
                        params.append(date_from)

                    if date_to:
                        where_clauses.append("report_date <= %s")
                        params.append(date_to)

                    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

                    # 总数
                    cur.execute(f"SELECT COUNT(*) FROM pd_deliveries {where_sql}", tuple(params))
                    total = cur.fetchone()[0]

                    # 分页数据
                    offset = (page - 1) * page_size
                    cur.execute(f"""
                        SELECT * FROM pd_deliveries 
                        {where_sql}
                        ORDER BY created_at DESC
                        LIMIT %s OFFSET %s
                    """, tuple(params + [page_size, offset]))

                    columns = [desc[0] for desc in cur.description]
                    rows = cur.fetchall()
                    data = []
                    for row in rows:
                        item = dict(zip(columns, row))
                        for key in ['report_date', 'delivery_time', 'created_at', 'updated_at']:
                            if item.get(key):
                                item[key] = str(item[key])
                        data.append(item)

                    return {
                        "success": True,
                        "data": data,
                        "total": total,
                        "page": page,
                        "page_size": page_size
                    }

        except Exception as e:
            logger.error(f"查询列表失败: {e}")
            return {"success": False, "error": str(e), "data": [], "total": 0}

    def delete_delivery(self, delivery_id: int) -> Dict[str, Any]:
        """删除订单"""
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    # 获取图片路径
                    cur.execute("SELECT delivery_order_image FROM pd_deliveries WHERE id = %s", (delivery_id,))
                    row = cur.fetchone()

                    if row and row[0] and os.path.exists(row[0]):
                        os.remove(row[0])

                    cur.execute("DELETE FROM pd_deliveries WHERE id = %s", (delivery_id,))
                    return {"success": True, "message": "删除成功"}

        except Exception as e:
            logger.error(f"删除订单失败: {e}")
            return {"success": False, "error": str(e)}


_delivery_service = None


def get_delivery_service():
    global _delivery_service
    if _delivery_service is None:
        _delivery_service = DeliveryService()
    return _delivery_service