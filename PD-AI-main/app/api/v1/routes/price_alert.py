"""
价格预警 API 路由
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional, Dict, Any
from datetime import date
from decimal import Decimal

from app.services.price_alert_service import get_price_alert_service, PriceAlertService
from pydantic import BaseModel, Field

router = APIRouter(prefix="/price-alerts", tags=["Price Alerts"])

# --- 请求/响应模型 ---

class AlertCreate(BaseModel):
    rule_id: str = Field(..., description="触发规则ID")
    rule_name: Optional[str] = Field(None, description="规则名称快照")
    category_code: str = Field(..., description="关联品类代码")
    current_price: Decimal = Field(..., description="触发时的当前价格")
    threshold_value: Optional[Decimal] = Field(None, description="触发阈值")
    trigger_reason: Optional[str] = Field(None, description="触发具体原因描述")
    level: Optional[int] = Field(None, ge=1, le=3, description="预警级别: 1-低, 2-中, 3-高")
    status: Optional[int] = Field(0, ge=0, le=2, description="状态: 0-未确认, 1-已确认, 2-已关闭")
    confirm_user: Optional[str] = Field(None, description="确认人")
    confirm_time: Optional[str] = Field(None, description="确认时间 (ISO格式)")
    remarks: Optional[str] = Field(None, description="备注")

class AlertStatusUpdate(BaseModel):
    status: int = Field(..., ge=0, le=2, description="新状态: 0-未确认, 1-已确认, 2-已关闭")
    confirm_user: Optional[str] = Field(None, description="操作确认的用户名")

class AlertResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    message: Optional[str] = None

# --- 路由 ---

@router.post("/", response_model=AlertResponse, summary="创建价格预警")
def create_alert(
    alert_data: AlertCreate,
    service: PriceAlertService = Depends(get_price_alert_service)
):
    result = service.create_alert(alert_data.dict())
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@router.get("/{alert_id}", summary="获取预警详情")
def get_alert(
    alert_id: int,
    service: PriceAlertService = Depends(get_price_alert_service)
):
    try:
        record = service.get_alert_by_id(alert_id)
        if not record:
            raise HTTPException(status_code=404, detail="Alert not found")
        return {"success": True, "data": record}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{alert_id}/status", response_model=AlertResponse, summary="更新预警状态")
def update_alert_status(
    alert_id: int,
    status_update: AlertStatusUpdate,
    service: PriceAlertService = Depends(get_price_alert_service)
):
    result = service.update_alert_status(
        alert_id=alert_id, 
        status=status_update.status, 
        confirm_user=status_update.confirm_user
    )
    if not result["success"]:
        if "not found" in result["error"].lower():
            raise HTTPException(status_code=404, detail=result["error"])
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@router.get("/", summary="分页查询预警列表")
def list_alerts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category_code: Optional[str] = None,
    status: Optional[int] = Query(None, ge=0, le=2),
    level: Optional[int] = Query(None, ge=1, le=3),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    fuzzy_keywords: Optional[str] = None,
    service: PriceAlertService = Depends(get_price_alert_service)
):
    try:
        result = service.list_alerts(
            page=page,
            page_size=page_size,
            category_code=category_code,
            status=status,
            level=level,
            date_from=date_from,
            date_to=date_to,
            fuzzy_keywords=fuzzy_keywords
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{alert_id}", response_model=AlertResponse, summary="删除预警记录")
def delete_alert(
    alert_id: int,
    service: PriceAlertService = Depends(get_price_alert_service)
):
    result = service.delete_alert(alert_id)
    if not result["success"]:
        if "not found" in result["error"].lower():
            raise HTTPException(status_code=404, detail=result["error"])
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@router.get("/export", summary="导出预警数据")
def export_alerts(
    ids: Optional[str] = Query(None, description="逗号分隔的ID列表"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    category_code: Optional[str] = None,
    service: PriceAlertService = Depends(get_price_alert_service)
):
    try:
        id_list = None
        if ids:
            try:
                id_list = [int(x.strip()) for x in ids.split(",")]
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid ID format. Use comma-separated integers.")
        
        data = service.export_alerts(
            ids=id_list,
            date_from=date_from,
            date_to=date_to,
            category_code=category_code
        )
        # 这里可以直接返回 JSON，或者集成 pandas 生成 Excel 文件流
        # 为了保持简单，暂时返回 JSON 列表
        return {"success": True, "data": data, "count": len(data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))