#!/usr/bin/env python3
import os, sys, json, time, re
from datetime import datetime, timedelta, date
from typing import Any, Dict, List, Tuple, Optional
import requests

BASE_URL = os.getenv("UNIFYIQ_BASE_URL", "http://127.0.0.1:8000")

OK = "PASS"
BAD = "FAIL"

def get(path: str, params: Dict[str, Any] = None, timeout=15):
    url = f"{BASE_URL}{path}"
    r = requests.get(url, params=params or {}, timeout=timeout)
    return r

def parse_iso(d: Optional[str]) -> Optional[date]:
    if not d: return None
    try:
        return datetime.strptime(d, "%Y-%m-%d").date()
    except:
        return None

class Suite:
    def __init__(self):
        self.results: List[Tuple[str, str, str]] = []

    def check(self, name: str, cond: bool, info: str = ""):
        self.results.append((name, OK if cond else BAD, info))

    def section(self, title: str):
        print(f"\n=== {title} ===")

    def report(self):
        passes = sum(1 for _, s, _ in self.results if s == OK)
        fails = sum(1 for _, s, _ in self.results if s == BAD)
        print("\n--- Summary ---")
        for name, status, info in self.results:
            line = f"[{status}] {name}"
            if info:
                line += f" | {info}"
            print(line)
        print(f"\nTotal: {passes + fails}, Pass: {passes}, Fail: {fails}")
        return 0 if fails == 0 else 1

def test_health(s: Suite):
    s.section("Service health")
    r = get("/")
    s.check("GET / root 200", r.status_code == 200, f"code={r.status_code}")
    r = get("/health")
    s.check("GET /health 200", r.status_code == 200, f"code={r.status_code}")

def test_raw_sources(s: Suite):
    s.section("Raw sources")
    r = get("/salesforce/health")
    ok = r.status_code == 200 and r.json().get("records", 0) > 0
    s.check("GET /salesforce/health", ok, f"code={r.status_code}, payload={r.text[:120]}")
    r = get("/jira/health")
    ok = r.status_code == 200 and r.json().get("records", 0) > 0
    s.check("GET /jira/health", ok, f"code={r.status_code}, payload={r.text[:120]}")

    r = get("/salesforce", {"limit": 5})
    js = r.json() if r.status_code == 200 else {}
    s.check("GET /salesforce paginated", r.status_code == 200 and js.get("count", 0) <= 5,
            f"code={r.status_code}, count={js.get('count')}")

    r = get("/jira", {"limit": 5})
    js = r.json() if r.status_code == 200 else {}
    s.check("GET /jira paginated", r.status_code == 200 and js.get("count", 0) <= 5,
            f"code={r.status_code}, count={js.get('count')}")

def test_mcp(s: Suite):
    s.section("MCP unified")
    r = get("/mcp/accounts", {"limit": 50})
    s.check("GET /mcp/accounts 200", r.status_code == 200, f"code={r.status_code}")
    if r.status_code != 200:
        return None, None
    data = r.json()
    items: List[Dict[str, Any]] = data.get("items", [])
    s.check("MCP items present", isinstance(items, list) and len(items) > 0, f"len={len(items)}")

    # Invariants per account
    first_id = None
    for a in items:
        oid = a.get("OpenIssues", 0)
        p1 = a.get("OpenP1Issues", 0) or 0
        p2 = a.get("OpenP2Issues", 0) or 0
        p3 = a.get("OpenP3Issues", 0) or 0

        s.check("sum(Px) <= OpenIssues",
                (p1 + p2 + p3) <= oid,
                f"AccountID={a.get('AccountID')}, OpenIssues={oid}, Px_sum={p1+p2+p3}")

        s.check("LastIssueDate ISO or None",
                (a.get("LastIssueDate") is None) or (parse_iso(a.get("LastIssueDate")) is not None),
                f"LastIssueDate={a.get('LastIssueDate')}")

        if not first_id:
            first_id = a.get("AccountID")

    # Single account lookup matches list entry shape
    if first_id:
        r2 = get(f"/mcp/accounts/{first_id}")
        s.check("GET /mcp/accounts/{id} 200", r2.status_code == 200, f"code={r2.status_code}")
        if r2.status_code == 200:
            one = r2.json()
            s.check("Single account has LinkedIssues list", isinstance(one.get("LinkedIssues", []), list),
                    f"len={len(one.get('LinkedIssues', []))}")
    return items, data

def test_insights_top_revenue(s: Suite):
    s.section("Insights: top revenue by priority")
    for priority in ["P1", "P2", "P3"]:
        r = get("/insights/top-revenue", {"priority": priority, "limit": 5})
        ok = r.status_code == 200
        s.check(f"top-revenue {priority} 200", ok, f"code={r.status_code}")
        if not ok: 
            continue
        js = r.json()
        items = js.get("items", [])
        # Items sorted by ARR desc
        arrs = [i.get("ARR") or 0 for i in items]
        s.check(f"top-revenue {priority} sorted desc",
                arrs == sorted(arrs, reverse=True), f"ARRs={arrs}")
        # Each has open count for that priority
        key = {"P1":"OpenP1Issues","P2":"OpenP2Issues","P3":"OpenP3Issues"}[priority]
        s.check(f"top-revenue {priority} all have open>0",
                all((i.get(key,0) or 0) > 0 for i in items),
                f"items={len(items)}")

def test_insights_threshold(s: Suite):
    s.section("Insights: threshold by priority")
    for priority in ["P1", "P2", "P3"]:
        r = get("/insights/accounts-with-critical", {"priority": priority, "min": 2})
        ok = r.status_code == 200
        s.check(f"accounts-with-critical {priority} 200", ok, f"code={r.status_code}")
        if not ok:
            continue
        js = r.json()
        key = {"P1":"OpenP1Issues","P2":"OpenP2Issues","P3":"OpenP3Issues"}[priority]
        s.check(f"threshold {priority} respects min",
                all((i.get(key,0) or 0) >= 2 for i in js.get("items", [])),
                f"count={len(js.get('items', []))}")

def test_insights_renewals(s: Suite):
    s.section("Insights: renewals window tests")
    # Use historical window that we know yields results in your dataset
    params = {"priority":"P1","days":90,"today":"2023-12-15"}
    r = get("/insights/renewals-with", params)
    s.check("renewals-with P1 200", r.status_code == 200, f"code={r.status_code}")
    if r.status_code != 200:
        return
    js = r.json()
    items = js.get("items", [])
    base_today = parse_iso(js.get("as_of"))
    horizon = base_today + timedelta(days=js.get("window_days", 0)) if base_today else None

    # each item in window
    in_window = True
    for it in items:
        rd = parse_iso(it.get("RenewalDate"))
        if not (rd and base_today and horizon and base_today <= rd <= horizon):
            in_window = False
            break
    s.check("renewals items within window", in_window, f"count={len(items)}")

    # sorted by date asc then ARR desc
    def sort_key(x):
        return (parse_iso(x.get("RenewalDate")) or date(2100,1,1), -(x.get("ARR") or 0))
    s.check("renewals sorted by date then ARR",
            items == sorted(items, key=sort_key), f"count={len(items)}")

def test_insights_summary(s: Suite):
    s.section("Insights: summary")
    r = get("/insights/summary")
    s.check("summary 200", r.status_code == 200, f"code={r.status_code}")
    if r.status_code != 200:
        return
    js = r.json()
    # Non negative integers
    for bucket in ["p1","p2","p3"]:
        b = js.get(bucket, {})
        ok = isinstance(b.get("accounts_with_open",0), int) and isinstance(b.get("total_open",0), int)
        s.check(f"summary {bucket} numeric fields", ok, f"{b}")
        s.check(f"summary {bucket} non negative", b.get("accounts_with_open",0) >= 0 and b.get("total_open",0) >= 0)

    # Optional cross check: total_open for P1 equals sum of OpenP1Issues over all accounts
    r2 = get("/mcp/accounts", {"limit": 1000})
    if r2.status_code == 200:
        accs = r2.json().get("items", [])
        sum_p1 = sum(a.get("OpenP1Issues",0) or 0 for a in accs)
        s.check("summary p1 total_open matches accounts sum", js.get("p1",{}).get("total_open", -1) == sum_p1,
                f"summary={js.get('p1',{}).get('total_open')} accounts_sum={sum_p1}")

def main():
    suite = Suite()
    try:
        test_health(suite)
        test_raw_sources(suite)
        test_mcp(suite)
        test_insights_top_revenue(suite)
        test_insights_threshold(suite)
        test_insights_renewals(suite)
        test_insights_summary(suite)
    except Exception as e:
        suite.check("Unhandled exception", False, str(e))
    exit_code = suite.report()
    # also write machine readable result for records
    out = {
        "base_url": BASE_URL,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "results": [{"name": n, "status": s, "info": i} for n,s,i in suite.results]
    }
    os.makedirs("scripts/_out", exist_ok=True)
    with open("scripts/_out/smoke_results.json", "w") as f:
        json.dump(out, f, indent=2)
    print("\nSaved report to scripts/_out/smoke_results.json")
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
