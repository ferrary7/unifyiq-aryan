import os
import re
import json
import csv
import io
from typing import Optional, Dict, Any, List, Literal, Tuple

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, conint

router = APIRouter(prefix="/agent", tags=["agent"])

API_BASE = os.getenv("UNIFYIQ_BASE_URL", "http://127.0.0.1:8000")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  # optional but recommended


# -----------------------------
# Mini planning schema
# -----------------------------
StepOp = Literal["fetch", "filter", "select", "sort", "top", "group", "summarize"]

class FetchArgs(BaseModel):
    endpoint: Literal[
        "/insights/top-revenue",
        "/insights/renewals-with",
        "/insights/accounts-with-critical",
        "/insights/summary",
        "/insights/group-by",
        "/mcp/accounts",
    ]
    params: Dict[str, Any] = Field(default_factory=dict)

class FilterCond(BaseModel):
    field: str
    op: Literal["=", "!=", ">", ">=", "<", "<=", "contains", "in"]
    value: Any

class SortSpec(BaseModel):
    by: str
    order: Literal["asc", "desc"] = "desc"

class GroupSpec(BaseModel):
    by: str
    agg: Literal["count", "sum"] = "count"
    field: Optional[str] = None  # for sum on a field, e.g. sum of ARR

class PlanStep(BaseModel):
    op: StepOp
    fetch: Optional[FetchArgs] = None
    filter: Optional[List[FilterCond]] = None
    select: Optional[List[str]] = None
    sort: Optional[SortSpec] = None
    top: Optional[conint(ge=1, le=2000)] = None
    group: Optional[GroupSpec] = None

class Plan(BaseModel):
    intent: Literal["answer", "csv", "debug"] = "answer"
    steps: List[PlanStep]
    answer_template: Optional[str] = Field(
        default=None,
        description="Jinja-lite style placeholders like {{count}} or {{sum_total_open}}"
    )

class AgentRequest(BaseModel):
    q: str
    format: Optional[Literal["json", "csv"]] = None


# -----------------------------
# Helpers
# -----------------------------
def _priority_map(tok: str) -> str:
    t = (tok or "").lower()
    if t in ["p0", "sev0", "sev1", "p1", "critical", "high", "severity high"]:
        return "P1"
    if t in ["p2", "sev2", "medium"]:
        return "P2"
    if t in ["p3", "sev3", "low"]:
        return "P3"
    return "P1"

def _prio_from_text(text: str) -> str:
    low = (text or "").lower()
    if any(k in low for k in ["p0", "sev0", "sev1", "high", "severity high", "p1"]):
        return "P1"
    if any(k in low for k in ["p2", "sev2", "medium"]):
        return "P2"
    if any(k in low for k in ["p3", "sev3", "low"]):
        return "P3"
    return "P1"

def _default_params_for(endpoint: str) -> Dict[str, Any]:
    if endpoint == "/insights/top-revenue":
        return {"priority": "P1", "limit": 10}
    if endpoint == "/insights/renewals-with":
        return {"priority": "P1", "days": 60, "limit": 100}
    if endpoint == "/insights/accounts-with-critical":
        return {"priority": "P1", "min": 3, "limit": 10}
    if endpoint == "/insights/group-by":
        return {"priority": "P1", "group_by": "region"}
    if endpoint == "/mcp/accounts":
        return {"limit": 100, "offset": 0}
    return {}

def _num_from_text(tok: str) -> Optional[int]:
    """
    Convert '100k', '1.2m', '250,000' to int. Returns None if not numeric.
    """
    if tok is None:
        return None
    s = str(tok).strip().lower().replace(",", "")
    mult = 1
    if s.endswith("k"):
        mult = 1_000
        s = s[:-1]
    elif s.endswith("m"):
        mult = 1_000_000
        s = s[:-1]
    try:
        return int(float(s) * mult)
    except Exception:
        return None

RELATIVE_TIME = [
    ("this quarter", 90),
    ("next quarter", 90),
    ("next month", 30),
    ("this month", 30),
    ("this week", 7),
    ("next week", 7),
]

def _infer_days(text: str) -> Optional[int]:
    low = text.lower()
    for phrase, days in RELATIVE_TIME:
        if phrase in low:
            return days
    m = re.search(r"(\d+)\s*(day|days)", low)
    if m:
        return int(m.group(1))
    return None

def _call_api(endpoint: str, params: Dict[str, Any]) -> Any:
    try:
        r = requests.get(f"{API_BASE}{endpoint}", params=params, timeout=20)
        r.raise_for_status()
        ct = r.headers.get("content-type", "")
        if "text/csv" in ct:
            return r.text
        return r.json()
    except requests.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Upstream error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def _extract_rows(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, dict):
        if "items" in data and isinstance(data["items"], list):
            return data["items"]
        return [data]
    if isinstance(data, list):
        return data
    return []

def _apply_filter(rows: List[Dict[str, Any]], conds: List[FilterCond]) -> List[Dict[str, Any]]:
    def ok(row: Dict[str, Any]) -> bool:
        for c in conds:
            val = row.get(c.field)
            if c.op == "=" and not (val == c.value): return False
            if c.op == "!=" and not (val != c.value): return False
            if c.op == ">" and not (isinstance(val, (int, float)) and val > c.value): return False
            if c.op == ">=" and not (isinstance(val, (int, float)) and val >= c.value): return False
            if c.op == "<" and not (isinstance(val, (int, float)) and val < c.value): return False
            if c.op == "<=" and not (isinstance(val, (int, float)) and val <= c.value): return False
            if c.op == "contains":
                if c.value is None: return False
                if str(c.value).lower() not in str(val or "").lower(): return False
            if c.op == "in":
                try:
                    if val not in c.value: return False
                except Exception:
                    return False
        return True
    return [r for r in rows if ok(r)]

def _apply_select(rows: List[Dict[str, Any]], cols: List[str]) -> List[Dict[str, Any]]:
    return [{k: r.get(k) for k in cols} for r in rows]

def _apply_sort(rows: List[Dict[str, Any]], spec: SortSpec) -> List[Dict[str, Any]]:
    reverse = spec.order == "desc"
    return sorted(rows, key=lambda x: (x.get(spec.by) is None, x.get(spec.by)), reverse=reverse)

def _apply_top(rows: List[Dict[str, Any]], n: int) -> List[Dict[str, Any]]:
    return rows[:n]

def _apply_group(rows: List[Dict[str, Any]], spec: GroupSpec) -> List[Dict[str, Any]]:
    buckets: Dict[Any, Dict[str, Any]] = {}
    for r in rows:
        g = r.get(spec.by, "Unknown")
        if g not in buckets:
            buckets[g] = {"group": g, "count": 0, "sum": 0}
        buckets[g]["count"] += 1
        if spec.agg == "sum":
            fld = spec.field or "ARR"
            try:
                buckets[g]["sum"] += int(r.get(fld) or 0)
            except Exception:
                pass
    out = list(buckets.values())
    out.sort(key=lambda x: (x["sum"] if spec.agg == "sum" else x["count"]), reverse=True)
    return out

def _rows_to_csv(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return ""
    fields = list({k for r in rows for k in r.keys()})
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields)
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


# -----------------------------
# LLM planning
# -----------------------------
SYSTEM_INSTRUCTIONS = """
You are a planning agent for a data platform.
Return a JSON object ONLY that matches the Plan schema.
No code. No prose. No Markdown. JSON only.

Core rules
1) Single fetch when one endpoint answers the ask. Chain at most 2 fetches only if strictly needed.
2) If the query contains "group by <region|stage|industry>", fetch /insights/group-by with group_by set to that value. Do not fetch /insights/top-revenue for grouping.
3) If the user says "csv", set intent to "csv". Keep the same plan, but the client will request CSV output.
4) If the user says "bugs only", "bug only", or "not counting enhancements", set issue_type="bug".
5) Severity mapping: p0, sev0, sev1, high, severity high -> P1. sev2, medium -> P2. sev3, low -> P3.
6) Relative time: "next month" -> days=30. "this quarter" or "next quarter" -> days=90. "this week" or "next week" -> days=7, unless the user gave a number of days.
7) Prefer sorting that matches intent:
   - top-revenue -> sort by ARR desc
   - accounts-with-critical -> sort by priority count desc then ARR desc
   - renewals-with -> sort by RenewalDate asc then ARR desc
   - group-by -> sort by total_open desc
8) Respect filters if present: region, stage, industry, account_name_contains, arr_min, arr_max.
9) Keep parameters minimal. Do not invent fields outside the allowed params.
10) If the request is outside the available tools (e.g., churn, NPS, cohorts, LTV, CAC, funnels, conversion rates, retention, engagement), RETURN an empty plan:
    {"intent":"answer","steps":[]}.

Raw data usage
- Use /mcp/accounts when the user asks for "show all", "list all accounts", "raw", "everything", or asks for fields/filters not supported by /insights (e.g., filtering by AccountID, name contains, ARR thresholds).
- After fetching /mcp/accounts, use filter/select/sort/top steps to shape the result.

Available tools
- /insights/top-revenue
  params: priority, limit, region, stage, industry, account_name_contains, arr_min, arr_max, issue_type
- /insights/renewals-with
  params: priority, days, today, limit, region, stage, industry, account_name_contains, arr_min, arr_max, issue_type
- /insights/accounts-with-critical
  params: priority, min, max, limit, region, stage, industry, account_name_contains, arr_min, arr_max, issue_type
- /insights/group-by
  params: priority, group_by=region|stage|industry, issue_type
- /mcp/accounts
  params: limit, offset

Planning patterns
- "show all data" -> fetch /mcp/accounts (limit 100), sort ARR desc, top 100.
- "list accounts in apac with arr > 100k" -> /mcp/accounts then filter Region="APAC", filter ARR>100000, sort ARR desc.
- "account A1001" -> /mcp/accounts then filter AccountID="A1001".
- "with p1 >= 3" -> /mcp/accounts then filter OpenP1Issues>=3.
- "group by region with bugs only for p1" -> /insights/group-by with priority=P1, issue_type=bug, sort total_open desc.

Output
- Always return a valid Plan JSON matching the schema. No extra keys. No comments.
"""

def call_gemini_plan(q: str) -> Optional[Plan]:
    if not GEMINI_API_KEY:
        return None
    try:
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
        headers = {"Content-Type": "application/json"}
        body = {
            "contents": [
                {"role": "user", "parts": [{"text": SYSTEM_INSTRUCTIONS}]},
                {"role": "user", "parts": [{"text": f"User query: {q}"}]},
                {"role": "user", "parts": [{"text": "Return the Plan JSON only. No prose."}]},
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.2,
                "candidateCount": 1
            },
        }
        resp = requests.post(f"{url}?key={GEMINI_API_KEY}", headers=headers, data=json.dumps(body), timeout=15)
        resp.raise_for_status()
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        plan_json = json.loads(text)
        return Plan(**plan_json)
    except Exception:
        return None


# -----------------------------
# Regex guardrails
# -----------------------------
GROUPBY_RE = re.compile(r"group by (region|stage|industry)", re.I)
BUGS_ONLY_RE = re.compile(r"(bugs? only|bug only|not counting enhancements)", re.I)
OUT_OF_SCOPE_RE = re.compile(
    r"\b(churn|nps|net promoter|csat|c-sat|cohort|ltv|lifetime value|cac|funnel|"
    r"conversion rate|ctr|arpu|mau|wau|dau|retention|engagement)\b",
    re.I
)
SHOW_ALL_RE = re.compile(r"\b(show|list|display)\s+(all|everything|data|accounts)\b|\ball data\b|\braw\b", re.I)
ACCOUNT_ID_RE = re.compile(r"\bA\d{3,}\b", re.I)
ARR_CMP_RE = re.compile(r"\barr\s*(>=|>|<=|<|=)\s*([0-9][0-9,\.]*\s*[km]?)", re.I)
ARR_RANGE_RE = re.compile(r"\barr\s*(\d[\d,\.]*\s*[km]?)\s*(?:to|-)\s*(\d[\d,\.]*\s*[km]?)", re.I)
NAME_CONTAINS_RE = re.compile(r"(?:name|account name)\s*(?:contains|like)\s*['\"]?([A-Za-z0-9 _-]+)['\"]?", re.I)
P_THRESHOLD_RE = re.compile(r"\b(p1|p2|p3)\s*(?:issues?|=)?\s*(>=|>|<=|<|=)?\s*(\d+)?", re.I)
REGION_TOK_RE = re.compile(r"\b(apac|europe|emea|north america|na|latam)\b", re.I)
STAGE_EQ_RE = re.compile(r"stage\s*=\s*([a-z ]+)", re.I)
INDUSTRY_EQ_RE = re.compile(r"industry\s*=\s*([a-z ]+)", re.I)


# -----------------------------
# Deterministic fallback plan
# -----------------------------
def _filters_from_text(low: str) -> List[FilterCond]:
    filters: List[FilterCond] = []

    # Region
    m = REGION_TOK_RE.search(low)
    if m:
        token = m.group(1).lower()
        region = {"na": "north america", "emea": "europe"}.get(token, token)
        filters.append(FilterCond(field="Region", op="=", value=region.title()))

    # Stage
    m = STAGE_EQ_RE.search(low)
    if m:
        filters.append(FilterCond(field="Stage", op="=", value=m.group(1).strip().title()))

    # Industry
    m = INDUSTRY_EQ_RE.search(low)
    if m:
        filters.append(FilterCond(field="Industry", op="=", value=m.group(1).strip().title()))

    # Name contains
    m = NAME_CONTAINS_RE.search(low)
    if m:
        filters.append(FilterCond(field="AccountName", op="contains", value=m.group(1).strip()))

    # ARR comparisons
    m = ARR_CMP_RE.search(low)
    if m:
        op, num = m.group(1), _num_from_text(m.group(2))
        if num is not None:
            filters.append(FilterCond(field="ARR", op=op, value=num))

    # ARR range
    m = ARR_RANGE_RE.search(low)
    if m:
        a = _num_from_text(m.group(1))
        b = _num_from_text(m.group(2))
        if a is not None and b is not None:
            lo, hi = (a, b) if a <= b else (b, a)
            filters.append(FilterCond(field="ARR", op=">=", value=lo))
            filters.append(FilterCond(field="ARR", op="<=", value=hi))

    # Priority thresholds (default >=1 if pX mentioned without number)
    for px, op, n in P_THRESHOLD_RE.findall(low):
        field = {"p1": "OpenP1Issues", "p2": "OpenP2Issues", "p3": "OpenP3Issues"}[px.lower()]
        if n:
            num = int(n)
            filters.append(FilterCond(field=field, op=(op or ">=") if op else ">=", value=num))
        else:
            filters.append(FilterCond(field=field, op=">=", value=1))

    # AccountID
    m = ACCOUNT_ID_RE.search(low)
    if m:
        filters.append(FilterCond(field="AccountID", op="=", value=m.group(0).upper()))

    return filters

def fallback_plan(q: str) -> Plan:
    low = q.lower()

    # Out-of-scope → empty plan
    if OUT_OF_SCOPE_RE.search(low):
        return Plan(intent="answer", steps=[], answer_template=None)

    # group-by first, deterministic
    m = GROUPBY_RE.search(low)
    if m:
        group_field = m.group(1).lower()
        params = _default_params_for("/insights/group-by")
        params["group_by"] = group_field
        params["priority"] = _prio_from_text(low)
        if BUGS_ONLY_RE.search(low):
            params["issue_type"] = "bug"
        steps = [
            PlanStep(op="fetch", fetch=FetchArgs(endpoint="/insights/group-by", params=params)),
            PlanStep(op="sort", sort=SortSpec(by="total_open", order="desc")),
        ]
        return Plan(
            intent="answer",
            steps=steps,
            answer_template="Grouped by {{group_by}} with open {{priority}} issues. Groups: {{count}}. Total open: {{sum_total_open}}."
        )

    # RAW / "show all" → /mcp/accounts
    if SHOW_ALL_RE.search(low) or "accounts" in low and "group by" not in low:
        params = _default_params_for("/mcp/accounts")
        steps: List[PlanStep] = [PlanStep(op="fetch", fetch=FetchArgs(endpoint="/mcp/accounts", params=params))]
        filt = _filters_from_text(low)
        if filt:
            steps.append(PlanStep(op="filter", filter=filt))
        steps += [
            PlanStep(op="sort", sort=SortSpec(by="ARR", order="desc")),
            PlanStep(op="top", top=params.get("limit", 100)),
        ]
        return Plan(intent="answer", steps=steps, answer_template=None)

    # Default insights flows
    intent = "answer"
    endpoint = "/insights/top-revenue"
    params: Dict[str, Any] = _default_params_for(endpoint)

    if "renewal" in low or "renewing" in low:
        endpoint = "/insights/renewals-with"
        params = _default_params_for(endpoint)
        d = _infer_days(low)
        if d:
            params["days"] = d

    if "critical" in low or "at least" in low or re.search(r"\d+\s*(to|-)\s*\d+", low):
        endpoint = "/insights/accounts-with-critical"
        params = _default_params_for(endpoint)
        m = re.search(r"(?:at least|>=)\s*(\d+)", low)
        if m:
            params["min"] = int(m.group(1))
        rng = re.search(r"(\d+)\s*(?:to|-)\s*(\d+)", low)
        if rng:
            a, b = int(rng.group(1)), int(rng.group(2))
            params["min"], params["max"] = min(a, b), max(a, b)

    # priority
    m = re.search(r"\b(p0|p1|p2|p3|sev1|sev2|sev3|high|medium|low)\b", low)
    if m:
        params["priority"] = _priority_map(m.group(1))

    # region, industry, stage simple grabs
    m = REGION_TOK_RE.search(low)
    if m:
        token = m.group(1).lower()
        params["region"] = {"na": "north america", "emea": "europe"}.get(token, token)
    m = INDUSTRY_EQ_RE.search(low)
    if m:
        params["industry"] = m.group(1).strip()
    m = STAGE_EQ_RE.search(low)
    if m:
        params["stage"] = m.group(1).strip()
    if BUGS_ONLY_RE.search(low):
        params["issue_type"] = "bug"

    if re.search(r"\bcsv|download\b", low):
        intent = "csv"

    steps = [PlanStep(op="fetch", fetch=FetchArgs(endpoint=endpoint, params=params))]
    if endpoint == "/insights/top-revenue":
        steps += [
            PlanStep(op="sort", sort=SortSpec(by="ARR", order="desc")),
            PlanStep(op="top", top=params.get("limit", 10)),
        ]
    if endpoint == "/insights/accounts-with-critical":
        steps += [
            PlanStep(op="sort", sort=SortSpec(by="ARR", order="desc")),
            PlanStep(op="top", top=params.get("limit", 10)),
        ]
    if endpoint == "/insights/renewals-with":
        steps += [PlanStep(op="top", top=params.get("limit", 100))]

    return Plan(intent=intent, steps=steps, answer_template=None)


# -----------------------------
# Plan executor
# -----------------------------
def execute_plan(plan: Plan) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Returns (rows, meta) where rows is the final tabular result and meta includes fetch traces.
    """
    rows: List[Dict[str, Any]] = []
    meta: Dict[str, Any] = {"fetches": []}

    for step in plan.steps:
        if step.op == "fetch":
            if not step.fetch:
                raise HTTPException(status_code=400, detail="fetch step missing args")
            params = {**_default_params_for(step.fetch.endpoint), **(step.fetch.params or {})}
            data = _call_api(step.fetch.endpoint, params)
            meta["fetches"].append({"endpoint": step.fetch.endpoint, "params": params})
            rows = _extract_rows(data)

        elif step.op == "filter":
            if not step.filter:
                continue
            rows = _apply_filter(rows, step.filter)

        elif step.op == "select":
            if not step.select:
                continue
            rows = _apply_select(rows, step.select)

        elif step.op == "sort":
            if not step.sort:
                continue
            rows = _apply_sort(rows, step.sort)

        elif step.op == "top":
            if not step.top:
                continue
            rows = _apply_top(rows, step.top)

        elif step.op == "group":
            if not step.group:
                continue
            rows = _apply_group(rows, step.group)

        elif step.op == "summarize":
            pass

        else:
            raise HTTPException(status_code=400, detail=f"unknown op {step.op}")

    return rows, meta


def render_answer(template: Optional[str], rows: List[Dict[str, Any]], context: Optional[Dict[str, Any]] = None) -> str:
    if not template:
        if not rows:
            return "No matching accounts found."
        sample = rows[:3]
        return f"Found {len(rows)} result(s). Showing {len(sample)} sample row(s)."

    # base context
    kv: Dict[str, Any] = {}
    kv["count"] = len(rows)

    if context:
        kv.update({k: v for k, v in context.items() if v is not None})

    for field in ["ARR", "OpenIssues", "OpenP1Issues", "OpenP2Issues", "OpenP3Issues", "total_open", "accounts_with_open"]:
        try:
            kv[f"sum_{field}"] = sum(int(r.get(field) or 0) for r in rows)
        except Exception:
            pass

    out = template
    for k, v in kv.items():
        out = out.replace(f"{{{{{k}}}}}", str(v))
    return out


def _first_fetch_context(plan: Plan) -> Dict[str, Any]:
    try:
        for step in plan.steps:
            if step.op == "fetch" and step.fetch:
                p = step.fetch.params or {}
                ctx = {}
                if "priority" in p:
                    ctx["priority"] = p["priority"]
                if "group_by" in p:
                    ctx["group_by"] = p["group_by"]
                return ctx
    except Exception:
        pass
    return {}


# -----------------------------
# Public endpoint
# -----------------------------
@router.post("/query")
def agent_query(body: AgentRequest):
    q = body.q.strip()
    if not q:
        raise HTTPException(status_code=400, detail="Empty query")

    warnings: List[str] = []

    # 1) Hard guardrail: GROUP BY (kept first)
    m = GROUPBY_RE.search(q)
    if m:
        group_field = m.group(1).lower()
        params = _default_params_for("/insights/group-by")
        params["group_by"] = group_field
        params["priority"] = _prio_from_text(q)
        if BUGS_ONLY_RE.search(q):
            params["issue_type"] = "bug"

        plan = Plan(
            intent="answer",
            steps=[
                PlanStep(op="fetch", fetch=FetchArgs(endpoint="/insights/group-by", params=params)),
                PlanStep(op="sort", sort=SortSpec(by="total_open", order="desc")),
            ],
            answer_template="Grouped by {{group_by}} with open {{priority}} issues. Groups: {{count}}. Total open: {{sum_total_open}}."
        )

        try:
            rows, meta = execute_plan(plan)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Plan execution error: {str(e)}")

        if body.format == "csv" or plan.intent == "csv":
            csv_text = _rows_to_csv(rows)
            return {
                "query": q,
                "intent": plan.intent,
                "warnings": warnings,
                "plan": json.loads(plan.model_dump_json()),
                "content_type": "text/csv",
                "result": csv_text,
                "meta": meta,
            }

        answer = render_answer(
            plan.answer_template,
            rows,
            context={"group_by": group_field, "priority": params.get("priority", "P1")}
        )
        return {
            "query": q,
            "intent": plan.intent,
            "warnings": warnings,
            "plan": json.loads(plan.model_dump_json()),
            "answer": answer,
            "result": rows,
            "meta": meta,
        }

    # 2) NEW hard guardrail: explicit AccountID lookups like "A1001"
    m = ACCOUNT_ID_RE.search(q)
    if m:
        acc_id = m.group(0).upper()
        params = _default_params_for("/mcp/accounts")
        plan = Plan(
            intent="answer",
            steps=[
                PlanStep(op="fetch", fetch=FetchArgs(endpoint="/mcp/accounts", params=params)),
                PlanStep(op="filter", filter=[FilterCond(field="AccountID", op="=", value=acc_id)]),
                PlanStep(op="top", top=1),
            ],
            answer_template=None,
        )

        try:
            rows, meta = execute_plan(plan)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Plan execution error: {str(e)}")

        if body.format == "csv" or plan.intent == "csv":
            csv_text = _rows_to_csv(rows)
            return {
                "query": q,
                "intent": plan.intent,
                "warnings": warnings,
                "plan": json.loads(plan.model_dump_json()),
                "content_type": "text/csv",
                "result": csv_text,
                "meta": meta,
            }

        answer = render_answer(plan.answer_template, rows)
        return {
            "query": q,
            "intent": plan.intent,
            "warnings": warnings,
            "plan": json.loads(plan.model_dump_json()),
            "answer": answer,
            "result": rows,
            "meta": meta,
        }

    # 3) OPTIONAL hard guardrail: “show/list/display all data/accounts”, “raw”
    if SHOW_ALL_RE.search(q):
        params = _default_params_for("/mcp/accounts")
        plan = Plan(
            intent="answer",
            steps=[
                PlanStep(op="fetch", fetch=FetchArgs(endpoint="/mcp/accounts", params=params)),
                PlanStep(op="sort", sort=SortSpec(by="ARR", order="desc")),
                PlanStep(op="top", top=params.get("limit", 100)),
            ],
            answer_template=None,
        )

        try:
            rows, meta = execute_plan(plan)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Plan execution error: {str(e)}")

        if body.format == "csv" or plan.intent == "csv":
            csv_text = _rows_to_csv(rows)
            return {
                "query": q,
                "intent": plan.intent,
                "warnings": warnings,
                "plan": json.loads(plan.model_dump_json()),
                "content_type": "text/csv",
                "result": csv_text,
                "meta": meta,
            }

        answer = render_answer(plan.answer_template, rows)
        return {
            "query": q,
            "intent": plan.intent,
            "warnings": warnings,
            "plan": json.loads(plan.model_dump_json()),
            "answer": answer,
            "result": rows,
            "meta": meta,
        }

    # 4) LLM plan
    plan: Optional[Plan] = None
    if GEMINI_API_KEY:
        p = call_gemini_plan(q)
        if p:
            plan = p
        else:
            warnings.append("LLM planning failed. Fallback used.")

    if not plan:
        plan = fallback_plan(q)

    # Honest "I don't know"
    if not plan or not getattr(plan, "steps", None):
        return {
            "query": q,
            "intent": "answer",
            "warnings": warnings + ["No valid plan could be generated."],
            "answer": "Sorry, I don't know how to answer that yet.",
            "result": [],
            "meta": {"fetches": []},
        }

    # Execute plan
    try:
        rows, meta = execute_plan(plan)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Plan execution error: {str(e)}")

    # CSV requested
    if body.format == "csv" or plan.intent == "csv":
        csv_text = _rows_to_csv(rows)
        return {
            "query": q,
            "intent": plan.intent,
            "warnings": warnings,
            "plan": json.loads(plan.model_dump_json()),
            "content_type": "text/csv",
            "result": csv_text,
            "meta": meta,
        }

    # Natural language answer + data
    answer_ctx = _first_fetch_context(plan)
    answer = render_answer(plan.answer_template, rows, context=answer_ctx)
    return {
        "query": q,
        "intent": plan.intent,
        "warnings": warnings,
        "plan": json.loads(plan.model_dump_json()),
        "answer": answer,
        "result": rows,
        "meta": meta,
    }
