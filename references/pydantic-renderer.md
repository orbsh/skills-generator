---
name: pydantic-renderer
description: 支持 Level-Aware 深度感知与自动降级的 Pydantic Markdown/YAML 渲染基类
---

# Pydantic 渲染基类 (BaseComponent)

本文档定义在 Skill 脚本中使用 `BaseComponent` 实现复杂数据结构输出的最佳实践。该基类专为 AI 可读性设计，采用 **"Markdown 骨架 + YAML 细节"** 的混合输出模式。

## 核心特性

| 特性 | 说明 |
|------|------|
| **层级自动感知** | 递归渲染时自动递增 `depth`，子组件无需手动传值 |
| **深度降级机制** | 嵌套超过 `max_md_depth` (默认 3) 时，自动转为 YAML 代码块输出 |
| **AI 友好输出** | 高层级用 Markdown 标题，底层级用 YAML 隔离，最大化信息熵 |
| **无缝集成** | 原生 Pydantic `BaseModel`，支持序列化、校验与循环引用 |

## 📦 组件复用指南

**⚠️ 禁止在脚本中重复编写基类代码。**

该基类实现已作为通用工具内置于本 Skill 架构中。在新建 Skill 时，请按以下步骤复用：

1. **拷贝文件**：将 `scripts/utils/renderer.py` 完整拷贝至目标 Skill 的 `scripts/utils/` 目录下。
2. **导入使用**：在脚本中通过 `from scripts.utils.renderer import BaseComponent` 引入。

如需查看完整源码实现，请参阅项目内的 `scripts/utils/renderer.py` 文件。

## 🚀 使用示例

构建简单的树状输出：

```python
from scripts.utils.renderer import BaseComponent

report = BaseComponent(
    title="项目周报",
    content=[
        BaseComponent(title="任务 A", content="已完成 80%"),
        # 嵌套深度超过 max_md_depth (默认 3) 时，子节点将自动转为 YAML 块
        BaseComponent(title="详情", content=[BaseComponent(title="深层数据", content="...")])
    ]
)

print(report.render(max_md_depth=3))
```

### 输出效果示意

```markdown
# 项目周报

## 任务 A
已完成 80%

## 详情
```yaml
深层数据: ...
```

## Skill 集成指南

### 1. 目录位置规范
渲染基类必须统一放置于 Skill 脚本的工具库中，以便多个命令复用：

```
<skill_name>/
├── scripts/
│   ├── run.py
│   └── utils/
│       ├── renderer.py       # [必选] 拷贝自 skills-generator 的核心渲染基类
│       └── components.py     # [可选] 基于 BaseComponent 封装的业务组件
└── assets/
    └── config.yaml
```

### 2. 参数配置建议
在 `assets/config.yaml` 中声明渲染阈值，便于运行时动态调整：
```yaml
render:
  max_md_depth: 3  # Markdown 最大标题层级，超过此深度触发降级
  yaml_fallback: true  # 启用深度降级机制
```

### 3. 与 Jinja2 模板配合
当需要复杂排版时，可先用 `BaseComponent` 结构化数据，再利用 `_to_dict_recursive()` 转为字典后交由 Jinja2 渲染：
```python
# 将组件树转为纯净字典
data = report._to_dict_recursive(report)
# 传入 Jinja2 模板
_jinja_env.get_template("report.j2").render(data=data)
```

### 4. 业务组件扩展
对于高频场景（如带状态的任务列表、代码块），建议继承 `BaseComponent` 创建子类。相关封装示例见 `scripts/utils/components.py`。

## 为什么这符合 Skill 约束？

1. **自动降级机制**：Markdown 标题一旦超过 4 级（`####`）在多数终端显示极差。脚本自动切到 YAML 模式，节省 Token 且利用 YAML 对长文本和嵌套的优良支持。
2. **组件自发现**：通过 `depth + 1` 的递归，只需定义树状数据结构，渲染逻辑会自动处理所有缩进。
3. **对 AI 高度友好**：
   - 高层级（重点）：用 Markdown 标题提示 AI 抓取主线。
   - 底层级（细节）：用 YAML 代码块隔离，防止 AI 误读列表嵌套关系。