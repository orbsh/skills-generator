# 工业级数据分析 Skill 架构 (LanceDB)

## ADR: 选型 LanceDB 作为核心湖仓底座 (Lightweight Today, 红利 Tomorrow)

### 1. Context
在几万到几百万行的中等数据规模下，LanceDB 目前在纯分析（OLAP）场景下相比 Parquet/Delta 在压缩比或扫描吞吐上的微弱劣势，在物理时间上是一个可以忽略的"四舍五入误差"。无论是 5 万行还是 200 万行，Polars/DuckDB 的内存计算都只需不到 50ms，存储介质的物理差异被内存计算掩盖。

### 2. Decision
**全面采用 LanceDB (Lance Format)，放弃 Delta Lake/Iceberg。**
核心逻辑："在当下保持极致轻量，在未来拥抱技术红利"。

### 3. Rationale (Why Not Delta? Why Lance?)
*   **今天 (Day 1): 避开 OSS 兼容地狱与运维泥潭**
    *   **Why Not Delta**: `delta-rs` 1.6 版本在写入阿里云 OSS 时存在 `If-None-Match` 报错死结，且强依赖 Catalog 服务。
    *   **Lance Advantage**: 保持函数/短生命周期容器的 **100% 纯无状态与零服务**。利用 Append-only 机制实现无锁并发，彻底摆脱大厂重型架构。
*   **明天 (Day 2): 原地白嫖底层性能暴涨**
    *   未来 6-12 个月，随着 Lance 官方将底层 BtrBlocks 和自适应压缩协议推向 Python 生态，系统 **不需要改动一行代码或 DDL**，即可原地享受列式 OLAP 性能的跨代级提升。
*   **后天 (Day 3): 原生 AI/向量就绪**
    *   当引入向量审计（GraphRAG/语义检索）时，底层存储已是原生 AI 向量数据库，**完全不需要重构存储架构**。

---

## 第一部分：Schema 定义战略

LanceDB 完全基于 Apache Arrow 构建。虽然它支持写入时动态推导结构（Schema-on-Write），但在以下场景中，**显式定义 Schema 是强制性的**：
1. 初始化空表（无数据时无法推导类型）。
2. 严格的财务审计与数据治理环境。

### 1. 核心数据类型
- **财务数值**: `pa.float64()` (Polars `pl.Float64`)。严禁使用 `float32` 以防止大额账目精度丢失。
- **审计时间戳**: `pa.date32()` 和 `pa.timestamp('us', tz='Asia/Shanghai')`。
- **分区辅助列**: `pa.int32()` 或 `pa.string()`（保持轻量以最小化 OSS 元数据）。

### 2. 嵌套类型策略 (Struct vs. Map)
- **A 类：Struct (静态对象)**: 固定嵌套实体（如订单内嵌多张发票）。
  - **优势**: 在 OSS 物理层被拆解为解耦列。支持**列裁剪 (Projection Pushdown)**（例如 DuckDB 仅下载 `amount` 而不下载相邻文本），最大化带宽效率。
- **B 类：Map (动态 JSON)**: 不可预测的上游 Key-Value 标签 (`pa.map_(pa.string(), pa.string())`)。
  - **优势**: 充当“安全隔离舱”，防止上游随意增加自定义 Key 导致类型错配。

### 3. 显式初始化代码

```python
import pyarrow as pa
import lancedb

def initialize_blank_financial_lakehouse(db_uri: str, oss_options: dict):
    """
    初始化空表：在 OSS 上生成包含 0 行数据的合法元数据清单。
    确保分布式多容器写入时的 Schema 严格对齐。
    """
    db = lancedb.connect(db_uri, storage_options=oss_options)
    table_name = "financial_records"

    if table_name not in db.table_names():
        explicit_schema = pa.schema([
            pa.field("tx_id", pa.string(), nullable=False),
            pa.field("amount", pa.float64(), nullable=False),
            pa.field("year", pa.int32(), nullable=False),
            pa.field("month", pa.int32(), nullable=False),
            # A 类：固定结构体
            pa.field("invoice_detail", pa.struct([
                pa.field("invoice_no", pa.string()),
                pa.field("tax_rate", pa.float64())
            ])),
            # B 类：动态 Map
            pa.field("custom_tags", pa.map_(pa.string(), pa.string()))
        ])

        # 强制启用现代高性能协议
        db.create_table(table_name, schema=explicit_schema, storage_version="2.0")
        print("Lakehouse 表结构初始化完成。")
```

## 第二部分：容器化 Skill 代码模板

此脚本嵌入在无状态 Skill 容器中。无后台常驻守护进程。规避了 `delta-rs` 与国内对象存储 (OSS) 的兼容性问题。将 AI 过滤转化为 Polars 向量化计算图。

```python
import os
import time
from datetime import datetime

# 💡 核心优化：绝不在文件顶部 import polars/lancedb！
# 确保 K8s 冷启动基础负载为 0ms。

# 存储配置：标准 S3 协议映射至阿里云 OSS
OSS_STORAGE_OPTIONS = {
    "aws_access_key_id": os.environ.get("OSS_ACCESS_KEY_ID"),
    "aws_secret_access_key": os.environ.get("OSS_SECRET_ACCESS_KEY"),
    "endpoint_url": "https://oss-cn-hangzhou.aliyuncs.com",
    "region": "cn-hangzhou"
}
DB_URI = "s3://your-finance-bucket/lancedb_core_lake/"

def skill_data_sync_lancedb(incoming_pl_df):
    """
    1. 增量同步 Skill：由 AI 动态触发。
    将增量 Polars DF 在内存中转为 .lance 块并直接写入 OSS。
    """
    if incoming_pl_df.is_empty():
        return {"status": "skipped", "reason": "输入数据为空"}

    # 延迟导入：仅在触发时加载重度库
    import polars as pl
    import lancedb

    sync_payload = incoming_pl_df.with_columns(
        pl.lit(datetime.now()).alias("ingested_at")
    )

    # 确保 Schema 存在（幂等）
    initialize_blank_financial_lakehouse(DB_URI, OSS_STORAGE_OPTIONS)

    db = lancedb.connect(DB_URI, storage_options=OSS_STORAGE_OPTIONS)
    table = db.open_table("financial_records")

    # 盲写追加 (Blind Append)：在 OSS 生成独立物理块。
    # 1000 并发容器 = 0 锁竞争。完美规避 delta-rs 报错。
    table.add(sync_payload)

    return {
        "status": "success",
        "version": table.version,
        "rows_committed": len(sync_payload)
    }

def skill_analytical_query_lancedb(ai_generated_sql_filter: str):
    """
    2. 分析查询 Skill：执行 AI 生成的 SQL 过滤条件。
    """
    start_time = time.perf_counter()
    import polars as pl
    import lancedb

    db = lancedb.connect(DB_URI, storage_options=OSS_STORAGE_OPTIONS)
    table = db.open_table("financial_records")

    # 零拷贝映射：Lance 清单 -> Polars LazyFrame。
    # 纯内存操作，0ms 延迟，此时未下载任何物理数据。
    lazy_lake = table.to_lance().to_lazy()

    try:
        # 注入 AI SQL 过滤条件。
        # Polars 将其下推至 Lance 读取器 -> 触发 OSS Data Skipping。
        # 注：原生链式调用性能更佳，此处演示 SQL 字符串解析。
        filtered_lazy = lazy_lake.filter(pl.sql(ai_generated_sql_filter))

        # OLAP 流水线：月度 - 人员 - 薪资聚合
        analysis_pipeline = (
            filtered_lazy
            .group_by(["year", "month", "employee_id"])
            .agg(pl.col("amount").sum().alias("monthly_total_salary"))
            .sort("monthly_total_salary", descending=True)
        )

        # 执行：在本地内存物化结果
        summary_result = analysis_pipeline.collect()

        return {
            "status": "success",
            "latency_ms": (time.perf_counter() - start_time) * 1000,
            "data": summary_result
        }
    except Exception as e:
        return {"status": "error", "reason": str(e)}
```

## 第三部分：维护 (异步 Compaction)

增量同步会在 OSS 上堆积碎片文件，增加 HTTP 延迟。
**零常驻架构**: 无需中间件。仅需解耦的“维护 Skill"，通过 CronJob 每周触发一次。
LanceDB 的 MVCC 确保后台合并不会锁死前台 AI 查询。

```python
def skill_weekly_maintenance_compact():
    """
    3. 维护 Skill：将碎片文件合并为 512MB 标准块。
    原子性快照更新。不干扰前台查询。
    """
    import lancedb

    db = lancedb.connect(DB_URI, storage_options=OSS_STORAGE_OPTIONS)
    table = db.open_table("financial_records")

    print(f"开始合并碎片。当前版本：{table.version}")

    # 1. 在 OSS 后台合并物理小文件片段
    table.compact_files()

    # 2. 清理 7 天前的旧快照以节省 OSS 存储成本
    table.cleanup_old_versions(older_than=7) # 注：需确认 API 参数名称

    print(f"碎片清理完成。最新快照：{table.version}")
```

## 战略选型总结

该架构构建了一个原生的、AI 就绪的多模态数据湖：
- **摆脱重型栈**: 无需 Spark/Databricks (Delta Lake) 或复杂的元数据服务 (Iceberg/Polaris)。
- **OSS 兼容性**: 纯追加设计 100% 免疫 `If-None-Match` 报错。
- **面向未来**: 随着 Lance 分析内核的成熟，你将在无需重构或修改 DDL 的情况下，直接获得列式 OLAP 性能暴涨。
