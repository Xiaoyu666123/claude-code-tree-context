# Claude Code Tree Context

这个模板给 Claude Code 增加一个轻量的项目树索引，让 Claude 在理解仓库时先拿到紧凑的目录地图，减少不必要的全仓库 `Grep` / `Glob` 扫描。

它包含：

- 手动 `/tree-context` Skill
- `UserPromptSubmit` hook：每次提交 prompt 前注入紧凑树上下文
- `PostToolUse` hook：在文件变更后刷新索引
- 注入前过期检查：外部编辑器增删/移动文件后，下一次 prompt 会自动刷新索引
- 质量保护规则：提醒 Claude 把候选文件当作起点，而不是完整证据
- 一个无第三方依赖的 Python 脚本

## 工作方式

1. `tree_context.py build` 生成 `.claude/context/` 下的索引文件。
2. 每次提交 prompt 前，`inject-tree-context` 会检查索引是否过期。
3. 如果项目文件列表、忽略规则或索引 schema 变化，会先自动重建索引。
4. 然后根据当前 prompt 选择候选目录和候选文件，注入到 Claude Code 上下文。
5. Claude 使用 `Write`、`Edit`、`MultiEdit` 或可能修改文件的 `Bash` 后，`post-update` 会刷新索引。
6. 明确只读的 Bash 命令会跳过刷新，例如 `rg`、`ls`、`git status`。

这不是文件系统实时监听器，而是基于 Claude Code hooks 的事件驱动更新。

## 安装

把 `.claude` 目录复制到你的项目根目录。

```bash
cp -R .claude /path/to/your/project/
cd /path/to/your/project
chmod +x .claude/hooks/*.sh .claude/scripts/tree_context.py
```

首次生成索引：

```bash
python3 .claude/scripts/tree_context.py build
```

如果你的环境没有 `python3`，可以使用：

```bash
python .claude/scripts/tree_context.py build
```

## 启用 hooks：macOS / Linux / Git Bash / WSL

检查 `.claude/settings.example.json`，确认命令路径符合你的环境，然后复制或合并到 `.claude/settings.json`：

```bash
cp .claude/settings.example.json .claude/settings.json
```

## 启用 hooks：Windows PowerShell

检查 `.claude/settings.windows.example.json`，确认 PowerShell 和 Python 可用，然后复制或合并到 `.claude/settings.json`：

```powershell
Copy-Item .claude\settings.windows.example.json .claude\settings.json
```

## 手动使用

在 Claude Code 里使用 Skill：

```text
/tree-context 帮我修复登录接口报错
```

也可以直接运行选择器：

```bash
python3 .claude/scripts/tree_context.py select --prompt "修复登录接口报错"
```

Windows：

```powershell
python .claude\scripts\tree_context.py select --prompt "修复登录接口报错"
```

## 生成的上下文包含什么

自动注入内容大致包括：

- 根模块概览
- Git changed / untracked 文件，如果当前环境支持 Git
- 从 prompt 提取并扩展出的路径匹配关键词
- 候选目录
- 候选文件
- token 节省规则
- 质量保护规则

示例：

```text
<tree-context compact="true">
## Candidate files
- README.md
- .claude/scripts/tree_context.py
- .claude/skills/tree-context/SKILL.md

## Quality guardrails
- Treat selected context as a starting point, not complete evidence.
- Before editing, verify the relevant entry point, call site, or configuration path.
</tree-context>
```

## 质量保护规则

这个插件只负责给 Claude 一个更好的起点，不应该替代正常的代码理解和验证。

内置规则会提醒 Claude：

- 候选文件只是起点，不是完整证据
- 修改前要确认相关入口、调用点或配置路径
- 候选文件不明确时，要从可能目录继续窄范围搜索
- 行为变更需要检查附近测试或给出聚焦验证步骤
- 没有明确修改路径和验证结果时，不应声称问题已经完整解决

## 文件结构

```text
.claude/
|-- skills/tree-context/SKILL.md
|-- hooks/inject-tree-context.sh
|-- hooks/update-tree.sh
|-- hooks/inject-tree-context.ps1
|-- hooks/update-tree.ps1
|-- scripts/tree_context.py
|-- context/project-tree.md       # 生成文件
|-- context/project-files.txt      # 生成文件
|-- context/tree-meta.json         # 生成文件
|-- settings.example.json
|-- settings.windows.example.json
`-- tree-context.ignore
```

## 自定义忽略规则

编辑 `.claude/tree-context.ignore` 可以排除项目里的大目录、产物目录或特殊文件类型。

每行一条规则：

```text
data/
uploads/
**/*.sqlite
**/*.pcap
```

目录规则建议以 `/` 结尾。Glob 规则会按 POSIX 风格的相对路径匹配。

默认会忽略常见依赖、构建、缓存、日志和二进制文件，例如：

- `node_modules/`
- `dist/`
- `build/`
- `.venv/`
- `.next/`
- `coverage/`
- `*.log`
- 图片、压缩包、可执行文件等二进制资源

常见 lock 文件不会被默认排除，因为它们通常对依赖问题很重要。

## 生成文件和版本控制

建议把生成索引排除在版本控制外，只保留 `.gitkeep`：

```gitignore
.claude/context/*
!.claude/context/.gitkeep
```

本模板已经提供根目录 `.gitignore`，会忽略：

- `.idea/`
- `.claude/context/*`
- Python 缓存文件

## 常用命令

重新生成索引：

```bash
python3 .claude/scripts/tree_context.py build
```

安静模式生成索引：

```bash
python3 .claude/scripts/tree_context.py build --quiet
```

根据 prompt 输出候选上下文：

```bash
python3 .claude/scripts/tree_context.py select --prompt "修复登录接口报错"
```

模拟 hook 后置刷新：

```bash
python3 .claude/scripts/tree_context.py post-update
```

## 注意事项

- 这个插件优化的是 Claude 的探索路径，不保证候选文件一定完整。
- 如果候选结果不明显，应继续使用窄范围搜索验证。
- 它追踪的是文件路径变化，不读取每个文件内容做语义索引。
- 外部编辑器改动会在下一次 prompt 注入前通过过期检查同步。
- 如果 Python 不可用，hook 会跳过，不会阻塞 Claude Code。