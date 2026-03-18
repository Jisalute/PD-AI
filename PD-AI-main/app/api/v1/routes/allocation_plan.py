"""
动态分配方案 API 路由
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional, Dict, Any
from datetime import date
from pydantic import BaseModel, Field

from app.services.allocation_plan_service import get_allocation_plan_service, AllocationPlanService

router = APIRouter(prefix="/allo cation-plans", tags=["Allocation Plans"])

# ---请求/响应模型  ---

class PlanCreate(BaseModel):
    biz_date: date = Field(..., description="执行日期")
    category_range: Optional[str] = Field(None, description="适用品类范围")
    plan_details: Dict[str, Any] = Field(..., description="方案详情: 包含各仓库分配量、物流指令等(JSON)")
    input_factors: Optional[Dict[str, Any]] = Field(None, description="输入因素快照: 库存/合同/成本等")
    expected_kpi: Optional[Dict[str, Any]] = Field(None, description="预期KPI评估: 成本/时效/满意度")
    status: Optional[int] = Field(0, ge=0, le=4, description="状态: 0-草稿, 1-已发布, 2-执行中, 3-已完成, 4-已取消")
    creator: Optional[str] = Field(None, description="创建人/生成算法版本")
    execute_log: Optional[str] = Field(None, description="执行日志摘要")

class PlanStatusUpdate(BaseModel):
    status: int = Field(..., ge=0, le=4, description="新状态")
    operator: Optional[str] = Field(None, description="操作人")

class PlanContentUpdate(BaseModel):
    category_range: Optional[str] = None
    plan_details: Optional[Dict[str, Any]] = None
    input_factors: Optional[Dict[str, Any]] = None
    expected_kpi: Optional[Dict[str, Any]] = None
    execute_log: Optional[str] = None

class PlanResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    message: Optional[str] = None

# --- 路由 ---

@router.post("/", response_model=PlanResponse, summary="创建分配方案")
def create_plan(
    plan_data: PlanCreate,
    service: AllocationPlanService = Depends(get_allocation_plan_service)
):
    result = service.create_plan(plan_data.dict())
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@router.get("/{plan_id}", summary="获取方案详情")
def get_plan(
    plan_id: int,
    service: AllocationPlanService = Depends(get_allocation_plan_service)
):
    try:
        record = service.get_plan_by_id(plan_id)
        if not record:
            raise HTTPException(status_code=404, detail="Plan not found")
        return {"success": True, "data": record}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{plan_id}/status", response_model=PlanResponse, summary="更新方案状态 (状态机)")
def update_plan_status(
    plan_id: int,
    status_update: PlanStatusUpdate,
    service: AllocationPlanService = Depends(get_allocation_plan_service)
):
    result = service.update_plan_status(
        plan_id=plan_id, 
        new_status=status_update.status, 
        operator=status_update.operator
    )
    if not result["success"]:
        if "not found" in result["error"].lower():
            raise HTTPException(status_code=404, detail=result["error"])
        # 状态流转错误返回 400
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@router.put("/{plan_id}/content", response_model=PlanResponse, summary="更新方案内容 (仅草稿)")
def update_plan_content(
    plan_id: int,
    content_update: PlanContentUpdate,
    service: AllocationPlanService = Depends(get_allocation_plan_service)
):
    data = {k: v for k, v in content_update.dict().items() if v is not None}
    if not data:
        return {"success": True, "data": service.get_plan_by_id(plan_id), "message": "No fields to update"}
        
    result = service.update_plan_content(plan_id=plan_id, data=data)
    if not result["success"]:
        if "not found" in result["error"].lower():
            raise HTTPException(status_code=404, detail=result["error"])
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@router.get("/", summary="分页查询方案列表")
def list_plans(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    biz_date: Optional[date] = None,
    status: Optional[int] = Query(None, ge=0, le=4),
    creator: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    service: AllocationPlanService = Depends(get_allocation_plan_service)
):
    try:
        result = service.list_plans(
            page=page,
            page_size=page_size,
            biz_date=biz_date,
            status=status,
            creator=creator,
            date_from=date_from,
            date_to=date_to
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{plan_id}", response_model=PlanResponse, summary="删除方案")
def delete_plan(
    plan_id: int,
    service: AllocationPlanService = Depends(get_allocation_plan_service)
):
    result = service.delete_plan(plan_id)
    if not result["success"]:
        if "not found" in result["error"].lower():
            raise HTTPException(status_code=404, detail=result["error"])
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@router.get("/export", summary="导出方案数据")
def export_plans(
    ids: Optional[str] = Query(None, description="逗号分隔的ID列表"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    status: Optional[int] = None,
    service: AllocationPlanService = Depends(get_allocation_plan_service)
):
    try:
        id_list = None
        if ids:
            try:
                id_list = [int(x.strip()) for x in ids.split(",")]
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid ID format.")
        
        data = service.export_plans(
            ids=id_list,
            date_from=date_from,
            date_to=date_to,
            status=status
        )
        return {"success": True, "data": data, "count": len(data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))