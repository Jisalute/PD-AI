from fastapi import APIRouter

from app.api.v1.routes import auth, balances, contracts, customers, deliveries, image_detection, weighbills

api_router =  APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(contracts.router, tags=["合同管理"])
api_router.include_router(customers.router, tags=["客户管理"])
api_router.include_router(deliveries.router, tags=["销售台账/报货订单"])
api_router.include_router(weighbills.router, tags=["磅单管理"])
api_router.include_router(balances.router, tags=["磅单结余管理"])
api_router.include_router(image_detection.router, tags=["AI图片真伪检测"])