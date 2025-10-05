import { useEffect, useMemo, useRef, useState } from "react";
import { Download, Loader2, Play, Search, SlidersHorizontal, Trash2 } from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";

type Row = Record<string, any>;

type AgentJSONResponse = {
  query: string;
  intent: string;
  warnings: string[];
  plan: any;
  answer?: string;
  result: Row[];
  meta: any;
};

type AgentCSVResponse = {
  query: string;
  intent: string;
  warnings: string[];
  plan: any;
  content_type: "text/csv";
  result: string; // CSV text
  meta: any;
};

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

const STARTER_QUERIES = [
  "group by region with bugs only for p1",
  "accounts with at least 3 p1",
  "renewals next month for sev2 in apac",
  "top revenue p1 in retail",
  "accounts with 3 to 5 p1 in north america",
];

function classNames(...xs: Array<string | false | null | undefined>) {
  return xs.filter(Boolean).join(" ");
}

export default function App() {
  const [q, setQ] = useState(STARTER_QUERIES[0]);
  const [data, setData] = useState<Row[]>([]);
  const [answer, setAnswer] = useState<string>("");
  const [plan, setPlan] = useState<any>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [errorText, setErrorText] = useState<string | null>(null);
  const [showPlan, setShowPlan] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    // autofocus
    inputRef.current?.focus();
  }, []);

  const columns = useMemo(() => {
    if (!Array.isArray(data)) return [];
    const keys = new Set<string>();
    data.forEach((r) => Object.keys(r).forEach((k) => keys.add(k)));
    return Array.from(keys);
  }, [data]);

  const isGroupBy = useMemo(() => {
    if (!Array.isArray(data) || !data?.length) return false;
    const r0 = data[0];
    return "group" in r0 && ("total_open" in r0 || "count" in r0);
  }, [data]);

  const chartData = useMemo(() => {
    if (!isGroupBy || !Array.isArray(data)) return [];
    return data.map((d) => ({
      name: d.group,
      total_open: Number(d.total_open ?? 0),
      count: Number(d.count ?? 0),
    }));
  }, [isGroupBy, data]);

  async function runQuery(asCSV = false) {
    setLoading(true);
    setErrorText(null);
    try {
      const res = await fetch(`${API_BASE}/agent/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(asCSV ? { q, format: "csv" } : { q }),
      });

      if (!res.ok) {
        const t = await res.text();
        throw new Error(`${res.status} ${res.statusText}: ${t}`);
      }

      const ct = res.headers.get("content-type") ?? "";
      if (ct.includes("application/json")) {
        const json = (await res.json()) as AgentJSONResponse;
        setData(json.result || []);
        setAnswer(json.answer || "");
        setPlan(json.plan);
        setWarnings(json.warnings || []);
      } else {
        // fallback; but server always JSON-wraps even for CSV path
        const txt = await res.text();
        setData([]);
        setAnswer(txt);
        setPlan(null);
      }
    } catch (err: any) {
      setErrorText(err?.message ?? "Request failed");
    } finally {
      setLoading(false);
    }
  }

  async function downloadCSV() {
    try {
      const res = await fetch(`${API_BASE}/agent/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ q, format: "csv" }),
      });
      if (!res.ok) throw new Error(await res.text());
      const json = (await res.json()) as AgentCSVResponse;
      const blob = new Blob([json.result ?? ""], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const fname = `agent-${Date.now()}.csv`;
      a.download = fname;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      setErrorText(e?.message ?? "CSV download failed");
    }
  }

  function clearAll() {
    setData([]);
    setAnswer("");
    setPlan(null);
    setWarnings([]);
    setErrorText(null);
  }

  return (
    <div className="min-h-screen w-full bg-gradient-to-br from-neutral-950 via-neutral-900 to-neutral-950 text-neutral-100">
      {/* Top bar */}
      <div className="sticky top-0 z-10 border-b border-neutral-800/50 bg-neutral-950/90 backdrop-blur-md shadow-lg">
        <div className="mx-auto flex max-w-7xl items-center gap-3 px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-lg bg-gradient-to-r from-indigo-600 to-purple-600 flex items-center justify-center">
              <Search className="h-5 w-5 text-white" />
            </div>
            <div className="text-xl font-bold tracking-tight bg-gradient-to-r from-indigo-400 to-purple-400 bg-clip-text text-transparent">
              UnifyIQ Console
            </div>
          </div>
          <div className="ml-auto flex items-center gap-3">
            <button
              onClick={downloadCSV}
              className="inline-flex items-center gap-2 rounded-lg border border-neutral-700 bg-neutral-800/50 px-4 py-2 text-sm font-medium text-neutral-200 hover:bg-neutral-700 hover:border-neutral-600 transition-all duration-200 hover:shadow-md"
              title="Download CSV of current query"
            >
              <Download className="h-4 w-4" />
              Export CSV
            </button>
            <button
              onClick={() => setShowPlan((s) => !s)}
              className={classNames(
                "inline-flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-medium transition-all duration-200 hover:shadow-md",
                showPlan
                  ? "border-indigo-500 bg-indigo-500/10 text-indigo-300 hover:bg-indigo-500/20"
                  : "border-neutral-700 bg-neutral-800/50 text-neutral-200 hover:bg-neutral-700 hover:border-neutral-600"
              )}
              title="Toggle plan/debug"
            >
              <SlidersHorizontal className="h-4 w-4" />
              {showPlan ? "Hide Debug" : "Show Debug"}
            </button>
          </div>
        </div>
      </div>

      {/* Query input */}
      <div className="mx-auto mt-8 max-w-7xl px-6">
        <div className="flex items-center gap-3">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-neutral-400" />
            <input
              ref={inputRef}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") runQuery(false); }}
              placeholder='Ask: "group by region with bugs only for p1"'
              className="w-full rounded-xl border border-neutral-700 bg-neutral-800/50 px-12 py-4 text-sm outline-none placeholder:text-neutral-500 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-all duration-200 hover:border-neutral-600"
            />
          </div>
          <button
            onClick={() => runQuery(false)}
            disabled={loading}
            className={classNames(
              "inline-flex items-center gap-2 rounded-xl border px-6 py-4 text-sm font-semibold transition-all duration-200 hover:shadow-lg disabled:opacity-50 disabled:cursor-not-allowed",
              loading
                ? "border-indigo-500 bg-indigo-500 text-white"
                : "border-indigo-600 bg-gradient-to-r from-indigo-600 to-purple-600 text-white hover:from-indigo-500 hover:to-purple-500"
            )}
          >
            {loading ? <Loader2 className="h-5 w-5 animate-spin" /> : <Play className="h-5 w-5" />}
            {loading ? "Running..." : "Run Query"}
          </button>
          <button
            onClick={clearAll}
            className="inline-flex items-center gap-2 rounded-xl border border-neutral-700 bg-neutral-800/50 px-4 py-4 text-sm font-medium text-neutral-200 hover:bg-neutral-700 hover:border-neutral-600 transition-all duration-200 hover:shadow-md"
            title="Clear all results"
          >
            <Trash2 className="h-5 w-5" />
          </button>
        </div>

        {/* Suggestions */}
        <div className="mt-4 flex flex-wrap gap-2">
          {STARTER_QUERIES.map((s) => (
            <button
              key={s}
              onClick={() => setQ(s)}
              className="rounded-full border border-neutral-700 bg-neutral-800/30 px-4 py-2 text-xs text-neutral-300 hover:bg-neutral-700 hover:border-neutral-600 transition-all duration-200 hover:shadow-sm"
            >
              {s}
            </button>
          ))}
        </div>

        {/* Errors / warnings */}
        {errorText && (
          <div className="mt-6 rounded-xl border border-red-900/60 bg-gradient-to-r from-red-950/40 to-red-900/20 p-4 text-sm text-red-300 shadow-lg">
            <div className="flex items-center gap-2">
              <div className="h-2 w-2 rounded-full bg-red-500"></div>
              <span className="font-medium">Error:</span>
            </div>
            <div className="mt-1">{errorText}</div>
          </div>
        )}
        {warnings?.length > 0 && (
          <div className="mt-6 rounded-xl border border-amber-900/60 bg-gradient-to-r from-amber-950/40 to-amber-900/20 p-4 text-sm text-amber-300 shadow-lg">
            <div className="flex items-center gap-2">
              <div className="h-2 w-2 rounded-full bg-amber-500"></div>
              <span className="font-medium">Warnings:</span>
            </div>
            <div className="mt-1 space-y-1">
              {warnings.map((w, i) => <div key={i}>• {w}</div>)}
            </div>
          </div>
        )}

        {/* Answer summary */}
        {answer && (
          <div className="mt-8 rounded-xl border border-neutral-700 bg-gradient-to-r from-neutral-800/50 to-neutral-900/50 p-6 text-sm text-neutral-200 shadow-lg">
            <div className="flex items-center gap-2 mb-3">
              <div className="h-2 w-2 rounded-full bg-green-500"></div>
              <span className="font-semibold text-neutral-100">Summary</span>
            </div>
            {answer}
          </div>
        )}

        {/* Group chart */}
        {isGroupBy && chartData.length > 0 && (
          <div className="mt-8 rounded-xl border border-neutral-700 bg-gradient-to-r from-neutral-800/50 to-neutral-900/50 p-6 shadow-lg">
            <div className="mb-4 text-lg font-semibold text-neutral-100">Group Analysis</div>
            <div className="h-80 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                  <XAxis dataKey="name" stroke="#9ca3af" tick={{ fontSize: 12 }} />
                  <YAxis stroke="#9ca3af" tick={{ fontSize: 12 }} />
                  <Tooltip
                    contentStyle={{
                      background: "linear-gradient(to right, #1f2937, #111827)",
                      border: "1px solid #374151",
                      borderRadius: "8px",
                      color: "#f3f4f6"
                    }}
                  />
                  <Bar dataKey="total_open" fill="url(#barGradient)" radius={[4, 4, 0, 0]} />
                  <defs>
                    <linearGradient id="barGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#6366f1" />
                      <stop offset="100%" stopColor="#8b5cf6" />
                    </linearGradient>
                  </defs>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* Results table */}
        <div className="mt-8 overflow-hidden rounded-xl border border-neutral-700 shadow-lg">
          <div className="max-h-[70vh] overflow-auto">
            <table className="min-w-full divide-y divide-neutral-700">
              <thead className="bg-gradient-to-r from-neutral-800 to-neutral-900">
                <tr>
                  {columns.length === 0 ? (
                    <th className="px-6 py-4 text-left text-sm font-semibold text-neutral-300">
                      <div className="flex items-center gap-2">
                        <div className="h-2 w-2 rounded-full bg-neutral-500"></div>
                        No results yet — run a query above
                      </div>
                    </th>
                  ) : (
                    columns.map((c) => (
                      <th
                        key={c}
                        className="px-6 py-4 text-left text-xs font-bold uppercase tracking-wider text-neutral-300"
                      >
                        {c.replace(/_/g, ' ')}
                      </th>
                    ))
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-800 bg-gradient-to-b from-neutral-900/50 to-neutral-950">
                {Array.isArray(data) && data.map((row, idx) => (
                  <tr key={idx} className="hover:bg-neutral-800/30 transition-colors duration-150">
                    {columns.map((c) => (
                      <td key={c} className="whitespace-nowrap px-6 py-3 text-sm text-neutral-200">
                        {formatCell(row[c])}
                      </td>
                    ))}
                  </tr>
                ))}
                {(!Array.isArray(data) || data.length === 0) && (
                  <tr>
                    <td className="px-6 py-12 text-center text-sm text-neutral-400">
                      <div className="flex flex-col items-center gap-2">
                        <div className="h-8 w-8 rounded-full bg-neutral-800 flex items-center justify-center">
                          <Search className="h-4 w-4 text-neutral-500" />
                        </div>
                        No rows to display.
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Plan / meta */}
        {showPlan && (
          <div className="mt-8 grid gap-8 md:grid-cols-2">
            <div className="rounded-xl border border-neutral-700 bg-gradient-to-r from-neutral-800/50 to-neutral-900/50 p-6 shadow-lg">
              <div className="mb-3 text-lg font-semibold text-neutral-100 flex items-center gap-2">
                <SlidersHorizontal className="h-5 w-5" />
                Execution Plan
              </div>
              <pre className="max-h-[50vh] overflow-auto rounded-lg bg-neutral-950/50 p-4 text-xs text-neutral-300 border border-neutral-800">
                {JSON.stringify(plan, null, 2)}
              </pre>
            </div>
            <div className="rounded-xl border border-neutral-700 bg-gradient-to-r from-neutral-800/50 to-neutral-900/50 p-6 shadow-lg">
              <div className="mb-3 text-lg font-semibold text-neutral-100 flex items-center gap-2">
                <Search className="h-5 w-5" />
                Data Sources
              </div>
              <pre className="max-h-[50vh] overflow-auto rounded-lg bg-neutral-950/50 p-4 text-xs text-neutral-300 border border-neutral-800">
                {JSON.stringify({ fetches: (plan?.steps ?? []).filter((s: any) => s.op === "fetch") }, null, 2)}
              </pre>
            </div>
          </div>
        )}

        <div className="my-16" />
      </div>
    </div>
  );
}

function formatCell(v: any) {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return new Intl.NumberFormat().format(v);
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (typeof v === "string" && v.length > 120) return v.slice(0, 117) + "…";
  if (Array.isArray(v)) return v.length ? `${v.length} item(s)` : "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}
