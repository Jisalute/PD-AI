"""
客户管理路由 - 冶炼厂客户档案
支持手动录入、编辑、查询
"""
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field

from app.services.customer_service import CustomerService, get_customer_service

router = APIRouter(prefix="/customers", tags=["客户管理"])


# ============ 请求/响应模型 ============

class CustomerCreateRequest(BaseModel):
    smelter_name: str = Field(..., description="冶炼厂名称", max_length=128)
    address: Optional[str] = Field(None, description="冶炼厂地址", max_length=255)
    contact_person: Optional[str] = Field(None, description="联系人", max_length=64)
    contact_phone: Optional[str] = Field(None, description="联系电话", max_length=32)
    contact_address: Optional[str] = Field(None, description="联系人地址", max_length=255)


class CustomerUpdateRequest(BaseModel):
    smelter_name: Optional[str] = Field(None, description="冶炼厂名称", max_length=128)
    address: Optional[str] = Field(None, description="冶炼厂地址", max_length=255)
    contact_person: Optional[str] = Field(None, description="联系人", max_length=64)
    contact_phone: Optional[str] = Field(None, description="联系电话", max_length=32)
    contact_address: Optional[str] = Field(None, description="联系人地址", max_length=255)


class CustomerOut(BaseModel):
    id: int
    smelter_name: str
    address: Optional[str] = None
    contact_person: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_address: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ============ 路由 ============

@router.post("/", response_model=dict)
async def create_customer(
        request: CustomerCreateRequest,
        service: CustomerService = Depends(get_customer_service)
):
    """手动录入客户"""
    try:
        data = {
            "smelter_name": request.smelter_name,
            "address": request.address,
            "contact_person": request.contact_person,
            "contact_phone": request.contact_phone,
            "contact_address": request.contact_address,
        }

        result = service.create_customer(data)

        if result["success"]:
            return result
        else:
            raise HTTPException(status_code=400, detail=result.get("error"))

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=dict)
async def list_customers(
        exact_smelter_name: Optional[str] = Query(None, description="精确冶炼厂名称"),
        exact_contact_person: Optional[str] = Query(None, description="精确联系人"),
        exact_contact_phone: Optional[str] = Query(None, description="精确联系电话"),
        fuzzy_keywords: Optional[str] = Query(None, description="模糊关键词（空格分隔）"),
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        service: CustomerService = Depends(get_customer_service)
):
    """查询客户列表（支持搜索）"""
    return service.list_customers(
        exact_smelter_name=exact_smelter_name,
        exact_contact_person=exact_contact_person,
        exact_contact_phone=exact_contact_phone,
        fuzzy_keywords=fuzzy_keywords,
        page=page,
        page_size=page_size,
    )


@router.get("/{customer_id}", response_model=CustomerOut)
async def get_customer(
        customer_id: int,
        service: CustomerService = Depends(get_customer_service)
):
    """查看客户详情"""
    customer = service.get_customer(customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="客户不存在")

    # 转换时间格式
    for key in ['created_at', 'updated_at']:
        if customer.get(key):
            customer[key] = str(customer[key])

    return customer


@router.put("/{customer_id}", response_model=dict)
async def update_customer(
        customer_id: int,
        request: CustomerUpdateRequest,
        service: CustomerService = Depends(get_customer_service)
):
    """编辑客户信息"""
    try:
        data = {}
        if request.smelter_name is not None:
            data["smelter_name"] = request.smelter_name
        if request.address is not None:
            data["address"] = request.address
        if request.contact_person is not None:
            data["contact_person"] = request.contact_person
        if request.contact_phone is not None:
            data["contact_phone"] = request.contact_phone
        if request.contact_address is not None:
            data["contact_address"] = request.contact_address

        result = service.update_customer(customer_id, data)

        if result["success"]:
            return result
        else:
            raise HTTPException(status_code=400, detail=result.get("error"))

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{customer_id}")
async def delete_customer(
        customer_id: int,
        service: CustomerService = Depends(get_customer_service)
):
    """删除客户"""
    result = service.delete_customer(customer_id)
    if result["success"]:
        return result
    else:
        raise HTTPException(status_code=400, detail=result.get("error"))
