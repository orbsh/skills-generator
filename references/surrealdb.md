---
name: surrealdb
description: SurrealDB 使用规范与最佳实践，供生成包含数据库操作的 Skill 时参考
---

# SurrealDB 使用规范

本文档说明技能如何正确操作 SurrealDB 数据库。

## 核心原则

- **禁止 DDL**：SurrealDB 采用 Schemaless 模式，严禁生成 `DEFINE TABLE`、`DEFINE FIELD` 等任何建表、定义字段或索引的初始化语句。
- **字面量表名**：Surql 语句中的表名必须是硬编码的字面量，严禁将表名作为变量传递。
- **状态隔离 (Statelessness)**：Skill 应尽可能无状态。严禁在 Skill 目录下创建 `.txt`、`.db`、`.json` 等本地持久化文件。所有持久化状态必须通过 SurrealDB 存储。

## 日志与连接配置

**日志规范**：详见 `references/structlog.md`

**连接配置**：
Settings 类定义和 YAML 加载方式详见 `references/context-env.md`。

在 `assets/config.yaml` 中添加 SurrealDB 配置项：
```yaml
surreal:
  addr: "http://localhost:8000"
  ns: "test"
  db: "mall"
  user: "master"
  password: "master"
```
在 Settings 类中添加对应字段：
```python
class SurrealDbSettings(BaseSettings):
    """SurrealDB 连接配置"""
    model_config = SettingsConfigDict(extra="ignore")
    addr: str = "http://localhost:8000"
    ns: str = "test"
    db: str = "mall"
    user: str = "master"
    password: str = "master"

class Settings(BaseSettings):
    # yaml_file、env_nested_delimiter 等详见 references/context-env.md
    model_config = SettingsConfigDict(env_nested_delimiter="__", extra="ignore")
    surreal: SurrealDbSettings = Field(default_factory=SurrealDbSettings)

cfg = Settings()
```

## 固定查询函数

必须使用以下 `surreal_query` 函数，**内置错误处理和超时控制**，调用时无需额外 try/except：

```python
def surreal_query(sql: str, vars: dict = None) -> list:
    """执行 SurrealDB SQL 查询，内置错误处理"""
    s = cfg.surreal
    try:
        with httpx.Client(auth=(s.user, s.password), timeout=30.0) as cl:
            h = {
                "Surreal-NS": s.ns,
                "Surreal-DB": s.db,
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
            r = cl.post(f"{s.addr}/sql", content=sql, headers=h, params=vars)
            return r.json()
    except httpx.ConnectTimeout:
        logger.error("SurrealDB 连接超时")
        typer.secho("错误：数据库连接超时", fg="red", err=True)
        raise typer.Exit(code=2)
    except Exception as e:
        logger.error("数据库查询失败", error=str(e))
        typer.secho(f"错误：数据库操作失败 - {str(e)}", fg="red", err=True)
        raise typer.Exit(code=2)
```

## 写入与超时控制

虽然不预设 Schema，但写入逻辑（INSERT/UPDATE）必须保证同一表内的数据字段名与类型一致。
**超时要求**：`surreal_query` 函数内部已强制设置 `timeout=30.0`，请勿修改。

**推荐模式：使用 `UPDATE ... CONTENT` 实现 Upsert**

```python
@app.command()
def save(id: str, content: str):
    """保存或更新数据（ID 存在时更新，不存在时创建）"""
    logger.info("保存数据", id=id)
    stmt = "UPDATE type::thing('literal_table', $id) CONTENT { content: $content, updated_at: time::now() }"
    results = surreal_query(stmt, {'id': id, 'content': content})
    logger.info("数据保存成功")
    typer.echo(json.dumps(results, ensure_ascii=False))
```

## 查询示例

```python
@app.command()
def get(query: str):
    """查询数据"""
    logger.info("查询数据", query=query)
    stmt = "SELECT * FROM literal_table WHERE content @1@ $query LIMIT 10"
    results = surreal_query(stmt, {'query': query})
    logger.info("查询成功", count=len(results))
    typer.echo(json.dumps(results, ensure_ascii=False))
```

## 常见错误

| ❌ 错误做法 | ✅ 正确做法 |
|------------|------------|
| `DEFINE TABLE my_table SCHEMAFULL` | 不执行 DDL，直接写入数据 |
| `SELECT * FROM $table_name` | `SELECT * FROM literal_table` |
| 本地文件缓存数据 | 所有状态存入 SurrealDB |
| 每次写入字段不一致 | 保持同一表字段名和类型一致 |
| 使用 `INSERT` 导致重复数据 | 使用 `UPDATE type::thing(...) CONTENT` 实现 Upsert |

## 变量绑定

使用 `$var_name` 语法绑定参数，避免 SQL 注入：

```python
# ✅ 正确：使用参数绑定
stmt = "SELECT * FROM users WHERE email = $email"
results = surreal_query(stmt, {'email': user_email})

# ❌ 错误：字符串拼接
stmt = f"SELECT * FROM users WHERE email = '{user_email}'"
```

## 记录 ID 格式

使用 `type::thing('table', 'id')` 构建记录 ID：

```sql
-- 创建/更新特定记录
UPDATE type::thing('orders', 'ORD20240101') CONTENT { status: 'completed' }

-- 查询特定记录
SELECT * FROM type::thing('orders', 'ORD20240101')
```
