# services/coze_service.py
import requests
import json
import logging
from typing import AsyncGenerator, Optional, Dict, Any
from fastapi import HTTPException
import os
import aiohttp
import asyncio

from app.core.config import settings

logger = logging.getLogger(__name__)


class CozeService:
    def __init__(self):
        self.api_token = settings.coze_api_token
        self.bot_url = settings.coze_bot_url
        self.project_id = settings.coze_project_id
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream"
        }
        
    async def chat_stream(self, message: str, session_id: str, user_id: Optional[str] = None) -> AsyncGenerator[str, None]:
        """
        流式调用Coze智能体
        """
        # 使用你同事代码中的正确格式
        payload = {
            "content": {
                "query": {
                    "prompt": [
                        {
                            "type": "text",
                            "content": {
                                "text": message
                            }
                        }
                    ]
                }
            },
            "type": "query",
            "session_id": session_id,
            "project_id": self.project_id
        }
        
        logger.info(f"发送到Coze: {json.dumps(payload, ensure_ascii=False)[:200]}...")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.bot_url,
                    headers=self.headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Coze API返回错误: {response.status}, {error_text}")
                        yield f"抱歉，AI服务暂时不可用（错误码：{response.status}）"
                        return
                    
                    # 处理流式响应
                    buffer = ""
                    async for chunk in response.content.iter_any():
                        if chunk:
                            chunk_str = chunk.decode('utf-8')
                            buffer += chunk_str
                            
                            # 按SSE格式分割
                            lines = buffer.split('\n')
                            buffer = lines[-1] if lines else ""
                            
                            for line in lines[:-1]:
                                if line.startswith('data:'):
                                    data = line[5:].strip()
                                    if data and data != '[DONE]':
                                        try:
                                            parsed = json.loads(data)
                                            logger.debug(f"收到原始数据: {data[:200]}")
                                            
                                            # 提取内容
                                            content = self._extract_content(parsed)
                                            if content:
                                                yield content
                                                
                                        except json.JSONDecodeError as e:
                                            logger.error(f"JSON解析失败: {e}, 数据: {data[:200]}")
                                            if data:
                                                yield data
                                                        
        except asyncio.TimeoutError:
            logger.error("Coze API请求超时")
            yield "抱歉，AI服务响应超时，请稍后重试"
        except aiohttp.ClientError as e:
            logger.error(f"Coze API请求失败: {e}")
            yield f"抱歉，AI服务连接失败"
        except Exception as e:
            logger.error(f"Coze服务内部错误: {e}", exc_info=True)
            yield f"抱歉，处理您的请求时出现错误"
    
    def _extract_content(self, parsed_data: Dict[str, Any]) -> Optional[str]:
        """
        从Coze返回的数据中提取文本内容
        """
        try:
            if isinstance(parsed_data, dict):
                # 检查是否有直接的 content 字段
                if 'content' in parsed_data:
                    content = parsed_data['content']
                    if isinstance(content, str):
                        return content
                    elif isinstance(content, dict):
                        return content.get('text') or content.get('content')
                
                # 检查是否有 text 字段
                if 'text' in parsed_data:
                    return parsed_data['text']
                
                # 检查是否有 message 字段
                if 'message' in parsed_data:
                    return parsed_data['message']
                
                # 检查是否有 answer 字段
                if 'answer' in parsed_data:
                    return parsed_data['answer']
                
                # 检查是否有 data 字段
                if 'data' in parsed_data:
                    data = parsed_data['data']
                    if isinstance(data, str):
                        return data
                    elif isinstance(data, dict):
                        return data.get('text') or data.get('content')
                
                # 检查是否有 choices 字段（常见于流式API）
                if 'choices' in parsed_data:
                    choices = parsed_data['choices']
                    if choices and isinstance(choices, list) and len(choices) > 0:
                        choice = choices[0]
                        if 'delta' in choice:
                            delta = choice['delta']
                            return delta.get('content') or delta.get('text')
                        elif 'message' in choice:
                            message = choice['message']
                            return message.get('content') or message.get('text')
                
                # 如果是 answer 类型，可能内容在别处
                if parsed_data.get('type') == 'answer':
                    # 尝试获取可能的文本字段
                    for field in ['text', 'content', 'message', 'data']:
                        if field in parsed_data:
                            return parsed_data[field]
                    return ""
                
                # 如果是 message_start 或 message_end，忽略
                if parsed_data.get('type') in ['message_start', 'message_end']:
                    return ""
                
        except Exception as e:
            logger.error(f"提取内容时出错: {e}")
        
        return None
    
    async def chat_sync(self, message: str, session_id: str, user_id: Optional[str] = None) -> str:
        """同步调用Coze智能体，返回完整回复"""
        full_response = ""
        chunk_count = 0
        async for chunk in self.chat_stream(message, session_id, user_id):
            if chunk:
                chunk_count += 1
                full_response += chunk
                print(f"收到第{chunk_count}个chunk: {chunk[:50]}...")
        
        logger.info(f"共收到 {chunk_count} 个chunk，总长度: {len(full_response)}")
        if not full_response:
            logger.warning("AI返回为空")
            # 如果没有内容，返回默认消息
            return "抱歉，AI服务暂时无法回复"
        
        return full_response
    
    async def chat_with_context(self, message: str, session_id: str, user_id: str, db=None):
        """
        带上下文的对话（可保存到数据库）
        """
        response = await self.chat_sync(message, session_id, user_id)
        return response


# 创建单例
coze_service = CozeService()