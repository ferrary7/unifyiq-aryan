import os
from fastapi import APIRouter, HTTPException, Query
import requests
from typing import List, Dict, Any
from mcp.normalization import to_iso_date, norm_priority, norm_status
from mcp.mapping import build_epic_to_account_map

router = APIRouter(prefix="/mcp", tags=["mcp"])

BASE_URL = os.getenv("http://localhost:8000", "http://127.0.0.1:8000")

def fetch_salesforce(limit=1000, offset=0) -> List[Dict[str, Any]]:
    r = requests.get(f"{BASE_URL}/salesforce", params={"limit": limit, "offset": offset}, timeout=10)
    r.raise_for_status()
    return r.json()["items"]

def fetch_jira(limit=1000, offset=0) -> List[Dict[str, Any]]:
    r = requests.get(f"{BASE_URL}/jira", params={"limit": limit, "offset": offset}, timeout=10)
    r.raise_for_status()
    return r.json()["items"]

def normalize_salesforce(records: List[dict]) -> List[dict]:
    out = []
    for r in records:
        out.append({
            "AccountID": r.get("AccountID"),
            "AccountName": str(r.get("AccountName") or "").strip(),
            "Owner": r.get("Owner"),
            "Region": r.get("Region"),
            "Industry": r.get("Industry"),
            "ARR": r.get("ARR"),
            "RenewalDate": to_iso_date(r.get("RenewalDate")),
            "Stage": r.get("Stage"),
            "CustomerSince": to_iso_date(r.get("CustomerSince")),
        })
    return out

def normalize_jira(records: List[dict]) -> List[dict]:
    out = []
    for r in records:
        created = to_iso_date(r.get("CreatedDate"))
        resolved = to_iso_date(r.get("ResolvedDate"))
        status = norm_status(r.get("Status"))
        out.append({
            "IssueID": r.get("IssueID"),
            "Summary": str(r.get("Summary") or "").strip(),
            "Status": status,
            "Priority": norm_priority(r.get("Priority")),
            "Assignee": r.get("Assignee"),
            "Reporter": r.get("Reporter"),
            "CreatedDate": created,
            "ResolvedDate": resolved,
            "StoryPoints": r.get("StoryPoints"),
            "EpicLink": r.get("EpicLink"),
            "IsOpen": status != "Closed",
        })
    return out

def unify_accounts(sf: List[dict], ji: List[dict]):
    epic_map = build_epic_to_account_map(sf, ji)
    sf_by_id = {r["AccountID"]: r for r in sf if r.get("AccountID")}
    issues_by_acc = {k: [] for k in sf_by_id.keys()}
    orphans = []

    for issue in ji:
        acc_id = epic_map.get(issue.get("EpicLink"))
        if acc_id and acc_id in issues_by_acc:
            issues_by_acc[acc_id].append(issue)
        else:
            orphans.append(issue)

    unified = []
    for acc_id, acc in sf_by_id.items():
        issues = issues_by_acc.get(acc_id, [])
        open_issues = sum(1 for x in issues if x.get("IsOpen"))
        open_p1 = sum(1 for x in issues if x.get("IsOpen") and x.get("Priority") == "P1")
        last_issue_date = max([d for d in [x.get("CreatedDate") for x in issues] if d], default=None)
        unified.append({
            "AccountID": acc_id,
            "AccountName": acc.get("AccountName"),
            "ARR": acc.get("ARR"),
            "RenewalDate": acc.get("RenewalDate"),
            "Stage": acc.get("Stage"),
            "Region": acc.get("Region"),
            "Industry": acc.get("Industry"),
            "OpenIssues": open_issues,
            "OpenP1Issues": open_p1,
            "LastIssueDate": last_issue_date,
            "LinkedIssues": [
                {
                    "IssueID": i.get("IssueID"),
                    "Summary": i.get("Summary"),
                    "Priority": i.get("Priority"),
                    "Status": i.get("Status"),
                    "CreatedDate": i.get("CreatedDate"),
                    "ResolvedDate": i.get("ResolvedDate"),
                    "EpicLink": i.get("EpicLink"),
                } for i in issues
            ],
        })

    return unified, orphans, epic_map

@router.get("/accounts")
def get_unified_accounts(limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
    try:
        sf_raw = fetch_salesforce()
        ji_raw = fetch_jira()
        sf = normalize_salesforce(sf_raw)
        ji = normalize_jira(ji_raw)
        unified, orphans, epic_map = unify_accounts(sf, ji)
        total = len(unified)
        items = unified[offset: offset + limit]
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "count": len(items),
            "items": items,
            "meta": {
                "orphans": len(orphans),
                "epic_to_account_sample": dict(list(epic_map.items())[:5])
            }
        }
    except requests.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Upstream API error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
