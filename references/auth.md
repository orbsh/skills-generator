---
name: auth
description: 认证模块，后端 API 认证（BackendApiClient）和环境变量 Token 读取（get_access_token_from_env）。用户身份验证已下沉至 skillforge server。
---

# 认证逻辑

本文档描述 skill 侧可用的认证工具。

## 📦 组件复用指南

**⚠️ 禁止在脚本中重复编写 Token 提取、API 调用与响应解析逻辑。**

### 用户身份验证（已下沉至 skillforge）

用户身份验证（token → user_name/user_info）已在 skillforge 服务端完成，skill 直接读取环境变量：

```python
import os

user_name = os.environ.get("CONTEXT_METADATA_USER_NAME")
user_info = json.loads(os.environ.get("CONTEXT_METADATA_USER_INFO", "{}"))
```

无需在 skill 中调用 User API 验证。

### 后端 API 请求（BackendApiClient）

当 Skill 需要向外部后端 API 发起请求时，使用 `BackendApiClient`：

```python
from skills_generator import BackendApiClient, get_access_token_from_env

access_token = get_access_token_from_env(cfg.context) or ""

client = BackendApiClient(
    auth_method=cfg.auth.auth_method,
    header_name=cfg.auth.header_name,
    cookie_name=cfg.auth.cookie_name,
    params_name=cfg.auth.params_name,
    access_token=access_token,
)
resp = client.request(api_url, params=params)
```

## 1. BackendApiClient

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

### 配置项

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

## 2. get_access_token_from_env

从环境变量中读取 Token，遵循 `DefaultContextSettings` 映射规范：

```python
from skills_generator import get_access_token_from_env

token = get_access_token_from_env(cfg.context)
```

## 3. 快速使用示例

```python
from skills_generator import BackendApiClient, get_access_token_from_env

cfg = Settings()

# 方式 1: 通过环境变量获取 Token (适用于 CLI 脚本)
token = get_access_token_from_env(cfg.context)

# 方式 2: 使用 BackendApiClient 按 auth_method 列表顺序尝试
access_token = get_access_token_from_env(cfg.context) or ""
client = BackendApiClient(
    auth_method=cfg.auth.auth_method,
    header_name=cfg.auth.header_name,
    cookie_name=cfg.auth.cookie_name,
    params_name=cfg.auth.params_name,
    access_token=access_token,
)
resp = client.request(api_url, params=params)
```

## 4. 日志追踪

认证过程中会输出以下关键日志事件，便于调试：

| 事件名 | 级别 | 说明 |
|--------|------|------|
| `auth-token-missing` | WARNING | Token 缺失 |
| `auth-mode-try` | INFO | 尝试某种认证方式 |
| `auth-success` | INFO | 认证成功 |
| `auth-failed` | WARNING | 认证失败（非 2xx） |
| `auth-error` | ERROR | 发生异常 |
| `auth-all-methods-failed` | ERROR | 所有认证方式都失败 |
| `auth-token-from-env` | INFO | 从环境变量获取 Token |
| `auth-token-missing-in-env` | WARNING | 环境变量中无 Token |
