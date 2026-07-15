"""Stress-test NewAPI: N requests/second, ~500-char unique multi-domain prompts.

Reports reply length (chars) and end-to-end latency for each request.
Question bank v2: expanded domains/topics/angles (distinct from the first run).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_URL = os.environ.get("API_BASE_URL", "https://newapi-jp2.xiaoqianran.xyz").rstrip("/")
# Prefer env; never commit real keys. Falls back to GOD_LLM_* if set in shell.
API_KEY = (
    os.environ.get("API_KEY")
    or os.environ.get("GOD_LLM_API_KEY")
    or ""
)
MODEL = os.environ.get("MODEL") or os.environ.get("GOD_LLM_MODEL") or "openai/gpt-oss-120b"

# --- Multi-domain prompt builders v2 (unique ~500 Chinese chars each) ---
# Completely refreshed topics vs v1 so repeated stress runs don't recycle the same set.

DOMAINS: dict[str, list[str]] = {
    "科技": [
        "多模态大模型对齐",
        "存算一体架构",
        "卫星互联网组网",
        "零信任安全体系",
        "生成式设计工具",
        "具身智能机器人",
        "隐私计算联邦学习",
        "低空经济与无人机",
        "脑机接口应用边界",
        "开源模型合规治理",
        "数字孪生工厂",
        "Web3身份体系",
    ],
    "医学": [
        "精准医疗分层",
        "阿尔茨海默早期筛查",
        "细胞与基因疗法定价",
        "院前急救协同",
        "罕见病诊断路径",
        "抗菌药物合理使用",
        "远程会诊质量控制",
        "围手术期风险管理",
        "妇幼保健体系",
        "职业病防护",
        "中西医结合证据",
        "临终关怀伦理",
    ],
    "经济": [
        "新质生产力测算",
        "平台经济反垄断",
        "银发经济业态",
        "跨境电商合规",
        "产业补贴有效性",
        "汇率波动传导",
        "地方债化解路径",
        "共享经济劳动权益",
        "碳市场交易机制",
        "创投退出渠道",
        "服务贸易逆差",
        "消费信贷风险",
    ],
    "教育": [
        "AI助教进课堂",
        "拔尖创新人才培养",
        "县域高中振兴",
        "研究生扩招质量",
        "家校社协同育人",
        "特殊教育融合",
        "教材审定与多元",
        "留学回流就业",
        "劳动教育落地",
        "科学素养测评",
        "职业教育产教融合",
        "教师数字素养",
    ],
    "历史": [
        "茶马古道网络",
        "印刷术传播影响",
        "郑和下西洋动因",
        "洋务运动局限",
        "民国城市化",
        "二战后国际秩序",
        "游牧与农耕互动",
        "殖民遗产与独立",
        "疫病与社会变迁",
        "海上丝绸之路节点",
        "科举制社会流动",
        "冷战科技竞赛",
    ],
    "法律": [
        "深度伪造法律责任",
        "算法推荐规制",
        "竞业限制合理性",
        "个人信息出境评估",
        "直播带货虚假宣传",
        "自动驾驶事故归责",
        "开源许可证纠纷",
        "网络安全等级保护",
        "未成年人网络保护",
        "ESG信息披露义务",
        "跨境电商消费税",
        "平台二选一垄断",
    ],
    "环境": [
        "蓝碳生态系统",
        "光伏沙漠化争议",
        "城市海绵改造",
        "微塑料人体暴露",
        "氢能储运安全",
        "森林碳汇计量",
        "重工业超低排放",
        "气候移民安置",
        "地下水超采治理",
        "厨余垃圾资源化",
        "核电退役管理",
        "生态补偿机制",
    ],
    "心理": [
        "完美主义陷阱",
        "FOMO与决策疲劳",
        "内耗与自我同情",
        "远程办公孤独感",
        "原生家庭影响",
        "习得性无助",
        "心流与刻意练习",
        "网络暴力心理创伤",
        "中年转型危机",
        "睡眠与情绪循环",
        "团队心理安全",
        "正念科学证据",
    ],
    "工程": [
        "超高层消防疏散",
        "微服务可观测性",
        "高铁轮轨关系",
        "深基坑支护",
        "芯片封装散热",
        "海上风电运维",
        "智慧城市传感网",
        "长距离输水渗漏",
        "电池热失控防护",
        "DevOps变更风险",
        "隧道盾构施工",
        "工业互联网时延",
    ],
    "文化": [
        "短视频叙事伦理",
        "城市夜经济文化",
        "方言保护与媒体",
        "独立书店生存",
        "游戏文化出海",
        "文旅IP开发边界",
        "古典园林当代转译",
        "粉丝文化治理",
        "公共艺术介入社区",
        "口述史采集方法",
        "美食纪录片传播",
        "二次元与主流对话",
    ],
    "体育": [
        "科学减脂与代谢",
        "马拉松大众化风险",
        "冬奥遗产利用",
        "校园足球体系",
        "运动心理韧性",
        "伤病复出评估",
        "女子体育平等",
        "虚拟体育与元宇宙",
        "青训选拔偏差",
        "体育博彩监管",
        "残奥无障碍设施",
        "高温赛事保障",
    ],
    "哲学": [
        "有效利他主义批评",
        "技术中立性神话",
        "分配正义与运气",
        "意识难问题",
        "后真相时代知识",
        "动物道德地位",
        "算法决策问责",
        "死亡哲学与安宁",
        "公共理性协商",
        "进步叙事反思",
        "虚构与真实边界",
        "工作意义危机",
    ],
    "农业": [
        "种业卡脖子突破",
        "智慧温室调控",
        "土壤碳汇农业",
        "冷链保鲜损耗",
        "农村电商物流",
        "转基因公众沟通",
        "淡水养殖污染",
        "农机共享模式",
        "粮食安全储备",
        "乡土人才回流",
        "气象指数保险",
        "垂直农场能效",
    ],
    "传媒": [
        "深度报道生存空间",
        "算法分发议程设置",
        "事实核查机制",
        "播客商业化路径",
        "本地新闻荒漠化",
        "虚拟主播伦理",
        "版权集体管理",
        "危机公关透明度",
        "短剧内容治理",
        "跨国媒体话语权",
        "用户生成内容审核",
        "注意力经济批判",
    ],
    "交通": [
        "TOD城市综合开发",
        "电动车充电布局",
        "航空延误协同",
        "城市拥堵收费",
        "货运自动驾驶路权",
        "共享单车调度",
        "港口自动化效率",
        "铁路货运公转铁",
        "低空物流适航",
        "公交优先信号",
        "车路协同安全",
        "跨境班列时效",
    ],
    "管理": [
        "OKR落地变形",
        "远程混合办公制度",
        "中层管理者赋能",
        "组织沉默文化",
        "并购后文化整合",
        "精益创业试错",
        "供应链韧性KPI",
        "知识管理失效",
        "危机领导力",
        "多元化招聘偏差",
        "平台型组织治理",
        "创新预算分配",
    ],
}

ANGLE_TEMPLATES = [
    "请按「问题画像→约束条件→可选路径→风险对冲→验收指标」五段式完整展开。",
    "请先给出一句话结论，再分别用支持证据、反方观点、折中方案加以论证。",
    "请以决策备忘录口吻写作：明确推荐选项、放弃选项、以及触发改判的信号。",
    "请用「现象—机制—干预—评估」链条解释，并至少给出两个可落地的小步试点。",
    "请比较乐观、中性、悲观三种情景，说明关键假设变化时结论如何翻转。",
    "请从成本、收益、公平性、可执行性四个维度打分式讨论（文字说明即可，不必真打分表）。",
    "请识别至少三类利益相关方，分析其激励是否一致，以及如何设计对齐机制。",
    "请把复杂问题拆成可并行推进的子问题清单，并标明依赖关系与优先序。",
    "请指出该议题最容易被媒体简化的误导叙事，并给出更严谨的表述框架。",
    "请结合一个虚构但合理的城市/企业案例走完分析全流程，最后抽象出可迁移原则。",
]

FILLER_BLOCKS = [
    "写作约束：禁止空话套话；每个判断尽量对应可观察现象或可验证条件。",
    "若必须使用专业术语，首次出现时用括号给出不超过十五字的白话释义。",
    "请在回答中段设置一个「常见失败模式」小节，列出至少三条踩坑路径。",
    "请用中文作答；专有英文缩写保留原文并附中文全称一次。",
    "信息不足时请明确列出假设清单，而不是把猜测写成既定事实。",
    "请保证段落之间有逻辑递进，避免同义反复堆砌篇幅。",
    "结尾除总结外，再给出「两周内可启动」与「一年内应规划」两档行动建议。",
    "如涉及政策或技术路线，请同时点出路径依赖与沉没成本可能带来的锁定效应。",
]


def _pad_to_target(text: str, target: int = 500) -> str:
    """Pad with stable, domain-neutral instructions until length ≈ target."""
    pads = [
        "请确保论证链条完整，从前提到结论之间不要跳步。",
        "若信息不足，请说明缺少哪些关键信息以及它们如何影响判断。",
        "请优先给出可执行建议，而不是只停留在现象描述层面。",
        "请注意区分事实、推断与价值判断，并在措辞上加以区分。",
        "回复请尽量使用中文，必要时可保留英文专有名词并附简短解释。",
        "请控制术语密度，对首次出现的专业概念给出一句话定义。",
    ]
    i = 0
    while len(text) < target:
        text = text + pads[i % len(pads)]
        i += 1
    # Trim softly if we overshot a lot; keep >= target-5 if possible.
    if len(text) > target + 40:
        text = text[:target]
    return text


def build_unique_prompt(seq: int, rng: random.Random) -> tuple[str, str]:
    """Build a ~500-char unique multi-domain Chinese question."""
    domain = list(DOMAINS.keys())[seq % len(DOMAINS)]
    topics = DOMAINS[domain]
    topic = topics[seq % len(topics)]
    angle = ANGLE_TEMPLATES[seq % len(ANGLE_TEMPLATES)]
    filler = FILLER_BLOCKS[seq % len(FILLER_BLOCKS)]
    salt = rng.randint(10_000_000, 99_999_999)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")

    # Core question body — uniqueness comes from seq/domain/topic/salt/ts.
    core = (
        f"【压测请求#{seq:05d}|领域:{domain}|主题:{topic}|盐值:{salt}|时间戳:{ts}】"
        f"请围绕「{domain}领域中的{topic}」撰写一份结构化深度回答。"
        f"{angle}{filler}"
        f"本题编号为 {seq}，请在回答开头用一句话复述你理解的核心问题，"
        f"随后分点展开，字数不限但内容应充实、逻辑自洽。"
        f"额外约束：不要复述本段指令原文；不要编造虚假数据来源编号；"
        f"若需要举例，请使用公开常识性例子并标注为示意。"
    )
    prompt = _pad_to_target(core, target=500)
    return domain, prompt


@dataclass
class ResultRow:
    seq: int
    domain: str
    prompt_chars: int
    ok: bool
    http_status: int | None
    latency_ms: float
    reply_chars: int
    reply_chars_no_ws: int
    finish_reason: str | None
    model: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    content_preview: str
    error: str | None
    started_at: str
    ended_at: str


def chat_once(prompt: str, max_tokens: int, timeout: float) -> tuple[int, dict[str, Any] | str, float]:
    """POST one chat completion. Returns (status, parsed_or_raw, latency_ms)."""
    url = f"{BASE_URL}/v1/chat/completions"
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "max_tokens": max_tokens,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "curl/8.5.0",
            "Accept": "application/json",
        },
    )

    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        status = e.code
        latency_ms = (time.perf_counter() - t0) * 1000
        try:
            return status, json.loads(raw), latency_ms
        except json.JSONDecodeError:
            return status, raw, latency_ms
    except Exception as e:  # noqa: BLE001 — want full failure surface for stress test
        latency_ms = (time.perf_counter() - t0) * 1000
        return 0, f"{type(e).__name__}: {e}", latency_ms

    latency_ms = (time.perf_counter() - t0) * 1000
    try:
        return status, json.loads(raw), latency_ms
    except json.JSONDecodeError:
        return status, raw, latency_ms


def extract_content(data: dict[str, Any] | str) -> tuple[str, str | None, dict[str, int | None], str | None]:
    """Return content, finish_reason, usage dict, model.

    Reasoning models (e.g. gpt-oss) may put the only usable text in
    ``reasoning`` / ``reasoning_content`` while ``content`` is null — count that
    so stress results are not false "empty content" failures.
    """
    if isinstance(data, str):
        return "", None, {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None}, None
    choices = data.get("choices") or []
    content = ""
    finish_reason = None
    if choices:
        msg = choices[0].get("message") or {}
        raw_content = msg.get("content")
        if isinstance(raw_content, str) and raw_content.strip():
            content = raw_content
        else:
            for key in ("reasoning", "reasoning_content"):
                alt = msg.get(key)
                if isinstance(alt, str) and alt.strip():
                    content = alt
                    break
        finish_reason = choices[0].get("finish_reason")
    usage = data.get("usage") or {}
    usage_out = {
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }
    return content, finish_reason, usage_out, data.get("model")


def print_row(row: ResultRow) -> None:
    status = "OK" if row.ok else "FAIL"
    print(
        f"[{row.seq:05d}] {status} domain={row.domain} "
        f"prompt={row.prompt_chars}字 "
        f"reply={row.reply_chars}字 (去空白{row.reply_chars_no_ws}) "
        f"latency={row.latency_ms:.0f}ms "
        f"http={row.http_status} "
        f"tokens={row.prompt_tokens}/{row.completion_tokens}/{row.total_tokens} "
        f"finish={row.finish_reason}"
        + (f" err={row.error}" if row.error else ""),
        flush=True,
    )


def summarize(rows: list[ResultRow]) -> dict[str, Any]:
    ok_rows = [r for r in rows if r.ok]
    fail_rows = [r for r in rows if not r.ok]
    latencies = [r.latency_ms for r in ok_rows]
    reply_chars = [r.reply_chars for r in ok_rows]

    def pct(xs: list[float], p: float) -> float | None:
        if not xs:
            return None
        ys = sorted(xs)
        k = min(len(ys) - 1, max(0, int(round((p / 100) * (len(ys) - 1)))))
        return ys[k]

    summary: dict[str, Any] = {
        "total": len(rows),
        "ok": len(ok_rows),
        "fail": len(fail_rows),
        "success_rate": (len(ok_rows) / len(rows) * 100) if rows else 0.0,
        "latency_ms": {
            "min": min(latencies) if latencies else None,
            "max": max(latencies) if latencies else None,
            "avg": statistics.fmean(latencies) if latencies else None,
            "p50": pct(latencies, 50),
            "p90": pct(latencies, 90),
            "p99": pct(latencies, 99),
        },
        "reply_chars": {
            "min": min(reply_chars) if reply_chars else None,
            "max": max(reply_chars) if reply_chars else None,
            "avg": statistics.fmean(reply_chars) if reply_chars else None,
        },
        "http_status_counts": {},
        "domain_ok_fail": {},
    }
    for r in rows:
        key = str(r.http_status)
        summary["http_status_counts"][key] = summary["http_status_counts"].get(key, 0) + 1
        d = summary["domain_ok_fail"].setdefault(r.domain, {"ok": 0, "fail": 0})
        d["ok" if r.ok else "fail"] += 1
    return summary


def print_summary(summary: dict[str, Any]) -> None:
    print("\n" + "=" * 72)
    print("压测汇总")
    print("=" * 72)
    print(
        f"总数={summary['total']}  成功={summary['ok']}  失败={summary['fail']}  "
        f"成功率={summary['success_rate']:.1f}%"
    )
    lat = summary["latency_ms"]
    rep = summary["reply_chars"]
    print(
        "时延(ms): "
        f"min={_fmt(lat['min'])} avg={_fmt(lat['avg'])} "
        f"p50={_fmt(lat['p50'])} p90={_fmt(lat['p90'])} p99={_fmt(lat['p99'])} "
        f"max={_fmt(lat['max'])}"
    )
    print(
        "回复字数: "
        f"min={_fmt(rep['min'], 0)} avg={_fmt(rep['avg'], 1)} max={_fmt(rep['max'], 0)}"
    )
    print(f"HTTP状态: {summary['http_status_counts']}")
    print(f"分领域: {summary['domain_ok_fail']}")
    print("=" * 72)


def _fmt(v: float | None, digits: int = 1) -> str:
    if v is None:
        return "-"
    if digits == 0:
        return str(int(round(v)))
    return f"{v:.{digits}f}"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="1 QPS multi-domain stress test for chat API")
    p.add_argument("-n", "--count", type=int, default=30, help="总请求数 (default: 30)")
    p.add_argument(
        "--rps",
        type=float,
        default=1.0,
        help="目标发送速率：每秒发起多少请求 (default: 1.0)",
    )
    p.add_argument(
        "--max-tokens",
        type=int,
        default=2048,
        help="completion max_tokens (default: 2048)",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=180.0,
        help="单请求超时秒数 (default: 180)",
    )
    p.add_argument(
        "--seed",
        type=int,
        default=42,
        help="随机种子，保证问题可复现但仍随 seq 唯一",
    )
    p.add_argument(
        "--out",
        type=str,
        default="",
        help="结果 JSONL 输出路径 (default: stress_results_<ts>.jsonl)",
    )
    p.add_argument(
        "--in-flight-cap",
        type=int,
        default=0,
        help="可选：限制同时未完成请求数；0 表示不限制（默认）。"
        " 若设为 1，则变成严格串行（发完等回再发）。",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.count <= 0:
        print("count must be > 0", file=sys.stderr)
        return 2
    if args.rps <= 0:
        print("rps must be > 0", file=sys.stderr)
        return 2
    if not API_KEY:
        print(
            "API_KEY (or GOD_LLM_API_KEY) is required. Export it before running.",
            file=sys.stderr,
        )
        return 2

    rng = random.Random(args.seed)
    out_path = Path(
        args.out
        or f"stress_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    )

    print(
        f"target={BASE_URL} model={MODEL} count={args.count} rps={args.rps} "
        f"max_tokens={args.max_tokens} timeout={args.timeout}s",
        flush=True,
    )
    print(f"results -> {out_path.resolve()}", flush=True)

    # Fire-and-collect with optional in-flight cap using a simple worker pool.
    # Default: schedule at 1/s without waiting for previous responses (true load).
    from concurrent.futures import Future, ThreadPoolExecutor, as_completed

    rows: list[ResultRow] = []
    futures: dict[Future[ResultRow], int] = {}
    interval = 1.0 / args.rps
    start_wall = time.perf_counter()

    # If in_flight_cap is 0, allow all requests to be in flight (cap = count).
    cap = args.in_flight_cap if args.in_flight_cap > 0 else args.count
    executor = ThreadPoolExecutor(max_workers=max(cap, 1))

    def run_one(seq: int, domain: str, prompt: str) -> ResultRow:
        started = datetime.now().isoformat(timespec="milliseconds")
        status, data, latency_ms = chat_once(prompt, args.max_tokens, args.timeout)
        ended = datetime.now().isoformat(timespec="milliseconds")
        content, finish_reason, usage, model = extract_content(data)
        ok = status == 200 and bool(content)
        err: str | None = None
        if not ok:
            if isinstance(data, str):
                err = data[:300]
            elif isinstance(data, dict) and data.get("error"):
                err = json.dumps(data.get("error"), ensure_ascii=False)[:300]
            elif not content:
                err = "empty content"
        no_ws = len("".join(content.split())) if content else 0
        return ResultRow(
            seq=seq,
            domain=domain,
            prompt_chars=len(prompt),
            ok=ok,
            http_status=status or None,
            latency_ms=latency_ms,
            reply_chars=len(content),
            reply_chars_no_ws=no_ws,
            finish_reason=finish_reason,
            model=model,
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
            total_tokens=usage["total_tokens"],
            content_preview=(content[:120] + "…") if len(content) > 120 else content,
            error=err,
            started_at=started,
            ended_at=ended,
        )

    next_seq = 0
    pending: set[Future[ResultRow]] = set()

    try:
        with out_path.open("w", encoding="utf-8") as fp:
            while next_seq < args.count or pending:
                # Launch new requests on schedule while under cap.
                while next_seq < args.count and len(pending) < cap:
                    # Pace by wall schedule from start (1 rps => t=0,1,2,...)
                    due = start_wall + next_seq * interval
                    now = time.perf_counter()
                    if now < due:
                        # Wait either until due or a short slice to collect finished jobs.
                        time.sleep(min(due - now, 0.05))
                        break
                    domain, prompt = build_unique_prompt(next_seq, rng)
                    if len(prompt) < 480:
                        raise RuntimeError(f"prompt too short: {len(prompt)}")
                    fut = executor.submit(run_one, next_seq, domain, prompt)
                    futures[fut] = next_seq
                    pending.add(fut)
                    print(
                        f"  -> sent #{next_seq:05d} at t+{time.perf_counter() - start_wall:.2f}s "
                        f"(in_flight={len(pending)})",
                        flush=True,
                    )
                    next_seq += 1

                if not pending:
                    continue

                # Collect any completed without blocking long.
                done_now = [f for f in list(pending) if f.done()]
                if not done_now:
                    # If we still have sends remaining and are at cap, wait for one to finish.
                    if next_seq < args.count and len(pending) >= cap:
                        done_iter = as_completed(pending, timeout=None)
                        fut = next(done_iter)
                        done_now = [fut]
                    else:
                        time.sleep(0.05)
                        continue

                for fut in done_now:
                    pending.discard(fut)
                    row = fut.result()
                    rows.append(row)
                    print_row(row)
                    fp.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")
                    fp.flush()
    finally:
        executor.shutdown(wait=True, cancel_futures=False)

    rows.sort(key=lambda r: r.seq)
    summary = summarize(rows)
    summary["elapsed_wall_s"] = time.perf_counter() - start_wall
    summary["config"] = {
        "base_url": BASE_URL,
        "model": MODEL,
        "count": args.count,
        "rps": args.rps,
        "max_tokens": args.max_tokens,
        "timeout": args.timeout,
        "in_flight_cap": args.in_flight_cap,
        "seed": args.seed,
    }
    print_summary(summary)
    summary_path = out_path.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"summary -> {summary_path.resolve()}", flush=True)

    # Sample uniqueness check: first few prompt lengths
    sample_domains = [r.domain for r in rows[: min(12, len(rows))]]
    print(f"前若干请求领域分布: {sample_domains}", flush=True)
    return 0 if summary["fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
