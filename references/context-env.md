---
name: context-env
description: Agent 上下文环境变量映射规范，说明技能如何正确读取上下文信息
---

# Context 环境变量映射规范

本文档说明技能如何正确读取 Agent 传递的上下文信息（如用户 ID、认证 Token 等）。

## 📦 组件复用指南

**⚠️ 禁止在脚本中重复编写 `Settings` 类加载逻辑与 `settings_customise_sources` 方法。**

配置加载框架已作为通用工具内置。在新建 Skill 时，请按以下步骤复用：

1. **拷贝文件**：将 `scripts/utils/config.py` 完整拷贝至目标 Skill 的 `scripts/utils/` 目录下。
2. **导入使用**：在 `run.py` 中通过 `from scripts.utils.config import load_settings` 引入。
3. **加载配置**：使用 `cfg = load_settings()` 自动获取配置并应用正确的环境变量优先级。

如需查看完整的 Settings 定义与优先级实现，请参阅项目内的 `scripts/utils/config.py` 文件。

## 核心原则

**严禁在代码中硬编码环境变量名**。必须在 `assets/config.yaml` 中定义映射关系，实现配置与代码解耦。

## 环境变量展平规则

Agent 框架将上下文对象展平为环境变量，命名规则为 `CONTEXT_{字段路径大写}`：

| 原始字段路径 | 展平后的环境变量名 |
|-------------|-------------------|
| `user_id` | `CONTEXT_USER_ID` |
| `session_id` | `CONTEXT_SESSION_ID` |
| `metadata.access_token` | `CONTEXT_METADATA_ACCESS_TOKEN` |
| `metadata.cookies.HrmApiCookie` | `CONTEXT_METADATA_COOKIES_HRMAPICOOKIE` |

## 配置加载方法

### 1. 在 `assets/config.yaml` 中定义映射

```yaml
# assets/config.yaml
context:
  user_id: "CONTEXT_USER_ID"
  token: "CONTEXT_METADATA_COOKIES_HRMAPICOOKIE"
  header_token: "CONTEXT_METADATA_ACCESS_TOKEN"
```

### 2. 在 Python 中读取

利用 `load_settings()` 加载后，通过 `cfg.context` 访问映射后的环境变量名，再通过 `os.environ.get()` 读取值：

```python
import os
from scripts.utils.config import load_settings

cfg = load_settings()

# 使用映射后的环境变量名读取，避免硬编码
token = os.environ.get(cfg.context.header_token) or os.environ.get(cfg.context.token)
```

## 为什么需要映射层？

1. **解耦**：框架底层的环境变量名可能变化（如 Cookie 名称变更），技能代码无需修改。
2. **可移植**：技能可以在不同环境中运行，只需修改 `config.yaml` 即可适配。
3. **可测试**：测试时可以通过修改 `config.yaml` 模拟不同的上下文环境。

## 认证 Token 获取示例

通过工具模块封装，获取 Token 变得极简：

```python
from scripts.utils.auth import get_access_token_from_env

# 自动尝试 Header 和 Cookie 映射
token = get_access_token_from_env(cfg.context)
if not token:
    raise ValueError("未找到认证 Token")
```

## 配置加载路径说明

`load_settings()` 内部通过 `Path(__file__).resolve().parent.parent / "assets" / "config.yaml"` 自动定位文件：
- 脚本 (`scripts/run.py`) 向上推两层即为 Skill 根目录。
- 此方式确保无论从何处执行脚本，都能正确找到配置文件。

## 注意事项

- `metadata` 下的嵌套字段会保留完整路径，如 `metadata.cookies.HrmApiCookie` → `CONTEXT_METADATA_COOKIES_HRMAPICOOKIE`。
- 所有环境变量名在展平时都会转换为**大写**。
- 如果某个 context 字段未设置，对应的环境变量不会存在，读取时应进行空值检查。
- **环境变量优先级高于 YAML 默认值**：`load_settings` 内部已实现 `env_settings` > `YamlConfigSettingsSource` 的优先级。
- **⚠️ 嵌套环境变量仅支持 BaseSettings 模型**：所有需要环境变量覆盖的配置项（如 API 地址）在定义 Settings 类时必须使用嵌套的 `BaseSettings` 子类，不能使用 `dict` 类型。