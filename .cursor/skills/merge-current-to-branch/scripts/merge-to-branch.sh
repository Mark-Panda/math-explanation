#!/usr/bin/env bash
# 将当前分支合并到指定分支：检查目标存在 → 合并 → 有冲突则中止并提示
# 用法: merge-to-branch.sh <目标分支>
# 在仓库根目录执行

set -e

TARGET="$1"
if [ -z "$TARGET" ]; then
  echo "用法: $0 <目标分支>"
  exit 1
fi

# 1. 检查目标分支是否存在（仅本地）
if ! git rev-parse --verify "refs/heads/$TARGET" >/dev/null 2>&1; then
  echo "指定分支 \"$TARGET\" 不存在。请先执行 git fetch 或确认分支名是否正确。"
  exit 1
fi

CURRENT=$(git branch --show-current)
if [ -z "$CURRENT" ]; then
  echo "无法获取当前分支名。"
  exit 1
fi

# 2. 切换到目标分支并合并
git checkout "$TARGET"

# 3. 合并；有冲突时 merge 会失败，仅提示，不执行 git merge --abort
if ! git merge "$CURRENT"; then
  echo "合并时存在冲突。请解决冲突后完成合并。"
  exit 1
fi

# 4. 推送到远程
if ! git push origin "$TARGET"; then
  echo "合并成功，但推送到 origin/$TARGET 失败。请检查网络或权限后手动执行: git push origin $TARGET"
  exit 1
fi

echo "已成功将分支 \"$CURRENT\" 合并到 \"$TARGET\" 并推送到 origin。"
