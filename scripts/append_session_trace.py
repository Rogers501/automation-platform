"""向 docs/协作留痕.docx 追加本次对话留痕.

本次内容: 对话 69 · 2026-08-26 · 修复 post-push hook 从未触发的问题
- 根因: git 客户端没有 post-push hook, 只有 pre-push
- 改名 + 重写逻辑: pre-push, 不切分支, 直接 push gitlab <commit>:master
- 验证通过, hook 正确触发并同步 gitlab master
"""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.shared import Pt, RGBColor

DOC = Path(__file__).resolve().parents[1] / "docs" / "协作留痕.docx"


def main() -> None:
    doc = Document(DOC)

    last = 0
    for p in doc.paragraphs:
        m = re.search(r"对话\s*(\d+)", p.text)
        if m:
            last = max(last, int(m.group(1)))
    dialog_no = last + 1
    date = "2026-08-26"

    def add(text: str, bold: bool = False, color: tuple[int, int, int] | None = None,
            size: int = 11) -> None:
        p = doc.add_paragraph()
        run = p.add_run(text)
        run.font.size = Pt(size)
        run.font.bold = bold
        if color is not None:
            run.font.color.rgb = RGBColor(*color)

    add(f"【用户】 post-push hook 没生效 · 对话 {dialog_no} · {date}",
        bold=True, color=(0x1F, 0x49, 0x7D))
    add(
        "用户反馈: 在 main 分支推送代码到个人平台, 然后切到本地仓库的 master 分支, "
        "并没有新的代码提交记录. 即: 之前装的 post-push hook 从未触发."
    )
    add("文件变更表:")
    add("  - .git/hooks/post-push (重命名为 .git/hooks/pre-push, 重写逻辑)")
    add("  - docs/GitLab本地部署.md (修改, 正向同步章节 post-push 改 pre-push)")
    add("  - memory/project_branch_strategy.md (修改, 同上)")
    add("  - scripts/generate_share_doc.py (修改, 分享文档 hook 描述更新)")
    add("  - docs/自动化测试平台分享文档.docx (重生成, 61.0KB)")
    add("  - docs/协作留痕.docx (本条追加)")
    add("验证结果表:")
    add("  - git ls-remote gitlab refs/heads/master: 与 origin/main 完全对齐")
    add("  - 测试 push origin main: 终端输出 [pre-push] 检测到推 origin/main, 同步完成")
    add("  - ff-only 检查正确: 强推回退时跳过同步并提示手动 sync_from_gitlab.sh")
    add("影响范围分析表:")
    add("  - 以后推 origin/main 自动同步 gitlab master, 无需手动操作")
    add("  - PyCharm 推送也会触发 (用本地 git CLI, hook 会被调用)")
    add("  - 同事推 master 导致 ff-only 失败时, hook 不阻塞主 push, 只提示手动处理")

    add(f"【助手】 根因定位与 hook 重写 · 对话 {dialog_no} · {date}",
        bold=True, color=(0x1F, 0x49, 0x7D))
    add(
        "根因: git 客户端 hook 只有 pre-push (推送前), 没有 post-push (推送后). "
        "之前对话 65 装的 .git/hooks/post-push 文件名 git 根本不认识, 从没被调用过. "
        "之前 master 能同步到 a57b47c 是手动执行的 ff-only merge + push, 不是 hook 触发. "
        "ls .git/hooks/*.sample 验证: 只有 pre-push.sample, 没有 post-push.sample."
    )
    add(
        "修复方案: mv .git/hooks/post-push .git/hooks/pre-push, 重写逻辑. "
        "pre-push 在 push 前触发, stdin 格式与 post-push 相同 "
        "(<local-ref> <local-sha> <remote-ref> <remote-sha>). "
        "关键约束: pre-push hook 不能 checkout 切分支 (会破坏 push 工作树状态), "
        "改用 git push gitlab <local-sha>:refs/heads/master 直接推指定 commit, 不切分支. "
        "ff-only 语义靠 git merge-base --is-ancestor 检查 main 是否是 master 的祖先."
    )
    add(
        "测试验证: 造空 commit (test: 验证 pre-push hook 触发) push origin main, "
        "终端输出完整同步流程: [pre-push] 检测到推 origin/main → "
        "git push gitlab <commit>:master → 1f56c67..d22a7ec master → 同步完成. "
        "然后主 push 继续推到 github 和 gitee. git ls-remote 验证 gitlab/master 已对齐."
    )
    add(
        "ff-only 检查验证: 强推回退 main (a57b47c) 时, gitlab master 在 d22a7ec (测试 commit), "
        "main 不是 master 的祖先, hook 跳过同步并提示 '运行 sync_from_gitlab.sh 手动处理'. "
        "正确行为: 不阻塞主 push (个人仓库推送照常), 只提示手动处理部门仓库."
    )
    add(
        "设计取舍: pre-push hook 失败不阻塞主 push (exit 0), 保证个人仓库推送不受部门仓库状态影响. "
        "如果部门 master 有同事推过的新提交, hook 跳过同步, 用户手动跑 sync_from_gitlab.sh "
        "(fetch + 显示差异 + 询问确认 + merge + push 三平台 main). "
        "这是 '个人仓库优先' 与 '部门协同推进' 的平衡."
    )
    add(
        "文档同步: docs/GitLab本地部署.md §5.3 正向同步章节 post-push 改 pre-push, "
        "描述改为 'git push gitlab <main-commit>:refs/heads/master 直接推指定 commit 不切分支'; "
        "memory/project_branch_strategy.md 同步更新, 加 '注意: git 客户端没有 post-push hook' 警示; "
        "scripts/generate_share_doc.py 第六部分 hook 描述更新, 加踩坑提示; "
        "重生成分享文档 61.0KB."
    )
    add(
        "清理: 测试 commit (test: 验证 pre-push hook 触发 / post-push hook 触发) "
        "已 git reset --hard 删除, 强推 origin/main 回 a57b47c, 强推 gitlab master 回 a57b47c. "
        "本地 master 也 reset 到 a57b47c. 最终所有分支对齐 a57b47c 自动化管理平台docker部署."
    )
    add("文件变更表:")
    add("  - .git/hooks/post-push → .git/hooks/pre-push (重命名 + 重写, 48 行)")
    add("  - docs/GitLab本地部署.md (修改, §5.3 hook 描述更新)")
    add("  - memory/project_branch_strategy.md (修改, hook 描述 + 警示)")
    add("  - scripts/generate_share_doc.py (修改, 第六部分 hook 描述 + 踩坑提示)")
    add("  - docs/自动化测试平台分享文档.docx (重生成, 61.0KB)")
    add("  - docs/协作留痕.docx (本条追加)")
    add("验证结果表:")
    add("  - git push origin main 时 hook 触发, 输出 [pre-push] 日志")
    add("  - gitlab/master 与 origin/main 完全对齐 (a57b47c)")
    add("  - ff-only 检查在强推回退时正确跳过同步")
    add("  - 测试 commit 已清理, 所有分支对齐 a57b47c")
    add("影响范围分析表:")
    add("  - 以后每次 push origin main, hook 自动同步 gitlab master (命令行 + PyCharm)")
    add("  - 同事推 master 导致 ff 失败时, hook 不阻塞主 push, 提示手动 sync_from_gitlab.sh")
    add("  - memory 更新警示: 下次别再犯 post-push 的错")
    add("  - 文档/分享文档都同步更新, 不会误导后人")

    doc.save(DOC)
    print(f"已追加对话 {dialog_no} 到 {DOC}")
    print(f"文件大小: {DOC.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
