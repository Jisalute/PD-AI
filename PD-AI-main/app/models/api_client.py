"""
通用API客户端
"""
import os
import json
import base64
import logging
from typing import Dict, Any, Optional
import requests
from pathlib import Path

logger = logging.getLogger(__name__)


class APIClient:
    """通用API客户端"""

    def __init__(self, base_url: str, api_key: str = None, timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.timeout = timeout
        self.session = requests.Session()

        # 设置默认headers
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'PD-API-Client/1.0'
        })

        if api_key:
            self.session.headers.update({
                'Authorization': f'Bearer {api_key}'
            })

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """通用请求方法"""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"

        try:
            response = self.session.request(method, url, timeout=self.timeout, **kwargs)
            response.raise_for_status()

            # 尝试解析JSON响应
            try:
                return response.json()
            except ValueError:
                return {"success": True, "data": response.text}

        except requests.exceptions.RequestException as e:
            logger.error(f"API请求失败: {method} {url} - {e}")
            return {"success": False, "error": str(e)}

    def post_json(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """发送JSON POST请求"""
        return self._make_request('POST', endpoint, json=data)

    def post_file(self, endpoint: str, file_path: str) -> Dict[str, Any]:
        """发送文件POST请求"""
        if not os.path.exists(file_path):
            return {"success": False, "error": f"文件不存在: {file_path}"}

        with open(file_path, 'rb') as f:
            files = {'file': (Path(file_path).name, f, 'application/octet-stream')}
            # 移除默认的Content-Type，让requests自动设置multipart
            headers = self.session.headers.copy()
            headers.pop('Content-Type', None)

            try:
                response = self.session.post(
                    f"{self.base_url}/{endpoint.lstrip('/')}",
                    files=files,
                    headers=headers,
                    timeout=self.timeout
                )
                response.raise_for_status()

                try:
                    return response.json()
                except ValueError:
                    return {"success": True, "data": response.text}

            except requests.exceptions.RequestException as e:
                logger.error(f"文件上传请求失败: {endpoint} - {e}")
                return {"success": False, "error": str(e)}

    def post_base64(self, endpoint: str, file_path: str) -> Dict[str, Any]:
        """发送Base64编码的文件POST请求"""
        if not os.path.exists(file_path):
            return {"success": False, "error": f"文件不存在: {file_path}"}

        try:
            with open(file_path, 'rb') as f:
                file_data = f.read()
                file_base64 = base64.b64encode(file_data).decode('utf-8')

            data = {
                "image": file_base64,
                "filename": Path(file_path).name
            }

            return self._make_request('POST', endpoint, json=data)

        except Exception as e:
            logger.error(f"Base64编码失败: {e}")
            return {"success": False, "error": str(e)}