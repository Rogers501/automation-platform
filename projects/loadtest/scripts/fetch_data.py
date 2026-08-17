"""数据源拉取脚本: 从生产运单库分页查询数据, 写入 CSV/TXT 供压测使用.

数据源接口: http://10.94.7.105:30122/waybillouterapi/order/waybillTimeRangePage
请求头: authtoken: 17f718ef5e0d4f108a66cc57c239dd01
请求体: {pageSize: 1000, current: <页码>, startTime, endTime}

数据源接口响应字段 -> 压测请求字段映射表:
  数据源字段              压测请求字段          说明
  id                     waybillId             运单表 ID
  pickNetworkCode        startPointNetworkCode  寄件网点编码
  pickNetworkCode        startNetworkCode       寄件网点编码 (同一个值, 两个字段都取)
  receiverPostalCode     terminalPostalCode     收件邮编
  expressTypeCode        productTypeCode        产品类型 Code
  (固定写死)              productTypeId          产品类型 ID, 固定 100
  goodsTypeId            goodsTypeId            物品类型 ID
  goodsTypeCode          goodsTypeCode          物品类型 Code
  sendCode               serviceMethodCode      寄件服务方式 (也固定写 01)
  packageChargeWeight    number                 包裹计费重量
  inputTime              currentTime            录入时间
  (写死 7178)             customerId             客户 ID, 固定 7178
  (固定写死)              smMode                 结算方式, 固定 2
  insuredAmount          insuredAmount          报价金额

生成的 CSV 文件可直接用于:
  1. 本项目 Locust 压测: 场景 YAML 中 {{data.jmsbr/cost_data.<列名>}}
  2. JMeter 压测: CSV Data Set Config 中引用列名 (如 ${waybillId})

两种输出模式:
  1. 默认模式: 生成 CSV (多字段, 供 comCostAndWeight 算费接口使用)
  2. --waybill-nos: 生成 TXT (每行一个运单号, 供运单查询接口使用)

用法 (在 projects/loadtest/ 目录下运行)::

    # 先查看接口返回结构 (推荐, 确认字段名)
    python scripts/fetch_data.py --inspect

    # 拉取 1000 页 x 1000 条 = 百万级记录, 生成 CSV
    python scripts/fetch_data.py

    # 拉取 500 页, 指定输出路径
    python scripts/fetch_data.py --pages 500 --output data/jmsbr/cost_data.csv

    # 拉取运单号 TXT (供 waybill_get / waybill_query 使用)
    python scripts/fetch_data.py --waybill-nos --pages 500

依赖 httpx (通过 framework 安装). 用主 .venv 或 loadtest venv 均可.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from pathlib import Path
from typing import Any

import httpx

# ---------------------------------------------------------------------------
# Data source API configuration
# ---------------------------------------------------------------------------
DATA_SOURCE_URL = "http://10.94.7.104:30131/waybillouterapi/order/waybillTimeRangePage"
AUTH_TOKEN = "17f718ef5e0d4f108a66cc57c239dd01"
START_TIME = "2026-05-31 08:00:00"
END_TIME = "2026-05-31 22:00:00"
PAGE_SIZE = 10000

# Concurrency: 20 concurrent page requests (balance speed vs. source API load).
MAX_CONCURRENT = 20
REQUEST_TIMEOUT = 60  # 每页请求超时 (秒)
MAX_RETRIES = 3

# ---------------------------------------------------------------------------
# CSV output columns -- must match {{csv.cost_data.<col>}} in scenario YAML
# ---------------------------------------------------------------------------
# CSV 输出列名: 只包含从数据源接口动态获取的字段.
# 固定值 (productTypeId=100, customerId=7178, smMode=2) 不写入 CSV,
# 直接在 JMeter/Locust 请求配置中写死, 改固定值时无需重新生成数据源文件.
# 同时可直接用于 JMeter CSV Data Set Config 的变量名引用 (如 ${waybillId}).
CSV_COLUMNS = [
    "waybillId",  # 运单表 ID (数据源: id)
    "startPointNetworkCode",  # 寄件网点编码 (数据源: pickNetworkCode)
    "startNetworkCode",  # 寄件网点编码 (同上, 两个字段取同一个值)
    "terminalPostalCode",  # 收件邮编 (数据源: receiverPostalCode)
    "productTypeCode",  # 产品类型 Code (数据源: expressTypeCode)
    "goodsTypeId",  # 物品类型 ID (数据源: goodsTypeId)
    "goodsTypeCode",  # 物品类型 Code (数据源: goodsTypeCode)
    "serviceMethodCode",  # 寄件服务方式 (数据源: sendCode)
    "number",  # 包裹计费重量 (数据源: packageChargeWeight)
    "currentTime",  # 录入时间 (数据源: inputTime)
    "insuredAmount",  # 报价金额 (数据源: insuredAmount)
]

# Field name aliases: try these keys in the record if the primary name is absent.
# Ordered by likelihood (camelCase first, then snake_case, then alternatives).
FIELD_ALIASES: dict[str, list[str]] = {
    "waybillId": ["id", "waybillId", "waybill_id", "waybillNo"],
    # pickNetworkCode 同时映射到 startPointNetworkCode 和 startNetworkCode
    "startPointNetworkCode": ["pickNetworkCode", "startPointNetworkCode", "startNetworkCode"],
    "startNetworkCode": ["pickNetworkCode", "startNetworkCode", "startPointNetworkCode"],
    "terminalPostalCode": ["receiverPostalCode", "terminalPostalCode", "destPostalCode"],
    "productTypeCode": ["expressTypeCode", "productTypeCode"],
    "goodsTypeId": ["goodsTypeId", "goods_type_id"],
    "goodsTypeCode": ["goodsTypeCode", "goods_type_code"],
    "serviceMethodCode": ["sendCode", "serviceMethodCode"],
    "number": ["packageChargeWeight", "number", "chargeWeight", "weight"],
    "currentTime": ["inputTime", "currentTime", "createTime", "orderTime"],
    "insuredAmount": ["insuredAmount", "insured_amount", "insuranceValue"],
}

# Default values for fields that might be missing in the data source.
# 固定值: 不从数据源取的字段, 直接写死.
# 兜底默认值: 数据源中可能缺失的字段, 给一个合理默认值.
DEFAULTS: dict[str, str] = {
    "productTypeCode": "EZ",
    "goodsTypeId": "60",
    "goodsTypeCode": "bm000006",
    "serviceMethodCode": "01",
    "number": "0.5",
    "insuredAmount": "0.69",
}


def extract_fields(record: dict[str, Any]) -> dict[str, str]:
    """从数据源记录中提取动态字段, 生成 CSV 行.

    只提取动态字段, 固定值不写入 CSV (在 JMeter/Locust 配置中写死).
    优先级: 数据源字段 (按别名查找) > 兜底默认值.
    """
    row: dict[str, str] = {}
    for col in CSV_COLUMNS:
        value: str | None = None
        for alias in FIELD_ALIASES.get(col, [col]):
            val = record.get(alias)
            if val is not None:
                value = str(val)
                break
        if value is None:
            value = DEFAULTS.get(col, "")
        row[col] = value
    return row


def find_records(data: Any) -> list[dict[str, Any]]:
    """从接口响应中提取记录列表.

    支持的响应结构:
      1. {"data": {"records": [...], "total": N, ...}}  -- MyBatis-Plus IPage
      2. {"data": [...]}                                 -- data 直接是列表
      3. {"records": [...]}                               -- 顶层 records
      4. [...]                                            -- 直接是列表
    """
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    inner = data.get("data")
    if isinstance(inner, dict) and isinstance(inner.get("records"), list):
        return inner["records"]
    if isinstance(inner, list):
        return inner
    if isinstance(data.get("records"), list):
        return data["records"]
    return []


async def fetch_page(
    client: httpx.AsyncClient,
    page_num: int,
    semaphore: asyncio.Semaphore,
    start_time: str = START_TIME,
    end_time: str = END_TIME,
) -> list[dict[str, Any]]:
    """拉取单页数据, 带重试 (最多 MAX_RETRIES 次)."""
    body = {
        "pageSize": PAGE_SIZE,
        "current": page_num,
        "startTime": start_time,
        "endTime": end_time,
    }
    headers = {
        "authtoken": AUTH_TOKEN,
        "Content-Type": "application/json",
    }
    async with semaphore:
        for attempt in range(MAX_RETRIES):
            try:
                resp = await client.post(
                    DATA_SOURCE_URL,
                    json=body,
                    headers=headers,
                    timeout=REQUEST_TIMEOUT,
                )
                resp.raise_for_status()
                records = find_records(resp.json())
                if attempt == 0 and page_num <= 2:
                    print(f"  [调试] 第 {page_num} 页: 返回 {len(records)} 条")
                return records
            except Exception as exc:
                if attempt == MAX_RETRIES - 1:
                    print(
                        f"  [ERROR] page {page_num} failed after {MAX_RETRIES} retries: {exc}",
                        file=sys.stderr,
                    )
                    return []
                await asyncio.sleep(1.0 * (attempt + 1))
    return []


async def inspect_mode(start_time: str = START_TIME, end_time: str = END_TIME) -> None:
    """Fetch first page and print response structure for field mapping verification."""
    print(f"URL: {DATA_SOURCE_URL}")
    print(f"Body: pageSize={PAGE_SIZE}, current=1, startTime={start_time}, endTime={end_time}")
    print()

    async with httpx.AsyncClient() as client:
        records = await fetch_page(client, 1, asyncio.Semaphore(1), start_time, end_time)

    if not records:
        print("[ERROR] No records returned. Check API URL, token, and time range.")
        return

    print(f"Records on page 1: {len(records)}")
    print(f"Fields in first record ({len(records[0])} keys):")
    for key in records[0]:
        val = records[0][key]
        val_str = str(val)
        if len(val_str) > 60:
            val_str = val_str[:60] + "..."
        print(f"  {key}: {val_str} ({type(val).__name__})")

    print("\n--- Field mapping preview ---")
    sample_row = extract_fields(records[0])
    for col in CSV_COLUMNS:
        print(f"  {col} -> {sample_row[col]}")


def _unique_path(path: Path) -> Path:
    """文件名不覆盖: 如同名文件存在, 自动加序号后缀.

    示例: cost_data.csv -> cost_data_1.csv -> cost_data_2.csv
    """
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    for i in range(1, 10000):
        candidate = parent / f"{stem}_{i}{suffix}"
        if not candidate.exists():
            return candidate
    return path  # fallback


async def fetch_all(
    pages: int,
    output: Path,
    max_records: int = 0,
    start_time: str = START_TIME,
    end_time: str = END_TIME,
) -> None:
    """分页查询数据源接口, 提取字段写入 CSV (生成计算费用的数据源文件).

    并发拉取: 每批 MAX_CONCURRENT*2 页并发请求, 全部返回后写入 CSV, 再拉下一批.
    超时 60 秒/页, 失败自动重试 3 次.

    参数:
        pages: 拉取页数, 每页 PAGE_SIZE 条
        output: CSV 输出路径
        max_records: 最大记录数, 0 表示不限制 (--count 指定时按条数截断)
        start_time: 查询起始时间
        end_time: 查询结束时间

    输出文件不覆盖已有文件, 如同名文件存在则自动加序号后缀.
    """
    output = _unique_path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    if max_records > 0:
        pages = (max_records + PAGE_SIZE - 1) // PAGE_SIZE
        print(f"目标: {max_records} 条 (需 {pages} 页 x {PAGE_SIZE}/页)")
    else:
        print(f"目标: {pages} 页 x {PAGE_SIZE} = {pages * PAGE_SIZE} 条")
    print(f"输出: {output}")
    print(f"模式: 并发 (每批 {MAX_CONCURRENT * 2} 页)")
    print(f"超时: {REQUEST_TIMEOUT} 秒/页")
    print()

    # 写 CSV 表头
    with output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()

    total = 0
    batch_size = MAX_CONCURRENT * 2
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        for batch_start in range(1, pages + 1, batch_size):
            batch_end = min(batch_start + batch_size, pages + 1)
            tasks = [
                fetch_page(client, p, semaphore, start_time, end_time)
                for p in range(batch_start, batch_end)
            ]
            results = await asyncio.gather(*tasks)

            # 第一批打印字段信息
            if batch_start == 1:
                for records in results:
                    if records:
                        print(f"  首条记录字段: {list(records[0].keys())}")
                        break

            # 写入 CSV
            batch_written = 0
            with output.open("a", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
                for records in results:
                    for rec in records:
                        if max_records > 0 and total >= max_records:
                            break
                        writer.writerow(extract_fields(rec))
                        total += 1
                        batch_written += 1
                    if max_records > 0 and total >= max_records:
                        break

            batch_records = sum(len(r) for r in results)
            empty_pages = sum(1 for r in results if not r)
            print(
                f"  页 {batch_start}-{batch_end - 1}: "
                f"本批返回 {batch_records} 条, 写入 {batch_written} 条, "
                f"空页 {empty_pages}, 累计 {total} 条"
            )

            # 整批全空: 没有更多数据了, 停止
            if batch_records == 0:
                print("  整批返回空, 时间范围内数据已拉完, 停止")
                break

            if max_records > 0 and total >= max_records:
                break

    # 文件行数校验 (减去表头 1 行)
    with output.open("r", encoding="utf-8") as f:
        file_lines = sum(1 for _ in f) - 1
    print(f"\n完成! 实际写入 {total} 条, 文件行数 {file_lines} 行")
    if file_lines != total:
        print(f"  [警告] total({total}) 与文件行数({file_lines}) 不一致!")
    print(f"输出: {output}")


async def fetch_waybill_nos(
    pages: int,
    output: Path,
    max_records: int = 0,
    start_time: str = START_TIME,
    end_time: str = END_TIME,
) -> None:
    """从数据源接口拉取运单号, 每行一个写入 TXT 文件.

    并发拉取: 每批 MAX_CONCURRENT*2 页并发请求, 全部返回后写入 TXT, 再拉下一批.

    参数:
        pages: 拉取页数, 每页 PAGE_SIZE 条
        output: TXT 输出路径
        max_records: 最大记录数, 0 表示不限制
        start_time: 查询起始时间
        end_time: 查询结束时间

    用法:
      python scripts/fetch_data.py --waybill-nos --count 500000
      python scripts/fetch_data.py --waybill-nos --pages 500
    """
    output = _unique_path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    if max_records > 0:
        pages = (max_records + PAGE_SIZE - 1) // PAGE_SIZE
        print(f"目标: {max_records} 个运单号 (需 {pages} 页)")
    else:
        print(f"目标: {pages} 页 x {PAGE_SIZE} = {pages * PAGE_SIZE} 条记录")
    print(f"输出: {output} (TXT, 每行一个运单号)")
    print(f"模式: 并发 (每批 {MAX_CONCURRENT * 2} 页)")
    print()

    waybill_no_keys = ["waybillNo", "waybill_no", "waybillNumber", "orderNo", "no"]

    total = 0
    batch_size = MAX_CONCURRENT * 2
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        with output.open("w", encoding="utf-8") as f:
            for batch_start in range(1, pages + 1, batch_size):
                batch_end = min(batch_start + batch_size, pages + 1)
                tasks = [
                    fetch_page(client, p, semaphore, start_time, end_time)
                    for p in range(batch_start, batch_end)
                ]
                results = await asyncio.gather(*tasks)

                batch_records = 0
                for records in results:
                    for rec in records:
                        if max_records > 0 and total >= max_records:
                            break
                        for key in waybill_no_keys:
                            val = rec.get(key)
                            if val:
                                f.write(str(val).strip() + "\n")
                                total += 1
                                batch_records += 1
                                break
                    if max_records > 0 and total >= max_records:
                        break

                print(f"  页 {batch_start}-{batch_end - 1}: 累计 {total} 个运单号")

                # 整批全空: 没有更多数据了, 停止
                if batch_records == 0 and all(not r for r in results):
                    print("  整批返回空, 时间范围内数据已拉完, 停止")
                    break

                if max_records > 0 and total >= max_records:
                    break

    # 文件行数校验
    with output.open("r", encoding="utf-8") as f:
        file_lines = sum(1 for _ in f)
    print(f"\n完成! 实际写入 {total} 个, 文件行数 {file_lines} 行")
    if file_lines != total:
        print(f"  [警告] total({total}) 与文件行数({file_lines}) 不一致!")
    print(f"输出: {output}")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Fetch waybill data from data source API -> CSV for load testing"
    )
    parser.add_argument(
        "--inspect",
        action="store_true",
        help="只拉第一页, 打印返回结构和字段名, 用于确认接口可用",
    )
    parser.add_argument(
        "--start-time",
        type=str,
        default=START_TIME,
        help=f"查询起始时间 (默认: {START_TIME})",
    )
    parser.add_argument(
        "--end-time",
        type=str,
        default=END_TIME,
        help=f"查询结束时间 (默认: {END_TIME})",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=0,
        help="拉取页数, 每页 1000 条 (默认 0, 由 --count 决定)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=0,
        help="拉取条数, 精确控制数据量 (如 --count 500000 = 50万条, 优先于 --pages)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/jmsbr/cost_data.csv",
        help="输出 CSV 文件路径 (默认: data/jmsbr/cost_data.csv)",
    )
    parser.add_argument(
        "--waybill-nos",
        action="store_true",
        help="提取运单号写入 TXT 文件 (每行一个, 供 waybill_get/waybill_query 使用)",
    )
    parser.add_argument(
        "--waybill-nos-output",
        type=str,
        default="data/jmsbr/waybill_nos_fetched.txt",
        help="运单号 TXT 输出路径 (默认: data/jmsbr/waybill_nos_fetched.txt)",
    )
    args = parser.parse_args()

    # --count 优先于 --pages; 都不指定时默认 1000 页 = 百万条
    max_records = args.count
    pages = args.pages if args.pages > 0 else (1000 if max_records == 0 else 0)

    if args.inspect:
        asyncio.run(inspect_mode(args.start_time, args.end_time))
    elif args.waybill_nos:
        asyncio.run(
            fetch_waybill_nos(
                pages,
                Path(args.waybill_nos_output),
                max_records,
                args.start_time,
                args.end_time,
            )
        )
    else:
        asyncio.run(
            fetch_all(
                pages,
                Path(args.output),
                max_records,
                args.start_time,
                args.end_time,
            )
        )


if __name__ == "__main__":
    main()
