---
name: skills-generator
description: 你是一个专门为 Claude / OpenClaw 编写 SKILLs 的自动化专家
---
## 📚 参考文档

- `references/auth.md` - 用户认证登录逻辑
- `references/context-env.md` - Agent 上下文环境变量映射规范
- `references/out-of-band-injection.md` - 带外数据注入架构模式（安全传递身份/权限到执行环境）
- `references/error-handling.md` - 错误处理与 Exit Code 规范
- `references/httpx.md` - HTTP 客户端使用规范
- `references/skill-structure.md` - SKILL.md 结构模板、多命令模式与 run.py 编写最佳实践
- `references/structlog.md` - 日志库使用规范（JSONL/logfmt 双格式）
- `references/surrealdb.md` - SurrealDB 使用规范
- `references/jinja2-templates.md` - Jinja2 模板编写约束与最佳实践
- `references/pydantic-renderer.md` - Pydantic 渲染基类规范（Level-Aware 深度感知与 Markdown/YAML 自动降级）
- `references/analytics-api-pattern.md` - 数据分析（nl-to-sql）Skill 生成模式：API → 同步到 Delta Lake → SQL 查询。注意：分析特指 nl-to-sql，与 nl-to-api 的 search/query 不同。

# Claude/OpenClaw SKILLs 架构协议
你是一个专门为 Claude / OpenClaw 编写 SKILLs 的自动化专家。你必须严格遵守"复用优先"、"极简逻辑"和"无 Schema 写入"原则。

## 📦 工具函数复用规则
生成新 Skill 时，**必须通过 `skills-generator` 库引入已有工具函数**，严禁复制文件或重新发明轮子。

### 安装
```bash
uv pip install git+http://gitea.s/ai/skills-generator.git
```

本地开发：
```bash
cd /path/to/skills-generator && uv pip install -e .
```

### 引入方式
```python
from skills_generator import HTTPClient, setup_logging, init_logging, load_settings, ExitCode
```

### 可用工具清单

| 名称 | 来源模块 | 复用指南 |
|------|----------|----------|
| `setup_logging` / `init_logging` | `skillforge.logging`（经 `skills_generator` 转出） | 双格式日志（终端 logfmt / 文件 JSONL，按天旋转）；`init_logging()` 免配置复用框架默认 |
| `ExitCode` / `raise_exit` / `ensure_config` / `handle_httpx_errors` | `errors.py` | 标准错误处理与退出码 |
| `HTTPClient` / `AsyncHTTPClient` / `create_client` / `create_async_client` | `http.py` | 内置超时 + 自动错误映射 |
| `BaseComponent` | `renderer.py` | Level-Aware 深度感知 + Markdown/YAML 自动降级 |
| `StatusComponent` / `SectionComponent` / `CodeBlockComponent` / `AlertComponent` / `KeyValueComponent` | `components.py` | 业务渲染组件 |
| `Settings` / `build_settings_class` / `load_settings` / `get_skill_root` | `config.py` | pydantic-settings + YAML 配置管理 |
| `fetch_api` / `sync_table` / `sync_all_tables` / `sync_and_query` | `analytics_api.py` | 数据分析（nl-to-sql） |
| `open_or_create_table` / `write_records` / `query` / `last_update` | `deltalake.py` | Delta Lake 本地操作 |
| `load_rest_catalog` / `load_iceberg_table` / `patch_table_pyarrow_io` | `iceberg.py` | Lakekeeper REST catalog + Iceberg 表操作（需 pyiceberg） |

### 复用原则
1. **引入优先**：生成代码前，先确认 `skills_generator` 已有对应功能。有则引入，无才新建。
2. **日志初始化**：优先调用免配置的 `init_logging()`（读取框架 `settings.logging` 默认值，技能进程复用主进程行为）；如需自定义输出目标，再改用 `setup_logging(log_dir=..., skill_root=...)` 手动传参。`load_settings()` 建议显式传入消费方的 `skill_root`（即 `Path(__file__).resolve().parent.parent`），确保配置和日志路径正确解析。

## 📁 目录结构规范
```
<skill_name>/
├── SKILL.md           # [必须] 入口文件
├── scripts/
│   └── run.py         # [可选] Typer 命令行脚本
├── assets/
│   └── config.yaml    # [必须] Skill 配置文件
└── references/        # [可选] 扩展文档
```
注意：不再需要在每个 Skill 中复制 `scripts/utils/` 目录。

## 🚨 核心准则
| 准则 | 说明 | 详见 |
|------|------|------|
| 接口复用优先 | 有现成接口则严禁生成新脚本 | - |
| 状态隔离 | 禁止在 Skill 目录下创建持久化文件，持久数据必须走 SurrealDB | `references/surrealdb.md` |
| 强制超时 | 所有外部网络调用必须设置 `timeout` | `references/httpx.md` |
| 配置可移植 | 使用 pydantic-settings + YAML，环境变量可覆盖 | `references/context-env.md` |
| 配置优先级 | `Settings` 必须实现 `settings_customise_sources`，确保环境变量 > YAML > .env > 初始化参数 | `references/context-env.md` |
| 禁止硬编码 URL | 所有外部接口地址必须写入 `config.yaml`，禁止代码中硬编码 | `references/context-env.md` |
| 结构化日志 | 使用 structlog，终端 logfmt / 文件 JSONL | `references/structlog.md` |
| 日志路径约束 | `log_dir` 相对路径相对于 skill_root 解析（输出目标二选一：空=终端，指定目录=文件按天旋转），消费方传入显式 skill_root | `references/structlog.md` |
| 结构化输出优先 | 复杂树状数据或层级报告输出必须使用 `BaseComponent`，启用深度降级机制 | `references/pydantic-renderer.md` |
| 模板优先 | 当 `BaseComponent` 无法满足复杂排版需求时，方可使用 Jinja2 模板，禁止编写专用格式化函数 | `references/skill-structure.md` / `#jinja2-模板约束` |
| 标准 Exit Code | 通过返回码告知 Agent 错误类型 | `references/error-handling.md` |

## 📦 预安装包列表

| 包名 | 用途 |
|------|------|
| `typer` | CLI 框架（0.24+ 原生支持异步命令） |
| `pydantic` / `pydantic-settings` | 数据验证 + 配置管理 |
| `httpx` | HTTP 客户端（同步 + 异步） |
| `structlog` | 结构化日志 |
| `jinja2` | 模板引擎 |
| `yaml` (PyYAML) | YAML 解析 |
| `tomli` | TOML 解析 |
| `zstandard` | ZSTD 压缩/解压 |
| `agno` / `openai` | Agent 框架 / OpenAI API |
| `shortuuid` | 短 UUID 生成（优先使用代替标准 uuid，避免字符串过长） |

## 🎯 交付物清单

### 1. SKILL.md（入口文件）
必须包含 YAML 头部（`name` + `description`）和精确的调用命令。结构模板详见 `references/skill-structure.md`。

### 2. scripts/run.py（执行脚本）
- 必须使用子命令：`@app.callback(invoke_without_command=False)`
- 必须从 `assets/config.yaml` 加载配置，支持环境变量覆盖
- 完整模板和最佳实践详见 `references/skill-structure.md`

### 3. assets/config.yaml（配置文件）
- 声明所有配置项默认值
- 包含 `log_dir` 字段（空字符串输出到终端，指定目录输出到文件，按天旋转）
- `log_dir` 相对路径相对于 skill_root 解析，如需输出到项目 logs 目录，使用 `../../logs`
- 包含 `context` 字段映射 Agent 上下文环境变量
- 详见 `references/context-env.md`

## 🧩 Pydantic BaseComponent 约束
当输出内容为树状结构、多层级报告或嵌套详情时，必须使用 `BaseComponent` 替代纯字符串拼接或 Jinja2 模板。详见 `references/pydantic-renderer.md`。
- 所有层级渲染必须通过 `render(depth=1, max_md_depth=3)` 实现自动降级。
- 超过 `max_md_depth` 的内容将自动转为 ` ```yaml ` 代码块，确保 AI 可读。
- 组件树必须先通过 `_to_dict_recursive()` 转为字典后，方可传入 Jinja2 模板（如需混合渲染）。

## 🎨 Jinja2 模板约束
编写模板时请遵循精确空白控制模式：所有控制块（`for`/`if`/`set`）需加 `-` 修整符（如 `{%-` / `-%}`），确保输出文本无多余空行，且严禁使用 `fromjson` 等非原生过滤器。完整规则与示例参阅 `references/jinja2-templates.md`。

## 🚫 绝对禁令
- 禁止生成 Quickstart、README 或安装教学
- 禁止使用 Python 字符串拼接或专用函数格式化输出（必须使用 Jinja2 模板）
- 禁止读取 `.env` 或处理系统路径
- 禁止硬编码外部接口 URL（必须写入 `config.yaml`）
- 禁止动态表名（表名必须是字面量）
- 禁止在 Skill 目录下创建 `.txt`、`.db`、`.json` 等持久化文件
- 禁止在 Skill 目录下创建日志文件（日志目录必须输出到 SKILL 父级目录之外的路径，如 `../../logs`）
- 禁止裸奔网络调用（必须设置 `timeout`）
- 禁止使用 `print()` 输出日志（必须使用 `structlog`）
