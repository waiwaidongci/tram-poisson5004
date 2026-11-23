"""信号台停测对账、全线共用断点检测与末段留出评分。"""

from collections import defaultdict
from datetime import date
from math import fsum, log

from .spec import SPEC


_MAX_ROWS = 5000
_MAX_OUTAGES = 2000
_MIN_SEGMENT_DAYS = 3
_TIE_REL = 1e-9
_TIE_ABS = 1e-12


def _validate_field(field, value):
    kind = field["type"]
    label = field["label"]
    if kind in {"int", "number"}:
        types = (int,) if kind == "int" else (int, float)
        if type(value) not in types or not field["min"] <= value <= field["max"]:
            unit = "整数" if kind == "int" else "数值"
            raise ValueError(f"{label}须为 {field['min']} 至 {field['max']} 之间的{unit}")
    elif kind == "date":
        try:
            if not isinstance(value, str) or len(value) != 10 or date.fromisoformat(value).isoformat() != value:
                raise ValueError
        except ValueError:
            raise ValueError(f"{label}须为有效的 YYYY-MM-DD 日期") from None
    elif kind == "select":
        if value not in field["options"]:
            raise ValueError(f"{label}须为{'、'.join(field['options'])}之一")
    elif not isinstance(value, str) or len(value) > field["max_length"] or not value.strip():
        raise ValueError(f"{label}须为非空文本，最多 {field['max_length']} 字符")
    return value.strip() if kind == "string" else value


def validate_rows(rows):
    if not isinstance(rows, (list, tuple)) or not 1 <= len(rows) <= _MAX_ROWS:
        raise ValueError(f"观测台账须包含 1 至 {_MAX_ROWS} 行")
    readings = {}
    for index, row in enumerate(rows, start=1):
        try:
            if not isinstance(row, dict):
                raise ValueError("须为一条观测记录")
            clean = {field["key"]: _validate_field(field, row.get(field["key"])) for field in SPEC["fields"]}
            window = (clean["date"], clean["road"], clean["intersection"], clean["shift"])
            if window in readings:
                raise ValueError("日期、道路、路口与时段重复")
            readings[window] = clean
        except ValueError as error:
            raise ValueError(f"第 {index} 条观测 · {error}") from None
    return [readings[key] for key in sorted(readings)]


def validate_outages(records):
    if records is None:
        return []
    if not isinstance(records, (list, tuple)) or len(records) > _MAX_OUTAGES:
        raise ValueError(f"停测单须包含 0 至 {_MAX_OUTAGES} 行")
    seen = {}
    for index, record in enumerate(records, start=1):
        try:
            if not isinstance(record, dict):
                raise ValueError("须为一条停测记录")
            clean = {field["key"]: _validate_field(field, record.get(field["key"])) for field in SPEC["outage_fields"]}
            key = (clean["date"], clean["road"], clean["intersection"], clean["shift"])
            if key in seen:
                raise ValueError("日期、道路、路口与停测时段重复")
            seen[key] = clean
        except ValueError as error:
            raise ValueError(f"第 {index} 条停测记录 · {error}") from None
    return [seen[key] for key in sorted(seen)]


def _reconcile(readings, outages):
    """停测单与逐窗观测跨系统对账：停测窗剔除，不能当零阻断。"""
    notices = defaultdict(list)
    for index, outage in enumerate(outages):
        notices[(outage["date"], outage["road"], outage["intersection"])].append(index)
    hits = [0] * len(outages)
    valid, excluded = [], []
    for row in readings:
        covering = [index for index in notices.get((row["date"], row["road"], row["intersection"]), ())
                    if outages[index]["shift"] in ("全天", row["shift"])]
        if covering:
            for index in covering:
                hits[index] += 1
            excluded.append({**row, "reason": "；".join(outages[index]["reason"] for index in covering)})
        else:
            valid.append(row)
    ledger = [{**outage, "matched": hits[index],
               "result": f"剔除 {hits[index]} 个观测窗" if hits[index] else "无对应观测窗"}
              for index, outage in enumerate(outages)]
    return valid, excluded, ledger


def _prefix(values):
    total = [0.0]
    for value in values:
        total.append(total[-1] + value)
    return total


def _better(candidate, current):
    """打平时选断点更少、日期更早的方案。"""
    objective, breaks, points = candidate
    reference, reference_breaks, reference_points = current
    tolerance = _TIE_ABS + _TIE_REL * max(abs(objective), abs(reference))
    if objective < reference - tolerance:
        return True
    if objective > reference + tolerance:
        return False
    return (breaks, points) < (reference_breaks, reference_points)


def _changepoints(training, penalty):
    """仅用训练日搜索全线共用断点，目标＝泊松偏差＋罚分×断点数，动态规划取全局最小。"""
    days = sorted({row["date"] for row in training})
    intersections = sorted({(row["road"], row["intersection"]) for row in training})
    position = {day: index for index, day in enumerate(days)}
    counts = {key: [0] * len(days) for key in intersections}
    exposure = {key: [0] * len(days) for key in intersections}
    weighted = {key: [0.0] * len(days) for key in intersections}
    present = {key: [0] * len(days) for key in intersections}
    for row in training:
        key = (row["road"], row["intersection"])
        slot = position[row["date"]]
        counts[key][slot] += row["count"]
        exposure[key][slot] += row["exposure"]
        if row["count"]:
            weighted[key][slot] += row["count"] * log(row["count"] / row["exposure"])
        present[key][slot] = 1
    series = {key: tuple(_prefix(values) for values in (counts[key], exposure[key], weighted[key], present[key]))
              for key in intersections}

    def segment_cost(start, end):
        """[start, end) 段的泊松偏差；任一路口有效观测日不足三天则整段不可行。"""
        total = 0.0
        for key in intersections:
            count_p, exposure_p, weighted_p, present_p = series[key]
            if present_p[end] - present_p[start] < _MIN_SEGMENT_DAYS:
                return None
            count = count_p[end] - count_p[start]
            if count:
                segment_exposure = exposure_p[end] - exposure_p[start]
                total += max(0.0, 2.0 * (weighted_p[end] - weighted_p[start]
                                         - count * log(count / segment_exposure)))
        return total

    size = len(days)
    best = [None] * (size + 1)
    best[0] = (0.0, 0, ())
    for end in range(1, size + 1):
        for start in range(end):
            if best[start] is None:
                continue
            cost = segment_cost(start, end)
            if cost is None:
                continue
            candidate = (best[start][0] + cost + (penalty if start else 0.0),
                         best[start][1] + (1 if start else 0),
                         best[start][2] + ((start,) if start else ()))
            if best[end] is None or _better(candidate, best[end]):
                best[end] = candidate
    if best[size] is None:
        raise ValueError(f"训练期每个路口每段至少需要 {_MIN_SEGMENT_DAYS} 天有效观测，请缩短留出或补充观测。")
    bounds = (0, *best[size][2], size)
    segments = []
    for index, (start, end) in enumerate(zip(bounds, bounds[1:]), start=1):
        rates = {}
        for key in intersections:
            count_p, exposure_p, _, present_p = series[key]
            count = count_p[end] - count_p[start]
            segment_exposure = exposure_p[end] - exposure_p[start]
            rates[key] = {"count": count, "exposure": segment_exposure,
                          "days": int(present_p[end] - present_p[start]),
                          "rate": count / segment_exposure}
        segments.append({"index": index, "start": days[start], "end": days[end - 1],
                         "cost": segment_cost(start, end), "rates": rates})
    return {"days": days, "intersections": intersections, "segments": segments,
            "objective": best[size][0], "breakpoints": [days[point] for point in best[size][2]],
            "deviance": fsum(segment["cost"] for segment in segments)}


def _deviance(count, expected):
    if count == 0:
        return 2 * expected
    return max(0.0, 2 * (count * (log(count) - log(expected)) - count + expected))


def _planning(windows, keys, threshold):
    groups = defaultdict(list)
    for row in windows:
        groups[tuple(row[key] for key in keys)].append(row)
    plan = []
    for group, records in groups.items():
        exposure = sum(row["exposure"] for row in records)
        expected = fsum(row["predicted"] for row in records)
        rate = 100 * expected / exposure
        severity = sum(rate >= limit for limit in (threshold, 2 * threshold))
        plan.append({
            **dict(zip(keys, group)), "exposure": exposure, "predicted": expected,
            "rate": rate, "severity": ("常规", "重点", "优先")[severity],
            "action": ("按常规频次抽查", "增排路口巡查", "优先复核放行相位与混行冲突")[severity],
        })
    return sorted(plan, key=lambda row: (-row["predicted"], -row["rate"], *(row[key] for key in keys)))


def _table(title, columns, rows):
    return {"title": title, "columns": [{"key": key, "label": label} for key, label in columns], "rows": rows}


def analyze(rows, outages, normalized_params):
    readings = validate_rows(rows)
    notices = validate_outages(outages)
    if set(normalized_params) - {field["key"] for field in SPEC["params"]}:
        raise ValueError("存在未知运行参数")
    params = {field["key"]: _validate_field(field, normalized_params.get(field["key"], field["default"]))
              for field in SPEC["params"]}
    valid, excluded, ledger = _reconcile(readings, notices)
    if not valid:
        raise ValueError("对账后没有有效观测窗：所有窗口都被停测单覆盖，请核对停测单。")
    days = sorted({row["date"] for row in valid})
    holdout_days = params["holdout_days"]
    if len(days) <= holdout_days:
        raise ValueError("留出观测日数须少于有效观测的不同日期数，以保留训练数据。")
    cutoff = days[-holdout_days]
    training = [row for row in valid if row["date"] < cutoff]
    holdout = [row for row in valid if row["date"] >= cutoff]
    penalty = params["breakpoint_penalty"]
    search = _changepoints(training, penalty)
    last = search["segments"][-1]["rates"]
    windows, scored = [], []
    unseen = zero_rate = 0
    for row in holdout:
        key = (row["road"], row["intersection"])
        entry = {**row, "predicted": None, "deviance": None, "note": ""}
        if key not in last:
            entry["note"] = "路口未见于训练期"
            unseen += 1
        elif not last[key]["rate"] and row["count"]:
            entry["predicted"] = 0.0
            entry["note"] = "末段率为零，无法评分"
            zero_rate += 1
        else:
            expected = last[key]["rate"] * row["exposure"]
            entry["predicted"] = expected
            entry["deviance"] = _deviance(row["count"], expected)
            scored.append(entry["deviance"])
        windows.append(entry)
    if not scored:
        raise ValueError("留出期没有可评分的有效窗口，请核对停测单与训练期路口覆盖。")
    mean_deviance = fsum(scored) / len(scored)
    threshold = params["severity_rate"]
    scored_windows = [row for row in windows if row["predicted"] is not None]
    roads = _planning(scored_windows, ("road",), threshold)
    intersections = _planning(scored_windows, ("road", "intersection"), threshold)
    focus = intersections[0]
    breakpoints = search["breakpoints"]
    unmatched = sum(1 for row in ledger if not row["matched"])
    plan_columns = (("exposure", "情景车次"), ("predicted", "预计阻断次数"), ("rate", "预计次／百车次"),
                    ("severity", "巡查级别"), ("action", "排班动作"))
    segment_rows = [
        {"segment": segment["index"], "start": segment["start"], "end": segment["end"],
         "days": min(rate["days"] for rate in segment["rates"].values()),
         "count": sum(rate["count"] for rate in segment["rates"].values()),
         "exposure": sum(rate["exposure"] for rate in segment["rates"].values()),
         "rate": 100 * sum(rate["count"] for rate in segment["rates"].values())
                 / sum(rate["exposure"] for rate in segment["rates"].values())}
        for segment in search["segments"]
    ]
    rate_rows = [
        {"segment": segment["index"], "road": road, "intersection": intersection,
         "days": rate["days"], "count": rate["count"], "exposure": rate["exposure"],
         "rate": 100 * rate["rate"]}
        for segment in search["segments"]
        for (road, intersection), rate in segment["rates"].items()
    ]
    daily = defaultdict(list)
    for row in windows:
        if row["deviance"] is not None:
            daily[row["date"]].append(row["deviance"])
    note = (f"训练 {days[0]} 至 {training[-1]['date']}，留出 {cutoff} 至 {days[-1]}。"
            f"断点罚分 {penalty:g}／个，停测剔除 {len(excluded)} 窗。"
            f"重点阈值 {threshold:g} 次／百车次，优先阈值 {2 * threshold:g} 次／百车次。")
    if breakpoints:
        headline = f"全线阻断率自 {'、'.join(breakpoints)} 起换档，训练期共 {len(breakpoints)} 个断点。"
    else:
        headline = "训练期内未检出全线阻断率换档。"
    return {
        "state": "warning" if unseen or zero_rate else "ok",
        "headline": f"{headline}{focus['road']} · {focus['intersection']}末段工作量最高。",
        "note": note,
        "breakpoints": breakpoints,
        "metrics": [
            {"label": "训练窗口", "value": len(training),
             "detail": f"{len(days) - holdout_days} 个观测日 · 每段每路口至少 {_MIN_SEGMENT_DAYS} 天有效观测"},
            {"label": "留出窗口", "value": len(holdout),
             "detail": f"{holdout_days} 个观测日 · {unseen + zero_rate} 个窗口无法评分"},
            {"label": "断点数", "value": len(breakpoints),
             "detail": "、".join(breakpoints) if breakpoints else "未检出换档"},
            {"label": "罚分后目标值", "value": search["objective"],
             "detail": f"训练偏差 {search['deviance']:.4g}＋罚分 {penalty:g}×{len(breakpoints)}"},
            {"label": "留出平均偏差", "value": mean_deviance,
             "detail": "末段率预测 · 留出期每窗口 Poisson 偏差"},
            {"label": "停测剔除窗口", "value": len(excluded),
             "detail": f"{len(ledger)} 条停测记录 · {unmatched} 条无对应观测"},
        ],
        "charts": [
            {"title": "全线分段阻断率（次／百车次）", "kind": "bar", "series": [
                {"label": f"{row['start']}～{row['end']}", "value": row["rate"]} for row in segment_rows]},
            {"title": "末段分路口阻断率（次／百车次）", "kind": "bar", "series": [
                {"label": f"{row['road']} · {row['intersection']}", "value": row["rate"]}
                for row in rate_rows if row["segment"] == len(search["segments"])]},
            {"title": "留出期每日平均 Poisson 偏差", "kind": "line", "series": [
                {"label": day, "value": fsum(values) / len(values)} for day, values in sorted(daily.items())]},
        ],
        "tables": [
            _table("全线分段与断点", (("segment", "段次"), ("start", "起始日期"), ("end", "截至日期"),
                   ("days", "有效观测日（最少路口）"), ("count", "确认阻断"), ("exposure", "过车车次"),
                   ("rate", "全线次／百车次")), segment_rows),
            _table("分路口分段阻断率", (("segment", "段次"), ("road", "道路"), ("intersection", "路口"),
                   ("days", "有效观测日"), ("count", "确认阻断"), ("exposure", "过车车次"),
                   ("rate", "次／百车次")), rate_rows),
            _table("停测对账", (("date", "停测日期"), ("road", "道路"), ("intersection", "路口"),
                   ("shift", "停测时段"), ("reason", "停测原因"), ("result", "对账结果")), ledger),
            _table("停测剔除窗口（不计为零阻断）",
                   tuple((field["key"], field["label"]) for field in SPEC["fields"]) + (("reason", "停测原因"),),
                   excluded),
            _table("留出窗口核对（只用末段预测）",
                   tuple((field["key"], field["label"]) for field in SPEC["fields"]) + (
                       ("predicted", "末段预计次数"), ("deviance", "泊松偏差"), ("note", "核对标记")), windows),
            _table("道路巡查计划", (("road", "道路"),) + plan_columns, roads),
            _table("路口巡查计划", (("road", "道路"), ("intersection", "路口")) + plan_columns, intersections),
        ],
        "sections": [
            {"title": "对账口径", "text": "信号台停测单按日期、道路、路口、时段与逐窗观测对账。"
             "停测窗剔除出拟合与评分，不计为零阻断；无对应观测的停测记录在对账表中单独列出。"},
            {"title": "断点口径", "text": "断点全线共用，仅用训练日搜索；每段每个路口至少三天有效观测。"
             "目标为训练期泊松偏差加每个断点的罚分，动态规划求全局最小；打平时选断点更少、日期更早的方案。"
             "留出期只用末段阻断率预测。"},
            {"title": "排班口径", "text": "巡查表复用留出期的过车车次，按末段率折算预计阻断次数排序。"
             "路段和路口各自按每百车次的预计率达到阈值为重点、两倍阈值为优先。源数据更新后本结论立即失效，"
             "重算完成才导出新的排班依据。"},
        ],
    }
