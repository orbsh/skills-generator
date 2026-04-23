---
name: auth
description: 认证模块，包含用户身份验证（UserAuthClient）和后端 API 认证（BackendApiClient）两种模式。
---

# 认证逻辑

本文档描述系统中两种认证模式的标准流程，供其他模块（如 Skills、API 端点）复用。

## 📦 组件复用指南

**⚠️ 禁止在脚本中重复编写 Token 提取、API 调用与响应解析逻辑。**

完整的认证客户端已作为通用工具内置。在新建 Skill 时，请按以下步骤复用：

1. **拷贝文件**：将 `scripts/utils/auth.py` 及其依赖 `scripts/utils/errors.py`、`scripts/utils/config.py` 拷贝至目标 Skill 的 `scripts/utils/` 目录下。
2. **导入使用**：在 `run.py` 中通过 `from scripts.utils.auth import UserAuthClient, BackendApiClient, get_access_token_from_env` 引入。
3. **初始化客户端**：
   - **用户身份验证**：使用配置中的 `user_api` 字段实例化 `UserAuthClient(api_url=..., cookie_name=...)`。
   - **后端 API 请求**：使用配置中的 `auth_method` 列表实例化 `BackendApiClient(auth_method=..., header_name=..., cookie_name=..., params_name=..., access_token=...)`。

如需查看完整源码实现，请参阅项目内的 `scripts/utils/auth.py` 文件。

## 1. 配置项

认证逻辑依赖 `config.toml` 中的 `[auth]` 配置，包含以下字段：

| 配置项 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `header_name` | `str` | 否 | `access-token` | HTTP Header 中 Token 的名称 |
| `cookie_name` | `str` | 否 | `HrmApiCookie` | Cookie 中 Token 的名称 |
| `ws_query_param` | `str` | 否 | `token` | WebSocket URL 查询参数中用于认证的参数名 |
| `params_name` | `str` | 否 | `token` | URL 查询参数中 Token 的名称 |
| `auth_method` | `list[str]` | 否 | `["query", "header", "cookie"]` | 按顺序尝试的认证方式列表 |

**配置示例** (`config.toml`):

```toml
[auth]
header_name = "access-token"        # HTTP Header 中 Token 的名称
cookie_name = "HrmApiCookie"        # Cookie 中 Token 的名称
ws_query_param = "token"            # WebSocket URL 查询参数中用于认证的参数名
params_name = "token"               # URL 查询参数中 token 的名称
auth_method = ["query", "header", "cookie"]  # 认证方式列表，按顺序尝试
```

## 2. Token 获取流程

系统支持两种认证客户端模式：

### BackendApiClient（后端 API 请求）

按 `auth_method` 列表顺序尝试不同认证方式，成功即返回：

```
1. query:   URL 查询参数 (?token=xxx)
        ↓ (失败时)
2. header:  HTTP Header (access-token: xxx)
        ↓ (失败时)
3. cookie:  HTTP Cookie (HrmApiCookie=xxx)
        ↓ (都失败时)
4. 返回 None (认证失败)
```

### UserAuthClient（用户身份验证）

从请求中提取 Token，调用 User API 验证身份：

```
1. 请求头: headers.get(header_name)
        ↓ (为空时)
2. Cookie: cookies.get(cookie_name)
        ↓ (都为空时)
3. 返回 None (认证失败)
```

**注意**: 以上配置项均为可选，只需确保至少有一种方式能够成功获取 Token 即可。

## 3. 调用 User API 验证

获取 Token 后，向 `settings.user_api.url` 发起请求验证身份：

```http
POST {url}
Content-Type: application/json

{
  "{token_param}": "{token}"
}
```

- 超时设置: 10 秒
- 支持 POST 和 GET 方法

## 4. 响应解析

API 返回成功后，自动兼容以下两种 JSON 结构解析用户信息：

- **结构 A**: `payload.info.user_info`
- **结构 B**: `info.user_info`

用户名提取优先级：`name` > `userName` > `username`

## 5. 快速使用示例

```python
from scripts.utils.auth import UserAuthClient, get_access_token_from_env
from scripts.utils.config import load_settings

cfg = load_settings()

# 方式 1: 通过环境变量获取 Token (适用于 CLI 脚本)
token = get_access_token_from_env(cfg.context)

# 方式 2: 通过 UserAuthClient 验证 Token (适用于 Web/Agent 上下文)
client = UserAuthClient(
    api_url=cfg.user_api.url,
    cookie_name=cfg.user_api.cookie_name,
    header_name=cfg.user_api.header_name
)
user = client.get_current_user(
    headers=request.headers,
    cookies=request.cookies
)
if user:
    print(f"当前用户: {user['user_name']}")
```

## 6. 返回值

- **成功**: 返回 `{"user_name": str, "user_info": dict}`，包含用户名和完整用户信息元数据
- **失败**: 返回 `None`（任何环节失败均静默返回 None，通过日志追踪）

## 7. 后端 API 认证（auth_method 列表模式）

当 Skill 需要向**外部后端 API** 发起请求时，使用 `auth_method` 列表配置按顺序尝试不同的认证方式。

### 配置项

在 `assets/config.yaml` 中定义：

| 配置项 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `auth_method` | `list[str]` | 否 | `["query", "header", "cookie"]` | 按顺序尝试的认证方式列表 |
| `header_name` | `str` | 否 | `access-token` | Header 中 Token 的名称 |
| `cookie_name` | `str` | 否 | `HrmApiCookie` | Cookie 中 Token 的名称 |
| `params_name` | `str` | 否 | `token` | URL 查询参数中 Token 的名称 |

### 认证方式说明

| 方式 | 行为 |
|------|------|
| `query` | 将 Token 作为 URL 查询参数附加（如 `?token=xxx`） |
| `header` | 将 Token 放入 HTTP Header（如 `access-token: xxx`） |
| `cookie` | 将 Token 放入 Cookie（如 `HrmApiCookie=xxx`） |

### 使用示例

```python
from scripts.utils.auth import BackendApiClient, get_access_token_from_env

# 从统一 Token 环境变量获取
access_token = get_access_token_from_env(cfg.context) or ""

# 使用 BackendApiClient 按 auth_method 列表顺序尝试
client = BackendApiClient(
    auth_method=cfg.auth.auth_method,
    header_name=cfg.auth.header_name,
    cookie_name=cfg.auth.cookie_name,
    params_name=cfg.auth.params_name,
    access_token=access_token,
)

resp = client.request(api_url, params=params)
```

或手动实现循环逻辑：

```python
import httpx
from scripts.utils.auth import get_access_token_from_env

# 从统一 Token 环境变量获取
access_token = get_access_token_from_env(cfg.context) or ""

with httpx.Client(timeout=30.0) as client:
    for method in cfg.auth.auth_method:
        headers = {cfg.auth.header_name: access_token} if method == "header" else None
        cookies = {cfg.auth.cookie_name: access_token} if method == "cookie" else None
        req_params = dict(params)
        if method == "query":
            req_params[cfg.auth.params_name] = access_token

        resp = client.get(api_url, params=req_params, headers=headers, cookies=cookies)
        if resp.status_code == 200:
            break  # 成功则停止尝试
```

### 配置示例

```yaml
# assets/config.yaml
auth:
  header_name: "access-token"
  cookie_name: "HrmApiCookie"
  params_name: "token"
  auth_method: ["query", "header", "cookie"]  # 按顺序尝试

order_api:
  url: "http://apinew.app-xmh.s/v1/orders/view"
```

> **注意**: `auth` 配置段需在 Settings 类中定义为嵌套的 `BaseSettings` 模型才能被 `cfg.auth` 正确读取。

## 8. 日志追踪

认证过程中会输出以下关键日志事件，便于调试：

| 事件名 | 级别 | 说明 |
|--------|------|------|
| `user-api-token-from-header` | INFO | 从 Header 获取 Token |
| `user-api-token-from-cookie` | INFO | 从 Cookie 获取 Token |
| `user-api-token-missing` | WARNING | Header 和 Cookie 都无 Token |
| `user-api-call-start` | INFO | 开始调用 User API |
| `user-api-request-failed` | ERROR | API 请求失败 (非 2xx) |
| `user-name-success` | INFO | 成功提取用户名 |
| `user-api-exception` | ERROR | 发生异常 (网络/解析错误) |
