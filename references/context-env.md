---
name: context-env
description: Agent 上下文环境变量映射规范，说明技能如何正确读取上下文信息
---

# Context 环境变量映射规范

本文档说明技能如何正确读取 Agent 传递的上下文信息（如用户 ID、认证 Token 等）。

## ⚙️ 配置加载实现

**✅ 推荐加载配置文件生成一个单独的 `config.py` 模块，放置在与 `run.py` 同级目录。这样可以实现配置与业务逻辑解耦，支持配置文件的独立修改。**

在新建 Skill 时，请创建独立的 `config.py` 文件，并按以下标准模板实现配置加载。该模板会自动定位 `assets/config.yaml` 并内置正确的环境变量优先级：

```python
import os
from pydantic import BaseModel
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
    PydanticBaseSettingsSource,
    YamlConfigSettingsSource,
)

# 1. 嵌套模型（字段名与 config.yaml 中的键一一对应）
class ContextConfig(BaseModel):
    session_id: str = ""    # 对应 config.yaml 中的 session_id
    user_id: str = ""       # 对应 config.yaml 中的 user_id
    token: str = ""         # 对应 config.yaml 中的 token

# 2. 主配置类
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SKILL__",         # 环境变量前缀（必须使用 SKILL目录名__ 作为默认前缀）
        env_nested_delimiter="__",    # 嵌套分隔符
        yaml_file="config.yaml"       # 自动向上查找至 assets/ 目录下的 config.yaml
    )

    context: ContextConfig
    debug: bool = False  # 🔍 调试开关：开启后会在回调函数中打印环境变量检查日志

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # 优先级：环境变量覆盖 YAML，YAML 覆盖代码默认值
        return (env_settings, YamlConfigSettingsSource(settings_cls), init_settings)

# 3. 实例化并读取
cfg = Settings()

## 🔍 调试开关使用说明

开启 `debug` 后，技能会在启动时打印嵌套环境变量（如 `ORDERS__API__URL`），便于排查配置加载问题。完整代码示例见 `skill-structure.md` 中的 `@app.callback` 部分。

**开启方式**：
```bash
# 方式 1：环境变量
export ORDERS__DEBUG=true

# 方式 2：修改 config.yaml
# debug: true
```



## 核心原则

**严禁在代码中硬编码环境变量名**。必须在 `assets/config.yaml` 中定义映射关系，并通过 `config.py` 集中管理配置读取逻辑，实现配置与代码解耦。

**⚠️ 环境变量前缀约束**：`env_prefix` 必须使用当前 Skill 的目录名加上 `__` 作为前缀（例如 `orders` 目录对应 `ORDERS__`），避免不同 Skill 之间的环境变量冲突。

## 可用环境变量参考

SKILL 可直接使用的上下文环境变量如下：

| 环境变量名 | config.yaml 映射示例 | 说明 |
|-----------|---------------------|------|
| `CONTEXT_SESSION_ID` | `session_id: "CONTEXT_SESSION_ID"` | 会话 ID |
| `CONTEXT_USER_ID` | `user_id: "CONTEXT_USER_ID"` | 用户 ID |
| `CONTEXT_METADATA_ACCESS_TOKEN` | `token: "CONTEXT_METADATA_ACCESS_TOKEN"` | 认证 Token |

## 配置映射与读取

### 1. 在 `assets/config.yaml` 中定义映射

```yaml
# assets/config.yaml
# 将框架环境变量映射为逻辑名称，供 ContextConfig 使用
context:
  session_id: "CONTEXT_SESSION_ID"
  user_id: "CONTEXT_USER_ID"
  token: "CONTEXT_METADATA_ACCESS_TOKEN"
```

### 2. 在 `config.py` 中集中读取

将上述 `Settings` 类和实例化代码统一放在 `config.py` 中。在 `run.py` 或其他业务脚本中，直接导入配置实例：

```python
# run.py 或其他脚本
from config import cfg

# 使用映射后的环境变量名读取，避免硬编码
token = os.environ.get(cfg.context.token)
```

`config.py` 中应包含完整的 `Settings` 定义和 `cfg = Settings()` 实例化代码，作为全局配置入口。

## 为什么需要映射层？

1. **解耦**：框架底层的环境变量名可能变化（如 Cookie 名称变更），技能代码无需修改。
2. **可移植**：技能可以在不同环境中运行，只需修改 `config.yaml` 即可适配。
3. **可测试**：测试时可以通过修改 `config.yaml` 模拟不同的上下文环境。

## 认证 Token 获取示例

用户身份与 Token 已由 skillforge 服务端解析并注入环境变量，skill 直接读取即可：

```python
import os

# 从统一 Token 环境变量读取（映射自 config.yaml 的 context.token）
token = os.environ.get(cfg.context.token)
if not token:
    raise ValueError("未找到认证 Token")
```

## 配置加载路径说明

`config.py` 中的 `Settings` 类通过 `pydantic-settings` 的内置机制自动定位并加载配置：
- `yaml_file="config.yaml"` 配合 `SettingsConfigDict`，框架会自动向上查找至 Skill 根目录下的 `assets/` 文件夹。
- 优先级通过 `settings_customise_sources` 明确指定：`env_settings`（环境变量） > `YamlConfigSettingsSource`（YAML 文件） > `init_settings`（代码初始化）。
- 独立的 `config.py` 模块使得配置文件可以独立于业务代码进行修改，提高了 Skill 的可维护性和灵活性。

## 🔍 调试入口

`config.py` 包含 `__main__` 入口，可直接运行以验证配置加载是否正确：

```bash
# 在 scripts/ 目录下运行
python config.py
```

运行后会打印完整的配置结构体，方便检查 YAML 加载和环境变量覆盖结果：

```python
# config.py 尾部
if __name__ == "__main__":
    """允许直接运行 config.py 以调试配置加载情况"""
    print(cfg)
```

## 注意事项

- 如果某个 context 字段未设置，对应的环境变量不会存在，读取时应进行空值检查。
- **环境变量优先级高于 YAML 默认值**：通过 `settings_customise_sources` 方法返回的优先级元组确保环境变量覆盖 YAML 值。
- **⚠️ 嵌套环境变量仅支持 BaseSettings 模型**：所有需要环境变量覆盖的配置项（如 API 地址）在定义 Settings 类时必须使用嵌套的 `BaseSettings` 子类，不能使用 `dict` 类型。
