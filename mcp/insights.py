import os
from datetime import datetime, timedelta, date
from typing import List, Dict, Any, Optional
import requests
from fastapi import APIRouter, HTTPException, Query
from mcp.schemas import (
    TopRevenueResponse, RenewalsResponse, CriticalResponse, SummaryResponse
)

router = APIRouter(prefix="/insights", tags=["insights"])

BASE_URL = os.getenv("UNIFYIQ_BASE_URL", "http://127.0.0.1:8000")

def fetch_unified_accounts(limit: int = 1000, offset: int = 0) -> List[Dict[str, Any]]:
    try:
        r = requests.get(f"{BASE_URL}/mcp/accounts", params={"limit": limit, "offset": offset}, timeout=15)
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

@router.get(
    "/top-revenue",
    response_model=TopRevenueResponse,
    summary="Top Revenue",
    description="Top ARR accounts with open issues at the given priority.",
)
def top_revenue(
    priority: str = Query("P1", description="One of P1, P2, P3"),
    limit: int = Query(10, ge=1, le=1000, description="Max accounts to return"),
):
    open_key = _open_key_for(priority)
    accounts = fetch_unified_accounts()
    impacted = [a for a in accounts if (a.get(open_key) or 0) > 0]
    impacted.sort(key=lambda x: (x.get("ARR") or 0), reverse=True)
    # Include the specific open count field in each item
    items = []
    for a in impacted[:limit]:
        row = {
            "AccountID": a["AccountID"],
            "AccountName": a["AccountName"],
            "ARR": a["ARR"],
            "RenewalDate": a["RenewalDate"],
            "Region": a["Region"],
            "Stage": a["Stage"],
        }
        row[open_key] = a.get(open_key, 0)
        items.append(row)
    return {"priority": priority.upper(), "count": len(items), "items": items}

@router.get(
    "/renewals-with",
    response_model=RenewalsResponse,
    summary="Renewals With",
    description="Accounts renewing within the next N days that have open issues at the given priority.",
)
def renewals_with(
    priority: str = Query("P1", description="One of P1, P2, P3"),
    days: int = Query(60, ge=1, le=365, description="Renewal window in days"),
    today: Optional[str] = Query(None, description="Override current date as YYYY-MM-DD for testing"),
):
    open_key = _open_key_for(priority)
    base_today = parse_date(today) if today else datetime.utcnow().date()
    horizon = base_today + timedelta(days=days)
    accounts = fetch_unified_accounts()

    def due_soon(a: Dict[str, Any]) -> bool:
        rd = parse_date(a.get("RenewalDate"))
        return rd is not None and base_today <= rd <= horizon

    impacted = [a for a in accounts if due_soon(a) and (a.get(open_key) or 0) > 0]
    impacted.sort(key=lambda x: (parse_date(x.get("RenewalDate")) or horizon, -(x.get("ARR") or 0)))
    items = []
    for a in impacted:
        row = {
            "AccountID": a["AccountID"],
            "AccountName": a["AccountName"],
            "ARR": a["ARR"],
            "RenewalDate": a["RenewalDate"],
            "OpenIssues": a["OpenIssues"],
            "Region": a["Region"],
            "Stage": a["Stage"],
        }
        row[open_key] = a.get(open_key, 0)
        items.append(row)
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
    summary="Accounts With Critical",
    description="Accounts with at least N open issues at the given priority.",
)
def accounts_with_critical(
    min: int = Query(3, ge=1, le=50, description="Minimum open issues at priority"),
    priority: str = Query("P1", description="One of P1, P2, P3"),
):
    open_key = _open_key_for(priority)
    accounts = fetch_unified_accounts()
    flagged = [a for a in accounts if (a.get(open_key) or 0) >= min]
    flagged.sort(key=lambda x: ((x.get(open_key) or 0), (x.get("ARR") or 0)), reverse=True)
    items = []
    for a in flagged:
        row = {
            "AccountID": a["AccountID"],
            "AccountName": a["AccountName"],
            "ARR": a["ARR"],
            "OpenIssues": a["OpenIssues"],
            "LastIssueDate": a["LastIssueDate"],
            "Region": a["Region"],
        }
        row[open_key] = a.get(open_key, 0)
        items.append(row)
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
        "p1": {"accounts_with_open": p1_accounts, "total_open": p1_open, "median_arr_impacted": p1_median},
        "p2": {"accounts_with_open": p2_accounts, "total_open": p2_open, "median_arr_impacted": p2_median},
        "p3": {"accounts_with_open": p3_accounts, "total_open": p3_open, "median_arr_impacted": p3_median},
    }
