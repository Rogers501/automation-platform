"""向 docs/协作留痕.docx 追加本次对话留痕.

本次内容: 对话 68 · 2026-08-25 · 文档全面同步容器化与分支策略变更
- README/技术方案/概要设计/详细设计/分享文档 全部同步
- 分享文档重生成, 含双分支策略、容器化部署、镜像备份
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
    date = "2026-08-25"

    def add(text: str, bold: bool = False, color: tuple[int, int, int] | None = None,
            size: int = 11) -> None:
        p = doc.add_paragraph()
        run = p.add_run(text)
        run.font.size = Pt(size)
        run.font.bold = bold
        if color is not None:
            run.font.color.rgb = RGBColor(*color)

    add(f"【用户】 检查并同步所有相关文档 · 对话 {dialog_no} · {date}",
        bold=True, color=(0x1F, 0x49, 0x7D))
    add(
        "用户诉求: 容器化部署和分支策略变更后, 检查所有相关文档是否需要更新, "
        "比如分享文档、方案文档. 同步更新, 不存在则创建."
    )
    add("文件变更表:")
    add("  - README.md (修改, 第 218 行加容器化部署小节, 访问入口加 8080)")
    add("  - docs/测试管理平台技术方案.md (修改, §6.2 加容器化部署模式, 访问地址表区分开发/生产)")
    add("  - docs/概要设计文档.md (修改, §6.3 部署形态拆成开发模式+生产模式)")
    add("  - docs/详细设计文档.md (修改, §11.1 CORS/Python 解释器改成 env/自动检测, §11.2 加部署形态/访问入口行)")
    add("  - docs/自动化测试平台分享文档.docx (重生成, 第六部分双分支策略, 第七部分容器化部署, 附录B命令速查)")
    add("  - scripts/generate_share_doc.py (修改, 上述 docx 内容对应的生成脚本)")
    add("  - docs/协作留痕.docx (本条追加)")
    add("验证结果表:")
    add("  - generate_share_doc.py 跑通, 分享文档从 59.1KB 增到 60.8KB")
    add("  - 各 markdown 文档 grep 验证 5173/8080/start_all/docker compose 引用一致")
    add("  - 文档间交叉引用 (docs/部署与运维.md §3.5) 在 README/技术方案/概要设计中都正确指向")
    add("影响范围分析表:")
    add("  - 新人/同事读文档: 看到的访问入口/部署命令都是最新的, 不会按过时信息操作")
    add("  - 分享文档: 部门内技术分享时, 第六/七部分内容与当前实际一致")
    add("  - 设计文档: CORS env 化、Python 解释器自动检测的设计决策记录到详细设计")

    add(f"【助手】 文档同步检查与更新 · 对话 {dialog_no} · {date}",
        bold=True, color=(0x1F, 0x49, 0x7D))
    add(
        "盘点: 列出 11 个文档 (README + docs/ 下 9 个 + AGENTS/AI_RULES), "
        "逐个判断是否受容器化部署或分支策略变更影响. "
        "结论: README/技术方案/概要设计/详细设计/分享文档 5 个需更新; "
        "架构设计/CI-CD/GitLab部署/快速上手 4 个已更新或不涉及; "
        "AGENTS/AI_RULES 2 个不涉及具体部署, 不动."
    )
    add(
        "更新策略: (1) markdown 直接改; (2) 分享文档 docx 改对应的 generate_share_doc.py 然后重生成. "
        "不直接改 docx, 否则下次重生成会丢内容."
    )
    add(
        "分享文档改动: "
        "第六部分 6.1 从 '三套 Git 远程' 改成 '三套 Git 远程 + 双分支策略', "
        "加 main/master 双分支表、post-push hook 自动同步说明、反向同步脚本; "
        "第七部分 7.2 从 '一键启动' 改成 '部署', 拆开发模式+生产模式两种, 加防火墙提示; "
        "§7.4 加平台镜像备份小节 (save_platform_images.ps1); "
        "附录B 命令速查加容器化部署命令、平台镜像备份/导入、sync_from_gitlab.sh 反向同步. "
        "目录同步更新."
    )
    add(
        "详细设计改动: §11.1 配置项清单, '前端 CORS 来源' 从 '(代码硬编码)' 改成 'APP_CORS_ORIGINS env', "
        "'Python 解释器' 从 'ROOT/.venv/Scripts/python.exe (Windows only)' 改成 '.venv 不存在则用 sys.executable', "
        "§11.2 环境差异配置加 '部署形态' 和 '访问入口' 两行 (DEV 本地进程 5173, 其他容器化 8080)."
    )
    add(
        "未改的文档及理由: "
        "docs/架构设计.md - 只讲 framework 模块职责, 不涉及部署; "
        "docs/CI-CD流水线.md - CI 流水线不涉及运行时容器化; "
        "docs/GitLab本地部署.md - 上次已更新分支策略章节; "
        "docs/快速上手.md - 新人上手流程, 容器化部署已在 README 和部署与运维.md 详细讲, 不重复; "
        "AGENTS.md/AI_RULES.md - 执行规范和开发红线, 不涉及具体部署命令."
    )
    add("文件变更表:")
    add("  - README.md (修改, 第 218-229 行加容器化部署小节)")
    add("  - docs/测试管理平台技术方案.md (修改, §6.2 加容器化部署 + 访问地址表分模式)")
    add("  - docs/概要设计文档.md (修改, §6.3 部署形态重写, 开发+生产两种模式)")
    add("  - docs/详细设计文档.md (修改, §11.1 §11.2 配置项与差异表更新)")
    add("  - scripts/generate_share_doc.py (修改, §6.1 §7.2 §7.4 附录B)")
    add("  - docs/自动化测试平台分享文档.docx (重生成, 60.8KB)")
    add("  - docs/协作留痕.docx (本条追加)")
    add("验证结果表:")
    add("  - .venv/Scripts/python.exe scripts/generate_share_doc.py 跑通无报错")
    add("  - 分享文档大小 60.8KB (较 59.1KB 增加 1.7KB, 对应新增内容)")
    add("  - grep 验证: README/技术方案/概要设计 的 5173/8080/start_all/docker compose 引用一致")
    add("影响范围分析表:")
    add("  - 同事读文档: 所有访问入口、部署命令与当前实际一致, 不会按过时信息操作")
    add("  - 分享文档: 部门内技术分享时, 第六/七部分与实际部署一致")
    add("  - 设计文档: CORS env 化、Python 自动检测、双分支策略的设计决策有据可查")
    add("  - 下次重生成分享文档不会丢内容 (改的是脚本, 不是 docx)")

    doc.save(DOC)
    print(f"已追加对话 {dialog_no} 到 {DOC}")
    print(f"文件大小: {DOC.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
