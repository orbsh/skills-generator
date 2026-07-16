"""
配置加载基础模块 (Config)

基于 pydantic-settings 提供统一的 Settings 配置加载模式。
手动加载 assets/config.yaml 确保配置正确读取（绕过 pydantic-settings 在某些环境中的 YAML 加载问题）。
严禁在代码中硬编码环境变量名，所有映射应在 config.yaml 中定义。
"""
from pathlib import Path
from typing import Any, Optional, Type, TypeVar
import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

T = TypeVar("T", bound=BaseSettings)


def get_skill_root(script_path: Path | str | None = None) -> Path:
    """
    获取 Skill 根目录（包含 SKILL.md 的目录）。

    Args:
        script_path: 当前脚本路径。默认自动检测 (从 utils/config.py 向上推三层至技能根目录)。
                     作为库使用时，消费方应显式传入自身脚本路径。

    Returns:
        Skill 根目录的绝对路径。
    """
    if script_path is None:
        script_path = Path(__file__).resolve().parent.parent.parent
    return Path(script_path).resolve()


def _load_yaml_config(config_path: Path) -> dict:
    """
    手动加载 YAML 配置文件。

    Args:
        config_path: config.yaml 路径。

    Returns:
        YAML 内容字典，文件不存在时返回空字典。
    """
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def build_settings_class(
    name: str = "Settings",
    config_path: Optional[Path] = None,
    extra_context_fields: Optional[dict[str, str]] = None,
    base_class: Type[BaseSettings] = BaseSettings,
    skill_root: Optional[Path] = None,
) -> Type[BaseSettings]:
    """
    动态构建 Settings 类，配合 load_settings() 使用。

    使用此函数可避免在每个 run.py 中重复编写冗长的 Settings 定义。

    Args:
        name: Settings 类名称。
        config_path: config.yaml 路径。默认自动定位 assets/config.yaml。
        extra_context_fields: 额外的 context 字段映射 (字段名 -> 环境变量名)。
        base_class: 基础 Settings 类，用于继承已有字段。
        skill_root: Skill 根目录。未提供时自动检测。

    Returns:
        配置好的 Settings 类。
    """
    if config_path is None:
        _root = skill_root or get_skill_root()
        config_path = _root / "assets" / "config.yaml"

    # 构建 context 字段注解
    context_annotations: dict[str, Any] = {}
    if extra_context_fields:
        for field_name, env_name in extra_context_fields.items():
            context_annotations[field_name] = (str, Field(default=env_name))

    # 动态创建 ContextSettings 子类
    ContextSettings = type(
        "ContextSettings",
        (BaseSettings,),
        {
            "__annotations__": context_annotations,
            "model_config": SettingsConfigDict(extra="ignore"),
        },
    )

    # 构建主 Settings 类（仅定义字段结构，YAML 加载由 load_settings() 完成）
    class DynamicSettings(base_class):
        model_config = SettingsConfigDict(
            env_nested_delimiter="__",
            extra="ignore",
        )

        context: ContextSettings = Field(default_factory=ContextSettings)  # type: ignore

    DynamicSettings.__name__ = name
    return DynamicSettings


# ==================== 默认 Settings 实现 ====================
# 大多数 Skill 可直接使用此类，如有特殊需求可调用 build_settings_class 自定义。

class DefaultContextSettings(BaseSettings):
    """默认上下文环境变量映射"""
    model_config = SettingsConfigDict(extra="ignore")
    user_id: str = "CONTEXT_USER_ID"
    token: str = "CONTEXT_METADATA_ACCESS_TOKEN"


class Settings(BaseSettings):
    """
    标准应用 Settings。

    配合 load_settings() 使用，YAML 加载由 load_settings() 手动完成。
    外部 API 配置必须使用嵌套 BaseSettings 模型。
    """
    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        extra="ignore",
    )
    context: DefaultContextSettings = Field(default_factory=DefaultContextSettings)


def load_settings(
    custom_class: Optional[Type[BaseSettings]] = None,
    skill_root: Optional[Path] = None,
) -> BaseSettings:
    """
    加载配置并返回 Settings 实例。

    手动加载 YAML 确保配置正确读取，绕过 pydantic-settings 在某些环境中的加载问题。
    配置优先级：环境变量 > YAML 默认值。

    Args:
        custom_class: 自定义 Settings 类。未提供时使用默认 Settings。
        skill_root: Skill 根目录。未提供时自动检测。作为库使用时建议显式传入。

    Returns:
        配置好的 Settings 实例。
    """
    cls = custom_class or Settings

    # 手动加载 YAML 配置
    _root = skill_root or get_skill_root()
    _config_path = _root / "assets" / "config.yaml"
    _yaml_data = _load_yaml_config(_config_path)

    # 将 YAML 配置传递给 Settings 构造函数
    # pydantic-settings 默认环境变量优先级高于 init 参数，因此环境变量可覆盖 YAML 值
    return cls(**_yaml_data)
