"""
供应异常 API 路由
对应表：t_supply_anomaly
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional, Dict, Any
from datetime import date
from pydantic import BaseModel, Field

from app.services.supply_anomaly_service import get_supply_anomaly_service, SupplyAnomalyService

router = APIRouter(prefix="/supply-anomalies", tags=["Supply Anomalies"])

# --- 请求/响应模型 ---

class AnomalyCreate(BaseModel):
    category_code: str = Field(..., description="受影响品类")
    supplier_code: str = Field(..., description="供应商代码")
    supplier_name: Optional[str] = Field(None, description="供应商名称")
    anomaly_type: Optional[str] = Field(None, description="异常类型: 断供/延迟/质量等")
    description: Optional[str] = Field(None, description="异常详细描述")
    impact_scope: Optional[str] = Field(None, description="影响范围描述")
    duration_days: Optional[int] = Field(None, ge=0, description="预计持续天数")
    status: Optional[int] = Field(0, ge=0, le=2, description="处理状态: 0-待处理, 1-处理中, 2-已解决")
    recommended_actions: Optional[Any] = Field(None, description="推荐应对动作列表(JSON格式)")
    handler: Optional[str] = Field(None, description="当前处理人")

class AnomalyStatusUpdate(BaseModel):
    status: int = Field(..., ge=0, le=2, description="新状态: 0-待处理, 1-处理中, 2-已解决")
    handler: Optional[str] = Field(None, description="当前处理人")

class AnomalyDetailsUpdate(BaseModel):
    description: Optional[str] = None
    impact_scope: Optional[str] = None
    duration_days: Optional[int] = None
    recommended_actions: Optional[Any] = None
    supplier_name: Optional[str] = None

class AnomalyResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    message: Optional[str] = None

# --- 路由 ---

@router.post("/", response_model=AnomalyResponse, summary="创建供应异常记录")
def create_anomaly(
    anomaly_data: AnomalyCreate,
    service: SupplyAnomalyService = Depends(get_supply_anomaly_service)
):
    result = service.create_anomaly(anomaly_data.dict())
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@router.get("/{anomaly_id}", summary="获取异常详情")
def get_anomaly(
    anomaly_id: int,
    service: SupplyAnomalyService = Depends(get_supply_anomaly_service)
):
    try:
        record = service.get_anomaly_by_id(anomaly_id)
        if not record:
            raise HTTPException(status_code=404, detail="Anomaly not found")
        return {"success": True, "data": record}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{anomaly_id}/status", response_model=AnomalyResponse, summary="更新异常处理状态")
def update_anomaly_status(
    anomaly_id: int,
    status_update: AnomalyStatusUpdate,
    service: SupplyAnomalyService = Depends(get_supply_anomaly_service)
):
    result = service.update_anomaly_status(
        anomaly_id=anomaly_id, 
        status=status_update.status, 
        handler=status_update.handler
    )
    if not result["success"]:
        if "not found" in result["error"].lower():
            raise HTTPException(status_code=404, detail=result["error"])
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@router.put("/{anomaly_id}/details", response_model=AnomalyResponse, summary="更新异常详细信息")
def update_anomaly_details(
    anomaly_id: int,
    details_update: AnomalyDetailsUpdate,
    service: SupplyAnomalyService = Depends(get_supply_anomaly_service)
):
    # 过滤掉 None 值，只更新传来的字段
    data = {k: v for k, v in details_update.dict().items() if v is not None}
    if not data:
        return {"success": True, "data": service.get_anomaly_by_id(anomaly_id), "message": "No fields to update"}
        
    result = service.update_anomaly_details(anomaly_id=anomaly_id, data=data)
    if not result["success"]:
        if "not found" in result["error"].lower():
            raise HTTPException(status_code=404, detail=result["error"])
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@router.get("/", summary="分页查询异常列表")
def list_anomalies(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category_code: Optional[str] = None,
    supplier_code: Optional[str] = None,
    anomaly_type: Optional[str] = None,
    status: Optional[int] = Query(None, ge=0, le=2),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    fuzzy_keywords: Optional[str] = None,
    service: SupplyAnomalyService = Depends(get_supply_anomaly_service)
):
    try:
        result = service.list_anomalies(
            page=page,
            page_size=page_size,
            category_code=category_code,
            supplier_code=supplier_code,
            anomaly_type=anomaly_type,
            status=status,
            date_from=date_from,
            date_to=date_to,
            fuzzy_keywords=fuzzy_keywords
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{anomaly_id}", response_model=AnomalyResponse, summary="删除异常记录")
def delete_anomaly(
    anomaly_id: int,
    service: SupplyAnomalyService = Depends(get_supply_anomaly_service)
):
    result = service.delete_anomaly(anomaly_id)
    if not result["success"]:
        if "not found" in result["error"].lower():
            raise HTTPException(status_code=404, detail=result["error"])
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@router.get("/export", summary="导出异常数据")
def export_anomalies(
    ids: Optional[str] = Query(None, description="逗号分隔的ID列表"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    category_code: Optional[str] = None,
    supplier_code: Optional[str] = None,
    service: SupplyAnomalyService = Depends(get_supply_anomaly_service)
):
    try:
        id_list = None
        if ids:
            try:
                id_list = [int(x.strip()) for x in ids.split(",")]
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid ID format.")
        
        data = service.export_anomalies(
            ids=id_list,
            date_from=date_from,
            date_to=date_to,
            category_code=category_code,
            supplier_code=supplier_code
        )
        return {"success": True, "data": data, "count": len(data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))