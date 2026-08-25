#!/usr/bin/env bash
# 从本地 GitLab 的 master 分支拉取同事提交, 合并到 main, 推送到三个平台 (gitee/github/gitlab main + gitlab master)
#
# 用途: 同事推送到 gitlab master 后, 你想把他们的改动同步到自己个人仓库
# 流程:
#   1. git fetch gitlab (拉 gitlab 最新)
#   2. 显示 master 与本地 main 的差异 (让你 review 后再决定是否合并)
#   3. 询问是否继续合并
#   4. git checkout main
#   5. git merge gitlab/master (产生 merge commit, 保留同事的提交历史)
#   6. git push origin main (推 gitee + github)
#   7. post-push hook 自动同步到 gitlab master
#
# 失败处理:
#   - merge 冲突: 脚本停在 merge 状态, 你手动解决后 git commit && git push origin main
#   - push 失败: 打印错误, 不回滚本地 merge (你解决后重推)
#
# 用法:
#   bash scripts/sync_from_gitlab.sh           # 交互模式, 问才合并
#   bash scripts/sync_from_gitlab.sh --yes     # 不询问, 直接合并 (慎用)

set -euo pipefail

YES=0
[[ "${1:-}" == "--yes" ]] && YES=1

# 必须在 main 分支上执行 (避免在 master 或 feature 分支误操作)
current=$(git rev-parse --abbrev-ref HEAD)
if [[ "$current" != "main" ]]; then
    echo "ERROR: 当前分支是 $current, 必须在 main 上执行" >&2
    exit 1
fi

echo "=== 1. 拉取 gitlab 最新 ==="
git fetch gitlab

# 检查 master 是否有 main 没有的提交
NEW_COMMITS=$(git log main..gitlab/master --oneline 2>/dev/null || echo "")
if [[ -z "$NEW_COMMITS" ]]; then
    echo "gitlab master 没有新提交, 无需同步"
    exit 0
fi

echo "=== 2. gitlab master 比本地 main 多以下提交 ==="
echo "$NEW_COMMITS"
echo ""
echo "=== 3. 改动的文件 ==="
git diff --stat main..gitlab/master
echo ""

if [[ "$YES" -eq 0 ]]; then
    read -p "确认合并到 main? (y/N) " confirm
    [[ "$confirm" =~ ^[yY]$ ]] || { echo "已取消"; exit 0; }
fi

echo "=== 4. 合并 gitlab/master 到 main ==="
# 用 merge (不是 ff-only), 因为是反向同步, 同事的提交历史要保留
# 如果 merge 默认 ff 就直接 ff, 否则产生 merge commit
if ! git merge gitlab/master; then
    echo ""
    echo "=== merge 冲突! 请手动解决 ===" >&2
    echo "解决步骤:" >&2
    echo "  1. 编辑冲突文件" >&2
    echo "  2. git add <resolved-files>" >&2
    echo "  3. git commit" >&2
    echo "  4. bash scripts/sync_from_gitlab.sh 重新跑 (会跳过已合并的)" >&2
    echo "  或放弃合并: git merge --abort" >&2
    exit 1
fi

echo "=== 5. 推送到 origin (gitee + github main) ==="
git push origin main

echo "=== 6. post-push hook 会自动同步 gitlab master ==="
echo "完成. main 已同步到三平台 main, master 已对齐."
