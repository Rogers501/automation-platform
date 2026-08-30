"""批量创建 GitLab 用户并分配项目角色.

用法:
    python scripts/create_gitlab_users.py           # 按下面 USERS 列表创建
    python scripts/create_gitlab_users.py --dry-run  # 只打印不实际创建

环境变量:
    GITLAB_TOKEN: root PAT (默认从 memory 读)
    GITLAB_URL: GitLab 地址 (默认 http://10.66.67.26:8929)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

# 配置
GITLAB_URL = os.getenv("GITLAB_URL", "http://10.66.67.26:8929")
TOKEN = os.getenv("GITLAB_TOKEN", "glpat-y0Q5yhq9iFvWxUjoj7ZM6286MQp1OjEH.01.0w0nsh5or")
PROJECT_PATH = "root/automation-platform"
DEFAULT_PASSWORD = "AutoDev2026!Xq"
ACCESS_LEVEL = 30  # Developer

# 待创建用户列表
USERS = [
    {"username": "xuhao",        "name": "许浩",     "email": "xuhao@jtexpress.com"},
    {"username": "lishuaishuai", "name": "李帅帅",  "email": "lishuaishuai@jtexpress.com"},
    {"username": "gaoqianqian",  "name": "高倩倩",  "email": "kenna.gao@jtexpress.com"},
    {"username": "lichuanhao",   "name": "李传浩",  "email": "lennard.li@jtexpress.com"},
    {"username": "xiaojuan",     "name": "小娟",     "email": "xiaojuan@jtexpress.com"},
    {"username": "sunzhouqing",  "name": "孙周清",  "email": "joy.sun@jtexpress.com"},
    {"username": "zhuyushuang",  "name": "朱玉双",  "email": "zhuyushuang@jtexpress.com"},
]


def api(method: str, path: str, data: dict | None = None) -> tuple[int, dict]:
    """调用 GitLab API, 返回 (status_code, response_dict)."""
    url = f"{GITLAB_URL}/api/v4{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(
        url, data=body, method=method,
        headers={
            "PRIVATE-TOKEN": TOKEN,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def get_project_id() -> int:
    """获取项目 ID (URL-encode 路径)."""
    encoded = urllib.request.quote(PROJECT_PATH, safe="")
    status, resp = api("GET", f"/projects/{encoded}")
    if status != 200:
        raise RuntimeError(f"获取项目失败: {status} {resp}")
    return resp["id"]


def create_user(user: dict, dry_run: bool) -> str:
    """创建用户, 返回状态字符串."""
    if dry_run:
        return f"[DRY-RUN] 会创建用户 {user['username']} ({user['email']})"

    payload = {
        "email": user["email"],
        "username": user["username"],
        "name": user["name"],
        "password": DEFAULT_PASSWORD,
        "reset_password": False,  # 不强制首次登录改密 (如需改成 True)
        "skip_confirmation": True,  # 跳过邮箱确认
    }
    status, resp = api("POST", "/users", payload)
    if status == 201:
        return f"[OK] 创建 {user['username']} (id={resp.get('id')}) 成功"
    if status == 409:
        return f"[SKIP] {user['username']} 已存在 ({resp.get('message', '')})"
    return f"[FAIL] 创建 {user['username']} 失败: {status} {resp}"


def add_member(project_id: int, user: dict, dry_run: bool) -> str:
    """查询用户 ID 并加为项目 Developer."""
    if dry_run:
        return f"[DRY-RUN] 会把 {user['username']} 加为项目 Developer"

    # 先查用户 ID
    status, resp = api("GET", f"/users?username={user['username']}")
    if status != 200 or not resp:
        return f"[FAIL] 查询 {user['username']} ID 失败: {status} {resp}"
    user_id = resp[0]["id"]

    # 加为项目成员
    payload = {"user_id": user_id, "access_level": ACCESS_LEVEL}
    status, resp = api("POST", f"/projects/{project_id}/members", payload)
    if status == 201:
        return f"[OK] {user['username']} 加为项目 Developer 成功"
    if status == 409:
        return f"[SKIP] {user['username']} 已是项目成员"
    return f"[FAIL] 加 {user['username']} 为成员失败: {status} {resp}"


def main() -> int:
    parser = argparse.ArgumentParser(description="批量创建 GitLab 用户")
    parser.add_argument("--dry-run", action="store_true", help="只打印不实际创建")
    args = parser.parse_args()

    if not TOKEN:
        print("ERROR: GITLAB_TOKEN 未设置", file=sys.stderr)
        return 1

    print(f"GitLab: {GITLAB_URL}")
    print(f"项目: {PROJECT_PATH}")
    print(f"角色: Developer (access_level={ACCESS_LEVEL})")
    print(f"初始密码: {DEFAULT_PASSWORD}")
    print(f"用户数: {len(USERS)}")
    print("=" * 60)

    # 获取项目 ID
    try:
        project_id = get_project_id()
        print(f"项目 ID: {project_id}")
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print("=" * 60)
    print("=== 创建用户 ===")
    for u in USERS:
        print(create_user(u, args.dry_run))

    print()
    print("=== 分配 Developer 角色 ===")
    for u in USERS:
        print(add_member(project_id, u, args.dry_run))

    print()
    print("=== 完成 ===")
    print(f"用户访问入口: {GITLAB_URL}")
    print("同事登录后可在 http://10.66.67.26:8080 跑测试 (前端工作台)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
