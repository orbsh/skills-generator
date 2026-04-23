"""
用户认证模块 (Auth)

基于 User API 提供标准化的身份验证与 Token 获取逻辑。
支持 Header 和 Cookie 两种 Token 传递方式，并自动处理 API 调用与响应解析。
严格遵循 context-env.md 规范，禁止硬编码环境变量名。
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


class UserAuthClient:
    """
    用户认证客户端。

    封装从 Token 提取、API 验证到用户信息解析的完整流程。

    使用示例:
        client = UserAuthClient(
            api_url=cfg.user_api.url,
            cookie_name=cfg.user_api.cookie_name,
            header_name=cfg.user_api.header_name
        )
        user = client.get_current_user(headers=request.headers, cookies=request.cookies)
    """
    def __init__(
        self,
        api_url: str,
        cookie_name: str = "",
        header_name: str = "access-token",
        token_param: str = "token",
        method: str = "POST",
        timeout: float = 10.0,
    ):
        """
        Args:
            api_url: 用户信息验证 API 地址。
            cookie_name: Cookie 中 Token 的名称 (必填)。
            header_name: Header 中 Token 的名称。
            token_param: 发送给 API 的 Token 参数名。
            method: 请求方法 (GET/POST)。
            timeout: API 超时时间。
        """
        if not api_url:
            raise ValueError("api_url 必须配置")
        if not cookie_name:
            raise ValueError("cookie_name 必须配置")

        self.api_url = api_url
        self.cookie_name = cookie_name
        self.header_name = header_name
        self.token_param = token_param
        self.method = method.upper()
        self.timeout = timeout
        self.logger = logger.bind(module="auth")

    def extract_token(self, headers: Dict[str, str], cookies: Dict[str, str]) -> Optional[str]:
        """
        从请求头或 Cookie 中提取 Token。
        优先级: Header > Cookie。
        """
        token = headers.get(self.header_name)
        if token:
            self.logger.info("user-api-token-from-header", header=self.header_name)
            return token

        token = cookies.get(self.cookie_name)
        if token:
            self.logger.info("user-api-token-from-cookie", cookie=self.cookie_name)
            return token

        self.logger.warning("user-api-token-missing")
        return None

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        调用 User API 验证 Token 并解析用户信息。

        Returns:
            {"user_name": str, "user_info": dict} 或 None
        """
        self.logger.info("user-api-call-start", url=self.api_url)

        try:
            with httpx.Client(timeout=self.timeout) as client:
                if self.method == "POST":
                    resp = client.post(self.api_url, json={self.token_param: token})
                else:
                    resp = client.get(self.api_url, params={self.token_param: token})

                resp.raise_for_status()
                result = resp.json()

            # 解析响应 (支持两种常见结构)
            # 结构 A: payload.info.user_info
            # 结构 B: info.user_info
            payload = result.get("payload", {})
            if not isinstance(payload, dict):
                payload = result

            info = payload.get("info", {})
            if not isinstance(info, dict):
                info = payload

            user_info = info.get("user_info", {})
            if not isinstance(user_info, dict):
                user_info = info

            # 用户名提取优先级: name > userName > username
            user_name = (
                user_info.get("name")
                or user_info.get("userName")
                or user_info.get("username")
            )

            if user_name:
                self.logger.info("user-name-success", user_name=user_name)
                return {"user_name": user_name, "user_info": user_info}
            else:
                self.logger.warning("user-name-missing")
                return None

        except httpx.HTTPStatusError as e:
            self.logger.error("user-api-request-failed", status=e.response.status_code)
            return None
        except Exception as e:
            self.logger.error("user-api-exception", error=str(e))
            return None

    def get_current_user(self, headers: Dict[str, str], cookies: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """
        完整的认证流程：提取 Token -> 验证 -> 返回用户信息。

        Args:
            headers: 请求头字典。
            cookies: Cookie 字典。

        Returns:
            用户信息字典或 None。
        """
        token = self.extract_token(headers, cookies)
        if not token:
            return None
        return self.verify_token(token)


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
    # 读取统一 Token 环境变量
    env_name = getattr(context_settings, "token", "")
    if env_name:
        token = os.environ.get(env_name)
        if token:
            logger.info("auth-token-from-env", env_var=env_name)
            return token

    logger.warning("auth-token-missing-in-env")
    return None
