"""
AI图片真伪检测路由
"""
import os
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query, Body
from pydantic import BaseModel, Field

from app.services.image_detection_service import ImageDetectionService, get_detection_service
from core.auth import get_current_user

router = APIRouter(tags=["AI图片真伪检测"])

UPLOAD_DIR = Path("uploads/detection_temp")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ========== 请求/响应模型 ==========

class DetectionResultResponse(BaseModel):
    record_id: int
    image_url: str
    detection_result: int
    confidence_score: float
    anomaly_type: Optional[str] = None
    anomaly_image: Optional[str] = None
    detection_time: str
    message: str = ""


class ReviewSubmitRequest(BaseModel):
    record_id: int = Field(..., description="检测记录ID")
    review_result: int = Field(..., description="复核结果：0-正常,1-可疑,2-篡改")
    remark: Optional[str] = Field(None, description="复核备注")


class PaginatedResponse(BaseModel):
    success: bool
    data: List[dict]
    total: int
    page: int
    page_size: int


# ========== 路由 ==========

@router.post("/upload", response_model=DetectionResultResponse)
async def upload_and_detect(
        file: UploadFile = File(..., description="磅单图片"),
        auto_detect: bool = Query(True, description="是否自动检测"),
        current_user: dict = Depends(get_current_user),
        service: ImageDetectionService = Depends(get_detection_service)
):
    """上传磅单图片进行真伪检测"""
    allowed_types = ["image/jpeg", "image/jpg", "image/png", "image/bmp"]
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="仅支持jpg/png/bmp格式")

    temp_path = None
    try:
        image_data = await file.read()
        image_md5 = service.calculate_md5(image_data)

        duplicate = service.check_duplicate(image_md5)
        if duplicate:
            return DetectionResultResponse(
                record_id=duplicate["id"],
                image_url="",
                detection_result=duplicate["detection_result"],
                confidence_score=1.0,
                detection_time="",
                message="图片已存在，返回历史检测结果"
            )

        filename = f"{image_md5[:8]}_{file.filename}"
        file_path = UPLOAD_DIR / filename
        with open(file_path, "wb") as f:
            f.write(image_data)
        temp_path = str(file_path)

        record_id = service.create_detection_record(
            image_path=temp_path,
            image_md5=image_md5,
            uploaded_by=current_user.get("id")
        )

        if not auto_detect:
            return DetectionResultResponse(
                record_id=record_id,
                image_url=temp_path,
                detection_result=0,
                confidence_score=0,
                detection_time="",
                message="图片已保存，等待检测"
            )

        result = service.detect_tampering(temp_path)

        if not result["success"]:
            return DetectionResultResponse(
                record_id=record_id,
                image_url=temp_path,
                detection_result=0,
                confidence_score=0,
                detection_time="",
                message=f"检测失败: {result.get('error', '未知错误')}"
            )

        service.update_detection_result(record_id, result)

        return DetectionResultResponse(
            record_id=record_id,
            image_url=temp_path,
            detection_result=result["result"],
            confidence_score=result["confidence"],
            anomaly_type=result.get("anomaly_type"),
            anomaly_image=result.get("anomaly_image"),
            detection_time=str(result.get("detection_time", "")),
            message="检测完成"
        )

    except Exception as e:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")


@router.get("/records", response_model=PaginatedResponse)
async def list_records(
        detection_result: Optional[int] = Query(None, description="检测结果筛选"),
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        current_user: dict = Depends(get_current_user),
        service: ImageDetectionService = Depends(get_detection_service)
):
    """查询检测记录列表"""
    try:
        from core.database import get_conn
        
        with get_conn() as conn:
            with conn.cursor() as cur:
                where = ["1=1"]
                params = []

                if detection_result is not None:
                    where.append("detection_result = %s")
                    params.append(detection_result)

                where_sql = " AND ".join(where)
                offset = (page - 1) * page_size

                cur.execute(f"SELECT COUNT(*) FROM pd_image_detection WHERE {where_sql}", tuple(params))
                total = cur.fetchone()[0]

                cur.execute(f"""
                    SELECT d.*, u.name as reviewer_name
                    FROM pd_image_detection d
                    LEFT JOIN pd_users u ON d.reviewer_id = u.id
                    WHERE {where_sql}
                    ORDER BY d.upload_time DESC
                    LIMIT %s OFFSET %s
                """, tuple(params + [page_size, offset]))

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
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/records/{record_id}", response_model=dict)
async def get_record(
        record_id: int,
        current_user: dict = Depends(get_current_user),
        service: ImageDetectionService = Depends(get_detection_service)
):
    """获取检测记录详情"""
    try:
        from core.database import get_conn
        
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT d.*, u.name as reviewer_name
                    FROM pd_image_detection d
                    LEFT JOIN pd_users u ON d.reviewer_id = u.id
                    WHERE d.id = %s
                """, (record_id,))

                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="记录不存在")

                columns = [desc[0] for desc in cur.description]
                data = dict(zip(columns, row))

                for key in ['upload_time', 'detection_time', 'review_time']:
                    if data.get(key):
                        data[key] = str(data[key])

                return {"success": True, "data": data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/review", response_model=dict)
async def submit_review(
        request: ReviewSubmitRequest,
        current_user: dict = Depends(get_current_user),
        service: ImageDetectionService = Depends(get_detection_service)
):
    """提交人工复核结果"""
    if request.review_result not in [0, 1, 2]:
        raise HTTPException(status_code=400, detail="复核结果必须为0、1或2")

    result = service.submit_review(
        record_id=request.record_id,
        reviewer_id=current_user["id"],
        review_result=request.review_result,
        remark=request.remark
    )

    if result["success"]:
        return result
    else:
        raise HTTPException(status_code=400, detail=result.get("error"))


@router.get("/review/pending", response_model=PaginatedResponse)
async def get_pending_reviews(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        current_user: dict = Depends(get_current_user),
        service: ImageDetectionService = Depends(get_detection_service)
):
    """获取待复核列表"""
    return service.get_pending_reviews(page, page_size)


@router.get("/dashboard", response_model=dict)
async def get_dashboard_stats(
        days: int = Query(7, ge=1, le=90),
        current_user: dict = Depends(get_current_user),
        service: ImageDetectionService = Depends(get_detection_service)
):
    """获取仪表盘统计数据"""
    return service.get_dashboard_stats(days)