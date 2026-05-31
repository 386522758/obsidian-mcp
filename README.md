# obsidian-mcp

[English](#english) | [中文](#中文)

<a name="english"></a>

## Obsidian MCP Server

An MCP (Model Context Protocol) server that lets AI agents directly interact with Obsidian vaults. Supports both direct file system access and the Obsidian Local REST API plugin.

### Features

**Note Operations**
- Read, create, update, delete, and move notes
- Parse YAML frontmatter, wikilinks (`[[links]]`), tags, embeds, and callouts
- Manage frontmatter metadata (merge updates without overwriting existing fields)

**Search**
- Full-text search with `+must-have` and `-exclude` syntax
- Search by tag, frontmatter metadata, or wikilink backlinks
- Context snippets for search results

**Obsidian-Specific**
- Wikilink creation and backlink discovery
- Vault link graph analysis
- Template management with `{{variable}}` substitution
- Daily notes (get, create, append)
- Built-in variables: `{{date}}`, `{{time}}`, `{{datetime}}`, `{{year}}`, `{{month}}`, `{{day}}`, `{{weekday}}`

**Memory Store**
- Save agent memories/knowledge as structured Obsidian notes
- Categorize memories (general, conversation, fact, task, insight)
- Set importance levels (1-5)
- Recall memories by text search, category, or importance
- Link memories to related notes via wikilinks

**REST API Integration**
- Use Obsidian's built-in search engine via the Local REST API plugin
- Open notes directly in the Obsidian app
- Execute Obsidian commands remotely
- Graceful fallback when the plugin is not installed

### Installation

#### From PyPI (recommended)

```bash
pip install obsidian-mcp
```

#### From source

```bash
git clone https://github.com/your-username/obsidian-mcp.git
cd obsidian-mcp
pip install -e .
```

### Configuration

Set environment variables to configure the server:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OBSIDIAN_VAULT_PATH` | Yes | - | Path to your Obsidian vault |
| `OBSIDIAN_REST_API_ENABLED` | No | `false` | Enable the REST API client |
| `OBSIDIAN_REST_API_URL` | No | `https://localhost:27124` | REST API endpoint |
| `OBSIDIAN_REST_API_TOKEN` | No | - | REST API auth token |
| `OBSIDIAN_DAILY_NOTES_FOLDER` | No | - | Subfolder for daily notes |
| `OBSIDIAN_DAILY_NOTES_FORMAT` | No | `%Y-%m-%d` | Date format for daily notes |
| `OBSIDIAN_TEMPLATES_FOLDER` | No | - | Subfolder for templates |
| `OBSIDIAN_MEMORY_FOLDER` | No | `memories` | Subfolder for stored memories |

### Usage with MCP Clients

#### Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "obsidian": {
      "command": "obsidian-mcp",
      "env": {
        "OBSIDIAN_VAULT_PATH": "/path/to/your/vault"
      }
    }
  }
}
```

#### Codex / Other MCP Clients

```json
{
  "mcpServers": {
    "obsidian": {
      "command": "obsidian-mcp",
      "env": {
        "OBSIDIAN_VAULT_PATH": "E:\\vault\\your-vault"
      }
    }
  }
}
```

#### With REST API enabled

```json
{
  "mcpServers": {
    "obsidian": {
      "command": "obsidian-mcp",
      "env": {
        "OBSIDIAN_VAULT_PATH": "/path/to/your/vault",
        "OBSIDIAN_REST_API_ENABLED": "true",
        "OBSIDIAN_REST_API_TOKEN": "your-api-token"
      }
    }
  }
}
```

### Available Tools

| Tool | Description |
|------|-------------|
| `obsidian_read_note` | Read and parse a note with full metadata |
| `obsidian_create_note` | Create a new note with optional frontmatter |
| `obsidian_update_note` | Update note content and/or frontmatter |
| `obsidian_delete_note` | Delete a note |
| `obsidian_move_note` | Move or rename a note |
| `obsidian_list_notes` | List notes in a folder or entire vault |
| `obsidian_list_folders` | List subdirectories |
| `obsidian_get_backlinks` | Find notes that link to a given note |
| `obsidian_get_graph` | Get the vault's wikilink graph |
| `obsidian_search` | Full-text search across all notes |
| `obsidian_search_by_tag` | Find notes by tag |
| `obsidian_search_by_metadata` | Search by frontmatter key/value |
| `obsidian_update_frontmatter` | Update frontmatter fields (merge) |
| `obsidian_list_templates` | List available templates |
| `obsidian_apply_template` | Create a note from a template |
| `obsidian_get_daily_note` | Get or create a daily note |
| `obsidian_append_daily` | Append content to a daily note |
| `obsidian_save_memory` | Save a memory/knowledge item |
| `obsidian_recall_memories` | Search stored memories |
| `obsidian_forget_memory` | Delete a stored memory |
| `obsidian_create_link` | Create a wikilink string |
| `obsidian_vault_stats` | Get vault statistics |
| `obsidian_rest_search` | Search via REST API (requires plugin) |
| `obsidian_open_in_app` | Open a note in Obsidian (requires plugin) |
| `obsidian_rest_api_status` | Check REST API availability |

### Obsidian Local REST API Plugin (Optional)

To use the REST API features:

1. Install the [Local REST API](https://github.com/coddingtonbear/obsidian-local-rest-api) community plugin in Obsidian
2. Enable it and note the API key from plugin settings
3. Set `OBSIDIAN_REST_API_ENABLED=true` and `OBSIDIAN_REST_API_TOKEN=<your-key>`

### License

MIT

---

<a name="中文"></a>

## Obsidian MCP 服务器

一个 MCP（模型上下文协议）服务器，让 AI 智能体可以直接与 Obsidian 笔记库交互。支持直接文件系统访问和 Obsidian Local REST API 插件两种方式。

### 功能特性

**笔记操作**
- 读取、创建、更新、删除和移动笔记
- 解析 YAML frontmatter、wikilinks (`[[双向链接]]`)、标签、嵌入和 Callout
- 管理 frontmatter 元数据（合并更新，不会覆盖现有字段）

**搜索**
- 全文搜索，支持 `+必须包含` 和 `-排除` 语法
- 按标签、frontmatter 元数据或 wikilink 反向链接搜索
- 搜索结果附带上下文片段

**Obsidian 特性**
- Wikilink 创建和反向链接发现
- 笔记库链接图谱分析
- 模板管理，支持 `{{变量}}` 替换
- 每日笔记（获取、创建、追加）
- 内置变量：`{{date}}`、`{{time}}`、`{{datetime}}`、`{{year}}`、`{{month}}`、`{{day}}`、`{{weekday}}`

**记忆存储**
- 将智能体记忆/知识保存为结构化的 Obsidian 笔记
- 分类管理（general、conversation、fact、task、insight）
- 设置重要性等级（1-5）
- 通过文本搜索、分类或重要性召回记忆
- 通过 wikilinks 将记忆与相关笔记关联

**REST API 集成**
- 通过 Local REST API 插件使用 Obsidian 内置搜索引擎
- 在 Obsidian 应用中直接打开笔记
- 远程执行 Obsidian 命令
- 插件未安装时优雅降级到直接文件访问

### 安装

```bash
pip install obsidian-mcp
```

或从源码安装：

```bash
git clone https://github.com/your-username/obsidian-mcp.git
cd obsidian-mcp
pip install -e .
```

### 配置

| 环境变量 | 必填 | 默认值 | 说明 |
|----------|------|--------|------|
| `OBSIDIAN_VAULT_PATH` | 是 | - | Obsidian vault 路径 |
| `OBSIDIAN_REST_API_ENABLED` | 否 | `false` | 启用 REST API 客户端 |
| `OBSIDIAN_REST_API_URL` | 否 | `https://localhost:27124` | REST API 地址 |
| `OBSIDIAN_REST_API_TOKEN` | 否 | - | REST API 认证令牌 |
| `OBSIDIAN_DAILY_NOTES_FOLDER` | 否 | - | 每日笔记子文件夹 |
| `OBSIDIAN_TEMPLATES_FOLDER` | 否 | - | 模板子文件夹 |
| `OBSIDIAN_MEMORY_FOLDER` | 否 | `memories` | 记忆存储子文件夹 |

### 在 MCP 客户端中使用

**Claude Desktop** — 在 `claude_desktop_config.json` 中添加：

```json
{
  "mcpServers": {
    "obsidian": {
      "command": "obsidian-mcp",
      "env": {
        "OBSIDIAN_VAULT_PATH": "E:\\vault\\YourVault"
      }
    }
  }
}
```

### License

MIT
