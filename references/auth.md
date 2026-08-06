---
name: auth
description: 认证处理规范。用户身份验证与 Token 提取已下沉至 skillforge 服务端，skill 直接读取注入的环境变量。
---

# 认证处理

本文档说明 skill 侧如何获取用户身份（user_id / user_name）与认证 Token。

## 📦 组件复用指南

**⚠️ 禁止在脚本中重复编写 Token 提取、用户身份验证逻辑。**

用户身份验证（token → user_id / user_name / user_info）已全部在 **skillforge 服务端**完成，并把结果注入环境变量。skill 侧**无需**任何认证模块，直接读取环境变量即可。

## 读取注入的环境变量

skill 入口处直接读取 skillforge 注入的环境变量：

```python
import os
import json

# 用户主键（必填，缺失时应视为权限不足）
user_id = os.environ.get(cfg.context.user_id)
if not user_id:
    raise_exit(ExitCode.BUSINESS_ERROR, "缺失用户身份，未通过带外注入")

# 认证 Token（如需调用外部后端 API）
token = os.environ.get(cfg.context.token)

# 用户元信息（可选，由 skillforge 注入）
user_name = os.environ.get("CONTEXT_METADATA_USER_NAME")
user_info = json.loads(os.environ.get("CONTEXT_METADATA_USER_INFO", "{}"))
```

## 关键点

- **不自行解析 Token**：token → user_id/user_name 的解析由 skillforge 完成，skill 禁止从 LLM Prompt、消息历史或参数中解析身份。
- **环境变量名映射**：通过 `config.yaml` 的 `context` 字段映射到统一环境变量名（见 `references/context-env.md`）。
- **缺失身份即报错**：入口处校验 `user_id` 环境变量，缺失调用 `raise_exit(ExitCode.BUSINESS_ERROR, ...)`。
- **调用外部后端 API**：如需携带 Token，使用 `HTTPClient`（`references/http.md`）并在请求中附加从环境变量读取的 Token。
