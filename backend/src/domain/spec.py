"""有轨电车路口阻断计数预测的共享配置。"""

SPEC = {
    "title": "有轨电车路口阻断计数预测",
    "short_name": "tram-poisson",
    "subtitle": "按实际过车量校准阻断风险，给下一轮路口巡查排班。",
    "organization": "澄浦有轨电车 2 号线行车调度组，负责港湾路与科创大道沿线的四处平交路口。",
    "workflow": (
        "调度员将信号系统过车量与值班员确认的阻断事件按路口、日期、时段合并成 CSV，"
        "信号台停测单单独导入并与逐窗观测对账。班前会上用训练期检出全线阻断率断点、"
        "用留出期检验末段计数预测，将道路负荷和具体路口交给信号班与沿线巡查员。"
    ),
    "pains": [
        "直接比较阻断次数，会把车次多的路口排得过高。",
        "停测窗口若当成零阻断，会拉低每车次阻断率的估计。",
        "阻断率换档后仍用全程均值，留出评分和巡查排班都会失真。",
    ],
    "steps": [
        "11 月 21 日 08:10，汇总 11 月 7–20 日的过车与阻断值班记录，并取回信号台停测单。",
        "在「过车与阻断台账」导入「澄浦2号线过车与阻断_20261107-20.csv」与停测单，确认 111 个观测窗口和 4 条停测记录。",
        "在「阻断模型试算」设定留出最近 3 个观测日、断点罚分 12，重点阈值填每百车次 9 次。",
        "在「路段与路口风险」核对全线断点日期、停测剔除窗口和 11 月 18–20 日留出评分。",
        "查看各段分路口每百车次阻断率，再按路段和路口核对同等过车量下的预计阻断次数。",
        "在「巡查排期复核」记录要跟进的路口和相应时段，交由信号班确认排班。",
        "在「排班依据导出」下载 CSV；源数据一旦更新，旧结论立即失效，重算完成后才出新依据。",
    ],
    "methodology": [
        "一行是一个日期、道路、路口、时段的观测窗口。阻断次数为确认事件数，暴露量为同窗口实际过车车次。",
        "信号台停测单按日期、道路、路口、时段与逐窗观测对账；停测窗剔除出拟合与评分，不计为零阻断，无对应观测的停测记录也会列出。",
        "按日期整组留出最近若干观测日。仅用训练日搜索全线共用断点，每段每个路口至少三天有效观测。",
        "每段分路口拟合每车次阻断率（阻断数÷过车车次），目标为训练期泊松偏差加每个断点的罚分，取全局最小；打平时选断点更少、日期更早的方案。",
        "留出期只用末段阻断率预测，逐窗报告泊松偏差，越低越好。",
        "巡查表以留出期过车量编制同等工作量情景，按每百车次预计率达到阈值为重点、两倍阈值为优先。源数据更新后旧结论立即失效，重算完成才导出新的排班依据。",
    ],
    "sample_name": "澄浦2号线过车与阻断_20261107-20.csv",
    "outage_sample_name": "澄浦2号线信号台停测单_20261107-20.csv",
    "default_dataset": "澄浦 2 号线 11 月 7–20 日路口记录",
    "entity": "路口观测窗口",
    "run": "阻断模型试算",
    "decision": "巡查排期复核",
    "action": "提交巡查排期",
    "modes": ["安排重点巡查", "补录观测后复算", "纳入常规巡查"],
    "pages": ["行车调度总览", "过车与阻断台账", "阻断模型试算", "路段与路口风险", "巡查排期复核", "排班依据导出"],
    "fields": [
        {"key": "date", "label": "观测日期", "type": "date", "required": True},
        {"key": "road", "label": "道路", "type": "string", "required": True, "max_length": 80},
        {"key": "intersection", "label": "路口", "type": "string", "required": True, "max_length": 80},
        {"key": "shift", "label": "时段", "type": "select", "required": True, "options": ["平峰", "高峰"]},
        {"key": "track", "label": "通行方式", "type": "select", "required": True, "options": ["独立通行", "混行"]},
        {"key": "exposure", "label": "实际过车车次", "type": "int", "required": True, "min": 1, "max": 10000},
        {"key": "count", "label": "确认阻断次数", "type": "int", "required": True, "min": 0, "max": 10000},
    ],
    "outage_fields": [
        {"key": "date", "label": "停测日期", "type": "date", "required": True},
        {"key": "road", "label": "道路", "type": "string", "required": True, "max_length": 80},
        {"key": "intersection", "label": "路口", "type": "string", "required": True, "max_length": 80},
        {"key": "shift", "label": "停测时段", "type": "select", "required": True, "options": ["平峰", "高峰", "全天"]},
        {"key": "reason", "label": "停测原因", "type": "string", "required": True, "max_length": 120},
    ],
    "params": [
        {"key": "holdout_days", "label": "留出观测日数", "type": "int", "required": True,
         "min": 1, "max": 90, "default": 3, "help": "从最新日期开始按有有效观测的日期留出，至少保留一个训练日。"},
        {"key": "breakpoint_penalty", "label": "断点罚分", "type": "number", "required": True,
         "min": 0, "max": 100000, "default": 12,
         "help": "目标函数＝训练期泊松偏差＋罚分×断点数。罚分越大越倾向少断点，可调整。"},
        {"key": "severity_rate", "label": "重点阈值（次／百车次）", "type": "number", "required": True,
         "min": 0.1, "max": 1000, "default": 9, "help": "达到阈值为重点，达到两倍阈值为优先。"},
    ],
    "fixture": {"holdout_days": 2, "breakpoint_penalty": 12, "severity_rate": 8},
    "axes": "分段率图纵轴为每百车次阻断率。留出偏差图纵轴为每窗口平均 Poisson 偏差。",
}
