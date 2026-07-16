"""
错误处理与 Exit Code 规范模块 (Errors)

提供统一的错误代码常量、异常映射与结构化错误输出工具。
确保所有 Skill 脚本遵循一致的退出码语义，便于 Agent 自动化判断执行状态。
"""
from enum import IntEnum
from typing import Optional, Any
import structlog
import typer
import httpx

# 初始化模块级 logger
logger = structlog.get_logger()


class ExitCode(IntEnum):
    """
    标准 Exit Code 定义。

    - 0: 业务成功 (正常执行完成)
    - 1: 配置/参数错误 (参数缺失、配置无效)
    - 2: 外部服务故障 (网络超时、API 5xx、数据库连接失败)
    - 3: 业务逻辑错误 (权限不足、资源不存在、业务校验失败)
    """
    SUCCESS = 0
    CONFIG_ERROR = 1
    SERVICE_FAILURE = 2
    BUSINESS_ERROR = 3


def raise_exit(
    code: ExitCode,
    message: str,
    exc: Optional[Exception] = None,
    **kwargs
) -> None:
    """
    记录结构化错误日志并通过 typer 退出程序。

    Args:
        code: 退出代码枚举。
        message: 面向用户的简短错误提示。
        exc: 捕获到的原始异常对象 (用于日志记录)。
        **kwargs: 附加的键值对上下文 (将写入日志)。
    """
    log_data: dict[str, Any] = {"exit_code": int(code), "message": message}

    if exc:
        log_data["exception_type"] = type(exc).__name__
        log_data["exception_msg"] = str(exc)

    log_data.update(kwargs)

    logger.error("skill-execution-failed", **log_data)
    typer.secho(f"错误: {message}", fg="red", err=True)
    raise typer.Exit(code=int(code))


def ensure_config(value: Any, field_name: str, hint: Optional[str] = None) -> Any:
    """
    校验关键配置是否存在。若缺失则输出日志并以 Exit Code 1 退出。

    Args:
        value: 待检查的配置值。
        field_name: 字段名称 (用于日志和提示)。
        hint: 可选的修复提示。

    Returns:
        检查通过的值。
    """
    if not value:
        msg = f"缺少必填配置项 '{field_name}'"
        if hint:
            msg += f" ({hint})"
        raise_exit(ExitCode.CONFIG_ERROR, msg, field=field_name)
    return value


def handle_httpx_errors(e: Exception, url: str, context: Optional[str] = None) -> None:
    """
    辅助函数：根据 httpx 异常类型自动映射 Exit Code。

    应在 except 块中调用。例如:
        except Exception as e:
            handle_httpx_errors(e, url)

    Args:
        e: 捕获的异常。
        url: 请求地址。
        context: 业务上下文描述。
    """
    # 直接根据 httpx 异常类型映射 Exit Code

    if isinstance(e, (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError)):
        raise_exit(
            ExitCode.SERVICE_FAILURE,
            f"外部服务连接超时或不可达: {url}",
            exc=e,
            url=url
        )
    elif isinstance(e, httpx.HTTPStatusError):
        raise_exit(
            ExitCode.SERVICE_FAILURE,
            f"外部服务返回错误状态: {e.response.status_code}",
            exc=e,
            url=url
        )
    elif isinstance(e, httpx.RequestError):
        raise_exit(
            ExitCode.SERVICE_FAILURE,
            f"网络请求异常: {url}",
            exc=e,
            url=url
        )
    else:
        # 未知异常视为业务错误或内部错误
        raise_exit(
            ExitCode.BUSINESS_ERROR,
            context or f"处理请求时发生未知错误: {url}",
            exc=e
        )
