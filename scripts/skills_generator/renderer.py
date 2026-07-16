"""
Pydantic 渲染基类模块 (BaseComponent)

支持层级感知 (Level-Aware) 的自动递归渲染。
当嵌套深度超过 Markdown 标题限制时，自动降级为 YAML 代码块，确保 AI 可读性。
"""
from pydantic import BaseModel
from typing import List, Union, Any
import yaml


class BaseComponent(BaseModel):
    """
    支持层级感知的组件基类。

    特性:
    - 自动计算层级：子组件无需手动传 level，递归时自动递增。
    - 深度降级（Degradation）：当嵌套过深（超过 3 层）导致 Markdown 标题失效时，
      自动将内容转为 YAML 代码块。
    """
    title: str
    content: Union[str, List["BaseComponent"]] = ""

    def render(self, depth: int = 1, max_md_depth: int = 3) -> str:
        """
        渲染组件树为 Markdown 或 YAML。

        Args:
            depth: 当前递归深度（初始调用默认为 1）
            max_md_depth: 最大 Markdown 标题深度，超过此值将触发降级转为 YAML 输出
        """
        # 1. 深度降级：如果深度超过阈值，为了防止 AI 迷失，将剩余部分转为 YAML
        if depth > max_md_depth:
            return self._render_as_yaml(depth)

        # 2. 正常渲染 Markdown 标题
        prefix = "#" * depth
        result = [f"{prefix} {self.title}\n"]

        # 3. 递归处理内容
        if isinstance(self.content, str):
            result.append(self.content)
        else:
            # 递归调用子组件，深度自增
            sub_renders = [
                child.render(depth=depth + 1, max_md_depth=max_md_depth)
                for child in self.content
            ]
            result.extend(sub_renders)

        return "\n".join(result)

    def _render_as_yaml(self, depth: int) -> str:
        """深度降级处理：转为缩进整齐的 YAML 代码块"""
        data_structure = {self.title: self.content}
        # 转换为字典以递归处理所有嵌套组件
        clean_data = self._to_dict_recursive(data_structure)
        yaml_str = yaml.dump(clean_data, allow_unicode=True, sort_keys=False)
        # 包装在代码块中，方便 AI 提取
        return f"```yaml\n{yaml_str}```"

    def _to_dict_recursive(self, obj: Any) -> Any:
        """将组件树平滑转为普通字典，用于 YAML 输出或 Jinja2 渲染"""
        if isinstance(obj, BaseComponent):
            return {obj.title: self._to_dict_recursive(obj.content)}
        if isinstance(obj, list):
            return [self._to_dict_recursive(i) for i in obj]
        return obj


# 为了支持循环引用（children 引用类自身），必须更新引用
BaseComponent.model_rebuild()
