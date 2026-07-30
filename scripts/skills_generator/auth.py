"""
用户认证模块 (Auth)

提供 BackendApiClient（后端 API 认证）和 get_access_token_from_env（环境变量读取）。
用户身份验证（token → user_name）已下沉至 skillforge server/auth.py。
"""
from typing import Optional, Dict, Any
import os
import structlog
import httpx

from .errors import ExitCode, raise_exit, handle_httpx_errors
from .logging import logger


class BackendApiClient:
    """
    后端 API 客户端，支持 auth_method 列表模式按顺序尝试不同认证方式。

    使用示例:
        client = BackendApiClient(
            auth_method=["query", "header", "cookie"],
            header_name="access-token",
            cookie_name="HrmApiCookie",
            params_name="token",
            access_token=access_token,
            timeout=30.0,
        )
        resp = client.request(api_url, params=params)
    """
    def __init__(
        self,
        auth_method: list[str] = None,
        header_name: str = "access-token",
        cookie_name: str = "HrmApiCookie",
        params_name: str = "token",
        access_token: str = "",
        timeout: float = 30.0,
    ):
        """
        Args:
            auth_method: 按顺序尝试的认证方式列表。
            header_name: Header 中 Token 的名称。
            cookie_name: Cookie 中 Token 的名称。
            params_name: URL 查询参数中 Token 的名称。
            access_token: 认证 Token 值。
            timeout: API 超时时间。
        """
        self.auth_method = auth_method or ["query", "header", "cookie"]
        self.header_name = header_name
        self.cookie_name = cookie_name
        self.params_name = params_name
        self.access_token = access_token
        self.timeout = timeout
        self.logger = logger.bind(module="backend_api")

    def request(
        self,
        url: str,
        method: str = "GET",
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Optional[httpx.Response]:
        """
        按 auth_method 列表顺序尝试发起请求，成功则返回响应。

        Args:
            url: 请求地址。
            method: HTTP 方法 (GET/POST)。
            params: URL 查询参数。
            json_body: JSON 请求体。

        Returns:
            httpx.Response 对象，所有方法都失败则返回 None。
        """
        if not self.access_token:
            self.logger.warning("auth-token-missing")
            return None

        req_params = dict(params) if params else {}
        json_data = json_body if json_body else None

        with httpx.Client(timeout=self.timeout) as client:
            for auth_mode in self.auth_method:
                self.logger.info("auth-mode-try", mode=auth_mode, cookie_name=self.cookie_name)

                headers = {self.header_name: self.access_token} if auth_mode == "header" else None
                cookies = {self.cookie_name: self.access_token} if auth_mode == "cookie" else None
                current_params = dict(req_params)
                if auth_mode == "query":
                    current_params[self.params_name] = self.access_token

                self.logger.info("http-req", url=url, params=current_params, auth_mode=auth_mode)

                try:
                    if method.upper() == "POST":
                        resp = client.post(url, params=current_params, json=json_data, headers=headers, cookies=cookies)
                    else:
                        resp = client.get(url, params=current_params, headers=headers, cookies=cookies)

                    if resp.status_code == 200:
                        self.logger.info("auth-success", mode=auth_mode)
                        return resp
                    else:
                        self.logger.warning("auth-failed", mode=auth_mode, status=resp.status_code)
                except Exception as e:
                    self.logger.error("auth-error", mode=auth_mode, error=str(e))

        self.logger.error("auth-all-methods-failed", methods=self.auth_method)
        return None


def get_access_token_from_env(context_settings: Any) -> Optional[str]:
    """
    从环境变量中获取认证 Token。
    遵循 context-env.md 规范，通过配置映射读取环境变量名。

    Args:
        context_settings: pydantic-settings 的 context 配置对象，
                          应包含 token 字段（统一 Token 环境变量名）。

    Returns:
        Token 字符串或 None。
    """
    env_name = getattr(context_settings, "token", "")
    if env_name:
        token = os.environ.get(env_name)
        if token:
            logger.info("auth-token-from-env", env_var=env_name)
            return token

    logger.warning("auth-token-missing-in-env")
    return None
