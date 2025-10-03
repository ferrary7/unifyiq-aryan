# UnifyIQ

UnifyIQ is a mini unified data platform that blends Salesforce and Jira data into one intelligent layer.  
This repo is built phase by phase to simulate how real data platforms work, clean APIs, a unification layer, insights, and a simple UI.

## Quick start
```bash
python -m venv venv
# Linux/macOS
source venv/bin/activate
# Windows
venv\Scripts\activate

pip install -r requirements.txt
uvicorn api.main:app --reload
```

## Open:
- http://127.0.0.1:8000/
- http://127.0.0.1:8000/docs

## Repo Layout:
```bash
/api            FastAPI app
  main.py
/api/jira       Jira API code
/api/salesforce Salesforce API code
/data           Excel files
/mcp            Unification layer
/ui             Simple UI
/tests          Unit tests
```

# Phases
1. Setup & Heartbeat API
2. Salesforce & Jira APIs
3. MCP (Unification Layer)
4. Insights
5. UI
6. Docs & Extras