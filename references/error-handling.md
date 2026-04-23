---
name: error-handling
description: 错误处理与 Exit Code 规范
---

# 错误处理与 Exit Code 规范

## 📦 组件复用指南

**⚠️ 禁止在脚本中重复编写 Exit Code 常量定义与结构化错误输出逻辑。**

错误处理机制已作为通用工具内置。在新建 Skill 时，请按以下步骤复用：

1. **拷贝文件**：将 `scripts/utils/errors.py` 完整拷贝至目标 Skill 的 `scripts/utils/` 目录下。
2. **导入使用**：在 `run.py` 中通过 `from scripts.utils.errors import ExitCode, raise_exit, ensure_config, handle_httpx_errors` 引入。
3. **调用退出**：使用 `raise_exit(ExitCode.SERVICE_FAILURE, "服务不可用")` 替代直接 `raise typer.Exit()`。

如需查看完整源码实现，请参阅项目内的 `scripts/utils/errors.py` 文件。

## Exit Code 定义

| Exit Code | 枚举常量 | 触发场景 |
|-----------|----------|----------|
| `0` | `ExitCode.SUCCESS` | 命令正常执行完成 |
| `1` | `ExitCode.CONFIG_ERROR` | 缺少必填参数、配置文件错误、环境变量未设置 |
| `2` | `ExitCode.SERVICE_FAILURE` | 网络超时、API 5xx、数据库连接失败 |
| `3` | `ExitCode.BUSINESS_ERROR` | 权限不足、资源不存在、业务校验失败 |

## 快速使用示例

```python
from scripts.utils.errors import ExitCode, raise_exit, ensure_config

# 配置校验
ensure_config(cfg.api_key, "api_key", "请在 config.yaml 中配置")

# 业务失败退出
if not result:
    raise_exit(ExitCode.BUSINESS_ERROR, "未找到指定的资源", resource_id=order_id)
```

## 异常与 Exit Code 映射

使用 `handle_httpx_errors(e, url)` 可自动将常见 httpx 异常映射为正确的 Exit Code。

| 异常 | 自动映射的 Exit Code |
|------|----------------------|
| `pydantic.ValidationError` | `1` |
| `FileNotFoundError`（配置文件） | `1` |
| `httpx.ConnectTimeout` / `ReadTimeout` | `2` |
| `httpx.HTTPStatusError` | `2` |
| `httpx.RequestError` | `2` |
| `ValueError`（业务校验） | `3` |
| 资源未找到（空结果） | `3` |

## 规范

- **统一使用 `raise_exit`**：替代直接使用 `typer.Exit()`，确保同时输出结构化日志与用户可读错误。
- **错误信息输出到 stderr**：`typer.secho(..., fg="red", err=True)`（已由 `raise_exit` 自动处理）。
- **同时使用 `logger.error()`**：`raise_exit` 会自动调用 `logger.error("skill-execution-failed", ...)` 记录详细上下文。
- **错误提示应告知用户原因和解决方向**：避免暴露内部技术细节，如堆栈或原始异常信息。
- **异常信息使用 `str(e)`**：避免直接传入异常对象到日志，防止序列化失败。