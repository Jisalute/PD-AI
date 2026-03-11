"""
通用API客户端 - 处理HTTP请求、重试、超时等
"""
import os
import json
import base64
import logging
import requests
from typing import Dict, Any, Optional
from pathlib import Path
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class APIClient:
    """通用API客户端，支持重试、超时、多种认证方式"""
    
    def __init__(self, base_url: str, api_key: Optional[str] = None, timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.timeout = timeout
        
        # 创建session，支持重试
        self.session = requests.Session()
        
        # 重试策略
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST"]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # 默认headers
        self.session.headers.update({
            "User-Agent": "PD-API-Client/1.0",
            "Accept": "application/json"
        })
        
        # 添加API密钥
        if self.api_key:
            self.session.headers.update({
                "Authorization": f"Bearer {self.api_key}"
            })
    
    def post_json(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """POST JSON数据"""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        try:
            logger.info(f"POST JSON请求: {url}")
            response = self.session.post(url, json=data, timeout=self.timeout)
            return self._handle_response(response)
        except requests.exceptions.Timeout:
            logger.error(f"请求超时: {url}")
            raise Exception("API请求超时")
        except requests.exceptions.ConnectionError:
            logger.error(f"连接失败: {url}")
            raise Exception("API连接失败")
        except Exception as e:
            logger.error(f"请求异常: {e}")
            raise
    
    def post_file(self, endpoint: str, file_path: str, field_name: str = "file") -> Dict[str, Any]:
        """上传文件"""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        try:
            with open(file_path, "rb") as f:
                files = {field_name: (Path(file_path).name, f, "image/jpeg")}
                response = self.session.post(url, files=files, timeout=self.timeout)
                return self._handle_response(response)
        except Exception as e:
            logger.error(f"上传文件异常: {e}")
            raise
    
    def post_base64(self, endpoint: str, file_path: str) -> Dict[str, Any]:
        """发送base64图片数据"""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        try:
            with open(file_path, "rb") as f:
                image_base64 = base64.b64encode(f.read()).decode('utf-8')
            
            headers = {"Content-Type": "text/plain"}
            response = self.session.post(url, data=image_base64, headers=headers, timeout=self.timeout)
            return self._handle_response(response)
        except Exception as e:
            logger.error(f"发送base64异常: {e}")
            raise
    
    def _handle_response(self, response) -> Dict[str, Any]:
        """处理HTTP响应"""
        logger.info(f"响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            try:
                return response.json()
            except:
                return {"success": True, "data": response.text}
        else:
            error_msg = f"HTTP {response.status_code}"
            try:
                error_data = response.json()
                error_msg = error_data.get("message") or error_data.get("error") or error_msg
            except:
                error_msg = response.text or error_msg
            raise Exception(error_msg)
    
    def close(self):
        """关闭session"""
        self.session.close()