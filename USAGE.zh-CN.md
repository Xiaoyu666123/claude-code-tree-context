# 本地项目接入指南

这份文档说明如何把 `claude-code-tree-context` 拉到本地项目里使用，以及 Claude Code 什么时候会自动加载它。

## 前提条件

目标项目所在机器需要有：

- Claude Code
- Python 3，或可用的 `python`
- Git

Windows 下如果 Git 不在 PATH，可以使用完整路径，例如：

```powershell
D:\Git\cmd\git.exe --version
```

## 推荐接入方式

进入你想启用 Tree Context 的目标项目根目录。

```powershell
cd D:\path\to\your-project
```

临时 clone 模板仓库：

```powershell
git clone https://github.com/Xiaoyu666123/claude-code-tree-context.git temp-tree-context
```

如果你的 Git 不在 PATH，使用：

```powershell
D:\Git\cmd\git.exe clone https://github.com/Xiaoyu666123/claude-code-tree-context.git temp-tree-context
```

把 `.claude` 目录复制到当前项目：

```powershell
Copy-Item -Recurse -Force temp-tree-context\.claude\* .\.claude\
```

复制完成后删除临时目录：

```powershell
Remove-Item -Recurse -Force temp-tree-context
```

## 启用 Windows hooks

在目标项目根目录执行：

```powershell
Copy-Item .claude\settings.windows.example.json .claude\settings.json
```

然后生成初始索引：

```powershell
python .claude\scripts\tree_context.py build
```

如果你的系统使用 `py` 启动 Python，可以执行：

```powershell
py -3 .claude\scripts\tree_context.py build
```

## 启用 macOS / Linux / Git Bash / WSL hooks

在目标项目根目录执行：

```bash
cp .claude/settings.example.json .claude/settings.json
chmod +x .claude/hooks/*.sh .claude/scripts/tree_context.py
python3 .claude/scripts/tree_context.py build
```

## Claude Code 会自动加载吗？

会，但前提是你在目标项目根目录里放好了：

```text
.claude/settings.json
```

Claude Code 在这个项目中启动后，会读取 `.claude/settings.json` 里的 hooks 配置。

当前模板里的自动行为包括：

- `UserPromptSubmit`：每次提交 prompt 前，自动注入 compact tree context
- `PostToolUse`：Claude 修改文件后，自动刷新树索引
- prompt 前过期检查：如果外部编辑器增删或移动了文件，下一次 prompt 前会自动同步索引

注意：只把这个仓库 clone 到某个目录，不会自动影响所有项目。你需要把 `.claude` 复制到每个想启用的项目根目录。

## 手动使用 Skill

启用后，你也可以手动调用：

```text
/tree-context 帮我修复登录接口报错
```

这会读取：

```text
.claude/skills/tree-context/SKILL.md
```

并按 Skill 文档里的规则先选择候选文件，再继续处理任务。

## 自动和手动入口的区别

自动入口：

```text
.claude/settings.json
```

负责 hooks 自动注入和动态刷新。只要 Claude Code 在该项目里启动并读取到 settings，就会自动生效。

手动入口：

```text
.claude/skills/tree-context/SKILL.md
```

负责 `/tree-context ...` 命令。只有你显式调用这个 Skill 时才会按它的完整流程执行。

## 推荐提交到目标项目的文件

如果你想让某个项目长期使用 Tree Context，建议把这些文件提交到该项目仓库：

```text
.claude/hooks/
.claude/scripts/
.claude/skills/
.claude/settings.example.json
.claude/settings.windows.example.json
.claude/settings.json
.claude/tree-context.ignore
.claude/context/.gitkeep
```

不要提交生成索引：

```text
.claude/context/project-tree.md
.claude/context/project-files.txt
.claude/context/tree-meta.json
```

建议目标项目的 `.gitignore` 里包含：

```gitignore
.claude/context/*
!.claude/context/.gitkeep
__pycache__/
*.pyc
```

## 更新模板

如果以后这个模板仓库有更新，可以重新 clone 一份，然后覆盖目标项目里的 `.claude`。

```powershell
git clone https://github.com/Xiaoyu666123/claude-code-tree-context.git temp-tree-context
Copy-Item -Recurse -Force temp-tree-context\.claude .\.claude
Remove-Item -Recurse -Force temp-tree-context
python .claude\scripts\tree_context.py build
```

覆盖前如果你修改过 `.claude/tree-context.ignore` 或 `.claude/settings.json`，建议先备份再合并。
