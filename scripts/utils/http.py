"""
HTTP 客户端工厂模块 (HTTP)

基于 httpx 提供带超时配置的客户端工厂与错误处理请求工具。
确保所有外部网络调用遵循"强制超时"和"结构化错误"规范。
"""
from typing import Optional, Any, Dict, Literal, Union
from contextlib import contextmanager, asynccontextmanager
import structlog
import httpx

from .errors import ExitCode, handle_httpx_errors, raise_exit
from typing import NoReturn

# 初始化模块级 logger
logger = structlog.get_logger()

# 默认超时配置 (秒)
DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)


class HTTPClient:
    """
    带错误处理的同步 HTTP 客户端封装。

    使用示例:
        client = HTTPClient(timeout=10.0)
        resp = client.get("https://api.example.com/data")
    """
    def __init__(self, timeout: Union[float, httpx.Timeout, None] = None, base_url: Optional[str] = None):
        """
        Args:
            timeout: 超时配置。未提供时使用 DEFAULT_TIMEOUT。
            base_url: 基础 URL，所有请求将基于此前缀。
        """
        self.timeout = timeout if timeout is not None else DEFAULT_TIMEOUT
        self.base_url = base_url
        client_kwargs: dict[str, Any] = {"timeout": self.timeout}
        if base_url:
            client_kwargs["base_url"] = base_url
        self._client = httpx.Client(**client_kwargs)

    def request(
        self,
        method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"],
        url: str,
        headers: Optional[Dict[str, str]] = None,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        cookies: Optional[Dict[str, str]] = None,
        context: Optional[str] = None
    ) -> httpx.Response:
        """
        发起 HTTP 请求并自动处理异常。

        Args:
            method: HTTP 方法。
            url: 请求路径 (若 base_url 已设置则为相对路径)。
            headers: 请求头。
            json: JSON 请求体。
            params: URL 查询参数。
            cookies: Cookie 字典。
            context: 业务上下文 (用于错误提示)。

        Returns:
            httpx.Response 对象。
        """
        try:
            resp = self._client.request(
                method=method,
                url=url,
                headers=headers,
                json=json,
                params=params,
                cookies=cookies,
            )
            resp.raise_for_status()
            logger.info("http-request-success", method=method, url=url, status=resp.status_code)
            return resp
        except httpx.HTTPStatusError as e:
            # 特定处理 4xx 业务错误 (可视为业务错误而非服务故障)
            if e.response.status_code == 404:
                raise_exit(ExitCode.BUSINESS_ERROR, context or f"资源未找到: {url}", exc=e, url=url)
            elif e.response.status_code == 401 or e.response.status_code == 403:
                raise_exit(ExitCode.BUSINESS_ERROR, context or f"认证失败或无权限: {url}", exc=e, url=url)
            else:
                handle_httpx_errors(e, url, context)
        except Exception as e:
            handle_httpx_errors(e, url, context)
        raise AssertionError("Unreachable: handle_httpx_errors or raise_exit should have raised")

    def get(self, url: str, **kwargs) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs) -> httpx.Response:
        return self.request("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs) -> httpx.Response:
        return self.request("DELETE", url, **kwargs)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "HTTPClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


class AsyncHTTPClient:
    """
    带错误处理的异步 HTTP 客户端封装。

    使用示例:
        async with AsyncHTTPClient() as client:
            resp = await client.get("https://api.example.com/data")
    """
    def __init__(self, timeout: Union[float, httpx.Timeout, None] = None, base_url: Optional[str] = None):
        self.timeout = timeout if timeout is not None else DEFAULT_TIMEOUT
        self.base_url = base_url
        async_client_kwargs: dict[str, Any] = {"timeout": self.timeout}
        if base_url:
            async_client_kwargs["base_url"] = base_url
        self._client = httpx.AsyncClient(**async_client_kwargs)

    async def request(
        self,
        method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"],
        url: str,
        headers: Optional[Dict[str, str]] = None,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        cookies: Optional[Dict[str, str]] = None,
        context: Optional[str] = None
    ) -> httpx.Response:
        try:
            resp = await self._client.request(
                method=method,
                url=url,
                headers=headers,
                json=json,
                params=params,
                cookies=cookies,
            )
            resp.raise_for_status()
            logger.info("http-request-success", method=method, url=url, status=resp.status_code)
            return resp
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise_exit(ExitCode.BUSINESS_ERROR, context or f"资源未找到: {url}", exc=e, url=url)
            elif e.response.status_code == 401 or e.response.status_code == 403:
                raise_exit(ExitCode.BUSINESS_ERROR, context or f"认证失败或无权限: {url}", exc=e, url=url)
            else:
                handle_httpx_errors(e, url, context)
        except Exception as e:
            handle_httpx_errors(e, url, context)
        raise AssertionError("Unreachable: handle_httpx_errors or raise_exit should have raised")

    async def get(self, url: str, **kwargs) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> httpx.Response:
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs) -> httpx.Response:
        return await self.request("PUT", url, **kwargs)

    async def delete(self, url: str, **kwargs) -> httpx.Response:
        return await self.request("DELETE", url, **kwargs)

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "AsyncHTTPClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()


@contextmanager
def create_client(timeout: Union[float, httpx.Timeout, None] = None, base_url: Optional[str] = None):
    """
    同步客户端上下文管理器。

    使用示例:
        with create_client(base_url="https://api.example.com") as client:
            resp = client.get("/data")
    """
    client = HTTPClient(timeout=timeout, base_url=base_url)
    try:
        yield client
    finally:
        client.close()


@asynccontextmanager
async def create_async_client(timeout: Union[float, httpx.Timeout, None] = None, base_url: Optional[str] = None):
    """
    异步客户端上下文管理器。

    使用示例:
        async with create_async_client(base_url="https://api.example.com") as client:
            resp = await client.get("/data")
    """
    client = AsyncHTTPClient(timeout=timeout, base_url=base_url)
    try:
        yield client
    finally:
        await client.close()
