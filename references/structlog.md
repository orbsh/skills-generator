---
name: structlog
description: structlog 日志库使用规范，包含双格式输出（JSONL/logfmt）、配置方法和最佳实践
---

# structlog 日志规范

本文档说明 Skill 中日志记录的标准用法。

## 📦 组件复用指南

**⚠️ 禁止在脚本中重复编写 `setup_logging()` 函数。**

日志初始化逻辑已统一下沉至 **skillforge** 包，作为独立子模块 `skillforge.logging` 提供。在新建 Skill 时，请按以下步骤复用：

1. **导入使用**：在 `run.py` 中通过 `from skillforge.logging import init_logging, setup_logging` 引入（`skills_generator` 的 `init_logging` / `setup_logging` 即由此转出）。
2. **调用初始化**：通常直接执行免配置的 `init_logging()`（读取框架 `settings.logging` 默认值，复用主进程日志行为）；如需自定义输出目标，再改用 `setup_logging(log_dir=cfg.log_dir)`。

如需查看完整源码实现，请参阅 skillforge 项目内的 `src/skillforge/logging.py`。

## 核心原则

- **统一使用 structlog**：禁止使用 `print()` 或标准 `logging` 直接输出
- **双格式输出**：终端使用 `logfmt`（人类可读），文件使用 `JSONL`（机器可解析）
- **结构化日志**：所有日志必须使用键值对，禁止字符串拼接

## 配置项

在 `assets/config.yaml` 中添加 `log_dir` 字段（输出目标二选一）：

```yaml
# 空字符串/缺省 = 输出到终端（logfmt）
# 指定目录       = 输出到文件（JSONL，按天旋转，默认保留 30 份，旧的自动删除）
# ⚠️ 相对路径相对于当前工作目录解析（cwd）
#   如需输出到项目 logs 目录，使用 ../../logs
log_dir: ""
backup_count: 30
```

## 使用示例

```python
import structlog
from skillforge.logging import init_logging, setup_logging

# 免配置初始化日志（读取框架默认），优先推荐
init_logging()

# 或：# 自定义输出目标时，相对路径按当前工作目录解析
# setup_logging(log_dir=cfg.log_dir)

# 各模块使用自己的 logger（不带共享实例）
logger = structlog.get_logger(__name__)

# ✅ 正确：结构化键值对 + 英文缩写事件名
logger.info("req-start", endpoint="/api/data", user_id=user_id)
logger.warning("api-slow", retry_count=2, latency_ms=1500)
logger.error("db-conn-fail", host="db.example.com", port=5432)

# ❌ 错误：字符串拼接 / 中文事件名 / 未使用键值对
logger.info(f"开始处理请求: {endpoint}, user: {user_id}")
logger.info("开始处理请求", endpoint="/api/data")
```

## 上下文绑定（logger 实例）

不要把 `user_id` / `session_id` 等请求级上下文重复传给每条日志。用 `logger.bind(...)` 绑定一次，返回的新 logger 自动携带这些字段，后续日志无需重复传入：

```python
logger = structlog.get_logger(__name__)

# 请求开始时绑定上下文，后续所有日志自动带上 user_id / session_id
log = logger.bind(user_id=user_id, session_id=session_id)
log.info("op-start", endpoint="/api/data")
log.error("op-fail", err=str(e))   # 自动包含 user_id / session_id

# ✅ 若需临时移除/覆盖，可再次 bind 覆盖，或用 log.unbind("user_id")
```

要点：

- `bind()` **不修改模块级共享 logger**，而是返回新的绑定实例，因此并发调用（如 `to_thread` 并行执行）互不干扰。
- 只适用于**同一作用域内需要共享上下文**的场景（如一次脚本执行、一次请求处理）。
- 若需让**整个请求链路的所有模块**都带上上下文（跨函数/跨模块），则用 `structlog.contextvars.bind_contextvars(...)`（配合框架已配置的 `merge_contextvars`），并在结束时 `clear_contextvars()` 清理。

## 日志级别


| 级别 | 使用场景 |
|------|----------|
| `INFO` | 正常业务流程关键节点（开始/完成/状态变更） |
| `WARNING` | 可恢复的异常或降级情况（重试、超时预警） |
| `ERROR` | 导致命令失败或 Exit Code 非 0 的错误 |
| `DEBUG` | 仅开发时启用，生产环境不输出 |

## 最佳实践

1. **事件名使用英文缩写**：使用 `-` 分隔，无空格，尽量短且便于分类，支持缩写（如 `app-start`, `auth-miss`, `ord-query`, `err-conn`）
2. **关键上下文必传**：`user_id`、`request_id`、`endpoint` 等；同一作用域复用同一上下文时用 `logger.bind()` 绑定一次，避免重复传入（见「上下文绑定」）
3. **异常信息使用 `str(e)`**：避免直接传入异常对象
4. **不要在日志中包含敏感信息**：如密码、Token、Cookie