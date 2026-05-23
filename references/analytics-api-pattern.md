---
name: analytics-api-pattern
description: 数据分析（nl-to-sql）Skill 生成模式：API → 同步到 Delta Lake → SQL 查询。注意：分析特指 nl-to-sql，与 nl-to-api 的 search/query 不同。
---

# 数据分析 API 模式

本文档描述分析类 Skill 的标准架构：**API 数据同步 → Delta Lake 存储 → SQL 查询**。

## 📦 组件复用指南

**⚠️ 禁止在脚本中重新编写 API 拉取、增量同步、Delta Lake 写入逻辑。**

数据同步和存储模块已作为通用工具内置。在新建 Skill 时，请按以下步骤复用：

1. **拷贝文件**：将 `scripts/utils/analytics_api.py` 和 `scripts/utils/delta_store.py` 完整拷贝至目标 Skill 的 `scripts/utils/` 目录。
2. **导入使用**：
   - `from scripts.utils.analytics_api import sync_table, sync_all_tables, sync_and_query, fetch_api`
   - `from scripts.utils.delta_store import open_or_create_table, write_records, query, last_update, delta_path, table_exists`
3. **依赖**：`analytics_api.py` 依赖 `delta_store.py`，两者必须同时拷贝。

## ⚠️ 存储要求：Delta Lake 仅支持 S3

**Delta Lake 强制使用 S3 / 对象存储，不支持本地文件系统。**

- `storage.root` 配置项必须是 `s3://` 开头的 URL（例如 `s3://my-bucket/delta`）
- 启动时会校验路径格式，本地路径（如 `/data/delta`）将直接报错拒绝
- `storage_options` 配置项用于传递 S3 凭证（`aws_access_key_id`、`aws_secret_access_key`、`endpoint` 等），走环境变量注入
- DuckDB 查询时自动加载 `httpfs` + `delta` 扩展并通过 `delta_scan` 读取 S3 上的 Delta 表
- Skill 实例保持无状态 — 所有数据状态委托给对象存储，实例可随时销毁重建

## 架构概览

# API 数据分析 Skill 生成模式（nl-to-sql）

## 术语定义：Analytics vs Search/Query

**在本 skill 的上下文中，术语有严格区分：**

| 术语 | 模式 | 数据流 | 典型用途 |
|------|------|--------|----------|
| **Analytics（数据分析）** | nl-to-sql | API → 同步到 Delta Lake → SQL 查询 | 跨时间趋势、多表聚合、复杂过滤 |
| **Search / Query（搜索/查询）** | nl-to-api | 直接调 API 接口 → 过滤/分页 | 单条记录查找、实时状态查询、简单列表 |

**核心区别：** Analytics 不是直接查接口。它先把数据全量/增量同步到一个专用的 OLAP 数据库（Delta Lake），然后用 SQL 从本地数据库查询。Search/Query 则是直接用自然语言构造 API 请求参数，调用接口获取结果。

本模式文档只覆盖 **Analytics（nl-to-sql）** 场景。nl-to-api 场景不属于本模式范畴。

## 概述

企业级应用中，**数据分析（nl-to-sql）** 是最常见的场景之一。本模式定义了 **从 API 接口描述生成完整 Analytics Skill** 的标准流程。

用户输入：
1. **接口描述** — "这是用户订单接口，返回订单列表"
2. **枚举/状态字段说明** — "status 字段是数字：0=待支付, 1=已支付, 2=已发货, 3=已完成, 4=已取消"
3. **示例 JSON 数据** — API 返回的实际响应样本
4. **字段业务含义** — 每个字段代表什么、有哪些注意事项

生成器输出：
- `assets/config.yaml` — 字段定义、类型推断、API 端点映射
- `SKILL.md` — 分析能力描述、注意事项、`<table-schemas>` 占位区（从配置自动生成）
- `scripts/run.py` — Typer CLI（`sync` + `query` 子命令）

---

## 生成流程

### 第一步：解析接口描述

从用户提供的信息中提取：
- 接口名称（用于 Skill name）
- API base_url 和 endpoint
- 认证方式（bearer / api_key / none）
- 返回的数据结构（列表 / 分页 / 嵌套对象）

### 第二步：推断字段 Schema

从示例 JSON 数据中推断每个字段的类型和业务含义：

| JSON 值示例 | 推断类型 | 规则 |
|------------|---------|------|
| `12345` | `i64` | 整数 ID、数量等 |
| `"ABC-001"` | `str` | 编码、名称 |
| `299.99` | `f64` | 金额、价格 |
| `"2024-01-15"` | `date` | 日期字符串 |
| `"2024-01-15T10:30:00Z"` | `timestamptz` | ISO 8601 时间戳 |
| `true` / `false` | `bool` | 布尔标志 |
| `0, 1, 2, 3, 4`（枚举） | `i8` 或 `i16` | 状态码，值域小用 i8 |

**枚举字段特殊处理：**
- 如果用户说明了数字对应的含义（如 status: 0=待支付），必须在 SKILL.md 的 schema 描述中注入枚举映射
- 类型仍用 `i8`/`i16`，但 description 中写明枚举值

示例：
```yaml
- name: status
  type: i8
  description: "订单状态：0=待支付, 1=已支付, 2=已发货, 3=已完成, 4=已取消"
  original: "order_status"
```

### 第三步：生成配置

按照以下规范生成 `assets/config.yaml`：
- `api.base_url` — 从接口描述提取
- `api.auth` — 认证配置（token 走环境变量）
- `storage.root` — Delta Lake 存储路径
- `tables` — 表定义列表，包含字段映射
- 每个表必须声明 `id_field`（去重主键）和 `update_field`（增量同步时间戳）
- `org_path` 字段自动生成（`generated: true`），用于行级安全

### 第四步：生成 SKILL.md

SKILL.md 结构：
1. **YAML 头部** — name + description（从 `generate_skill_description()` 生成）
2. **Trigger Scenarios** — 根据接口描述生成可分析的场景列表
3. **Available Commands** — sync 和 query 的使用说明
4. **`<table-schemas>` 占位区** — 由 `generate_schema_description()` 自动生成并替换
5. **Special Notes** — 根据用户提供的注意事项生成（如枚举含义、业务规则）
6. **Authentication** — 说明 token 环境变量名

**`<table-schemas>` 标记规范：**
生成器在 SKILL.md 中预留标记区域，随后用配置数据填充：
```xml
<table-schemas>
You are a SQL generator. Available tables:
...
</table-schemas>
```
AI 读取 SKILL.md 时，这段内容就是可用的 schema context。

### 第五步：生成 run.py

使用 `references/skill-structure.md` 中的模板生成 `scripts/run.py`：
- 引用 `scripts.utils.analytics_api` 和 `scripts.utils.delta_store`
- `Settings` 从 `assets/config.yaml` 加载
- 两个子命令：`sync`（增量同步）和 `query`（sync + SQL 执行）
- 结构化日志、标准 Exit Code

---

## 枚举字段处理规则

数字状态字段是数据分析中最容易出错的地方，生成时必须：

1. **类型用最小足够整数** — 0-127 用 `i8`，-32768~32767 用 `i16`，其余用 `i32`
2. **description 必须包含枚举映射** — AI 生成 SQL 时需要知道数字含义
3. **在 SKILL.md Special Notes 中额外说明** — 帮助 AI 理解业务语义

示例 Special Notes 段落：
```markdown
# Special Notes

- The `status` field uses numeric codes: 0=pending, 1=paid, 2=shipped, 3=completed, 4=cancelled
- When filtering "completed orders", use `WHERE status = 3` (not `status > 0`)
- `amount` is in CNY (Chinese Yuan), no currency conversion needed
- All timestamps are UTC
```

---

## 多表关联

如果用户描述了多个相关接口（如 orders + products + users）：
- 每个接口对应一个 table 配置
- 表名必须是蛇形命名（`order_items`, `product_catalog`）
- 关联键（如 `product_id`）在 description 中注明外键关系
- AI 生成的 SQL 可以使用 JOIN

示例外键描述：
```yaml
- name: product_id
  type: i64
  description: "关联 product_catalog 表的 ID（外键）"
  original: "pid"
```

---

## 安全约束

生成时必须遵守：
- API token 必须走环境变量，禁止明文写入 config
- SQL 只允许 SELECT（`delta_store.py` 的 `validate_sql()` 会拒绝 DDL/DML）
- 查询强制 `LIMIT 1000`（可在 SQL 中显式覆盖）
- `org_path` 行级安全自动附加（用户不需在 SQL 中写 WHERE）
- 表名必须是字面量（禁止动态表名）

---

## 生成器输出检查清单

生成完成后自检：
- [ ] `config.yaml` 中每个表有 `id_field` 和 `update_field`
- [ ] 所有枚举字段 description 包含数值→含义映射
- [ ] `SKILL.md` 中有 `<table-schemas>` 标记且内容已填充
- [ ] `run.py` 引用了 `analytics_api` 和 `delta_store` 模块
- [ ] 没有硬编码 URL 或 token
- [ ] `org_path` 字段标记为 `generated: true`
- [ ] 字段名（name）使用蛇形命名
