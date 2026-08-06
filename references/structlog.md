---
name: structlog
description: structlog 日志库使用规范，包含双格式输出（JSONL/logfmt）、配置方法和最佳实践
---

# structlog 日志规范

本文档说明 Skill 中日志记录的标准用法。

## 📦 组件复用指南

**⚠️ 禁止在脚本中重复编写 `setup_logging()` 函数。**

日志初始化逻辑已统一下沉至 **skillforge** 包，作为独立子模块 `skillforge.logging` 提供。在新建 Skill 时，请按以下步骤复用：

1. **导入使用**：在 `run.py` 中通过 `from skillforge.logging import setup_logging, logger` 引入（`skills_generator` 的 `setup_logging` / `logger` 即由此转出）。
2. **调用初始化**：在加载配置后执行 `setup_logging(log_dir=cfg.log_dir, skill_root=skill_root)`。

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
# ⚠️ 相对路径相对于 skill_root 解析，消费方传入显式 skill_root
#   如需输出到项目 logs 目录，使用 ../../logs
log_dir: ""
backup_count: 30
```

## 使用示例

```python
from skillforge.logging import setup_logging, logger
from skills_generator.config import get_skill_root

# 配置加载后初始化日志（显式传入消费方 skill_root，确保相对路径正确解析）
skill_root = get_skill_root()
setup_logging(log_dir=cfg.log_dir, skill_root=skill_root)

# ✅ 正确：结构化键值对 + 英文缩写事件名
logger.info("req-start", endpoint="/api/data", user_id=user_id)
logger.warning("api-slow", retry_count=2, latency_ms=1500)
logger.error("db-conn-fail", host="db.example.com", port=5432)

# ❌ 错误：字符串拼接 / 中文事件名 / 未使用键值对
logger.info(f"开始处理请求: {endpoint}, user: {user_id}")
logger.info("开始处理请求", endpoint="/api/data")
```

## 日志级别

| 级别 | 使用场景 |
|------|----------|
| `INFO` | 正常业务流程关键节点（开始/完成/状态变更） |
| `WARNING` | 可恢复的异常或降级情况（重试、超时预警） |
| `ERROR` | 导致命令失败或 Exit Code 非 0 的错误 |
| `DEBUG` | 仅开发时启用，生产环境不输出 |

## 最佳实践

1. **事件名使用英文缩写**：使用 `-` 分隔，无空格，尽量短且便于分类，支持缩写（如 `app-start`, `auth-miss`, `ord-query`, `err-conn`）
2. **关键上下文必传**：`user_id`、`request_id`、`endpoint` 等
3. **异常信息使用 `str(e)`**：避免直接传入异常对象
4. **不要在日志中包含敏感信息**：如密码、Token、Cookie