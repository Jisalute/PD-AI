# app/api/v1/routes/wechat_chat.py
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer
import json
import logging
import uuid
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator
import time
import asyncio

from core.auth import get_current_user
from core.database_async import db_async
from core.websocket import manager
from services.coze_service import coze_service
from services.matching_service import matching_service

logger = logging.getLogger(__name__)

# 创建安全方案实例，用于Swagger文档
security = HTTPBearer()

router = APIRouter(
    prefix="/wechat", 
    tags=["微信小程序-智能体对话"],
    dependencies=[Depends(security)],  # 所有接口都需要认证
    responses={
        401: {"description": "未授权，请提供有效的JWT token"},
        403: {"description": "禁止访问，权限不足"},
        500: {"description": "服务器内部错误"}
    }
)


# ==================== 请求/响应模型 ====================

class ChatRequest(BaseModel):
    """聊天请求模型"""
    message: str = Field(..., description="用户消息内容", min_length=1, max_length=2000)
    session_id: Optional[str] = Field(None, description="会话ID，不传则自动生成")
    stream: bool = Field(False, description="是否使用流式响应")
    
    @validator('message')
    def validate_message(cls, v):
        if not v or not v.strip():
            raise ValueError('消息不能为空')
        return v.strip()
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "你好，我想报单",
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "stream": False
            }
        }


class ChatData(BaseModel):
    """聊天数据模型"""
    reply_text: str = Field(..., description="AI回复内容")
    session_id: str = Field(..., description="当前会话ID")
    status: str = Field(..., description="对话状态：collecting(收集中)/completed(完成)")
    missing_fields: List[str] = Field(default=[], description="缺失的字段列表")
    order_data: Optional[Dict[str, Any]] = Field(None, description="报单数据（如有）")
    
    class Config:
        json_schema_extra = {
            "example": {
                "reply_text": "您好，我是AI助手，有什么可以帮您？",
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "completed",
                "missing_fields": [],
                "order_data": None
            }
        }


class ChatResponse(BaseModel):
    """聊天响应模型"""
    code: int = Field(200, description="状态码")
    message: str = Field("success", description="状态信息")
    data: Optional[ChatData] = Field(None, description="响应数据")
    
    class Config:
        json_schema_extra = {
            "example": {
                "code": 200,
                "message": "success",
                "data": {
                    "reply_text": "您好，我是AI助手，有什么可以帮您？",
                    "session_id": "550e8400-e29b-41d4-a716-446655440000",
                    "status": "completed",
                    "missing_fields": [],
                    "order_data": None
                }
            }
        }


class HistoryItem(BaseModel):
    """历史记录项"""
    id: int
    session_id: str
    user_message: str
    ai_reply: str
    created_at: Optional[str]
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": 1,
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "user_message": "你好",
                "ai_reply": "你好，有什么可以帮您？",
                "created_at": "2024-01-01T12:00:00"
            }
        }


class SessionItem(BaseModel):
    """会话项"""
    session_id: str
    status: str
    is_completed: bool
    last_message: Optional[str]
    last_message_time: Optional[str]
    updated_at: Optional[str]
    
    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "active",
                "is_completed": False,
                "last_message": "你好",
                "last_message_time": "2024-01-01T12:00:00",
                "updated_at": "2024-01-01T12:00:00"
            }
        }


# ==================== 业务逻辑函数 ====================

async def process_order_message(
    user_id: int,
    message: str,
) -> Dict[str, Any]:
    """
    处理报单相关消息
    """
    try:
        result = await matching_service.process_chat_message(
            user_id=user_id,
            message=message,
        )
        
        # 检查是否是确认操作
        confirm_keywords = ["确认", "确定", "是的", "ok", "OK", "提交", "确认提交", "确认订单", "提交订单"]
        if message in confirm_keywords or message.lower() in ["ok", "yes", "confirm"]:
            confirm_result = await matching_service.confirm_order(user_id)
            return {
                "reply_text": confirm_result.get("msg", "订单已确认"),
                "session_id": "temp",
                "status": "completed",
                "missing_fields": [],
                "order_data": result.get("data") if result else None
            }
        
        # 检查是否是取消操作
        cancel_keywords = ["取消", "重填", "重置", "不了", "不要了", "取消订单", "重新填写", "重来"]
        if message in cancel_keywords:
            cancel_result = matching_service.cancel_order(user_id)
            return {
                "reply_text": cancel_result.get("msg", "订单已取消"),
                "session_id": "temp",
                "status": "completed",
                "missing_fields": []
            }
        
        # 正常报单填写流程
        return {
            "reply_text": result.get("message", "请继续填写信息"),
            "session_id": "temp",
            "status": "collecting" if result.get("type") == "incomplete" else "completed",
            "missing_fields": result.get("missing_fields", []),
            "order_data": result.get("data")
        }
        
    except Exception as e:
        logger.error(f"报单处理失败: {e}", exc_info=True)
        return {
            "reply_text": f"⚠️ 处理失败：{str(e)}，请稍后重试",
            "session_id": "temp",
            "status": "error",
            "missing_fields": []
        }


def is_order_related(message: str) -> bool:
    """
    判断消息是否与报单相关
    """
    message_lower = message.lower()
    order_keywords = [
        # 中文关键词
        "报单", "车号", "车牌", "司机", "联单", "电话", "手机号", "身份证", 
        "身份证号", "品类", "货物", "运单", "订单", "下单", "确认", "提交", 
        "取消", "重置", "重填", "重来", "填写", "信息",
        # 英文关键词
        "order", "plate", "car", "driver", "phone", "id card", "category",
        "confirm", "submit", "cancel", "reset"
    ]
    
    # 检查是否包含任何关键词
    for keyword in order_keywords:
        if keyword in message or keyword in message_lower:
            return True
    
    # 检查是否包含数字（可能是车号、电话等）
    if any(char.isdigit() for char in message) and len(message) < 50:
        return True
        
    return False


async def save_chat_history(
    user_id: int,
    session_id: str,
    user_message: str,
    ai_reply: str
):
    """
    保存聊天历史到数据库（异步任务）
    """
    if not ai_reply or not user_message:
        return
        
    try:
        # 确保数据库连接池已初始化
        await db_async.init_pool()
        
        async with db_async.get_cursor() as cursor:
            await cursor.execute("""
                INSERT INTO chat_history 
                (user_id, session_id, user_message, ai_reply, created_at)
                VALUES (%s, %s, %s, %s, NOW())
            """, (user_id, session_id, user_message[:1000], ai_reply[:1000]))
            
            # 同时更新会话的更新时间
            await cursor.execute("""
                UPDATE chat_sessions 
                SET updated_at = NOW() 
                WHERE session_id = %s AND user_id = %s
            """, (session_id, user_id))
            
            # 如果会话不存在，则创建
            if cursor.rowcount == 0:
                await cursor.execute("""
                    INSERT INTO chat_sessions (session_id, user_id, status, created_at, updated_at)
                    VALUES (%s, %s, 'active', NOW(), NOW())
                """, (session_id, user_id))
                
    except Exception as e:
        logger.error(f"保存聊天历史失败: {e}")


async def update_session_status(session_id: str, user_id: int, status: str = "completed"):
    """
    更新会话状态
    """
    try:
        async with db_async.get_cursor() as cursor:
            await cursor.execute("""
                UPDATE chat_sessions 
                SET status = %s, updated_at = NOW() 
                WHERE session_id = %s AND user_id = %s
            """, (status, session_id, user_id))
    except Exception as e:
        logger.error(f"更新会话状态失败: {e}")


# ==================== API 端点 ====================

@router.post("/chat", response_model=ChatResponse)
async def chat_with_ai(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """
    AI智能对话接口
    
    与扣子智能体进行对话，支持普通回复和报单填写流程。
    
    **请求参数:**
    - **message**: 用户消息内容（必填）
    - **session_id**: 会话ID，不传则自动生成
    - **stream**: 是否使用流式响应（默认false，如需要流式请使用 /chat/stream 端点）
    
    **返回数据:**
    - **code**: 状态码（200成功，其他失败）
    - **message**: 状态信息
    - **data**: 
        - **reply_text**: AI回复内容
        - **session_id**: 当前会话ID
        - **status**: 对话状态（collecting/complete）
        - **missing_fields**: 缺失的字段列表（报单流程中）
        - **order_data**: 报单数据（报单流程中）
    """
    start_time = time.time()
    session_id = request.session_id or str(uuid.uuid4())
    
    # 获取用户ID
    user_id = current_user.get('id') if isinstance(current_user, dict) else getattr(current_user, 'id', None)
    
    if not user_id:
        return ChatResponse(
            code=401,
            message="无法获取用户ID",
            data=None
        )
    
    logger.info(f"用户[{user_id}]发起对话: {request.message[:50]}...")
    
    try:
        # 判断是否是流式请求
        if request.stream:
            return ChatResponse(
                code=400,
                message="流式请求请使用 /chat/stream 端点",
                data=None
            )
        
        # 初始化数据库连接池
        try:
            await db_async.init_pool()
        except Exception as e:
            logger.warning(f"数据库连接池初始化失败（不影响对话）: {e}")
        
        # 判断是否是报单相关消息
        result = None
        if is_order_related(request.message):
            logger.info(f"用户[{user_id}]进入报单流程")
            result = await process_order_message(user_id, request.message)
        else:
            # 普通对话，调用扣子智能体
            try:
                logger.info(f"用户[{user_id}]调用Coze智能体")
                reply = await coze_service.chat_sync(request.message, session_id, str(user_id))
                result = {
                    "reply_text": reply,
                    "session_id": session_id,
                    "status": "completed",
                    "missing_fields": [],
                    "order_data": None
                }
            except Exception as e:
                logger.error(f"AI对话失败: {e}", exc_info=True)
                return ChatResponse(
                    code=503,
                    message="AI服务暂时不可用，请稍后重试",
                    data=None
                )
        
        # 后台保存聊天记录
        if result and result.get("reply_text"):
            background_tasks.add_task(
                save_chat_history,
                user_id,
                session_id,
                request.message,
                result["reply_text"]
            )
        
        # 计算处理时间
        process_time = (time.time() - start_time) * 1000
        logger.info(f"对话处理完成，耗时: {process_time:.2f}ms")
        
        # 构建响应
        chat_data = ChatData(
            reply_text=result["reply_text"],
            session_id=result["session_id"],
            status=result["status"],
            missing_fields=result.get("missing_fields", []),
            order_data=result.get("order_data")
        )
        
        return ChatResponse(
            code=200,
            message="success",
            data=chat_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"对话处理异常: {e}", exc_info=True)
        return ChatResponse(
            code=500,
            message="系统处理异常，请稍后重试",
            data=None
        )


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    AI流式对话
    
    以流式方式返回AI回复，适合实时显示
    
    **请求参数:**
    - **message**: 用户消息内容（必填）
    - **session_id**: 会话ID，不传则自动生成
    
    **返回格式:**
    Server-Sent Events 流式数据
    """
    session_id = request.session_id or str(uuid.uuid4())
    
    # 获取用户ID
    user_id = current_user.get('id') if isinstance(current_user, dict) else getattr(current_user, 'id', None)
    
    if not user_id:
        async def error_generator():
            yield f"data: {json.dumps({'error': '无法获取用户ID', 'session_id': session_id})}\n\n"
        return StreamingResponse(
            error_generator(),
            media_type="text/event-stream"
        )
    
    logger.info(f"用户[{user_id}]发起流式对话: {request.message[:50]}...")
    
    async def generate():
        try:
            # 发送开始标记
            yield f"data: {json.dumps({'type': 'start', 'session_id': session_id})}\n\n"
            
            full_response = ""
            
            # 判断是否是报单相关消息
            if is_order_related(request.message):
                # 报单流程返回完整消息
                result = await process_order_message(user_id, request.message, session_id)
                full_response = result["reply_text"]
                
                # 模拟流式效果，分块发送
                text = result["reply_text"]
                chunk_size = 10
                
                for i in range(0, len(text), chunk_size):
                    chunk = text[i:i+chunk_size]
                    yield f"data: {json.dumps({
                        'type': 'chunk',
                        'content': chunk,
                        'session_id': session_id,
                        'status': result['status']
                    }, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0.01)
                    
            else:
                # 调用扣子智能体流式接口
                async for chunk in coze_service.chat_stream(request.message, session_id, str(user_id)):
                    if chunk:
                        full_response += chunk
                        yield f"data: {json.dumps({
                            'type': 'chunk',
                            'content': chunk,
                            'session_id': session_id
                        }, ensure_ascii=False)}\n\n"
                        await asyncio.sleep(0.005)
            
            # 后台保存聊天记录
            if full_response:
                asyncio.create_task(
                    save_chat_history(user_id, session_id, request.message, full_response)
                )
            
            # 发送结束标记
            yield f"data: {json.dumps({
                'type': 'done',
                'session_id': session_id,
                'full_response': full_response
            }, ensure_ascii=False)}\n\n"
            
        except Exception as e:
            logger.error(f"流式对话失败: {e}", exc_info=True)
            yield f"data: {json.dumps({
                'type': 'error',
                'error': str(e),
                'session_id': session_id
            })}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream",
            "X-Accel-Buffering": "no",
        }
    )


@router.websocket("/ws/chat")
async def websocket_chat(
    websocket: WebSocket,
    user_id: str,
    session_id: Optional[str] = None,
    token: Optional[str] = None
):
    """
    WebSocket实时对话
    
    通过WebSocket进行双向实时对话
    
    连接参数:
    - user_id: 用户ID（必填）
    - session_id: 会话ID（可选）
    - token: JWT令牌（可选，用于认证）
    
    消息格式:
    
    发送到服务器:
    {
        "type": "chat",
        "message": "用户消息内容"
    }
    
    从服务器接收:
    {
        "type": "chunk",
        "content": "AI回复片段",
        "session_id": "xxx"
    }
    
    心跳机制:
    客户端可发送 {"type": "ping"}，服务器返回 {"type": "pong"}
    """
    # WebSocket 连接
    await manager.connect(websocket, user_id)
    
    current_session_id = session_id or str(uuid.uuid4())
    
    try:
        # 发送连接成功消息
        await websocket.send_json({
            "type": "connected",
            "session_id": current_session_id,
            "user_id": user_id
        })
        
        while True:
            # 接收前端消息
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            msg_type = message_data.get("type", "chat")
            user_message = message_data.get("message", "")
            
            # 处理心跳
            if msg_type == "ping":
                await websocket.send_json({"type": "pong", "timestamp": time.time()})
                continue
            
            # 处理关闭连接
            if msg_type == "close":
                await websocket.close()
                break
            
            # 处理普通消息
            if msg_type == "chat" and user_message:
                logger.info(f"WebSocket收到消息: {user_message[:50]}...")
                
                full_response = ""
                
                # 判断是否是报单相关消息
                if is_order_related(user_message):
                    # 报单流程
                    result = await process_order_message(int(user_id), user_message, current_session_id)
                    
                    # 模拟流式发送
                    text = result["reply_text"]
                    chunk_size = 20
                    
                    for i in range(0, len(text), chunk_size):
                        chunk = text[i:i+chunk_size]
                        await websocket.send_json({
                            "type": "chunk",
                            "content": chunk,
                            "session_id": current_session_id,
                            "status": result["status"]
                        })
                        await asyncio.sleep(0.02)
                    
                    full_response = text
                    
                else:
                    # 调用扣子智能体（流式）
                    async for chunk in coze_service.chat_stream(user_message, current_session_id, user_id):
                        if chunk:
                            full_response += chunk
                            await websocket.send_json({
                                "type": "chunk",
                                "content": chunk,
                                "session_id": current_session_id
                            })
                            await asyncio.sleep(0.01)
                
                # 发送结束标记
                await websocket.send_json({
                    "type": "done",
                    "session_id": current_session_id
                })
                
                # 后台保存聊天记录
                if full_response:
                    asyncio.create_task(
                        save_chat_history(int(user_id), current_session_id, user_message, full_response)
                    )
            
    except WebSocketDisconnect:
        manager.disconnect(user_id)
        logger.info(f"WebSocket连接断开: user_id={user_id}")
    except Exception as e:
        logger.error(f"WebSocket错误: {e}", exc_info=True)
        try:
            await websocket.send_json({
                "type": "error",
                "content": "服务器内部错误",
                "session_id": current_session_id
            })
        except:
            pass
        finally:
            manager.disconnect(user_id)


@router.get("/chat/history", response_model=ChatResponse)
async def get_chat_history(
    session_id: Optional[str] = Query(None, description="会话ID，不传返回所有会话的最新消息"),
    limit: int = Query(20, description="返回条数", ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    """
    获取聊天历史
    
    **查询参数:**
    - **session_id**: 会话ID（可选，不传返回所有会话的最新消息）
    - **limit**: 返回条数（默认20，最大100）
    
    **返回数据:**
    - 聊天历史列表
    """
    # 获取用户ID
    user_id = current_user.get('id') if isinstance(current_user, dict) else getattr(current_user, 'id', None)
    
    if not user_id:
        return ChatResponse(
            code=401,
            message="无法获取用户ID",
            data=None
        )
    
    try:
        # 初始化数据库连接池
        await db_async.init_pool()
        
        async with db_async.get_cursor() as cursor:
            if session_id:
                # 获取指定会话的历史
                await cursor.execute("""
                    SELECT id, session_id, user_message, ai_reply, created_at
                    FROM chat_history
                    WHERE user_id = %s AND session_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (user_id, session_id, limit))
            else:
                # 获取所有会话的最新消息
                await cursor.execute("""
                    SELECT ch.id, ch.session_id, ch.user_message, ch.ai_reply, ch.created_at
                    FROM chat_history ch
                    INNER JOIN (
                        SELECT session_id, MAX(created_at) as max_created
                        FROM chat_history
                        WHERE user_id = %s
                        GROUP BY session_id
                    ) latest ON ch.session_id = latest.session_id AND ch.created_at = latest.max_created
                    ORDER BY ch.created_at DESC
                    LIMIT %s
                """, (user_id, limit))
            
            rows = await cursor.fetchall()
            
            history = []
            for row in rows:
                history.append({
                    "id": row['id'],
                    "session_id": row['session_id'],
                    "user_message": row['user_message'],
                    "ai_reply": row['ai_reply'],
                    "created_at": row['created_at'].isoformat() if row['created_at'] else None
                })
            
            return ChatResponse(
                code=200,
                message="success",
                data={
                    "total": len(history),
                    "history": history
                }
            )
            
    except Exception as e:
        logger.error(f"获取聊天历史失败: {e}", exc_info=True)
        return ChatResponse(
            code=500,
            message=f"获取失败: {str(e)}",
            data=None
        )


@router.post("/chat/session/{session_id}/end", response_model=ChatResponse)
async def end_chat_session(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    结束对话会话
    
    结束指定的对话会话，将其标记为已完成
    
    **路径参数:**
    - **session_id**: 要结束的会话ID
    """
    # 获取用户ID
    user_id = current_user.get('id') if isinstance(current_user, dict) else getattr(current_user, 'id', None)
    
    if not user_id:
        return ChatResponse(
            code=401,
            message="无法获取用户ID",
            data=None
        )
    
    try:
        # 初始化数据库连接池
        await db_async.init_pool()
        
        async with db_async.get_cursor() as cursor:
            await cursor.execute("""
                UPDATE chat_sessions
                SET is_completed = TRUE, status = 'completed', updated_at = NOW()
                WHERE session_id = %s AND user_id = %s
            """, (session_id, user_id))
            
            if cursor.rowcount > 0:
                return ChatResponse(
                    code=200,
                    message="success",
                    data={"message": f"会话 {session_id} 已结束"}
                )
            else:
                return ChatResponse(
                    code=404,
                    message="会话不存在或已结束",
                    data=None
                )
                
    except Exception as e:
        logger.error(f"结束会话失败: {e}", exc_info=True)
        return ChatResponse(
            code=500,
            message=f"操作失败: {str(e)}",
            data=None
        )


@router.get("/chat/sessions", response_model=ChatResponse)
async def get_user_sessions(
    limit: int = Query(20, description="返回的会话数量", ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    """
    获取用户的会话列表
    
    **查询参数:**
    - **limit**: 返回的会话数量，默认20
    
    **返回数据:**
    - 用户的会话列表，包含最后一条消息
    """
    # 获取用户ID
    user_id = current_user.get('id') if isinstance(current_user, dict) else getattr(current_user, 'id', None)
    
    if not user_id:
        return ChatResponse(
            code=401,
            message="无法获取用户ID",
            data=None
        )
    
    try:
        # 初始化数据库连接池
        await db_async.init_pool()
        
        async with db_async.get_cursor() as cursor:
            await cursor.execute("""
                SELECT cs.session_id, cs.status, cs.is_completed, cs.updated_at,
                       (SELECT user_message FROM chat_history 
                        WHERE session_id = cs.session_id 
                        ORDER BY created_at DESC LIMIT 1) as last_message,
                       (SELECT created_at FROM chat_history 
                        WHERE session_id = cs.session_id 
                        ORDER BY created_at DESC LIMIT 1) as last_message_time
                FROM chat_sessions cs
                WHERE cs.user_id = %s
                ORDER BY cs.updated_at DESC
                LIMIT %s
            """, (user_id, limit))
            
            rows = await cursor.fetchall()
            
            sessions = []
            for row in rows:
                sessions.append({
                    "session_id": row['session_id'],
                    "status": row['status'],
                    "is_completed": bool(row['is_completed']),
                    "last_message": row['last_message'],
                    "last_message_time": row['last_message_time'].isoformat() if row['last_message_time'] else None,
                    "updated_at": row['updated_at'].isoformat() if row['updated_at'] else None
                })
            
            return ChatResponse(
                code=200,
                message="success",
                data={
                    "total": len(sessions),
                    "sessions": sessions
                }
            )
            
    except Exception as e:
        logger.error(f"获取会话列表失败: {e}", exc_info=True)
        return ChatResponse(
            code=500,
            message=f"获取失败: {str(e)}",
            data=None
        )


@router.delete("/chat/session/{session_id}", response_model=ChatResponse)
async def delete_chat_session(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    删除对话会话及其历史记录
    
    **路径参数:**
    - **session_id**: 要删除的会话ID
    
    **注意:** 此操作不可恢复，会同时删除会话和所有聊天记录
    """
    # 获取用户ID
    user_id = current_user.get('id') if isinstance(current_user, dict) else getattr(current_user, 'id', None)
    
    if not user_id:
        return ChatResponse(
            code=401,
            message="无法获取用户ID",
            data=None
        )
    
    try:
        # 初始化数据库连接池
        await db_async.init_pool()
        
        async with db_async.get_cursor() as cursor:
            # 先删除聊天历史
            await cursor.execute("""
                DELETE FROM chat_history
                WHERE session_id = %s AND user_id = %s
            """, (session_id, user_id))
            
            deleted_history = cursor.rowcount
            
            # 再删除会话
            await cursor.execute("""
                DELETE FROM chat_sessions
                WHERE session_id = %s AND user_id = %s
            """, (session_id, user_id))
            
            if cursor.rowcount > 0:
                return ChatResponse(
                    code=200,
                    message="success",
                    data={
                        "message": f"会话 {session_id} 已删除",
                        "deleted_history_count": deleted_history
                    }
                )
            else:
                return ChatResponse(
                    code=404,
                    message="会话不存在",
                    data=None
                )
                
    except Exception as e:
        logger.error(f"删除会话失败: {e}", exc_info=True)
        return ChatResponse(
            code=500,
            message=f"删除失败: {str(e)}",
            data=None
        )