"""Locust 压测入口文件.

本文件由 Locust 自动加载 (当前目录下查找 locustfile.py).
负责:
  1. 读取环境变量 APP_ENV / SCENARIO_FILE / LOAD_PROFILE
  2. 从 YAML 场景文件构建 Locust HttpUser 子类 (压测用户)
  3. 可选: 从 YAML 压测形状文件构建 LoadTestShape (压测曲线)

运行方式:
  # 方式一: 用 run.py 启动 (推荐, 自动设置环境变量)
  python run.py waybill_get -t 10s              # 快速调试, 1 个用户
  python run.py waybill_get -t 10s -u 200 -r 20  # 200 并发, 10 秒
  python run.py waybill_get --shape -t 3600s    # 完整压测形状 (1 小时)

  # 方式二: 直接用 locust 命令 (需手动设环境变量)
  $env:APP_ENV="jmsbr"
  $env:SCENARIO_FILE="scenarios/jmsbr/waybill_get.yaml"
  $env:LOAD_PROFILE="load_profile_jmsbr"
  locust --headless -t 3600s

环境变量说明:
  APP_ENV        -- 环境名称, 对应 config/envs/<APP_ENV>.yaml (如 jmsbr)
  SCENARIO_FILE  -- 场景文件路径, 如 scenarios/jmsbr/waybill_get.yaml
  LOAD_PROFILE   -- 压测形状文件名, 对应 config/<LOAD_PROFILE>.yaml (如 load_profile_jmsbr)
  SKIP_SHAPE     -- 设为 "1" 时跳过压测形状, 用 --users/--spawn-rate 手动控制并发
"""

from __future__ import annotations

import os

from runner import build_shape_class, build_user_class

# 从环境变量读取配置 (run.py 会自动设置这些变量).
_ENV = os.environ.get("APP_ENV", "dev")
_SCENARIO_FILE = os.environ.get("SCENARIO_FILE", os.path.join("scenarios", _ENV, "login.yaml"))

# 从 YAML 场景文件构建 Locust HttpUser 子类.
# 这是 Locust 发现的唯一用户类 (必须是模块级变量).
JmsLoadUser = build_user_class(_SCENARIO_FILE)

# 可选: 从 YAML 压测形状文件构建 LoadTestShape.
# 当 SKIP_SHAPE 环境变量为 "1" 时跳过 (run.py 不带 --shape 时会设置).
# LoadTestShape 必须是唯一的模块级子类, 否则 Locust 报 "Duplicate shape classes".
if os.environ.get("SKIP_SHAPE"):
    _shape = None
else:
    _shape = build_shape_class()
    if _shape is not None:
        YamlLoadTestShape = _shape
del _shape
