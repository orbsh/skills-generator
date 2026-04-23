---
name: httpx
description: HTTP 客户端使用规范，包含超时配置、同步/异步模式与错误处理映射
---

# httpx 使用规范

本文档说明 Skill 中发起外部 HTTP 请求的标准用法。

## 📦 组件复用指南

**⚠️ 禁止在脚本中手动编写带完整超时和错误处理的 `httpx.Client` 逻辑。**

该 HTTP 客户端封装已作为通用工具内置。在新建 Skill 时，请按以下步骤复用：

1. **拷贝文件**：将 `scripts/utils/http.py` 及其依赖 `scripts/utils/errors.py` 拷贝至目标 Skill 的 `scripts/utils/` 目录下。
2. **导入使用**：在 `run.py` 中通过 `from scripts.utils.http import create_client, create_async_client` 引入。
3. **发起请求**：使用上下文管理器 `with create_client(base_url=url) as client:`，确保连接安全关闭且异常自动映射。

如需查看完整源码实现，请参阅项目内的 `scripts/utils/http.py` 文件。

## 核心原则

- **强制超时**：所有请求必须设置 `timeout`，禁止裸奔网络调用。
- **同步/异步**：少量请求用同步 `create_client`，高并发批量请求用 `create_async_client`。
- **错误处理**：网络异常统一映射 Exit Code 2，详见 `references/error-handling.md`。
- **连接复用**：优先复用 Client 实例，避免重复建连。

## 使用示例

### 同步请求
```python
from scripts.utils.http import create_client

with create_client(base_url="https://api.example.com", timeout=10.0) as client:
    resp = client.get("/data", context="获取业务数据")
    data = resp.json()
```

### 异步批量请求
```python
import asyncio
from scripts.utils.http import create_async_client

async def fetch_all(urls):
    async with create_async_client() as client:
        tasks = [client.get(url) for url in urls]
        return await asyncio.gather(*tasks)

# asyncio.run(fetch_all([...]))
```

## 异常与 Exit Code 映射

使用工具模块 (`scripts/utils/http.py`) 中的客户端时，以下异常会自动映射为对应的 Exit Code：

| 异常 | Exit Code | 说明 |
|------|-----------|------|
| `ConnectTimeout` / `ReadTimeout` | `2` | 服务连接或读取超时 |
| `HTTPStatusError` (5xx) | `2` | 服务端内部错误 |
| `HTTPStatusError` (401/403) | `3` | 认证失败或无权限 |
| `HTTPStatusError` (404) | `3` | 资源未找到 |
| `RequestError` | `2` | DNS 解析失败、SSL 错误等网络层故障 |

## 最佳实践

1. **必须设置 timeout**：即使是内网调用，也应设置合理的超时（建议 5-15 秒）。
2. **使用上下文管理器**：通过 `with` / `async with` 确保连接池在请求结束后正确释放。
3. **显式调用 `raise_for_status()`**：工具模块已内置此行为，无需手动调用。
4. **区分 4xx 与 5xx**：客户端已自动区分认证/资源类错误（Exit 3）与服务类错误（Exit 2），业务层无需额外处理。

