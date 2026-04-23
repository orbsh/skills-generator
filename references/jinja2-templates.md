---
name: jinja2-templates
description: Jinja2 模板编写约束与最佳实践
---

# Jinja2 模板约束

本文档定义在 SKILL 脚本中使用 Jinja2 模板时必须遵守的约束规则，确保输出格式整洁、兼容性强且安全。

## 1. 标签修整约束 (Tag Trimming)

**规则**：除变量插值 `{{ }}` 外，所有逻辑控制块（`if`、`for`、`set`）必须使用修整符。

**格式**：
- 左侧使用 `{%-` 去除前置空格/换行
- 右侧使用 `-%}` 去除后续换行/空格

**目的**：防止逻辑嵌套导致输出结果中出现大量空行。

**示例**：
```jinja2
{%- for item in items -%}
{{ item.name }}
{%- endfor -%}
```

**错误示例**（会输出多余空行）：
```jinja2
{% for item in items %}
{{ item.name }}
{% endfor %}
```

## 2. 过滤器兼容性约束 (Filter Compatibility)

**规则**：严禁在未配置的环境中使用非原生过滤器（如 `fromjson`）。

**操作**：
- 若需处理 JSON 字符串，应要求在 Python 环境中预先注册过滤器：
  ```python
  env.filters['fromjson'] = json.loads
  ```
- 或引导 AI 改用原生数据结构传入，避免在模板中解析 JSON。

**安全清单**：
| 过滤器类型 | 状态 | 说明 |
|------------|------|------|
| `default` | ✅ 原生 | 安全使用 |
| `upper` / `lower` | ✅ 原生 | 安全使用 |
| `trim` / `replace` | ✅ 原生 | 安全使用 |
| `fromjson` | ⚠️ 需注册 | 必须在 Python 侧注册 |
| `tojson` | ⚠️ 需注册 | 必须在 Python 侧注册 |

## 3. 行内元素间距约束 (Inline Spacing)

**规则**：在生成列表或连续文本时，变量与文本之间需明确修整边界。

**格式**：使用 `{{- var -}}` 确保紧贴两侧文本，不产生多余空格。

**示例**：
```jinja2
Hello, {{- user.name -}}!
```
**输出**：`Hello, Alice!`（无多余空格）

**错误示例**：
```jinja2
Hello, {{ user.name }}!
```
**输出**：`Hello, Alice !`（可能包含换行或空格）

## 4. 缩进保留约束 (Indentation Preservation)

**规则**：若生成 YAML 或 Markdown 列表，仅在行尾使用 `-%}`，行首保留物理缩进。

**目的**：确保生成的结构化文本缩进正确，避免破坏 YAML/Markdown 语法。

**示例**（生成 YAML 列表）：
```jinja2
{%- for item in items %}
  - {{ item.name }}: {{ item.value }}
{%- endfor %}
```

**示例**（生成 Markdown 列表）：
```jinja2
{%- for task in tasks %}
- [ ] {{ task.title }}
{%- endfor %}
```

## 5. 变量存在性防御 (Existence Check)

**规则**：引用对象属性前必须进行定义检查，避免渲染中断。

**格式**：
```jinja2
{{ item.summary if item.summary is defined else "" }}
```

**嵌套对象防御**：
```jinja2
{{ item.author.name if item.author is defined and item.author.name is defined else "Unknown" }}
```

**列表安全迭代**：
```jinja2
{%- for item in items | default([]) -%}
{{ item.name }}
{%- endfor -%}
```

## 模板加载最佳实践

在 Python 脚本中配置 Jinja2 环境：

```python
from jinja2 import Environment, FileSystemLoader, select_autoescape

_template_dir = Path(__file__).resolve().parent.parent / "assets" / "templates"
_jinja_env = Environment(
    loader=FileSystemLoader(_template_dir),
    autoescape=select_autoescape(),
    trim_blocks=False,      # 手动控制修整
    lstrip_blocks=False,    # 手动控制缩进
)

# 注册非原生过滤器（如需要）
import json
_jinja_env.filters['fromjson'] = json.loads
_jinja_env.filters['tojson'] = json.dumps
```

## 常见陷阱

| 陷阱 | 后果 | 解决方案 |
|------|------|----------|
| 未使用修整符 | 输出大量空行 | 使用 `{%-` 和 `-%}` |
| 直接使用非原生过滤器 | 渲染报错 | 提前注册或改用 Python 处理 |
| 未检查变量存在性 | 模板渲染中断 | 使用 `is defined` 或 `default()` |
| 行首使用 `{%-` | 破坏缩进结构 | 仅行尾使用 `-%}`，保留行首缩进 |