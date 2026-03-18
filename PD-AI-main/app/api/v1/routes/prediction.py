"""
预测每日配运量路由 
支持预测生成、人工调整、历史记录查询、准确率分析基础数据
"""
import os
import re
import shutil
from decimal import Decimal
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Query, Body
from pydantic import BaseModel, Field
from datetime import date, datetime
from app.services.prediction_service import PredictionService, get_prediction_service

router = APIRouter(prefix="/predictions", tags=["预测每日配运量"])

# ============ 请求/响应模型 ============

class PredictionProductItem(BaseModel):
    """预留品类扩展字段，当前主要用 category_code"""
    category_code: str
    notes: Optional[str] = None

class PredictionCreateRequest(BaseModel):
    """创建/生成预测记录"""
    biz_date: date = Field(..., description="预测日期")
    category_code: str = Field(..., max_length=50, description="品类代码")
    predicted_value: float = Field(..., ge=0, description="预测配运量")
    rec_interval_start: Optional[datetime] = Field(None, description="推荐收货开始时间")
    rec_interval_end: Optional[datetime] = Field(None, description="推荐收货结束时间")
    operator: str = Field(..., description="操作人姓名/ID")
    remarks: Optional[str] = Field(None, description="备注")

class PredictionUpdateRequest(BaseModel):
    """人工调整预测记录"""
    adjusted_value: Optional[float] = Field(None, ge=0, description="调整后数值")
    adjust_reason: Optional[str] = Field(None, max_length=255, description="人工调整原因")
    status: Optional[int] = Field(None, ge=0, le=1, description="状态: 1-有效, 0-作废")
    operator: str = Field(..., description="操作人姓名/ID")
    remarks: Optional[str] = Field(None, description="备注")

class PredictionOut(BaseModel):
    """预测记录详情响应"""
    predict_id: int
    biz_date: date
    category_code: str
    predicted_value: float
    rec_interval_start: Optional[datetime] = None
    rec_interval_end: Optional[datetime] = None
    status: int
    adjust_reason: Optional[str] = None
    adjusted_value: Optional[float] = None
    operator: Optional[str] = None
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None
    remarks: Optional[str] = None

    class Config:
        from_attributes = True

class PredictionListResponse(BaseModel):
    """分页列表响应"""
    total: int
    items: List[PredictionOut] = []
    page: int
    page_size: int

# ============ 路由 ============

@router.post("/", response_model=PredictionOut)
async def create_prediction(
    request: PredictionCreateRequest,
    service: PredictionService = Depends(get_prediction_service)
):
    """
    创建新的预测记录。
    如果同日期同品类已存在有效记录，Service层应处理冲突或抛出异常。
    """
    try:
        # 转换数据类型以匹配 Service 层期望 (Decimal)
        data = {
            "biz_date": request.biz_date,
            "category_code": request.category_code,
            "predicted_value": Decimal(str(request.predicted_value)),
            "rec_interval_start": request.rec_interval_start,
            "rec_interval_end": request.rec_interval_end,
            "operator": request.operator,
            "remarks": request.remarks,
        }
        
        result = service.create_prediction(data)
        
        if result["success"]:
            # 获取刚创建的详情返回
            detail = service.get_prediction_by_id(result["data"]["predict_id"])
            return detail
        else:
            raise HTTPException(status_code=400, detail=result.get("error"))
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{predict_id}", response_model=dict)
async def update_prediction(
    predict_id: int,
    request: PredictionUpdateRequest,
    service: PredictionService = Depends(get_prediction_service)
):
    """
    人工调整预测记录（修改数值、填写原因、作废等）。
    """
    try:
        data = {}
        if request.adjusted_value is not None:
            data["adjusted_value"] = Decimal(str(request.adjusted_value))
        if request.adjust_reason is not None:
            data["adjust_reason"] = request.adjust_reason
        if request.status is not None:
            data["status"] = request.status
        if request.remarks is not None:
            data["remarks"] = request.remarks
            
        # 必须传入操作人
        data["operator"] = request.operator

        result = service.update_prediction(predict_id, data)
        
        if result["success"]:
            return {"success": True, "message": "更新成功"}
        else:
            # 区分是“未找到记录”还是“其他错误”
            if "not found" in str(result.get("error")).lower():
                raise HTTPException(status_code=404, detail=result.get("error"))
            raise HTTPException(status_code=400, detail=result.get("error"))
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/", response_model=PredictionListResponse)
async def list_predictions(
    biz_date_from: Optional[date] = Query(None, description="开始日期"),
    biz_date_to: Optional[date] = Query(None, description="结束日期"),
    category_code: Optional[str] = Query(None, description="品类代码"),
    status: Optional[int] = Query(None, description="状态筛选"),
    fuzzy_keywords: Optional[str] = Query(None, description="模糊关键词（空格分隔，暂未实现，预留）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: PredictionService = Depends(get_prediction_service)
):
    """
    获取预测记录列表（分页）。
    支持按日期范围、品类、状态筛选。
    """
    try:
        result = service.list_predictions(
            page=page,
            page_size=page_size,
            biz_date_from=biz_date_from,
            biz_date_to=biz_date_to,
            category_code=category_code,
            status=status,
            fuzzy_keywords=fuzzy_keywords
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{predict_id}", response_model=PredictionOut)
async def get_prediction_detail(
    predict_id: int,
    service: PredictionService = Depends(get_prediction_service)
):
    """
    查看单条预测记录详情。
    """
    detail = service.get_prediction_by_id(predict_id)
    if not detail:
        raise HTTPException(status_code=404, detail="预测记录不存在")
    return detail

@router.delete("/{predict_id}")
async def delete_prediction(
    predict_id: int,
    service: PredictionService = Depends(get_prediction_service)
):
    """
    删除预测记录（逻辑删除或物理删除，取决于 Service 实现）。
    """
    result = service.delete_prediction(predict_id)
    if result["success"]:
        return {"success": True, "message": "删除成功"}
    else:
        if "not found" in str(result.get("error")).lower():
            raise HTTPException(status_code=404, detail=result.get("error"))
        raise HTTPException(status_code=400, detail=result.get("error"))

@router.post("/export")
async def export_predictions(
    predict_ids: List[int] = Body(None, description="要导出的预测ID列表，空则导出当前筛选结果"),
    biz_date_from: Optional[date] = Body(None, description="导出范围开始日期"),
    biz_date_to: Optional[date] = Body(None, description="导出范围结束日期"),
    service: PredictionService = Depends(get_prediction_service)
):
    """
    导出预测数据为 CSV。
    逻辑参考 contracts.py 的 export_contracts，需 Service 层支持。
    """
    try:
        # 这里假设 Service 层有一个 export_predictions 方法返回字典列表
        # 如果 Service 层尚未实现，此处会报错，需补充 Service 代码
        data = service.export_predictions(
            ids=predict_ids,
            date_from=biz_date_from,
            date_to=biz_date_to
        )
        
        import csv
        from io import StringIO
        from fastapi.responses import StreamingResponse
        
        if not data:
            raise HTTPException(status_code=404, detail="无数据可导出")

        columns = list(data[0].keys())
        buffer = StringIO()
        writer = csv.writer(buffer)
        writer.writerow(columns)
        for row in data:
            writer.writerow([row.get(col) for col in columns])

        filename = "predictions_export.csv"
        csv_bytes = buffer.getvalue().encode("utf-8-sig")
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        
        return StreamingResponse(
            iter([csv_bytes]),
            media_type="text/csv; charset=utf-8",
            headers=headers,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")