# 🧠 UnifyIQ – Unified Data Intelligence Platform (Mini)

This repo contains a working simulation of a unified data platform that blends **Salesforce** and **Jira** datasets into one intelligent layer, with a backend (FastAPI) and a frontend (React). The platform can answer natural language queries like  
> “Show accounts with ARR between 100k and 300k and at least 2 P1 issues in Europe”  
by dynamically planning and executing API calls.

---

## ⚡ What This Repo Does

- Serves **Salesforce** and **Jira** Excel data as APIs (`/salesforce`, `/jira`)  
- Builds a **unification layer** (`/mcp/accounts`) to merge, normalize, and enrich records  
- Exposes **insight endpoints** (`/insights/...`) to query revenue, renewals, critical issues, and aggregations  
- Integrates a **natural language agent** (`/agent/query`) powered by LLM planning + deterministic fallbacks  
- Provides a clean **React UI** to run queries and view results in real time

---

## 🏗️ Project Structure

```
unifyiq/
├── api/ # FastAPI backend
│ ├── salesforce/ # Salesforce data API
│ ├── jira/ # Jira data API
│ ├── mcp/ # Unification layer
│ ├── insights/ # Derived insights endpoints
│ ├── agent/ # LLM + deterministic planner
│ └── main.py # FastAPI entry point (port 8000)
│
├── ui/ # React frontend (port 5173)
│ ├── src/
│ └── package.json
│
├── data/
│ ├── Salesforce_accounts_large.xlsx
│ └── Jira_issues_large.xlsx
│
└── README.md
```


---

## ⚙️ Setup Instructions

### 1. Backend (FastAPI)

```bash
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000
```
Create a `.env` file in the project root with the following:
```bash
GEMINI_API_KEY=your_gemini_api_key_here
```

### 2. Frontent (React)
```bash
cd ui
npm install
npm run dev
```
Create a `.env.local` file inside the ui folder:
```bash
VITE_APP_BASE=http://localhost:8000
```

- Access frontend at http://localhost:5173
- Access backend at http://localhost:8000

--- 

## 🧠 Key Implementation Details

### Salesforce & Jira APIs
- `/salesforce` and `/jira` simply serve data from the Excel files.
- We normalize:
    - Dates to ISO format
    - Status fields in Jira (open/closed mapping)
    - Priorities to `P1 | P2 | P3`

### MCP (Unification Layer)
- Unified by `AccountID` and `Jira EpicLink`.
- If `EpicLink` was missing, we generated a synthetic key by concatenating `AccountName` (Salesforce) and a hash fallback.
- Orphan Jira issues (with no matching account) are counted separately but not discarded.

### Insights Endpoints
- `/insights/top-revenue` → Top accounts by ARR
- `/insights/renewals-with` → Accounts renewing soon
- `/insights/accounts-with-critical` → Threshold queries for open P1s
- `/insights/group-by` → Region/Stage/Industry level aggregations
- `/insights/summary` → Basic stats snapshot

### Agent
- Converts natural language into a structured Plan JSON
- Picks correct endpoint, applies filters, sorting, grouping, etc.
- Uses Gemini 1.5 Flash for planning, falls back to deterministic regex routes when needed
- If the question is outside supported scope (e.g., churn, NPS, retention), it responds with “Sorry, I don’t know how to answer that yet.” instead of hallucinating

### UI
- Inspired by linear.app aesthetics
- Clean query bar at the top
- Dynamic results table with auto-rendered columns
- Handles error states, loading states, and empty results gracefully

---

## 📝 Assumptions Made
- Missing EpicLink in Jira was handled using fallback key logic as described above.
- ARR values are treated as integers (no currency conversions).
- Data is static from Excel files. In real use, this would be replaced by live Salesforce/Jira APIs.
- Queries are stateless; the agent doesn’t maintain conversational context.

---

## 🚀 Example Queries
Try these in the UI to test different paths:
- `top revenue accounts p1`
- `renewals next month apac p2`
- `group by region with bugs only for p1`
- `accounts with at least 3 p1`
- `show accounts arr 100k to 300k with p1 >= 2 in europe`

---

## 🧪 Tech Stack
- Backend: Python, FastAPI, Pydantic, Uvicorn
- Frontend: React (Vite), TailwindCSS
- LLM: Gemini 1.5 Flash (planning only, no direct answering)
---

## 💭 Why This Architecture
- Keeping Salesforce/Jira endpoints separate preserves modularity and mirrors real-world integrations.
- MCP unification creates a single source of truth layer for downstream insights.
- Agent planning layer lets us handle natural language without hardcoding every query.
- React UI provides a clean and minimal client to validate end-to-end behavior.

---

## 🪄 Bonus Features
- Honest "I don't know" fallback for out-of-scope queries
- Supports CSV download for any query
---

## 🙌 Credits

Parts of the planning, documentation, and code structuring were refined with help from ChatGPT (OpenAI), used as a coding assistant.

--- 


> LLM key (Gemini) is optional. If not set, fallback planner handles basic queries.
