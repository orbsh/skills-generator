"""
配置加载基础模块 (Config)

基于 pydantic-settings 提供统一的 Settings 配置加载模式。
自动定位 assets/config.yaml 并设置正确的环境变量优先级。
严禁在代码中硬编码环境变量名，所有映射应在 config.yaml 中定义。
"""
from pathlib import Path
from typing import Any, Optional, Type, TypeVar
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict, YamlConfigSettingsSource

T = TypeVar("T", bound=BaseSettings)


def get_skill_root(script_path: Path | str | None = None) -> Path:
    """
    获取 Skill 根目录（包含 SKILL.md 的目录）。

    Args:
        script_path: 当前脚本路径。默认自动检测 (从 utils/config.py 向上推三层至技能根目录)。

    Returns:
        Skill 根目录的绝对路径。
    """
    if script_path is None:
        script_path = Path(__file__).resolve().parent.parent.parent
    return Path(script_path).resolve()


def build_settings_class(
    name: str = "Settings",
    config_path: Optional[Path] = None,
    extra_context_fields: Optional[dict[str, str]] = None,
    base_class: Type[BaseSettings] = BaseSettings,
) -> Type[BaseSettings]:
    """
    动态构建 Settings 类，自动配置 YAML 加载与环境变量优先级。

    使用此函数可避免在每个 run.py 中重复编写冗长的 Settings 定义。

    Args:
        name: Settings 类名称。
        config_path: config.yaml 路径。默认自动定位 assets/config.yaml。
        extra_context_fields: 额外的 context 字段映射 (字段名 -> 环境变量名)。
        base_class: 基础 Settings 类，用于继承已有字段。

    Returns:
        配置好的 Settings 类。
    """
    if config_path is None:
        config_path = get_skill_root() / "assets" / "config.yaml"

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

    # 构建主 Settings 类
    class DynamicSettings(base_class):
        model_config = SettingsConfigDict(
            yaml_file=config_path,
            yaml_file_encoding="utf-8",
            env_nested_delimiter="__",
            extra="ignore",
        )

        context: ContextSettings = Field(default_factory=ContextSettings)  # type: ignore

        @classmethod
        def settings_customise_sources(
            cls,
            settings_cls: type[BaseSettings],
            init_settings: Any,
            env_settings: Any,
            dotenv_settings: Any,
            file_secret_settings: Any,
        ) -> tuple[Any, ...]:
            """配置源优先级：环境变量 > YAML > .env > init_settings"""
            return (env_settings, YamlConfigSettingsSource(settings_cls), dotenv_settings, init_settings)

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

    自动加载 assets/config.yaml，支持环境变量覆盖。
    外部 API 配置必须使用嵌套 BaseSettings 模型。
    """
    model_config = SettingsConfigDict(
        yaml_file=get_skill_root() / "assets" / "config.yaml",
        yaml_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )
    context: DefaultContextSettings = Field(default_factory=DefaultContextSettings)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: Any,
        env_settings: Any,
        dotenv_settings: Any,
        file_secret_settings: Any,
    ) -> tuple[Any, ...]:
        return (env_settings, YamlConfigSettingsSource(settings_cls), dotenv_settings, init_settings)


def load_settings(custom_class: Optional[Type[BaseSettings]] = None) -> BaseSettings:
    """
    加载配置并返回 Settings 实例。

    Args:
        custom_class: 自定义 Settings 类。未提供时使用默认 Settings。
    """
    cls = custom_class or Settings
    return cls()
