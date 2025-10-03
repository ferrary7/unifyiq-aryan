from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"

SALESFORCE_XLSX = DATA_DIR / "salesforce_accounts_large.xlsx"
JIRA_XLSX = DATA_DIR / "jira_issues_large.xlsx"
