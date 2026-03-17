"""
AI图片真伪检测服务 - 调用模型API
"""
import os
import json
import base64
import logging
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

from core.database import get_conn
from app.models.api_client import APIClient

logger = logging.getLogger(__name__)

# 上传目录配置
UPLOAD_DIR = Path("uploads/detection")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ANOMALY_DIR = Path("uploads/anomaly")
ANOMALY_DIR.mkdir(parents=True, exist_ok=True)


class ImageDetectionService:
    """图片真伪检测服务"""
    
    # 常量定义
    DETECTION_STATUS_PENDING = 0
    DETECTION_STATUS_PROCESSING = 1
    DETECTION_STATUS_COMPLETED = 2

    DETECTION_RESULT_NORMAL = 0
    DETECTION_RESULT_SUSPICIOUS = 1
    DETECTION_RESULT_TAMPERED = 2

    REVIEW_STATUS_PENDING = 0
    REVIEW_STATUS_PASSED = 1

    def __init__(self):
        """初始化，创建API客户端"""
        self.api_url = os.getenv("MODEL_API_URL", "")
        self.api_key = os.getenv("MODEL_API_KEY")
        self.api_format = os.getenv("MODEL_API_FORMAT", "json")
        self.timeout = int(os.getenv("MODEL_API_TIMEOUT", "30"))
        
        if self.api_url:
            self.api_client = APIClient(
                base_url=self.api_url,
                api_key=self.api_key,
                timeout=self.timeout
            )
            logger.info(f"API客户端初始化成功: {self.api_url}")
        else:
            self.api_client = None
            logger.warning("未配置模型API地址，将使用模拟模式")
    
    # ========== 基础方法 ==========
    
    def calculate_md5(self, image_data: bytes) -> str:
        """计算图片MD5值"""
        return hashlib.md5(image_data).hexdigest()
    
    def save_image(self, image_data: bytes, filename: str = None) -> str:
        """保存图片"""
        if not filename:
            md5 = self.calculate_md5(image_data)
            filename = f"{md5[:8]}_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
        
        file_path = UPLOAD_DIR / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, "wb") as f:
            f.write(image_data)
        
        return str(file_path)
    
    # ========== API调用 ==========
    
    def detect_tampering(self, image_path: str) -> Dict[str, Any]:
        """
        调用模型API检测图片篡改
        """
        # 如果没有配置API，使用模拟模式
        if not self.api_client:
            logger.warning("使用模拟检测模式")
            return self._simulate_detection(image_path)
        
        try:
            # 根据配置的格式调用API
            if self.api_format == "file":
                result = self.api_client.post_file("predict", image_path)
            elif self.api_format == "base64":
                result = self.api_client.post_base64("predict", image_path)
            else:  # 默认json
                with open(image_path, "rb") as f:
                    image_base64 = base64.b64encode(f.read()).decode('utf-8')
                
                payload = {
                    "image": image_base64,
                    "task": "tampering_detection",
                    "timestamp": datetime.now().isoformat()
                }
                result = self.api_client.post_json("predict", payload)
            
            logger.info(f"API返回结果: {json.dumps(result)[:200]}")
            
            # 解析API返回结果
            return self._parse_api_result(result, image_path)
            
        except Exception as e:
            logger.error(f"调用模型API失败: {e}")
            return {
                "success": False,
                "result": 0,
                "confidence": 0,
                "anomaly_type": None,
                "anomaly_image": None,
                "error": str(e)
            }
    
    def _parse_api_result(self, api_result: Dict, image_path: str) -> Dict[str, Any]:
        """
        解析API返回结果 - **需要根据实际API响应格式修改**
        
        假设API返回格式为：
        {
            "code": 0,
            "message": "success",
            "data": {
                "is_tampered": true,
                "probability": 0.95,
                "tamper_type": "photoshop",
                "tamper_regions": [{"x":100, "y":200, "width":150, "height":50}],
                "annotated_image": "base64_string"
            }
        }
        """
        parsed = {
            "success": True,
            "result": 0,
            "confidence": 0,
            "anomaly_type": None,
            "anomaly_image": None,
            "error": None
        }
        
        try:
            # 检查是否成功
            if api_result.get("code") == 0:
                data = api_result.get("data", {})
                
                # 提取检测结果
                is_tampered = data.get("is_tampered", False)
                prob = float(data.get("probability", 0))
                
                if is_tampered:
                    parsed["result"] = self.DETECTION_RESULT_TAMPERED if prob > 0.8 else self.DETECTION_RESULT_SUSPICIOUS
                
                parsed["confidence"] = prob
                parsed["anomaly_type"] = data.get("tamper_type")
                
                # 保存标注图片
                annotated = data.get("annotated_image")
                if annotated:
                    parsed["anomaly_image"] = self._save_annotated_image(annotated, image_path)
            else:
                parsed["success"] = False
                parsed["error"] = api_result.get("message", "未知错误")
        
        except Exception as e:
            logger.error(f"解析API结果失败: {e}")
            parsed["success"] = False
            parsed["error"] = str(e)
        
        return parsed
    
    def _save_annotated_image(self, base64_data: str, original_path: str) -> str:
        """保存标注后的图片"""
        try:
            image_data = base64.b64decode(base64_data)
            original = Path(original_path)
            filename = f"annotated_{original.stem}_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
            save_path = ANOMALY_DIR / filename
            
            with open(save_path, "wb") as f:
                f.write(image_data)
            
            return str(save_path)
        except Exception as e:
            logger.error(f"保存标注图片失败: {e}")
            return None
    
    def _simulate_detection(self, image_path: str) -> Dict[str, Any]:
        """模拟检测（当API未配置时使用）"""
        import random
        
        rand = random.random()
        if rand < 0.7:
            result = self.DETECTION_RESULT_NORMAL
            confidence = random.uniform(0.7, 0.99)
            anomaly_type = None
        elif rand < 0.9:
            result = self.DETECTION_RESULT_SUSPICIOUS
            confidence = random.uniform(0.5, 0.8)
            anomaly_type = "边缘模糊"
        else:
            result = self.DETECTION_RESULT_TAMPERED
            confidence = random.uniform(0.8, 0.99)
            anomaly_type = "字体篡改"
        
        return {
            "success": True,
            "result": result,
            "confidence": confidence,
            "anomaly_type": anomaly_type,
            "anomaly_image": None,
            "error": None
        }
    
    # ========== 数据库操作 ==========
    
    def check_duplicate(self, image_md5: str) -> Optional[Dict]:
        """检查图片是否已检测过"""
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT id, detection_result, review_status
                        FROM pd_image_detection
                        WHERE image_md5 = %s
                        ORDER BY created_at DESC
                        LIMIT 1
                    """, (image_md5,))
                    
                    row = cur.fetchone()
                    if row:
                        return {
                            "id": row[0],
                            "detection_result": row[1],
                            "review_status": row[2]
                        }
                    return None
        except Exception as e:
            logger.error(f"查重失败: {e}")
            return None
    
    def create_detection_record(self, image_path: str, image_md5: str,
                                uploaded_by: int = None) -> int:
        """创建检测记录"""
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO pd_image_detection
                        (image_url, image_md5, detection_status, upload_time)
                        VALUES (%s, %s, %s, %s)
                    """, (image_path, image_md5, self.DETECTION_STATUS_PENDING, datetime.now()))
                    
                    record_id = cur.lastrowid
                    self._add_log(record_id, "info", f"创建检测记录")
                    return record_id
        except Exception as e:
            logger.error(f"创建检测记录失败: {e}")
            raise
    
    def update_detection_result(self, record_id: int, result_data: Dict) -> bool:
        """更新检测结果"""
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE pd_image_detection
                        SET detection_status = %s,
                            detection_result = %s,
                            confidence_score = %s,
                            anomaly_type = %s,
                            anomaly_area_image = %s,
                            detection_time = %s
                        WHERE id = %s
                    """, (
                        self.DETECTION_STATUS_COMPLETED,
                        result_data.get("result", 0),
                        result_data.get("confidence", 0),
                        result_data.get("anomaly_type"),
                        result_data.get("anomaly_image"),
                        datetime.now(),
                        record_id
                    ))
                    
                    self._add_log(record_id, "info", f"检测完成，结果: {result_data.get('result', 0)}")
                    return True
        except Exception as e:
            logger.error(f"更新检测结果失败: {e}")
            return False
    
    def _add_log(self, record_id: int, level: str, content: str):
        """添加检测日志"""
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO pd_detection_log
                        (record_id, log_level, log_content)
                        VALUES (%s, %s, %s)
                    """, (record_id, level, content))
        except Exception as e:
            logger.error(f"添加日志失败: {e}")
    
    def submit_review(self, record_id: int, reviewer_id: int,
                      review_result: int, remark: str = None) -> Dict:
        """提交复核结果"""
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE pd_image_detection
                        SET review_status = %s,
                            reviewer_id = %s,
                            review_time = %s,
                            review_remark = %s
                        WHERE id = %s
                    """, (self.REVIEW_STATUS_PASSED, reviewer_id, datetime.now(), remark, record_id))
                    
                    self._add_log(record_id, "info", f"人工复核完成")
                    
                    return {"success": True, "message": "复核成功"}
        except Exception as e:
            logger.error(f"提交复核失败: {e}")
            return {"success": False, "error": str(e)}
    
    def get_pending_reviews(self, page: int = 1, page_size: int = 20) -> Dict:
        """获取待复核列表"""
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    offset = (page - 1) * page_size
                    
                    cur.execute("""
                        SELECT COUNT(*)
                        FROM pd_image_detection
                        WHERE detection_result IN (1, 2)
                        AND review_status = %s
                    """, (self.REVIEW_STATUS_PENDING,))
                    total = cur.fetchone()[0]
                    
                    cur.execute("""
                        SELECT d.*, u.name as reviewer_name
                        FROM pd_image_detection d
                        LEFT JOIN pd_users u ON d.reviewer_id = u.id
                        WHERE d.detection_result IN (1, 2)
                        AND d.review_status = %s
                        ORDER BY d.detection_time DESC
                        LIMIT %s OFFSET %s
                    """, (self.REVIEW_STATUS_PENDING, page_size, offset))
                    
                    columns = [desc[0] for desc in cur.description]
                    data = []
                    for row in cur.fetchall():
                        item = dict(zip(columns, row))
                        for key in ['upload_time', 'detection_time', 'review_time']:
                            if item.get(key):
                                item[key] = str(item[key])
                        data.append(item)
                    
                    return {"success": True, "data": data, "total": total, "page": page, "page_size": page_size}
        except Exception as e:
            logger.error(f"获取待复核列表失败: {e}")
            return {"success": False, "error": str(e)}
    
    def get_dashboard_stats(self, days: int = 7) -> Dict:
        """获取仪表盘统计"""
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    start_date = datetime.now() - timedelta(days=days)
                    
                    cur.execute("""
                        SELECT
                            COUNT(*) as total,
                            SUM(CASE WHEN detection_result = 0 THEN 1 ELSE 0 END) as normal,
                            SUM(CASE WHEN detection_result = 1 THEN 1 ELSE 0 END) as suspicious,
                            SUM(CASE WHEN detection_result = 2 THEN 1 ELSE 0 END) as tampered
                        FROM pd_image_detection
                        WHERE detection_time >= %s
                    """, (start_date,))
                    row = cur.fetchone()
                    total, normal, suspicious, tampered = row if row else (0,0,0,0)
                    
                    return {
                        "success": True,
                        "data": {
                            "period_days": days,
                            "total": total or 0,
                            "normal": normal or 0,
                            "suspicious": suspicious or 0,
                            "tampered": tampered or 0
                        }
                    }
        except Exception as e:
            logger.error(f"获取仪表盘统计失败: {e}")
            return {"success": False, "error": str(e)}


# 单例模式
_detection_service = None

def get_detection_service():
    global _detection_service
    if _detection_service is None:
        _detection_service = ImageDetectionService()
    return _detection_service