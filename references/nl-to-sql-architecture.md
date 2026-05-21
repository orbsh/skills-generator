---
name: nl-to-sql-architecture
description: NL-to-SQL 业务查询 Skill 架构分析与决策参考
---

# NL-to-SQL 业务查询 Skill 架构

## 问题背景

业务方提出"用 AI 分析数据"的需求，但理解偏差导致初始方案失败：把原始数据直接扔给 AI，结果速度极慢、token 爆炸、准确率差。

正确定位：**这是一个 NL-to-SQL 任务**。用户用自然语言提问（如"本月产品销量排名"），AI 生成 SQL，交给数据库查询。数据已经是结构化的，SQL 能精确查询，中间不存在信息损耗。

## 核心约束

| 约束 | 原因 |
|---|---|
| Skill 无状态、可移植 | 禁止在 Skill 目录下创建持久化文件或本地数据库 |
| 企业级多用户系统 | 多 Skill 实例并行写入同一数据表是可能的 |
| 不能直连业务数据库 | AI 生成的 SQL 直接打生产库风险不可控 |
| 排除 Java 生态 | Skill 非持续运行，JVM 启动预热 + 大型集群维护成本过高 |
| RisingWave 已用于 ETL | 现有 API 已返回宽表数据，可复用 |

---

## 决策 0：为什么不自建数据库

在确定了"不能直连业务库"之后，最直接的替代方案是：**新建一个数据库实例，然后从 API 同步数据进来**。这看起来合理，但实际评估后被排除：

### 方案对比

| 维度 | 新建 RDBMS（PostgreSQL/MySQL/SQLite） | Delta Lake（文件存储） |
|---|---|---|
| **服务依赖** | 需要运行中的数据库服务器进程 | 无服务器，纯文件存储 |
| **Skill 约束** | 违背"无状态、可移植"原则 — Skill 需要知道 DB 连接串、管理连接池、处理断线重连 | 只读文件，开箱即用 |
| **运维成本** | 备份、版本升级、连接数限制、磁盘监控、高可用配置 | 文件级操作，无额外服务 |
| **同步复杂度** | 需要处理 CDC 或自定义 upsert 逻辑、事务管理、锁竞争 | 直接追加新文件，Delta 日志自动处理一致性 |
| **多租户隔离** | 需要 schema/user/role 管理，或为每个租户建独立库 | 目录前缀隔离（`data/{tenant}/`），天然支持 |
| **部署门槛** | 企业环境申请一个数据库实例的审批流程长 | 指定一个存储路径即可 |

### 决策链

```
新建数据库方案
  ├─ 需要运行数据库服务 → 违背 Skill 无状态约束
  ├─ 需要连接管理、断线重连 → 增加脚本复杂度
  ├─ 需要运维（备份/升级/监控） → 企业环境审批成本高
  └─ 结论 → 文件存储方案（Delta Lake）更轻量、更符合 Skill 定位
```

Delta Lake 本质上是**带事务日志的文件存储**，不需要任何后台服务进程。Skill 脚本只需指定一个存储路径，通过 `deltalake` 库直接读写，天然契合"无状态、可移植"的设计要求。

### 关键差异：同步方式

- **RDBMS 同步**：需要处理 upsert（插入或更新）、主键冲突、事务回滚。API 返回的数据可能包含更新，需要在 DB 端执行 `INSERT ... ON CONFLICT UPDATE` 逻辑
- **Delta Lake 同步**：只需追加新数据文件，Delta 的事务日志自动保证一致性。如果需要去重/更新，在 query 阶段通过 SQL 的 `ROW_NUMBER() OVER (PARTITION BY id ORDER BY update_time DESC)` 取最新记录即可，**sync 阶段只需 append**

这种"append-only + query-time dedup"的模式大幅降低了 sync 逻辑的复杂度。

---

## 决策 1：存储格式 — 为什么选 Delta Lake

### 被排除：Iceberg

- 需要外部 Catalog 服务（Polaris / REST Catalog）
- 运维成本超过数据库本身，对单个 Skill 来说过重
- **结论**：杀鸡用牛刀，排除

### 被排除：纯 Parquet

初看 Parquet 足够（只读、追加写入），但以下场景使其不可行：

1. **多 Skill 业务关联**：多个 Skill 各自维护的 Delta 表可能需要跨表 JOIN。纯 Parquet 文件之间没有注册机制、没有元数据关联，无法落地"业务关联"
2. **并发写入**：企业多用户场景下，并行写入同一表是可能的。Parquet 无 ACID、无写协调、无隔离，并发写会损坏文件
3. **碎片化问题**：sync-on-query 模式下反复追加增量数据，产生大量小 Parquet 文件。查询性能严重退化，且 Parquet 自身没有任何合并/优化机制
4. **无 compaction**：没有 `OPTIMIZE`、没有 `VACUUM`，碎片只能手动处理

### 选择 Delta Lake 的决策链

```
纯 Parquet 不够
  ├─ 需要 ACID 处理并发 → 选 Delta 或 Iceberg
  ├─ Iceberg 需要 Catalog → 运维过重
  └─ 结论 → Delta Lake 是唯一合理选择
```

Delta Lake 满足所有需求：
- ACID 事务保证并发写入安全
- 事务日志支持 append + update/delete
- 内置 `OPTIMIZE` 合并小文件、`VACUUM` 清理过期文件
- 自包含，无需外部 Catalog 服务
- 接受适度复杂性作为解决并发和碎片化的代价

### Delta Lake 碎片整理策略

| 策略 | 说明 |
|---|---|
| `OPTIMIZE` | 合并小文件为大文件，减少 I/O |
| `VACUUM` | 删除超过保留期的过期文件 |
| 触发条件 | 文件数 > 100 或增量体积 > 50MB 时才触发，避免每次 sync 都跑 |
| 分区级 OPTIMIZE | `OPTIMIZE table WHERE partition_col = 'X'`，只合并被写入的分区，减少写放大 |
| 大表异步执行 | OPTIMIZE 耗时较长时，先返回查询结果给用户，再在后台执行（或推迟到下次 sync 周期） |
| 内嵌在 sync 流程 | sync 由 skill script 控制，compaction 逻辑写在同一流程中，无需外部调度器 |

---

## 决策 2：计算引擎 — DuckDB vs Polars

| 引擎 | SQL 支持 | Delta Lake 写入 | Delta Lake 读取 | AI 兼容性 |
|---|---|---|---|---|
| DuckDB | 完整 | 不成熟 / 有限 | 良好（通过 delta-rs） | 优秀（AI 生成 SQL） |
| Polars | 有限（SubSQL 子集） | 良好（deltalake crate） | 良好 | 差（SQL 子集太窄） |

**矛盾**：DuckDB 写 Delta 不成熟，Polars SQL 对 AI 生成太受限。

**解决方案**：分层使用。

```
┌─ 写层 ──────────────────────────────┐
│  deltalake (Rust/Python 库)          │
│  sync 阶段：API 取数 → 写入 Delta     │
│  AI 不接触写路径，只负责生成 SELECT    │
└─────────────────────────────────────┘

┌─ 读层 ──────────────────────────────┐
│  DuckDB                              │
│  query 阶段：在 Delta 上执行 SQL      │
│  只读模式，完整 SQL，AI 友好           │
└─────────────────────────────────────┘
```

职责清晰：`deltalake` 库处理写入（成熟稳定），DuckDB 处理查询（完整 SQL 支持），AI 只生成 SELECT 语句。

---

## 决策 3：数据同步 — 为什么不用 RisingWave

### 被排除：外部 RisingWave 物化视图

- 需要在 Skill 项目之外维护独立 pipeline
- 如果接受外部基础设施，直接用 RisingWave（物化视图 + 直接查询）更简单高效
- 这违背了"Skill 逻辑自包含"的设计目标
- **结论**：如果能接受运维 RisingWave，那整个方案就不需要 Delta Lake 了

### 选择嵌入式 sync-on-query

- 同步逻辑写在 Skill 脚本内部
- 复用现有数据 API（与 RisingWave 同源），已返回扁平宽表
- 逻辑内聚：sync、compaction、query 在同一流程中
- 无外部服务依赖

### 冷启动问题

- 首次查询或长期未查询后，增量窗口很大，同步耗时较长
- **现实情况**：首次请求通常来自内部测试人员，有心理预期，愿意等待
- 不需要 cronjob 预热（如果加了 cronjob，不如直接用 RisingWave）

### 同步流程

```
1. 查询 Delta Lake 的 MAX(update_time) — 表为空则用 epoch
2. 调用 API 获取 update_time > last_sync 的记录
   （API 必须支持按时间范围查询；所有记录必须携带 update_time 字段）
3. 通过 deltalake 库写入新/更新记录
   → 并发冲突处理：CommitConflict 时指数退避重试（max 3 次）
4. 检查文件数量 — 超过阈值则执行分区级 OPTIMIZE
5. 更新表注册信息（用于跨 Skill JOIN）
6. 进入查询阶段
```

### Schema 变更处理

- **不实现 schema evolution / mergeSchema**
- API 返回的字段可能增减，处理 schema 迁移的复杂度远超收益
- 数据量小（通常几百万行以内），schema 变更时直接删表重建
- 全量重建比迁移逻辑更简单、更可靠

---

## 决策 4：AI SQL 生成 — Schema 上下文与容错

### Schema Context 注入

- AI 必须收到表 schema（列名、类型、枚举值示例）
- 没有 schema 时 AI 会猜列名 → 无效 SQL
- Schema 在运行时从 Delta Lake 元数据提取，传递给 AI 作为上下文

### 无效 SQL 重试循环

```
生成 SQL → 执行 → 如果报错：
  1. 捕获错误信息
  2. 将错误 + schema 重新喂给 AI，附修正提示
  3. 重试（最多 2-3 次）
  4. 全部失败 → 返回结构化错误给用户
```

### 查询保护（脚本中硬编码）

| 保护项 | 机制 |
|---|---|
| 只读 | DuckDB 以 readonly 模式打开；或解析 SQL 拒绝 DDL/DML |
| 行数限制 | 强制追加 `LIMIT 1000` |
| 超时 | `SET statement_timeout='30s'` |
| 组织隔离 | `WHERE org_path LIKE '<user_prefix>%'` 强制附加 — AI 只生成中间部分 |

---

## 决策 5：数据安全 — 组织路径枚举

- 所有数据记录携带 `org_path` 字段（路径枚举：如 `/root/dept-a/team-b/`）
- 用户身份通过带外注入（skill context / auth token）
- 用户所属组织前缀从身份映射（如 `/root/dept-a/`）
- 每个查询被重写，强制追加：`WHERE org_path LIKE '/root/dept-a/%'`

### 分区优化

- `org_path`（或派生的 `org_prefix` 列）设为 Delta Lake 的 **分区列**
- 写入时指定 `partition_by=["org_prefix"]`
- 查询时直接裁剪分区，不走全表扫描
- 避免 `LIKE` 导致的全表扫描性能问题

### AI Prompt 设计

> "最终 SQL 会自动附加 `WHERE org_path LIKE '<prefix>%'`。请只生成 SELECT ... FROM ... WHERE ... AND ... ORDER BY ... LIMIT 部分。不要包含 `WHERE org_path`。"

效果：
- AI 不需要知道安全层存在
- 安全过滤在脚本层强制执行，AI 无法绕过
- 用户只能看到其组织子树内的数据

---

## 决策 6：跨 Skill 表注册

多个 Skill 各自维护相关的 Delta Lake 表时，跨 Skill JOIN 需要 DuckDB 能发现所有表的位置。

**路径约定**：所有 Delta 表存储在共享根目录下：
```
data/{tenant}/{skill}/{table}/
```

**注册机制**：
- 每个 Skill 在 sync 成功后，将表元数据（表名、Delta 路径、列信息）写入共享注册表
- 注册表可以是存储根目录下的小型 JSON 文件，也可以是 SurrealDB 记录
- 查询执行前，DuckDB 读取注册表，为每个注册的表 `CREATE VIEW`
- 跨 Skill JOIN 通过标准 SQL 实现

保持 Skill 独立（无共享代码），同时在查询时实现可组合性。

---

## 最终架构

```
┌─ 用户（自然语言查询）─────────────────┐
│                                      ▼
│                             AI（NL-to-SQL）
│                             + schema context
│                             + 强制 WHERE org_path LIKE 'x%'
│                                      ▼
│                    ┌─── sync 阶段（deltalake 库）───┐
│                    │ 1. 查询 MAX(update_time)       │
│                    │ 2. API 取数: update_time > last│
│                    │ 3. delta.write（冲突重试）      │
│                    │ 4. OPTIMIZE（文件数超阈值时）   │
│                    │    （分区级别）                 │
│                    │ 5. 更新表注册信息               │
│                    └────────────────────────────────┘
│                                      ▼
│                    query 阶段（duckdb readonly）
│                    + 加载注册表 → CREATE VIEW
│                    + 自动 WHERE org_path LIKE 'x%'
│                    + 分区裁剪（org_prefix）
│                    + LIMIT 1000 + 超时 30s
│                    + 重试循环（最多 3 次）
│                                      ▼
│                    结果 → AI 格式化 → 用户
└──────────────────────────────────────┘
```

**组件清单**：

| 组件 | 技术选型 | 职责 |
|---|---|---|
| 存储 | Delta Lake | ACID 写入、compaction、碎片管理 |
| 写层 | `deltalake`（Rust/Python） | Sync：API 取数 → 写入 Delta Lake |
| 读层 | DuckDB | Query：在 Delta Lake 上执行 SQL |
| CLI | Typer | 脚本入口（接受 SQL 文本） |
| 日志 | structlog | 结构化日志（logfmt/JSONL） |
| 配置 | pydantic-settings + YAML | API 端点、Delta 路径、compaction 阈值 |

**Skill 脚本只接受 SQL 文本** — sync、compaction、安全过滤、重试、格式化全部硬编码。AI 的工作纯粹是 NL → SQL 生成，附带 schema 上下文。
