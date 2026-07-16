"""
可复用组件模块 (Components)

提供基于 BaseComponent 的业务级组件封装，适用于各类 Skill 脚本的结构化输出场景。
包含：状态组件、分组容器、代码块、警告通知、键值对等常用模式。
"""
from typing import List, Union, Dict, Optional, Literal, Any
from pydantic import Field, field_validator
import yaml

# 导入基础组件（注意：此处为相对导入，实际使用时需确保路径正确）
# 如果与 renderer.py 在同一包下，可使用：from .renderer import BaseComponent
try:
    from .renderer import BaseComponent
except ImportError:
    # 兼容直接运行此文件的场景
    from renderer import BaseComponent


# ==================== 1. 状态感知组件 ====================

class StatusComponent(BaseComponent):
    """
    带进度/状态标识的组件。

    适用于任务列表、流程节点、检查项等需要展示执行状态的场景。
    """
    status: Literal["pending", "running", "success", "failed", "skipped"] = "pending"
    progress: float = Field(default=0.0, ge=0.0, le=100.0)
    detail: str = ""

    _status_icons = {
        "pending": "⏳",
        "running": "🔄",
        "success": "✅",
        "failed": "❌",
        "skipped": "⏭️",
    }

    def render(self, depth: int = 1, max_md_depth: int = 3) -> str:
        # 构建带状态标记的标题
        icon = self._status_icons.get(self.status, "•")
        status_tag = f"[{self.progress:.0f}%]" if self.progress > 0 else ""
        full_title = f"{self.title} {icon} {status_tag}".strip()

        # 临时替换 title 用于渲染
        original_title = self.title
        self.title = full_title

        try:
            # 调用父类渲染
            result = super().render(depth, max_md_depth)

            # 如果有 detail，在渲染结果后追加
            if self.detail and isinstance(self.content, str) and self.content == "":
                result += f"\n{self.detail}"
            elif self.detail:
                result += f"\n> {self.detail}"

            return result
        finally:
            # 恢复原始 title
            self.title = original_title


# ==================== 2. 分组容器组件 ====================

class SectionComponent(BaseComponent):
    """
    逻辑分组容器组件。

    将多个相关组件包装为一个区块，支持自定义分隔符和区块前缀。
    """
    items: List[BaseComponent] = Field(default_factory=list)
    separator: str = "\n---\n"
    show_header_line: bool = True

    def render(self, depth: int = 1, max_md_depth: int = 3) -> str:
        # 先渲染标题
        if depth > max_md_depth:
            return self._render_as_yaml(depth)

        prefix = "#" * depth
        parts = [f"{prefix} {self.title}\n"]

        if self.show_header_line:
            parts.append("---\n")

        # 递归渲染子项
        if self.items:
            rendered_items = []
            for item in self.items:
                rendered = item.render(depth=depth + 1, max_md_depth=max_md_depth)
                rendered_items.append(rendered)

            # 用分隔符连接
            if self.separator:
                parts.append(self.separator.join(rendered_items))
            else:
                parts.extend(rendered_items)

        return "\n".join(parts)


# ==================== 3. 代码块组件 ====================

class CodeBlockComponent(BaseComponent):
    """
    代码/日志/配置片段组件。

    自动识别语言类型，支持行号标记和折叠提示。
    """
    language: str = "text"
    code: str = ""
    show_lines: bool = False
    collapsible: bool = False

    def render(self, depth: int = 1, max_md_depth: int = 3) -> str:
        if depth > max_md_depth:
            return self._render_as_yaml(depth)

        prefix = "#" * depth
        parts = [f"{prefix} {self.title}\n"]

        # 处理代码内容
        code_content = self.code
        if self.show_lines:
            lines = code_content.split("\n")
            numbered_lines = []
            for i, line in enumerate(lines, 1):
                numbered_lines.append(f"{i:4d} | {line}")
            code_content = "\n".join(numbered_lines)

        # 构建代码块
        if self.collapsible:
            # Markdown 不原生支持折叠代码块，使用 HTML 细节标签
            parts.append(f"<details>\n<summary>点击查看 {self.language} 代码</summary>\n\n")
            parts.append(f"```{self.language}\n{code_content}\n```\n")
            parts.append("</details>")
        else:
            parts.append(f"```{self.language}\n{code_content}\n```")

        return "\n".join(parts)

    def _render_as_yaml(self, depth: int) -> str:
        # 代码块降级时保留语言标记作为 YAML 字段
        data = {
            self.title: {
                "language": self.language,
                "code": self.code,
                "show_lines": self.show_lines,
            }
        }
        yaml_str = yaml.dump(data, allow_unicode=True, sort_keys=False)
        return f"```yaml\n{yaml_str}```"


# ==================== 4. 警告/通知组件 ====================

class AlertComponent(BaseComponent):
    """
    警告/通知组件。

    根据级别自动渲染不同图标和样式，支持高亮关键行动项。
    """
    level: Literal["info", "warning", "error", "success"] = "info"
    action_required: bool = False
    source: str = ""

    _level_config = {
        "info": {"icon": "ℹ️", "prefix": "INFO"},
        "warning": {"icon": "⚠️", "prefix": "WARNING"},
        "error": {"icon": "🔴", "prefix": "ERROR"},
        "success": {"icon": "✅", "prefix": "SUCCESS"},
    }

    def render(self, depth: int = 1, max_md_depth: int = 3) -> str:
        if depth > max_md_depth:
            return self._render_as_yaml(depth)

        config = self._level_config.get(self.level, self._level_config["info"])
        icon = config["icon"]
        prefix_tag = config["prefix"]

        # 构建标题
        title_text = f"{self.title}"
        if self.action_required:
            title_text += f" 🔔 [{prefix_tag}] {icon} **需人工介入**"
        else:
            title_text += f" [{prefix_tag}] {icon}"

        prefix = "#" * depth
        parts = [f"{prefix} {title_text}\n"]

        # 添加来源信息
        if self.source:
            parts.append(f"> 📍 来源: `{self.source}`\n")

        # 添加内容
        if isinstance(self.content, str) and self.content:
            parts.append(self.content)
        elif isinstance(self.content, list):
            sub_renders = [
                child.render(depth=depth + 1, max_md_depth=max_md_depth)
                for child in self.content
            ]
            parts.extend(sub_renders)

        return "\n".join(parts)

    def _render_as_yaml(self, depth: int) -> str:
        data = {
            self.title: {
                "level": self.level,
                "action_required": self.action_required,
                "source": self.source,
                "content": self.content,
            }
        }
        yaml_str = yaml.dump(data, allow_unicode=True, sort_keys=False)
        return f"```yaml\n{yaml_str}```"


# ==================== 5. 键值对组件 ====================

class KeyValueComponent(BaseComponent):
    """
    键值对/配置表组件。

    统一对齐键值，支持嵌套值的缩进处理和表格化输出。
    """
    pairs: Dict[str, Any] = Field(default_factory=dict)
    align_keys: bool = True
    table_mode: bool = False

    def render(self, depth: int = 1, max_md_depth: int = 3) -> str:
        if depth > max_md_depth:
            return self._render_as_yaml(depth)

        prefix = "#" * depth
        parts = [f"{prefix} {self.title}\n"]

        if not self.pairs:
            parts.append("*无数据*")
            return "\n".join(parts)

        if self.table_mode:
            # 表格模式渲染
            parts.append("| Key | Value |")
            parts.append("|-----|-------|")
            for key, value in self.pairs.items():
                # 处理嵌套值
                if isinstance(value, dict):
                    value_str = yaml.dump(value, allow_unicode=True, default_flow_style=False).strip()
                else:
                    value_str = str(value)
                parts.append(f"| `{key}` | {value_str} |")
        else:
            # 列表模式渲染
            if self.align_keys:
                max_key_len = max(len(k) for k in self.pairs.keys()) if self.pairs else 0
                for key, value in self.pairs.items():
                    padded_key = key.ljust(max_key_len)
                    if isinstance(value, dict):
                        value_str = yaml.dump(value, allow_unicode=True, default_flow_style=False).strip()
                        parts.append(f"- `{padded_key}`: \n  ```yaml\n  {value_str}\n  ```")
                    else:
                        parts.append(f"- `{padded_key}`: {value}")
            else:
                for key, value in self.pairs.items():
                    if isinstance(value, dict):
                        value_str = yaml.dump(value, allow_unicode=True, default_flow_style=False).strip()
                        parts.append(f"- `{key}`: \n  ```yaml\n  {value_str}\n  ```")
                    else:
                        parts.append(f"- `{key}`: {value}")

        return "\n".join(parts)

    def _render_as_yaml(self, depth: int) -> str:
        data = {self.title: self.pairs}
        yaml_str = yaml.dump(data, allow_unicode=True, sort_keys=False)
        return f"```yaml\n{yaml_str}```"


# ==================== 循环引用支持 ====================

# 重建所有组件模型以支持自引用
StatusComponent.model_rebuild()
SectionComponent.model_rebuild()
CodeBlockComponent.model_rebuild()
AlertComponent.model_rebuild()
KeyValueComponent.model_rebuild()
