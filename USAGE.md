# obsidian-mcp 使用说明

## 这是什么

`obsidian-mcp` 是一个 MCP 服务器，让 AI 智能体（Claude Desktop、Cursor、Codex 等）可以直接读写你的 Obsidian 笔记库。

装上之后，AI 就能：
- 搜索你的笔记
- 读取/创建/编辑笔记
- 把对话中的知识保存到笔记里
- 查询笔记之间的链接关系

---

## 一、安装

```bash
pip install obsidian-mcp
```

或者从 GitHub 安装（最新版）：

```bash
git clone https://github.com/386522758/obsidian-mcp.git
cd obsidian-mcp
pip install -e .
```

安装完成后会获得一个命令行工具 `obsidian-mcp`，可以在任何 MCP 客户端中调用。

---

## 二、配置环境变量

你需要告诉 MCP 服务器你的 vault 在哪。设置以下环境变量：

### 必填

| 变量 | 值 | 示例 |
|------|-----|------|
| `OBSIDIAN_VAULT_PATH` | 你的 vault 路径 | `E:\vault\杨自宝的知识库` |

### 可选

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `OBSIDIAN_REST_API_ENABLED` | `false` | 启用 Obsidian REST API 插件 |
| `OBSIDIAN_REST_API_URL` | `https://localhost:27124` | REST API 地址 |
| `OBSIDIAN_REST_API_TOKEN` | 空 | REST API 认证令牌 |
| `OBSIDIAN_DAILY_NOTES_FOLDER` | 空 | 每日子文件夹名 |
| `OBSIDIAN_DAILY_NOTES_FORMAT` | `%Y-%m-%d` | 日期文件名格式 |
| `OBSIDIAN_TEMPLATES_FOLDER` | 空 | 模板子文件夹名 |
| `OBSIDIAN_MEMORY_FOLDER` | `memories` | 记忆存储子文件夹 |

---

## 三、在各客户端中配置

### 1. Claude Desktop

编辑配置文件：

- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "obsidian": {
      "command": "obsidian-mcp",
      "env": {
        "OBSIDIAN_VAULT_PATH": "E:\\vault\\杨自宝的知识库"
      }
    }
  }
}
```

改完后重启 Claude Desktop。

### 2. Cursor

打开 Cursor 设置 → MCP → Add new server，填入：

```json
{
  "command": "obsidian-mcp",
  "args": [],
  "env": {
    "OBSIDIAN_VAULT_PATH": "E:\\vault\\杨自宝的知识库"
  }
}
```

### 3. Codex (OpenAI)

在 MCP 配置文件中添加同上格式的 server 配置。

### 4. 其他 MCP 客户端

任何支持 MCP 的客户端都可以使用，只需指向 `obsidian-mcp` 命令并设置 `OBSIDIAN_VAULT_PATH`。

---

## 四、功能使用指南

### 读笔记

AI 可以直接让你读取任何笔记的完整内容、标签和链接：

```
你：帮我看看 Python基础语法总结 这篇笔记讲了什么
AI：[自动调用 obsidian_read_note，返回完整解析结果]
```

### 搜索笔记

支持三种搜索方式：

| 工具 | 用途 | 示例 |
|------|------|------|
| `obsidian_search` | 全文搜索 | 搜 "函数" 找到所有包含"函数"的笔记 |
| `obsidian_search_by_tag` | 按标签搜 | 搜标签 `机器学习`，找到 6 篇笔记 |
| `obsidian_search_by_metadata` | 按 frontmatter 搜 | 搜 `status: draft` 找所有草稿笔记 |

全文搜索还支持语法：
- `+函数` — 必须包含"函数"
- `-机器学习` — 排除含"机器学习"的结果
- `python 函数` — 同时包含两个词

### 创建笔记

```
你：帮我在 00.inbox 里创建一篇关于 Docker 的学习笔记
AI：[调用 obsidian_create_note，自动设置 frontmatter 和内容]
```

支持一次性创建带 frontmatter 的完整笔记：

```python
# AI 内部调用示例
obsidian_create_note(
    path="00.inbox/Docker入门",
    content="# Docker 入门\n\n## 安装\n\n...",
    frontmatter='{"tags": ["docker", "devops"], "status": "draft"}'
)
```

### 编辑笔记

两种模式：
- **替换**：用新内容替换整个笔记体
- **追加**：在笔记末尾添加内容（适合日志、日记）

```
你：在机器学习完整流程那篇笔记末尾加上「实践心得」章节
AI：[调用 obsidian_update_note，append=true]
```

### 管理 Frontmatter

可以单独更新 frontmatter 字段，不会影响正文内容：

```
你：把 Python基础语法总结 的 status 改成 done
AI：[调用 obsidian_update_frontmatter，merge 更新]
```

### 反向链接查询

```
你：有哪些笔记链接到了「Python基础语法总结」？
AI：[调用 obsidian_get_backlinks，返回 4 篇引用该笔记的文章]
```

### 链接图谱

```
你：帮我看看整个知识库的链接关系
AI：[调用 obsidian_get_graph，返回 15 个节点的完整关系网]
```

---

## 五、记忆存储（核心功能）

这是最强大的功能之一——让 AI 把对话中的知识、经验、决策保存为 Obsidian 笔记，构建可持续积累的"AI 记忆库"。

### 保存记忆

```
你：记住，Python 装饰器的本质是高阶函数
AI：[调用 obsidian_save_memory]
    - category: fact
    - importance: 4
    - tags: [python, decorator]
    - 保存到: memories/20260531-190840_Python装饰器本质.md
```

### 召回记忆

```
你：我之前跟你说过关于装饰器的什么？
AI：[调用 obsidian_recall_memories，query="装饰器"]
    返回: "Python 的装饰器本质上是一个高阶函数..."
```

### 记忆管理

```
你：我有哪些类型的记忆？
AI：[调用 obsidian_recall_memories，列出所有分类]
```

记忆的 frontmatter 结构：

```yaml
---
type: memory
category: fact          # general/conversation/fact/task/insight
importance: 4           # 1-5 级
source: agent           # agent/user/conversation
created: 2026-05-31T19:08:40
tags: [memory, fact, python, decorator]
---
```

### 关联笔记

保存记忆时可以链接到 vault 中已有的笔记：

```
你：记住这个 Python 技巧，关联到 Python基础语法总结
AI：[调用 obsidian_save_memory, related_notes=["Python基础语法总结"]]
    笔记末尾自动添加：Related: [[Python基础语法总结]]
```

---

## 六、每日笔记

```
你：打开今天的日记
AI：[调用 obsidian_get_daily_note，自动创建或读取]

你：在今天的日记里加上「完成了 MCP 服务器开发」
AI：[调用 obsidian_append_daily]
```

每日笔记自动带 frontmatter：

```yaml
---
date: 2026-05-31
tags: [daily]
---

# 2026-05-31 (Saturday)

## Tasks
- [ ] 

## Notes


## Journal

```

---

## 七、模板

### 列出可用模板

```
你：我有哪些模板？
AI：[调用 obsidian_list_templates]
```

### 从模板创建笔记

```
你：用「项目笔记」模板创建一篇关于新项目的笔记
AI：[调用 obsidian_apply_template]
```

模板变量语法：`{{变量名}}`

内置变量：
- `{{date}}` → `2026-05-31`
- `{{time}}` → `19:08`
- `{{datetime}}` → `2026-05-31 19:08`
- `{{year}}` / `{{month}}` / `{{day}}`
- `{{weekday}}` → `Saturday`
- `{{date:%m月%d日}}` → `05月31日`（自定义格式）

自定义变量：`{{title}}`、`{{project}}` 等，创建时通过 `variables` 参数传入。

---

## 八、使用 Obsidian REST API（可选）

如果你想让 AI 能直接在 Obsidian 应用中打开笔记、或使用 Obsidian 内置搜索引擎，需要：

### 1. 安装插件

在 Obsidian 中打开 `设置 → 社区插件 → 浏览`，搜索 "Local REST API" 并安装。

### 2. 获取 API Key

打开插件设置页，复制 API Key。

### 3. 配置环境变量

```json
{
  "env": {
    "OBSIDIAN_VAULT_PATH": "E:\\vault\\杨自宝的知识库",
    "OBSIDIAN_REST_API_ENABLED": "true",
    "OBSIDIAN_REST_API_TOKEN": "你的API Key"
  }
}
```

### 4. 额外功能

启用后，AI 可以：

| 工具 | 功能 |
|------|------|
| `obsidian_open_in_app` | 在 Obsidian 中直接打开某篇笔记 |
| `obsidian_rest_search` | 用 Obsidian 内置搜索引擎搜索（比文件搜索更精确） |
| `obsidian_rest_api_status` | 检查插件是否在线 |

> 不装插件也能用所有核心功能。REST API 是可选增强。

---

## 九、完整工具列表

| 工具 | 说明 |
|------|------|
| `obsidian_read_note` | 读取并解析笔记（含 frontmatter、标签、链接） |
| `obsidian_create_note` | 创建新笔记 |
| `obsidian_update_note` | 更新笔记内容（替换或追加） |
| `obsidian_delete_note` | 删除笔记 |
| `obsidian_move_note` | 移动或重命名笔记 |
| `obsidian_list_notes` | 列出笔记列表 |
| `obsidian_list_folders` | 列出子文件夹 |
| `obsidian_get_backlinks` | 查找引用某篇笔记的所有文章 |
| `obsidian_get_graph` | 获取整个库的链接关系图 |
| `obsidian_search` | 全文搜索（支持布尔语法） |
| `obsidian_search_by_tag` | 按标签搜索 |
| `obsidian_search_by_metadata` | 按 frontmatter 字段搜索 |
| `obsidian_update_frontmatter` | 更新 frontmatter（合并写入） |
| `obsidian_list_templates` | 列出可用模板 |
| `obsidian_apply_template` | 从模板创建笔记 |
| `obsidian_get_daily_note` | 获取/创建每日笔记 |
| `obsidian_append_daily` | 追加内容到每日笔记 |
| `obsidian_save_memory` | 保存一条 AI 记忆 |
| `obsidian_recall_memories` | 检索存储的记忆 |
| `obsidian_forget_memory` | 删除一条记忆 |
| `obsidian_create_link` | 生成 wikilink 文本 |
| `obsidian_vault_stats` | 获取笔记库统计信息 |
| `obsidian_rest_search` | REST API 搜索（需插件） |
| `obsidian_open_in_app` | 在 Obsidian 中打开笔记（需插件） |
| `obsidian_rest_api_status` | 检查 REST API 状态 |

---

## 十、常见问题

### Q: 运行时报 "Vault path does not exist"

检查 `OBSIDIAN_VAULT_PATH` 路径是否正确，路径应该指向包含 `.obsidian` 文件夹的目录。

### Q: Windows 路径中的反斜杠

在 JSON 配置中，反斜杠需要转义：`"E:\\vault\\杨自宝的知识库"`

### Q: Claude Desktop 改了配置后不生效

重启 Claude Desktop。macOS 需要完全退出（Cmd+Q）再重新打开。

### Q: REST API 连不上

1. 确认 Obsidian 已打开并运行
2. 确认已安装并启用 "Local REST API" 插件
3. 确认 API Key 正确
4. 默认端口 27124，如果改过需要同步修改 `OBSIDIAN_REST_API_URL`

### Q: 能否同时访问多个 vault

当前版本每个实例对应一个 vault。如需多 vault，可以启动多个 MCP 实例，分别配置不同的 `OBSIDIAN_VAULT_PATH`。

### Q: 记忆存在哪

默认存在 vault 根目录下的 `memories/` 文件夹，每条记忆是一个独立的 .md 文件，带 frontmatter 元数据。你可以在 Obsidian 中直接浏览和编辑它们。

### Q: 支持中文笔记名吗

完全支持。笔记名、标签、frontmatter 内容都可以使用中文。
