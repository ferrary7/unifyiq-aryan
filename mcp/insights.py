import os
from datetime import datetime, timedelta, date
from typing import List, Dict, Any, Optional

import requests
from fastapi import APIRouter, HTTPException, Query

from mcp.schemas import (
    TopRevenueResponse,
    RenewalsResponse,
    CriticalResponse,
    SummaryResponse,
)

router = APIRouter(prefix="/insights", tags=["insights"])

BASE_URL = os.getenv("UNIFYIQ_BASE_URL", "http://127.0.0.1:8000")


# -----------------------------
# Utilities
# -----------------------------
def fetch_unified_accounts(limit: int = 1000, offset: int = 0) -> List[Dict[str, Any]]:
    try:
        r = requests.get(
            f"{BASE_URL}/mcp/accounts",
            params={"limit": limit, "offset": offset},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()["items"]
    except requests.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Upstream MCP error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def _open_key_for(priority: str) -> str:
    p = priority.upper()
    if p not in {"P1", "P2", "P3"}:
        raise HTTPException(status_code=400, detail="priority must be one of P1, P2, P3")
    return {"P1": "OpenP1Issues", "P2": "OpenP2Issues", "P3": "OpenP3Issues"}[p]


def _text_match(val: Optional[str], needle: Optional[str]) -> bool:
    if not needle:
        return True
    return (val or "").lower().find(needle.lower()) >= 0


def _passes_filters(
    a: dict,
    region: Optional[str],
    stage: Optional[str],
    industry: Optional[str],
    name_contains: Optional[str],
    arr_min: Optional[int],
    arr_max: Optional[int],
) -> bool:
    if region and (a.get("Region") or "").lower() != region.lower():
        return False
    if stage and (a.get("Stage") or "").lower() != stage.lower():
        return False
    if industry and (a.get("Industry") or "").lower() != industry.lower():
        return False
    if name_contains and not _text_match(a.get("AccountName"), name_contains):
        return False
    arr = a.get("ARR") or 0
    if arr_min is not None and arr < arr_min:
        return False
    if arr_max is not None and arr > arr_max:
        return False
    return True


def _is_open(status: Optional[str]) -> bool:
    return (status or "").lower() != "closed"


def _is_enhancement(summary: Optional[str]) -> bool:
    return "enhancement" in (summary or "").lower()


def _open_count_for_account(a: dict, priority: str, issue_type: Optional[str]) -> int:
    """
    Returns the open issue count for an account at a given priority.
    If issue_type == 'bug', exclude enhancements using LinkedIssues.
    Falls back to the precomputed OpenP*Issues fields when issue_type is not 'bug'.
    """
    if issue_type and issue_type.lower() == "bug":
        # Recompute using LinkedIssues since not all builds have Bug-only counters
        prio = priority.upper()
        issues = a.get("LinkedIssues") or []
        cnt = 0
        for i in issues:
            if _is_open(i.get("Status")) and (i.get("Priority") or "").upper() == prio and not _is_enhancement(i.get("Summary")):
                cnt += 1
        return cnt
    # default: use precomputed counters
    return int(a.get(_open_key_for(priority)) or 0)


# -----------------------------
# Endpoints
# -----------------------------
@router.get(
    "/top-revenue",
    response_model=TopRevenueResponse,
    response_model_exclude_none=True,
    summary="Top Revenue",
    description="Top ARR accounts with open issues at the given priority. Supports optional filters.",
)
def top_revenue(
    priority: str = Query("P1", description="One of P1, P2, P3"),
    limit: int = Query(10, ge=1, le=1000, description="Max accounts to return"),
    # filters
    region: Optional[str] = Query(None, description="Exact region match, e.g. APAC"),
    stage: Optional[str] = Query(None, description="Exact stage match, e.g. Closed Won"),
    industry: Optional[str] = Query(None, description="Exact industry match, e.g. Retail"),
    account_name_contains: Optional[str] = Query(None, description="Substring match on account name"),
    arr_min: Optional[int] = Query(None, ge=0, description="Minimum ARR"),
    arr_max: Optional[int] = Query(None, ge=0, description="Maximum ARR"),
):
    open_key = _open_key_for(priority)
    accounts = fetch_unified_accounts()
    impacted = [a for a in accounts if (a.get(open_key) or 0) > 0]
    impacted = [
        a
        for a in impacted
        if _passes_filters(a, region, stage, industry, account_name_contains, arr_min, arr_max)
    ]
    impacted.sort(key=lambda x: (x.get("ARR") or 0), reverse=True)

    items = []
    for a in impacted[:limit]:
        items.append(
            {
                "AccountID": a["AccountID"],
                "AccountName": a["AccountName"],
                "ARR": a["ARR"],
                "RenewalDate": a["RenewalDate"],
                "Region": a["Region"],
                "Stage": a["Stage"],
                open_key: a.get(open_key, 0),
            }
        )
    return {"priority": priority.upper(), "count": len(items), "items": items}


@router.get(
    "/renewals-with",
    response_model=RenewalsResponse,
    response_model_exclude_none=True,
    summary="Renewals With",
    description="Accounts renewing within the next N days that have open issues at the given priority. Supports optional filters.",
)
def renewals_with(
    priority: str = Query("P1", description="One of P1, P2, P3"),
    days: int = Query(60, ge=1, le=365, description="Renewal window in days"),
    today: Optional[str] = Query(None, description="Override current date as YYYY-MM-DD for testing"),
    limit: int = Query(100, ge=1, le=1000, description="Max accounts to return"),
    # filters
    region: Optional[str] = Query(None),
    stage: Optional[str] = Query(None),
    industry: Optional[str] = Query(None),
    account_name_contains: Optional[str] = Query(None),
    arr_min: Optional[int] = Query(None, ge=0),
    arr_max: Optional[int] = Query(None, ge=0),
):
    open_key = _open_key_for(priority)
    base_today = parse_date(today) if today else datetime.utcnow().date()
    horizon = base_today + timedelta(days=days)
    accounts = fetch_unified_accounts()

    def due_soon(a: Dict[str, Any]) -> bool:
        rd = parse_date(a.get("RenewalDate"))
        return rd is not None and base_today <= rd <= horizon

    impacted = [
        a
        for a in accounts
        if due_soon(a) and (a.get(open_key) or 0) > 0
    ]
    impacted = [
        a
        for a in impacted
        if _passes_filters(a, region, stage, industry, account_name_contains, arr_min, arr_max)
    ]

    # sort by nearest renewal date asc, then ARR desc
    impacted.sort(
        key=lambda x: (parse_date(x.get("RenewalDate")) or horizon, -(x.get("ARR") or 0))
    )

    items = []
    for a in impacted[:limit]:
        items.append(
            {
                "AccountID": a["AccountID"],
                "AccountName": a["AccountName"],
                "ARR": a["ARR"],
                "RenewalDate": a["RenewalDate"],
                "OpenIssues": a["OpenIssues"],
                "Region": a["Region"],
                "Stage": a["Stage"],
                open_key: a.get(open_key, 0),
            }
        )
    return {
        "priority": priority.upper(),
        "as_of": base_today.isoformat(),
        "window_days": days,
        "count": len(items),
        "items": items,
    }


@router.get(
    "/accounts-with-critical",
    response_model=CriticalResponse,
    response_model_exclude_none=True,
    summary="Accounts With Critical",
    description="Accounts with open issues at the given priority. Supports min and max thresholds and optional filters.",
)
def accounts_with_critical(
    min: int = Query(3, ge=1, le=50, description="Minimum open issues at priority"),
    max: Optional[int] = Query(None, ge=1, le=1000, description="Optional maximum open issues at priority"),
    priority: str = Query("P1", description="One of P1, P2, P3"),
    limit: int = Query(10, ge=1, le=1000, description="Max accounts to return"),
    # filters
    region: Optional[str] = Query(None),
    stage: Optional[str] = Query(None),
    industry: Optional[str] = Query(None),
    account_name_contains: Optional[str] = Query(None),
    arr_min: Optional[int] = Query(None, ge=0),
    arr_max: Optional[int] = Query(None, ge=0),
):
    open_key = _open_key_for(priority)
    accounts = fetch_unified_accounts()

    flagged = []
    for a in accounts:
        cnt = a.get(open_key) or 0
        if cnt < min:
            continue
        if max is not None and cnt > max:
            continue
        if not _passes_filters(a, region, stage, industry, account_name_contains, arr_min, arr_max):
            continue
        flagged.append(a)

    # sort by priority count desc, then ARR desc
    flagged.sort(key=lambda x: ((x.get(open_key) or 0), (x.get("ARR") or 0)), reverse=True)

    items = []
    for a in flagged[:limit]:
        items.append(
            {
                "AccountID": a["AccountID"],
                "AccountName": a["AccountName"],
                "ARR": a["ARR"],
                "OpenIssues": a["OpenIssues"],
                "LastIssueDate": a["LastIssueDate"],
                "Region": a["Region"],
                open_key: a.get(open_key, 0),
            }
        )
    return {"priority": priority.upper(), "threshold": min, "count": len(items), "items": items}


@router.get(
    "/summary",
    response_model=SummaryResponse,
    summary="Summary",
    description="Portfolio rollup of open issue exposure at P1, P2, and P3.",
)
def summary():
    import statistics

    accounts = fetch_unified_accounts()
    total = len(accounts)

    def collect(priority: str):
        key = _open_key_for(priority)
        impacted = [a for a in accounts if (a.get(key) or 0) > 0]
        total_open = sum(a.get(key) or 0 for a in accounts)
        arrs = [a.get("ARR") or 0 for a in impacted]
        median_arr = statistics.median(arrs) if arrs else 0
        return len(impacted), total_open, median_arr

    p1_accounts, p1_open, p1_median = collect("P1")
    p2_accounts, p2_open, p2_median = collect("P2")
    p3_accounts, p3_open, p3_median = collect("P3")

    return {
        "total_accounts": total,
        "p1": {
            "accounts_with_open": p1_accounts,
            "total_open": p1_open,
            "median_arr_impacted": p1_median,
        },
        "p2": {
            "accounts_with_open": p2_accounts,
            "total_open": p2_open,
            "median_arr_impacted": p2_median,
        },
        "p3": {
            "accounts_with_open": p3_accounts,
            "total_open": p3_open,
            "median_arr_impacted": p3_median,
        },
    }


# -----------------------------
# New: group-by aggregation
# -----------------------------
@router.get(
    "/group-by",
    summary="Group by dimension",
    description="Aggregate counts by region, stage, or industry for accounts with open issues at a given priority. Supports issue_type=bug and the same filters.",
)
def group_by(
    priority: str = Query("P1", description="One of P1, P2, P3"),
    group_by: str = Query("region", pattern="^(region|stage|industry)$"),
    issue_type: Optional[str] = Query(None, description="any | bug"),
    # filters
    region: Optional[str] = Query(None),
    stage: Optional[str] = Query(None),
    industry: Optional[str] = Query(None),
    account_name_contains: Optional[str] = Query(None),
    arr_min: Optional[int] = Query(None, ge=0),
    arr_max: Optional[int] = Query(None, ge=0),
):
    dim_map = {"region": "Region", "stage": "Stage", "industry": "Industry"}
    dim_field = dim_map[group_by.lower()]

    accounts = fetch_unified_accounts()

    buckets: Dict[str, Dict[str, int]] = {}
    for a in accounts:
        # apply top-level filters first
        if not _passes_filters(a, region, stage, industry, account_name_contains, arr_min, arr_max):
            continue

        open_cnt = _open_count_for_account(a, priority, issue_type)
        if open_cnt <= 0:
            continue

        key = a.get(dim_field) or "Unknown"
        if key not in buckets:
            buckets[key] = {"accounts_with_open": 0, "total_open": 0}
        buckets[key]["accounts_with_open"] += 1
        buckets[key]["total_open"] += int(open_cnt)

    items = [{"group": k, **v} for k, v in buckets.items()]
    items.sort(key=lambda x: x["total_open"], reverse=True)

    return {
        "priority": priority.upper(),
        "group_by": group_by.lower(),
        "count": len(items),
        "items": items,
    }
