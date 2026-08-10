"""压测启动脚本 -- 一个 PyCharm 配置, 用参数切换场景.

用法:
    python run.py waybill_get                   # 自动查找场景, 默认 60 秒
    python run.py waybill_get -t 300s           # 跑 5 分钟
    python run.py waybill_get -t 10s -u 200 -r 20  # 200 并发, 每秒拉起 20 个, 跑 10 秒
    python run.py waybill_get --shape -t 3600s  # 走压测形状 (ramp-up/hold/ramp-down, 1 小时)
    python run.py --list                        # 列出所有可用场景

参数说明:
    场景名       -- 场景文件名或路径 (如 waybill_get, jmsbr/waybill_get)
    -t           -- 压测持续时间 (如 10s, 300s, 3600s)
    -u           -- 并发用户数 (默认 1; 加 --shape 时忽略)
    -r           -- 每秒拉起用户数 (spawn rate, 类似 JMeter 的 Ramp-Up 速率)
    --shape      -- 使用压测形状文件 (config/load_profile_<env>.yaml)
    -e           -- 覆盖环境名 APP_ENV (默认从场景目录名推断)
    -p           -- 覆盖压测形状文件名 LOAD_PROFILE (默认从环境名推断)
    --list       -- 列出所有可用场景

JMeter 参数对照:
    JMeter 线程数        -> Locust -u (并发用户数)
    JMeter Ramp-Up 时间  -> Locust -r (每秒拉起速率 = 线程数 / Ramp-Up 时间)

两种运行模式:
    1. 固定并发模式 (默认): 不走压测形状, 用 -u/-r 控制并发, -t 控制时间.
       适合快速调试和短时间验证.
    2. 压测形状模式 (--shape): 走 config/load_profile_<env>.yaml 定义的
       ramp-up/hold/ramp-down 阶段. 适合完整压测和大促容量验证.

APP_ENV 和 LOAD_PROFILE 自动从场景所在目录推断:
    scenarios/jmsbr/waybill_get.yaml -> APP_ENV=jmsbr, LOAD_PROFILE=load_profile_jmsbr
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def find_scenarios() -> list[Path]:
    """扫描 scenarios/ 目录下所有 YAML 场景文件."""
    root = Path("scenarios")
    if not root.exists():
        return []
    return sorted(root.rglob("*.yaml"))


def match_scenario(query: str) -> Path | None:
    """按名称、路径或模糊匹配查找场景文件."""
    scenarios = find_scenarios()

    # 标准化查询: 去掉 .yaml 后缀, 统一用正斜杠, 去掉 scenarios/ 前缀
    q = query.replace("\\", "/").removesuffix(".yaml")
    if q.startswith("scenarios/"):
        q = q.removeprefix("scenarios/")

    # 精确匹配相对路径: "jmsbr/waybill_get"
    for s in scenarios:
        rel = str(s.relative_to("scenarios")).replace("\\", "/").removesuffix(".yaml")
        if rel == q:
            return s

    # 按文件名精确匹配: "waybill_get"
    exact_stems = [s for s in scenarios if s.stem == query]
    if len(exact_stems) == 1:
        return exact_stems[0]
    if len(exact_stems) > 1:
        print(f"场景名 '{query}' 有多个匹配, 请用完整路径:")
        for m in exact_stems:
            print(f"  {m}")
        return None

    # 模糊匹配: 文件名包含查询字符串
    fuzzy = [s for s in scenarios if query.lower() in s.stem.lower()]
    if len(fuzzy) == 1:
        return fuzzy[0]
    if len(fuzzy) > 1:
        print(f"场景名 '{query}' 有多个匹配, 请用完整路径:")
        for m in fuzzy:
            print(f"  {m}")
        return None

    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="压测启动脚本 -- 一个配置, 用参数切换场景",
    )
    parser.add_argument(
        "scenario",
        nargs="?",
        help="场景名或路径 (如 waybill_get, jmsbr/waybill_get)",
    )
    parser.add_argument(
        "-t",
        "--duration",
        default="60s",
        help="压测持续时间 (默认 60s)",
    )
    parser.add_argument(
        "-u",
        "--users",
        type=int,
        default=1,
        help="并发用户数 (默认 1; 加 --shape 时忽略)",
    )
    parser.add_argument(
        "-r",
        "--spawn-rate",
        type=float,
        default=0,
        help="每秒拉起用户数 (默认 1; 类似 JMeter Ramp-Up 速率)",
    )
    parser.add_argument(
        "-e",
        "--env",
        default="",
        help="覆盖环境名 APP_ENV (默认从场景目录名自动推断)",
    )
    parser.add_argument(
        "-p",
        "--profile",
        default="",
        help="覆盖压测形状文件名 LOAD_PROFILE (默认从环境名自动推断)",
    )
    parser.add_argument(
        "--shape",
        action="store_true",
        help="使用压测形状 (ramp-up/hold/ramp-down, 见 config/load_profile_<env>.yaml)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="列出所有可用场景",
    )
    args = parser.parse_args()

    # --list: 列出所有场景并退出
    if args.list:
        scenarios = find_scenarios()
        if not scenarios:
            print("scenarios/ 目录下没有场景文件")
            return
        print("可用场景:")
        print(f"{'名称':<32} {'环境':<8} 路径")
        print("-" * 70)
        for s in scenarios:
            env = s.parent.name
            print(f"{s.stem:<32} {env:<8} {s}")
        return

    if not args.scenario:
        parser.print_help()
        return

    scenario_path = match_scenario(args.scenario)
    if scenario_path is None:
        print(f"场景 '{args.scenario}' 未找到, 用 --list 查看所有可用场景")
        sys.exit(1)

    # 从场景目录名推断 APP_ENV (如 scenarios/jmsbr/ -> jmsbr)
    env = args.env or scenario_path.parent.name

    # 推断 LOAD_PROFILE: 优先 load_profile_<env>.yaml, 不存在则用 load_profile.yaml
    if args.profile:
        profile = args.profile
    else:
        candidate = Path("config") / f"load_profile_{env}.yaml"
        profile = candidate.stem if candidate.exists() else "load_profile"

    # 在 locustfile.py 被加载之前设置环境变量
    os.environ["APP_ENV"] = env
    os.environ["SCENARIO_FILE"] = str(scenario_path).replace("\\", "/")
    os.environ["LOAD_PROFILE"] = profile

    print(f"场景:       {scenario_path}")
    print(f"APP_ENV:    {env}")
    print(f"Profile:    {profile}")
    print(f"持续时间:   {args.duration}")
    if args.shape:
        print("模式:       压测形状 (load profile)")
    else:
        spawn_rate = args.spawn_rate if args.spawn_rate > 0 else 1.0
        print("模式:       固定并发")
        print(f"并发用户:   {args.users}")
        print(f"拉起速率:   {spawn_rate}/s")
    print()

    # 构建 Locust 命令行参数
    # 不带 --shape: 固定并发, 设 SKIP_SHAPE 跳过压测形状
    # 带 --shape: 压测形状控制 ramp-up/hold/ramp-down
    locust_args = ["--headless", "-t", args.duration]
    if args.shape:
        os.environ.pop("SKIP_SHAPE", None)
    else:
        os.environ["SKIP_SHAPE"] = "1"
        spawn_rate = args.spawn_rate if args.spawn_rate > 0 else 1.0
        locust_args.extend(["-u", str(args.users), "-r", str(spawn_rate)])

    sys.argv = ["locust", *locust_args]

    from locust.main import main as locust_main

    locust_main()


if __name__ == "__main__":
    main()
