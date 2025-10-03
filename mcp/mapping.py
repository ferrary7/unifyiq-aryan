from typing import Dict, List

def build_epic_to_account_map(salesforce_records: List[dict], jira_records: List[dict]) -> Dict[str, str]:
    acc_ids = sorted({r.get("AccountID") for r in salesforce_records if r.get("AccountID")})
    epics = sorted({r.get("EpicLink") for r in jira_records if r.get("EpicLink")})
    if not acc_ids or not epics:
        return {}
    mapping = {}
    i = 0
    for e in epics:
        mapping[e] = acc_ids[i]
        i = (i + 1) % len(acc_ids)
    return mapping
