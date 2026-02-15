---
name: merge-current-to-branch
description: Merges the current Git branch into a specified target branch after verifying the target exists and checking for conflicts. Use when the user wants to merge the current branch into another branch (e.g. main, develop), or when they ask to "合并到某分支" or "merge into branch".
---

# 将当前分支合并到指定分支

在合并前检查目标分支是否存在；合并后若有冲突则中止并提示解决，否则完成合并。

## 输入

- **目标分支**：用户指定的要合并到的分支名（如 `main`、`develop`）。若未提供，需向用户询问。

## 流程

按顺序执行，任一步失败则停止并给出对应提示。

### 1. 确认目标分支存在

在本地检查目标分支是否存在：

```bash
git rev-parse --verify refs/heads/<目标分支>
```

- **若命令失败（退出码非 0）**：提示「指定分支不存在」，不继续。可建议用户先拉取远程：`git fetch origin`，或确认分支名是否正确。
- **若成功**：继续下一步。

### 2. 记录当前分支并执行合并

```bash
CURRENT=$(git branch --show-current)
git checkout <目标分支>
git merge "$CURRENT"
```

### 3. 检查是否有冲突

合并后检查：

- **若 `git merge` 已因冲突退出（退出码非 0）**：视为存在冲突，仅提示「存在合并冲突，请解决冲突后完成合并」（不执行 `git merge --abort`，保留当前合并状态供用户解决）。
- **若 `git merge` 成功**：合并完成，可提示「已成功将当前分支合并到指定分支」。

### 4. 可选：合并后回到原分支

若希望用户继续在原分支工作，可执行：

```bash
git checkout "$CURRENT"
```

由 agent 根据用户习惯或上下文决定是否执行此步。

## 使用脚本（推荐）

项目内提供脚本，可保证步骤一致、错误信息统一：

```bash
.cursor/skills/merge-current-to-branch/scripts/merge-to-branch.sh <目标分支>
```

- 脚本会依次：检查目标分支存在 → 合并 → 有冲突则仅提示，不执行 `git merge --abort`。
- 执行脚本时从仓库根目录运行；脚本需有执行权限（`chmod +x`）。

## 提示文案

- **分支不存在**：「指定分支 `<分支名>` 不存在。请先执行 `git fetch` 或确认分支名是否正确。」
- **存在冲突**：「合并时存在冲突。请解决冲突后完成合并。」

## 注意事项

- 仅检查**本地**分支是否存在；若目标分支只在远程，需先 `git fetch` 再合并（或先 `git checkout -b <目标分支> origin/<目标分支>` 再按本流程合并）。
- 未提交的修改可能阻止 checkout/merge；若有未提交更改，先提示用户提交或 stash。
