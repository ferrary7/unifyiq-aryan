import os
from datetime import datetime, timedelta, date
from typing import List, Dict, Any, Optional
import requests
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/insights", tags=["insights"])

BASE_URL = os.getenv("http://localhost:8000", "http://127.0.0.1:8000")


def fetch_unified_accounts(limit: int = 1000, offset: int = 0) -> List[Dict[str, Any]]:
    """
    Pull unified accounts from MCP with pagination.
    """
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


@router.get("/top-revenue-with-p1")
def top_revenue_with_p1(limit: int = Query(10, ge=1, le=1000)):
    """
    Top ARR accounts that currently have open P1 issues.
    """
    accounts = fetch_unified_accounts()
    impacted = [a for a in accounts if (a.get("OpenP1Issues") or 0) > 0]
    impacted.sort(key=lambda x: (x.get("ARR") or 0), reverse=True)
    return {
        "count": min(limit, len(impacted)),
        "items": [
            {
                "AccountID": a["AccountID"],
                "AccountName": a["AccountName"],
                "ARR": a["ARR"],
                "OpenP1Issues": a["OpenP1Issues"],
                "RenewalDate": a["RenewalDate"],
                "Region": a["Region"],
                "Stage": a["Stage"],
            }
            for a in impacted[:limit]
        ],
    }


@router.get("/renewals-with-p1")
def renewals_with_p1(
    days: int = Query(60, ge=1, le=365),
    today: Optional[str] = Query(None, description="Override current date as YYYY-MM-DD for testing"),
):
    """
    Accounts renewing within the next N days that still have open P1 issues.
    You can pass ?today=YYYY-MM-DD to test historical windows.
    """
    base_today = parse_date(today) if today else datetime.utcnow().date()
    horizon = base_today + timedelta(days=days)

    accounts = fetch_unified_accounts()

    def due_soon(a: Dict[str, Any]) -> bool:
        rd = parse_date(a.get("RenewalDate"))
        return rd is not None and base_today <= rd <= horizon

    impacted = [a for a in accounts if due_soon(a) and (a.get("OpenP1Issues") or 0) > 0]
    impacted.sort(
        key=lambda x: (parse_date(x.get("RenewalDate")) or horizon, -(x.get("ARR") or 0))
    )
    return {
        "as_of": base_today.isoformat(),
        "window_days": days,
        "count": len(impacted),
        "items": [
            {
                "AccountID": a["AccountID"],
                "AccountName": a["AccountName"],
                "ARR": a["ARR"],
                "RenewalDate": a["RenewalDate"],
                "OpenP1Issues": a["OpenP1Issues"],
                "OpenIssues": a["OpenIssues"],
                "Region": a["Region"],
                "Stage": a["Stage"],
            }
            for a in impacted
        ],
    }


@router.get("/accounts-with-critical")
def accounts_with_critical(min: int = Query(3, ge=1, le=50)):
    """
    Accounts with at least N open P1 issues.
    """
    accounts = fetch_unified_accounts()
    flagged = [a for a in accounts if (a.get("OpenP1Issues") or 0) >= min]
    flagged.sort(
        key=lambda x: ((x.get("OpenP1Issues") or 0), (x.get("ARR") or 0)),
        reverse=True,
    )
    return {
        "threshold": min,
        "count": len(flagged),
        "items": [
            {
                "AccountID": a["AccountID"],
                "AccountName": a["AccountName"],
                "ARR": a["ARR"],
                "OpenP1Issues": a["OpenP1Issues"],
                "OpenIssues": a["OpenIssues"],
                "LastIssueDate": a["LastIssueDate"],
                "Region": a["Region"],
            }
            for a in flagged
        ],
    }


@router.get("/summary")
def summary():
    """
    Portfolio rollup of open P1 exposure.
    """
    import statistics

    accounts = fetch_unified_accounts()
    total = len(accounts)
    with_p1 = [a for a in accounts if (a.get("OpenP1Issues") or 0) > 0]
    p1_count = sum(a.get("OpenP1Issues") or 0 for a in accounts)
    arrs = [a.get("ARR") or 0 for a in with_p1]
    median_arr = statistics.median(arrs) if arrs else 0
    return {
        "total_accounts": total,
        "accounts_with_open_p1": len(with_p1),
        "total_open_p1_issues": p1_count,
        "median_arr_impacted": median_arr,
    }
