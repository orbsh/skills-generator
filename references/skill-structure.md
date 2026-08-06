---
name: skill-structure
description: SKILL.md 结构规范与多命令模式指南
---

# SKILL.md 结构与脚本编写规范

本文档详细说明技能入口文件（SKILL.md）的标准结构、多命令模式以及脚本编写最佳实践。

## SKILL.md 标准结构模板

每个技能的 `SKILL.md` 必须遵循以下结构，确保 LLM 能准确识别调用时机和参数：

```markdown
---
name: [skill_unique_name]
description: [极其简洁的功能描述，用于 LLM 识别调用时机]
---

# 触发场景
当用户想进行 [具体业务领域] 相关操作时调用。包括：
- [场景 1：具体描述]
- [场景 2：具体描述]
- [场景 3：具体描述]

# 可用命令

## 命令 1 (cmd1)
```bash
python3 scripts/run.py cmd1 --arg1 "值" [--arg2 值]
```

### 使用示例
```bash
# 示例 1：描述场景
python3 scripts/run.py cmd1 --arg1 "xxx"

# 示例 2：描述场景
python3 scripts/run.py cmd1 --arg1 "xxx" --arg2 "yyy"
```

## 占位命令（待实现）
以下命令框架已预留，具体实现待后续补充：

### 命令 2 (cmd2)
```bash
python3 scripts/run.py cmd2 --arg1 "值"
```

### 命令 3 (cmd3)
```bash
python3 scripts/run.py cmd3 --arg1 "值" [--arg2 值]
```

---

# cmd1 命令参数定义
- `arg1`: [描述，是否必填，格式要求，如"订单号，字符串类型"]
- `arg2`: [描述，如"订单状态筛选，枚举值：0待确认 1待付款 2已取消"]
  - `0`: 待确认
  - `1`: 待付款
  - `2`: 已取消

# 认证说明
[说明技能如何获取认证信息]
- 自动从 Agent 上下文获取认证 Token
- 无需手动传递 `--token` 参数
- 通过 `assets/config.yaml` 中的 context 配置映射环境变量

# 注意事项
- [边界条件 1：如"查询特定订单号时返回单个详情，按条件查询时返回分页列表"]
- [边界条件 2：如"时间范围查询时，start_time 和 end_time 应同时提供"]
- [边界条件 3：如"需要认证后才能访问数据"]
```

## 结构要点说明

### 1. YAML 头部
- `name`: 技能唯一标识，使用小写字母和连字符（如 `order-management`）
- `description`: 极其简洁的功能描述，一句话说明技能用途，供 LLM 识别调用时机

### 2. 触发场景
- 列出所有会触发此技能的用户意图
- 使用具体描述，避免模糊表述
- 包含查询、创建、修改、删除等多种操作场景

### 3. 可用命令
- **已实现命令**：提供完整的调用命令和使用示例
- **占位命令**：为未来功能预留框架，标记"待实现"，返回友好提示
- 命令命名使用小写字母和连字符，与 Typer 子命令一致

### 4. 参数定义
- 列出每个参数的名称、描述、是否必填、格式要求
- 枚举参数必须列出所有可能值及含义
- 时间参数必须说明格式（如 `YYYY-MM-DD HH:mm:ss`）

### 5. 认证说明
- 说明技能如何获取认证信息（自动从上下文获取 vs 手动传递）
- 如需手动传递，说明参数名称和获取方式

### 6. 注意事项
- 列出边界条件和特殊处理逻辑
- 说明返回数据格式（单个详情 vs 分页列表）
- 说明必填参数的组合要求

## 多命令与占位模式

### 设计原则
一个技能可包含多个相关的业务操作，使用 Typer 子命令实现。未来操作可先定义占位子命令，避免后续重构。

### 实现示例

```python
import typer
from typing import Optional

# 导入通用工具模块
from scripts.utils import (
    setup_logging,
    get_skill_root,
    # Settings 类直接定义在 run.py 中（详见 references/context-env.md）
    ExitCode,
    raise_exit,
    handle_httpx_errors,
    HTTPClient,
    logger,
)

# ==================== 初始化 ====================

# 1. 加载配置 (详见 references/context-env.md)
# 定义 Settings 类后实例化
cfg = Settings()

# 2. 初始化日志 (详见 references/structlog.md)
skill_root = get_skill_root()
setup_logging(log_dir=cfg.log_dir, skill_root=skill_root)

# 3. 初始化 Typer App
app = typer.Typer(
    help="订单管理技能，支持查询、跟踪、取消等多种订单操作",
    rich_markup_mode=None,
    add_completion=False,
    no_args_is_help=True,
)

@app.callback(invoke_without_command=False)
def main(ctx: typer.Context):
    """CLI - 必须使用子命令调用"""
    setup_logging(log_dir=cfg.log_dir, skill_root=skill_root)
    session_id = os.environ.get(cfg.context.session_id) or shortuuid.uuid()
    user_id = os.environ.get(cfg.context.user_id) or f"anon-{shortuuid.uuid()[:8]}"

    # 🔍 调试：打印包含双下划线的环境变量，排查嵌套变量加载问题
    if cfg.debug:
        nested_envs = {k: v for k, v in os.environ.items() if "__" in k}
        logger.info("env-check", nested_env=str(nested_envs), loaded_api_url=cfg.api.url)

    logger.info("app-start", auth_method=cfg.auth_method, session_id=session_id, user_id=user_id)

# ==================== 已实现命令 ====================

@app.command()
def fetch(
    order_id: Optional[str] = typer.Option(None, "--order-id", help="订单号"),
    status: Optional[int] = typer.Option(None, "--status", help="订单状态"),
):
    """查询订单列表或详情"""
    logger.info("ord-query", id=order_id, status=status)
    try:
        # 使用 HTTPClient 自动处理超时与错误映射 (详见 references/httpx.md)
        with HTTPClient(timeout=10.0) as client:
            resp = client.get(f"{cfg.api.url}/orders", context="查询订单")
            logger.info("ord-query-success", status=resp.status_code)
            typer.echo(resp.json())
    except Exception as e:
        # 自动映射 httpx 异常到 Exit Code 2
        handle_httpx_errors(e, cfg.api.url, "查询订单失败")

# ==================== 占位命令（待实现） ====================

@app.command()
def track(
    order_id: str = typer.Option(..., "--order-id", help="订单号"),
):
    """跟踪订单物流（待实现）"""
    logger.info("ord-track", order_id=order_id)
    typer.secho("该功能暂未实现，敬请期待", fg="yellow")

@app.command()
def cancel(
    order_id: str = typer.Option(..., "--order-id", help="订单号"),
    reason: Optional[str] = typer.Option(None, "--reason", help="取消原因"),
):
    """取消订单（待实现）"""
    logger.info("ord-cancel", order_id=order_id, reason=reason)
    typer.secho("该功能暂未实现，敬请期待", fg="yellow")

@app.command()
def confirm(
    order_id: str = typer.Option(..., "--order-id", help="订单号"),
):
    """确认收货（待实现）"""
    logger.info("ord-confirm", order_id=order_id)
    typer.secho("该功能暂未实现，敬请期待", fg="yellow")

if __name__ == "__main__":
    app()
```

### 占位命令规范
1. 必须使用 `@app.command()` 装饰器定义
2. 必须包含所有必要参数（即使暂未实现）
3. 使用 `typer.secho(..., fg="yellow")` 输出友好提示
4. 在 SKILL.md 中标记为"占位命令（待实现）"

## 脚本编写最佳实践

### 1. 配置管理
- **内联 `Settings` 类**：直接在 `run.py` 中定义 `Settings(BaseSettings)`，配置 `yaml_file` 与 `settings_customise_sources`，确保环境变量 > YAML > 代码默认值。详见 `references/context-env.md`。
- 外部 API 配置必须使用嵌套 `BaseSettings` 模型。

### 2. 日志与错误处理
- **使用 `setup_logging()`**：初始化双格式日志（终端 logfmt / 文件 JSONL）。详见 `references/structlog.md`。
- **事件名使用英文缩写**：如 `ord-query`, `auth-start`, `err-conn`，禁止使用中文。
- **使用 `raise_exit()` / `handle_httpx_errors()`**：统一结构化错误输出与 Exit Code 映射。详见 `references/error-handling.md`。

### 3. HTTP 请求
- **使用 `HTTPClient` / `create_client()`**：强制超时、自动 `raise_for_status()`、异常自动映射。详见 `references/httpx.md`。

### 4. 数据处理与模板
- 实现 `preprocess_*` 函数转换 API 响应为标准化格式。
- **格式化输出必须使用 Jinja2 模板**：模板文件放在 `assets/templates/` 目录，禁止编写专用格式化函数。详见 `references/jinja2-templates.md`。

### 5. 代码结构
```
<skill_name>/
├── scripts/
│   ├── run.py
│   │   ├── imports (typer, scripts.utils.*)
│   │   ├── cfg = Settings()
│   │   ├── setup_logging(log_dir=cfg.log_dir, skill_root=skill_root)
│   │   ├── app = typer.Typer(...)
│   │   ├── @app.command() implementations (使用 HTTPClient / raise_exit)
│   │   └── if __name__ == "__main__": app()
│   └── utils/
│       ├── renderer.py       # [必选] BaseComponent 渲染基类
│       ├── components.py     # [可选] 业务组件封装
│       ├── logging.py        # [必选] structlog 初始化
│       ├── errors.py         # [必选] ExitCode 与错误处理
│       ├── http.py           # [推荐] HTTPClient 封装
└── assets/
    ├── config.yaml
    └── templates/
        └── *.j2          # Jinja2 模板文件
```
