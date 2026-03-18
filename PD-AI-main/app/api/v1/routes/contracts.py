"""
合同管理路由 - 完整版
支持OCR识别、手动录入、查看、编辑、导出
"""
import csv
import os
import re
import shutil
from io import StringIO
from decimal import Decimal
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query, Body
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from datetime import date

from app.services.contract_service import ContractService, get_contract_service

router = APIRouter(prefix="/contracts", tags=["合同管理"])

UPLOAD_DIR = Path("uploads/contracts")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ============ 请求/响应模型 ============

class ProductItem(BaseModel):
    product_name: str
    unit_price: Optional[float] = None

class ContractProductOut(BaseModel):
    id: int
    product_name: str
    unit_price: Optional[float] = None
    sort_order: int

class ContractOCRResponse(BaseModel):
    contract_no: Optional[str] = None
    contract_date: Optional[str] = None
    end_date: Optional[str] = None
    smelter_company: Optional[str] = None
    total_quantity: Optional[float] = None
    arrival_payment_ratio: float = 0.9
    final_payment_ratio: float = 0.1
    products: List[ProductItem] = []
    contract_unit_price: Optional[float] = None
    remittance_unit_price: Optional[float] = None
    unit_price: Optional[float] = None
    ocr_success: bool = True
    ocr_message: str = ""
    saved_to_db: bool = False
    contract_id: Optional[int] = None
    db_message: Optional[str] = None
    image_saved: bool = False
    image_path: Optional[str] = None
    image_filename: Optional[str] = None
    raw_text: Optional[str] = None

class ContractCreateRequest(BaseModel):
    contract_no: str
    contract_date: Optional[str] = None
    end_date: Optional[str] = None
    smelter_company: Optional[str] = None
    total_quantity: Optional[float] = None
    arrival_payment_ratio: float = 0.9
    final_payment_ratio: float = 0.1
    products: List[ProductItem] = []
    status: str = "生效中"
    remarks: Optional[str] = None

class ContractUpdateRequest(BaseModel):
    contract_no: Optional[str] = None
    contract_date: Optional[str] = None
    end_date: Optional[str] = None
    smelter_company: Optional[str] = None
    total_quantity: Optional[float] = None
    arrival_payment_ratio: Optional[float] = None
    final_payment_ratio: Optional[float] = None
    products: Optional[List[ProductItem]] = None
    status: Optional[str] = None
    remarks: Optional[str] = None

class ContractOut(BaseModel):
    id: int
    seq_no: Optional[int] = None  # ← 改为可选
    contract_no: str
    contract_date: Optional[date] = None
    end_date: Optional[date] = None
    smelter_company: Optional[str] = None
    total_quantity: Optional[float] = None
    arrival_payment_ratio: float
    final_payment_ratio: float
    status: str
    products: List[ContractProductOut] = []
    created_at: Optional[str] = None  # ← 保持str，但在获取数据时转换
    updated_at: Optional[str] = None  # ← 也加上这个


# ============ 路由 ============

@router.post("/ocr", response_model=ContractOCRResponse)
async def ocr_recognize(
    file: UploadFile = File(..., description="合同图片"),
    auto_save: bool = Query(True, description="是否自动保存（默认true，OCR可能不完整）"),
    save_image: bool = Query(False, description="是否保存图片"),
    service: ContractService = Depends(get_contract_service)
):
    """OCR识别合同 - 支持不完整识别，用户后续补充"""
    allowed_types = ["image/jpeg", "image/jpg", "image/png", "image/bmp"]
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="仅支持jpg/png/bmp格式")

    temp_path = UPLOAD_DIR / f"temp_{os.urandom(4).hex()}.jpg"

    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        processed_path = service.preprocess_image(str(temp_path))
        result = service.recognize_contract(processed_path)

        if processed_path != str(temp_path) and os.path.exists(processed_path):
            os.remove(processed_path)

        data = result["data"]
        contract_no = data.get("contract_no")

        # 图片处理
        image_saved = False
        image_path = None
        image_filename = None

        if save_image and contract_no:
            safe_name = re.sub(r'[^\w\-]', '_', contract_no)
            image_filename = f"{safe_name}.jpg"
            final_path = UPLOAD_DIR / image_filename

            if final_path.exists():
                os.remove(final_path)

            os.rename(temp_path, final_path)
            image_saved = True
            image_path = str(final_path)
        else:
            os.remove(temp_path)

        # 自动保存逻辑
        if auto_save and contract_no:
            existing = service.get_contract_detail_by_no(contract_no)
            if existing:
                data["saved_to_db"] = False
                data["db_message"] = f"合同 {contract_no} 已存在"
                data["contract_id"] = existing["id"]
            else:
                save_data = {
                    "contract_no": contract_no,
                    "contract_date": data.get("contract_date"),
                    "end_date": data.get("end_date"),
                    "smelter_company": data.get("smelter_company"),
                    "total_quantity": Decimal(str(data["total_quantity"])) if data.get("total_quantity") else None,
                    "arrival_payment_ratio": Decimal(str(data["arrival_payment_ratio"])),
                    "final_payment_ratio": Decimal(str(data["final_payment_ratio"])),
                    "contract_image_path": image_path,
                }

                products_data = []
                for p in data.get("products", []):
                    products_data.append({
                        "product_name": p["product_name"],
                        "unit_price": Decimal(str(p["unit_price"])) if p.get("unit_price") else None,
                    })

                result_db = service.create_contract(save_data, products_data)

                if result_db["success"]:
                    data["saved_to_db"] = True
                    data["contract_id"] = result_db["data"]["id"]
                    if data.get("products"):
                        data["db_message"] = "合同已自动保存"
                    else:
                        data["db_message"] = "合同已保存，但品种信息为空"
                else:
                    data["saved_to_db"] = False
                    data["db_message"] = f"保存失败: {result_db.get('error')}"
                    if result_db.get("existing_id"):
                        data["contract_id"] = result_db["existing_id"]
        else:
            data["saved_to_db"] = False
            if not contract_no:
                data["db_message"] = "未识别到合同编号，请手动填写后保存"
            else:
                data["db_message"] = "OCR结果不完整，请检查并补充后手动保存"

        data["image_saved"] = image_saved
        data["image_path"] = image_path
        data["image_filename"] = image_filename

        return ContractOCRResponse(**data)

    except HTTPException:
        if temp_path.exists():
            os.remove(temp_path)
        raise
    except Exception as e:
        if temp_path.exists():
            os.remove(temp_path)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/manual", response_model=ContractOut)
async def create_manual(
    request: ContractCreateRequest,
    service: ContractService = Depends(get_contract_service)
):
    """手动录入合同"""
    try:
        existing = service.get_contract_detail_by_no(request.contract_no)
        if existing:
            raise HTTPException(status_code=400, detail=f"合同编号 {request.contract_no} 已存在")

        data = {
            "contract_no": request.contract_no,
            "contract_date": request.contract_date,
            "end_date": request.end_date,
            "smelter_company": request.smelter_company,
            "total_quantity": Decimal(str(request.total_quantity)) if request.total_quantity else None,
            "arrival_payment_ratio": Decimal(str(request.arrival_payment_ratio)),
            "final_payment_ratio": Decimal(str(request.final_payment_ratio)),
            "status": request.status,
            "remarks": request.remarks,
        }

        products = []
        for p in request.products:
            products.append({
                "product_name": p.product_name,
                "unit_price": Decimal(str(p.unit_price)) if p.unit_price else None,
            })

        result = service.create_contract(data, products)

        if result["success"]:
            detail = service.get_contract_detail(result["data"]["id"])
            return detail
        else:
            raise HTTPException(status_code=400, detail=result.get("error"))

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=dict)
async def list_contracts(
    exact_contract_no: Optional[str] = Query(None, description="精确合同编号"),
    exact_smelter_company: Optional[str] = Query(None, description="精确冶炼厂"),
    exact_status: Optional[str] = Query(None, description="精确状态"),
    fuzzy_keywords: Optional[str] = Query(None, description="模糊关键词（空格分隔）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: ContractService = Depends(get_contract_service)
):
    """获取合同列表（分页）"""
    return service.list_contracts(
        page,
        page_size,
        exact_contract_no,
        exact_smelter_company,
        exact_status,
        fuzzy_keywords,
    )


@router.get("/{contract_id}", response_model=ContractOut)
async def get_contract(
    contract_id: int,
    service: ContractService = Depends(get_contract_service)
):
    """查看合同详情"""
    detail = service.get_contract_detail(contract_id)
    if not detail:
        raise HTTPException(status_code=404, detail="合同不存在")
    return detail


@router.put("/{contract_id}", response_model=dict)
async def update_contract(
    contract_id: int,
    request: ContractUpdateRequest,
    service: ContractService = Depends(get_contract_service)
):
    """编辑合同"""
    try:
        data = {}
        if request.contract_no is not None:
            data["contract_no"] = request.contract_no
        if request.contract_date is not None:
            data["contract_date"] = request.contract_date
        if request.end_date is not None:
            data["end_date"] = request.end_date
        if request.smelter_company is not None:
            data["smelter_company"] = request.smelter_company
        if request.total_quantity is not None:
            data["total_quantity"] = Decimal(str(request.total_quantity))
        if request.arrival_payment_ratio is not None:
            data["arrival_payment_ratio"] = Decimal(str(request.arrival_payment_ratio))
        if request.final_payment_ratio is not None:
            data["final_payment_ratio"] = Decimal(str(request.final_payment_ratio))
        if request.status is not None:
            data["status"] = request.status
        if request.remarks is not None:
            data["remarks"] = request.remarks

        products = None
        if request.products is not None:
            products = []
            for p in request.products:
                products.append({
                    "product_name": p.product_name,
                    "unit_price": Decimal(str(p.unit_price)) if p.unit_price else None,
                })

        result = service.update_contract(contract_id, data, products)

        if result["success"]:
            return {"success": True, "message": "更新成功"}
        else:
            raise HTTPException(status_code=400, detail=result.get("error"))

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{contract_id}")
async def delete_contract(
    contract_id: int,
    service: ContractService = Depends(get_contract_service)
):
    """删除合同"""
    result = service.delete_contract(contract_id)
    if result["success"]:
        return {"success": True, "message": "删除成功"}
    else:
        raise HTTPException(status_code=400, detail=result.get("error"))


@router.post("/export")
async def export_contracts(
    contract_ids: List[int] = Body(None, description="要导出的合同ID列表，空则导出全部"),
    service: ContractService = Depends(get_contract_service)
):
    """导出合同"""
    data = service.export_contracts(contract_ids)
    columns: List[str] = []
    for row in data:
        for key in row.keys():
            if key not in columns:
                columns.append(key)

    buffer = StringIO()
    writer = csv.writer(buffer)
    if columns:
        writer.writerow(columns)
        for row in data:
            writer.writerow([row.get(col) for col in columns])

    filename = "contracts_export.csv"
    if contract_ids and len(contract_ids) == 1 and data:
        contract_no = str(data[0].get("contract_no") or "").strip()
        if contract_no:
            safe_name = re.sub(r"[^A-Za-z0-9_-]", "_", contract_no)
            filename = f"{safe_name}.csv"

    csv_bytes = buffer.getvalue().encode("utf-8-sig")
    headers = {"Content-Disposition": f"attachment; filename=\"{filename}\""}
    return StreamingResponse(
        iter([csv_bytes]),
        media_type="text/csv; charset=utf-8",
        headers=headers,
    )