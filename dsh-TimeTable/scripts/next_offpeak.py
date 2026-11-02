#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TimeTable —— 计算下一个 DeepSeek 谷时起点（北京时间 Asia/Shanghai）。

峰谷规则（用户定义）：
  高峰：周一至周五 09:00–12:00、14:00–18:00（不含法定节假日）
  谷时：其余全部时间（工作日早晚与午间、周末全天、法定节假日全天）

用法：
  python next_offpeak.py                          # 以当前时间计算，人类可读
  python next_offpeak.py --json                   # 机器可读，含 schedule_create 参数
  python next_offpeak.py --now 2026-11-02T10:30:00+08:00
  python next_offpeak.py --wait-next              # 已在谷时也强制等下一段谷时
  python next_offpeak.py --selftest               # 回归测试

只依赖标准库（Python 3.9+）。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# DSH 的 pwsh 以 UTF-8 解码子进程输出，而 Windows 下 Python 默认用 GBK 写管道，
# 中文会变成乱码；这里强制 UTF-8 输出。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):  # 老版本 Python / 非常规流
        pass

SKILL_DIR = Path(__file__).resolve().parent.parent
HOLIDAY_FILE = SKILL_DIR / "references" / "holidays.json"

try:
    TZ = ZoneInfo("Asia/Shanghai")
except Exception:  # Windows 上没装 tzdata 时退回固定 +08:00（中国无夏令时）
    from datetime import timezone

    TZ = timezone(timedelta(hours=8), "UTC+08:00")

BUFFER = timedelta(minutes=1)  # 已在谷时：立即执行时的最小前置量
AM = (time(9, 0), time(12, 0))
PM = (time(14, 0), time(18, 0))
BLOCKS = (
    (AM[0], AM[1], "工作日上午高峰 09:00–12:00"),
    (PM[0], PM[1], "工作日下午高峰 14:00–18:00"),
)
WEEKDAY = "一二三四五六日"


def load_holidays(path: Path = HOLIDAY_FILE):
    """返回 (放假日期集合, 已覆盖的年份集合, 原始数据)。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    days: set[date] = set()
    covered: set[int] = set()
    for year_s, ranges in data.get("ranges", {}).items():
        if not ranges:
            continue
        covered.add(int(year_s))
        for item in ranges:
            start = date.fromisoformat(item[0])
            end = date.fromisoformat(item[-1])
            if end < start:
                raise ValueError(f"{year_s} 年区间 {item[0]}~{item[-1]} 终点早于起点")
            d = start
            while d <= end:
                days.add(d)
                d += timedelta(days=1)
    return days, covered, data


def parse_now(text: str | None) -> datetime:
    if not text:
        return datetime.now(TZ)
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    return dt.astimezone(TZ)


def classify(dt: datetime, holidays: set[date]) -> tuple[bool, str]:
    """True=高峰；第二个元素是判定依据。"""
    d, t = dt.date(), dt.time()
    if d in holidays:
        return False, "法定节假日"
    if d.weekday() >= 5:
        return False, "周末"
    for start, end, label in BLOCKS:
        if start <= t < end:
            return True, label
    return False, "工作日谷间（00:00–09:00 / 12:00–14:00 / 18:00–24:00）"


def next_peak_block(now: datetime, holidays: set[date]):
    """下一个高峰区间 (开始, 结束)，两周内找不到返回 None。"""
    d = now.date()
    for _ in range(15):
        if d not in holidays and d.weekday() < 5:
            for start, end, _label in BLOCKS:
                begin = datetime.combine(d, start).replace(tzinfo=TZ)
                if begin > now:
                    return begin, datetime.combine(d, end).replace(tzinfo=TZ)
        d += timedelta(days=1)
    return None


def compute(now: datetime, holidays: set[date], covered: set[int], wait_next: bool = False) -> dict:
    warnings = []
    for y in sorted({now.year, (now + timedelta(days=3)).year}):
        if y not in covered:
            warnings.append(
                f"WARN {y} 年法定节假日数据缺失：仅按「工作日/周末」判断，"
                f"工作日假期可能被误判为高峰。请先核对 references/holidays.json。"
            )

    peak, why = classify(now, holidays)
    if peak:
        end = AM[1] if now.time() < AM[1] else PM[1]
        target = datetime.combine(now.date(), end).replace(tzinfo=TZ)
        if target <= now:  # 保险：理论上到不了
            target = now + BUFFER
        action = "schedule"
        reason = f"当前处于{why}，谷时起点 = 本段高峰结束时刻"
    elif wait_next:
        block = next_peak_block(now, holidays)
        if block is None:
            target = now + BUFFER
            action = "run_now"
            reason = "当前已是谷时，且两周内找不到高峰段"
        else:
            begin, finish = block
            target = finish
            action = "schedule"
            reason = (
                f"当前已是谷时（{why}），按你的要求等下一段高峰 "
                f"{begin:%m-%d %H:%M}–{finish:%H:%M} 结束后再执行"
            )
    else:
        target = now + BUFFER
        action = "run_now"
        reason = f"当前已是谷时（{why}），谷时已生效，立即执行，无需空等"

    delta = int((target - now).total_seconds())
    return {
        "now": now.isoformat(timespec="seconds"),
        "now_human": f"{now:%Y-%m-%d %H:%M}（周{WEEKDAY[now.weekday()]}）",
        "state": "peak" if peak else "off_peak",
        "state_reason": why,
        "action": action,
        "target": target.isoformat(timespec="seconds"),
        "target_date": f"{target:%Y-%m-%d}",
        "target_time": f"{target:%H:%M:00}",
        "target_human": f"{target:%Y-%m-%d %H:%M}（周{WEEKDAY[target.weekday()]}）",
        "delta_seconds": delta,
        "delta_human": humanize(delta),
        "reason": reason,
        "warnings": warnings,
        "schedule_args": (
            {"at": {"date": f"{target:%Y-%m-%d}", "time": f"{target:%H:%M:00}", "time_zone": "Asia/Shanghai"}}
            if action == "schedule"
            else None
        ),
    }


def humanize(seconds: int) -> str:
    if seconds < 0:
        return "0 分钟"
    minutes = round(seconds / 60)
    if minutes < 1:
        return "不到 1 分钟"
    if minutes < 60:
        return f"{minutes} 分钟"
    hours, rest = divmod(minutes, 60)
    if hours < 24:
        return f"{hours} 小时 {rest} 分" if rest else f"{hours} 小时"
    days, rest_h = divmod(hours, 24)
    return f"{days} 天 {rest_h} 小时" if rest_h else f"{days} 天"


def render(info: dict) -> str:
    lines = [
        f"TimeTable · 北京时间 {info['now_human']}",
        f"当前状态：{'高峰' if info['state'] == 'peak' else '谷时'}（{info['state_reason']}）",
    ]
    if info["action"] == "schedule":
        lines += [
            "动作：创建定时任务（schedule_create）",
            f"目标时刻：{info['target_human']}，距现在 {info['delta_human']}",
            '  at = {"date": "%s", "time": "%s", "time_zone": "Asia/Shanghai"}'
            % (info["target_date"], info["target_time"]),
        ]
    else:
        lines += [
            "动作：立即执行（run_now），不要建定时任务",
            f"起点：现在 + 1 分钟（{info['target_human']}）",
        ]
    lines.append(f"依据：{info['reason']}")
    lines.extend(info["warnings"])
    return "\n".join(lines)


CASES = [
    # (now, 期望 action, 期望 target, wait_next)
    ("2026-11-02T10:30:00+08:00", "schedule", "2026-11-02T12:00:00+08:00", False),
    ("2026-11-02T15:10:00+08:00", "schedule", "2026-11-02T18:00:00+08:00", False),
    ("2026-11-02T11:59:00+08:00", "schedule", "2026-11-02T12:00:00+08:00", False),
    ("2026-11-04T09:00:00+08:00", "schedule", "2026-11-04T12:00:00+08:00", False),
    ("2026-11-02T12:00:00+08:00", "run_now", None, False),
    ("2026-11-02T18:00:00+08:00", "run_now", None, False),
    ("2026-11-02T07:30:00+08:00", "run_now", None, False),
    ("2026-11-02T13:00:00+08:00", "run_now", None, False),
    ("2026-11-02T20:00:00+08:00", "run_now", None, False),
    ("2026-11-07T10:00:00+08:00", "run_now", None, False),   # 周六
    ("2026-11-08T15:00:00+08:00", "run_now", None, False),   # 周日
    ("2026-02-17T10:30:00+08:00", "run_now", None, False),   # 春节假期（周二）
    ("2026-01-04T10:30:00+08:00", "run_now", None, False),   # 周日调休上班
    ("2026-11-02T07:30:00+08:00", "schedule", "2026-11-02T12:00:00+08:00", True),
    ("2027-03-02T10:30:00+08:00", "schedule", "2027-03-02T12:00:00+08:00", False),  # 缺 2027 数据 → 告警
]


def selftest() -> int:
    holidays, covered, _ = load_holidays()
    failed = 0
    for now_s, want_action, want_target, wait_next in CASES:
        info = compute(parse_now(now_s), holidays, covered, wait_next)
        ok = info["action"] == want_action and (want_target is None or info["target"] == want_target)
        if not ok:
            failed += 1
            print(f"FAIL {now_s} wait_next={wait_next}: got {info['action']} {info['target']}, want {want_action} {want_target}")
        else:
            print(f"ok   {now_s} wait_next={wait_next} -> {info['action']} {info['target']}")
    # 2027 数据缺失必须告警
    info = compute(parse_now("2027-03-02T10:30:00+08:00"), holidays, covered)
    if not any("2027" in w for w in info["warnings"]):
        failed += 1
        print("FAIL 2027 数据缺失未告警")
    else:
        print("ok   2027 数据缺失告警")
    print(f"\n{'全部通过' if failed == 0 else f'{failed} 个用例失败'}")
    return 0 if failed == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="计算下一个 DeepSeek 谷时起点（北京时间）")
    ap.add_argument("--now", help="基准时间，ISO 8601，例如 2026-11-02T10:30:00+08:00")
    ap.add_argument("--wait-next", action="store_true", help="已在谷时也强制等下一段谷时起点")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--selftest", action="store_true", help="运行回归测试")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    holidays, covered, _ = load_holidays()
    info = compute(parse_now(args.now), holidays, covered, args.wait_next)
    print(json.dumps(info, ensure_ascii=False, indent=2) if args.json else render(info))
    return 0


if __name__ == "__main__":
    sys.exit(main())
