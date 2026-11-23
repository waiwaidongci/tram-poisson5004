"""澄浦 2 号线的可复现观测台账与信号台停测单。"""

from datetime import date, timedelta
from math import exp
from random import Random


# 11 月 14 日起科创大道施工，港湾路分流混行冲突加剧，全线阻断率换档。
_INTERSECTIONS = (
    ("港湾路", "货栈街口", "混行", 0.10, 0.22),
    ("港湾路", "渡口街口", "混行", 0.085, 0.19),
    ("科创大道", "智造街口", "独立通行", 0.045, 0.025),
    ("科创大道", "东环街口", "独立通行", 0.04, 0.022),
)

_CHANGE = "2026-11-14"

# 停测窗：台账里仍有记录但读数不可信，对账时必须剔除，不能当零阻断。
_OUTAGED = {
    ("2026-11-10", "港湾路", "货栈街口", "平峰"),
    ("2026-11-12", "科创大道", "智造街口", "平峰"),
    ("2026-11-12", "科创大道", "智造街口", "高峰"),
    ("2026-11-19", "港湾路", "渡口街口", "高峰"),
}

# 该窗停测且值班员未生成台账记录，对账时应列为无对应观测。
_ABSENT = ("2026-11-16", "科创大道", "东环街口", "平峰")


def _poisson(rng, mean):
    limit = exp(-mean)
    product = rng.random()
    count = 0
    while product > limit:
        product *= rng.random()
        count += 1
    return count


def demo_rows():
    rng = Random(261160)
    rows = []
    for day in range(14):
        stamp = (date(2026, 11, 7) + timedelta(days=day)).isoformat()
        for road, intersection, track, before, after in _INTERSECTIONS:
            for shift in ("平峰", "高峰"):
                if (stamp, road, intersection, shift) == _ABSENT:
                    continue
                peak = shift == "高峰"
                exposure = (38 if peak else 20) + rng.randrange(13)
                if (stamp, road, intersection, shift) in _OUTAGED:
                    # 停测窗：过车量记录不全、阻断无确认，不能当零阻断
                    rows.append({
                        "date": stamp, "road": road, "intersection": intersection,
                        "shift": shift, "track": track,
                        "exposure": max(1, exposure // 6), "count": 0,
                    })
                    continue
                rate = (after if stamp >= _CHANGE else before) * (1.5 if peak else 1.0)
                rows.append({
                    "date": stamp, "road": road, "intersection": intersection,
                    "shift": shift, "track": track, "exposure": exposure,
                    "count": _poisson(rng, exposure * rate),
                })
    return rows


def demo_outages():
    return [
        {"date": "2026-11-10", "road": "港湾路", "intersection": "货栈街口", "shift": "平峰",
         "reason": "信号机年检"},
        {"date": "2026-11-12", "road": "科创大道", "intersection": "智造街口", "shift": "全天",
         "reason": "联锁关系试验"},
        {"date": "2026-11-16", "road": "科创大道", "intersection": "东环街口", "shift": "平峰",
         "reason": "计轴器更换，未生成观测"},
        {"date": "2026-11-19", "road": "港湾路", "intersection": "渡口街口", "shift": "高峰",
         "reason": "通信中断"},
    ]
