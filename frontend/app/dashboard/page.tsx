"use client";

import { useState, useEffect } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  Cell, LabelList,
} from "recharts";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const GREEN = "#33503f";
const TERRA = "#c1743f";
const SAND = "#c9c1ad";
const INK2 = "#8a8678";
const LINE = "#e7e1d3";

type ModeStats = { p: number; r: number; mrr: number; hit: number };
type Bucket = { n: number; modes: Record<string, ModeStats> };
type Retrieval = {
  top_k: number;
  overall: Bucket;
  by_style: { "natural-language": Bucket; "exact-term": Bucket };
};
type Answers = {
  correctness: { overall: { correct: number; total: number }; by_type: Record<string, { correct: number; total: number }> };
  faithfulness: { score: number | null; counts: Record<string, number>; n: number };
  out_of_scope: { appropriate: number; total: number };
};
type Latency = { n: number; unit: string; stages: Record<string, { mean: number; p50: number; p95: number }> };
type Results = { retrieval: Retrieval | null; answers: Answers | null; latency: Latency | null };

const MODE_COLOR: Record<string, string> = {
  "keyword-only": SAND,
  "vector-only": TERRA,
  "hybrid (RRF)": GREEN,
};

function pct(n: number) {
  return `${Math.round(n * 100)}%`;
}

function Metric({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="metric">
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
      {sub && <div className="metric-sub">{sub}</div>}
    </div>
  );
}

function RetrievalChart({ bucket, metric }: { bucket: Bucket; metric: keyof ModeStats }) {
  const data = Object.entries(bucket.modes).map(([mode, stats]) => ({
    mode: mode.replace(" (RRF)", ""),
    fullMode: mode,
    value: stats[metric],
  }));
  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={data} margin={{ top: 18, right: 8, left: -18, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={LINE} vertical={false} />
        <XAxis dataKey="mode" tick={{ fontSize: 12, fill: INK2 }} axisLine={{ stroke: LINE }} tickLine={false} />
        <YAxis domain={[0, 1]} tick={{ fontSize: 11, fill: INK2 }} axisLine={false} tickLine={false} />
        <Tooltip
          cursor={{ fill: "rgba(0,0,0,0.03)" }}
          contentStyle={{ background: "#fffdf8", border: `1px solid ${LINE}`, borderRadius: 10, fontSize: 13 }}
          formatter={(v) => [typeof v === "number" ? v.toFixed(3) : v, metric.toUpperCase()]}
        />
        <Bar dataKey="value" radius={[5, 5, 0, 0]}>
          {data.map((d) => <Cell key={d.fullMode} fill={MODE_COLOR[d.fullMode] || INK2} />)}
          <LabelList dataKey="value" position="top" formatter={(v: number | string | undefined) => typeof v === "number" ? v.toFixed(2) : v} style={{ fontSize: 11, fill: INK2 }} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function LatencyChart({ latency }: { latency: Latency }) {
  const data = Object.entries(latency.stages).map(([stage, s]) => ({
    stage: stage.replace("_", " "),
    mean: Math.round(s.mean),
    p95: Math.round(s.p95),
  }));
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 18, right: 8, left: -8, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={LINE} vertical={false} />
        <XAxis dataKey="stage" tick={{ fontSize: 12, fill: INK2 }} axisLine={{ stroke: LINE }} tickLine={false} />
        <YAxis tick={{ fontSize: 11, fill: INK2 }} axisLine={false} tickLine={false} unit="ms" width={56} />
        <Tooltip
          cursor={{ fill: "rgba(0,0,0,0.03)" }}
          contentStyle={{ background: "#fffdf8", border: `1px solid ${LINE}`, borderRadius: 10, fontSize: 13 }}
          formatter={(v, name) => [`${typeof v === "number" ? v : String(v)} ms`, name === "mean" ? "Mean" : "p95"]}
        />
        <Bar dataKey="mean" fill={GREEN} radius={[5, 5, 0, 0]}>
          <LabelList dataKey="mean" position="top" formatter={(v: number | string | undefined) => `${v ?? ""}`} style={{ fontSize: 11, fill: INK2 }} />
        </Bar>
        <Bar dataKey="p95" fill={TERRA} radius={[5, 5, 0, 0]}>
          <LabelList dataKey="p95" position="top" formatter={(v: number | string | undefined) => `${v ?? ""}`} style={{ fontSize: 11, fill: INK2 }} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export default function Dashboard() {
  const [data, setData] = useState<Results | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [scope, setScope] = useState<"overall" | "natural-language" | "exact-term">("overall");
  const [metric, setMetric] = useState<keyof ModeStats>("p");

  useEffect(() => {
    fetch(`${API}/eval/results`)
      .then((r) => { if (!r.ok) throw new Error(`server responded ${r.status}`); return r.json(); })
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  const bucket =
    data?.retrieval
      ? scope === "overall"
        ? data.retrieval.overall
        : data.retrieval.by_style[scope]
      : null;

  const METRIC_LABEL: Record<string, string> = { p: "Precision@5", r: "Recall@5", mrr: "MRR", hit: "Hit rate" };

  return (
    <main className="app">
      <header className="topbar">
        <div className="logo">iA</div>
        <span className="wordmark">InsightAgent</span>
        <span className="divider" />
        <span className="assistant-label">Evaluation</span>
        <span className="spacer" />
        <a className="navlink" href="/">Assistant</a>
      </header>

      <div className="dash-scroll">
        <div className="dash-center">
          <div className="dash-head">
            <h1 className="dash-title">How well the system works</h1>
            <p className="dash-lead">
              Retrieval quality, answer correctness, grounding, and speed, measured on a
              fixed set of labeled questions. Numbers come from the offline evaluation,
              served live from the API.
            </p>
          </div>

          {error && (
            <div className="dash-error">
              Could not load results ({error}). Confirm the backend is running at {API} and that
              the evaluation has been run.
            </div>
          )}

          {!error && !data && <div className="dash-loading">Loading results...</div>}

          {data?.retrieval && bucket && (
            <section className="dash-section">
              <div className="section-label">Retrieval</div>
              <div className="panel-card">
                <p className="section-note">
                  Three search methods on the same queries and candidate pool. Only the
                  ranking and fusion differ. Hybrid combines vector and keyword by reciprocal
                  rank fusion.
                </p>

                <div className="toggle-row">
                  <div className="toggle-group">
                    {(["overall", "natural-language", "exact-term"] as const).map((s) => (
                      <button
                        key={s}
                        className={`toggle ${scope === s ? "on" : ""}`}
                        onClick={() => setScope(s)}
                      >
                        {s === "overall" ? "Overall" : s === "natural-language" ? "Natural language" : "Exact term"}
                      </button>
                    ))}
                  </div>
                  <div className="toggle-group">
                    {(["p", "r", "mrr", "hit"] as const).map((m) => (
                      <button
                        key={m}
                        className={`toggle ${metric === m ? "on" : ""}`}
                        onClick={() => setMetric(m)}
                      >
                        {METRIC_LABEL[m]}
                      </button>
                    ))}
                  </div>
                </div>

                <RetrievalChart bucket={bucket} metric={metric} />

                <div className="legend-row">
                  <span><i style={{ background: SAND }} />keyword</span>
                  <span><i style={{ background: TERRA }} />vector</span>
                  <span><i style={{ background: GREEN }} />hybrid</span>
                  <span className="legend-n">{bucket.n} queries</span>
                </div>

                {scope === "exact-term" && (
                  <p className="section-note insight">
                    On exact-term queries (section numbers, regulation codes), keyword
                    matches what vector misses, and hybrid leads on every metric. This is the
                    case that justifies fusing the two.
                  </p>
                )}
              </div>
            </section>
          )}

          {data?.answers && (
            <section className="dash-section">
              <div className="section-label">Answer quality</div>
              <div className="metric-grid">
                <Metric
                  label="Correctness"
                  value={pct(data.answers.correctness.overall.correct / data.answers.correctness.overall.total)}
                  sub={`${data.answers.correctness.overall.correct} of ${data.answers.correctness.overall.total} contain the expected facts`}
                />
                <Metric
                  label="Faithfulness"
                  value={data.answers.faithfulness.score != null ? data.answers.faithfulness.score.toFixed(2) : "n/a"}
                  sub="grounded = 1, partial = 0.5, unsupported = 0"
                />
                <Metric
                  label="Out-of-scope honesty"
                  value={`${data.answers.out_of_scope.appropriate}/${data.answers.out_of_scope.total}`}
                  sub="declined instead of fabricating"
                />
              </div>

              <div className="panel-card" style={{ marginTop: 14 }}>
                <div className="section-label" style={{ marginBottom: 12 }}>Correctness by question type</div>
                <div className="bars">
                  {Object.entries(data.answers.correctness.by_type).map(([type, c]) => {
                    const frac = c.total ? c.correct / c.total : 0;
                    return (
                      <div className="bar-row" key={type}>
                        <span className="bar-label">{type}</span>
                        <div className="bar-track">
                          <div className="bar-fill" style={{ width: `${frac * 100}%` }} />
                        </div>
                        <span className="bar-val">{pct(frac)} <span className="bar-frac">({c.correct}/{c.total})</span></span>
                      </div>
                    );
                  })}
                </div>

                <div className="section-label" style={{ margin: "20px 0 12px" }}>Faithfulness breakdown</div>
                <div className="faith-bar">
                  {(["grounded", "partial", "unsupported"] as const).map((k) => {
                    const v = data.answers!.faithfulness.counts[k] || 0;
                    const total = data.answers!.faithfulness.n || 1;
                    const color = k === "grounded" ? GREEN : k === "partial" ? TERRA : "#a23b2b";
                    return v > 0 ? (
                      <div key={k} className="faith-seg" style={{ width: `${(v / total) * 100}%`, background: color }} title={`${k}: ${v}`} />
                    ) : null;
                  })}
                </div>
                <div className="faith-legend">
                  <span><i style={{ background: GREEN }} />grounded {data.answers.faithfulness.counts.grounded || 0}</span>
                  <span><i style={{ background: TERRA }} />partial {data.answers.faithfulness.counts.partial || 0}</span>
                  <span><i style={{ background: "#a23b2b" }} />unsupported {data.answers.faithfulness.counts.unsupported || 0}</span>
                </div>
              </div>
            </section>
          )}

          {data?.latency && (
            <section className="dash-section">
              <div className="section-label">Latency</div>
              <div className="panel-card">
                <p className="section-note">
                  Search time split into its stages, over {data.latency.n} queries. Mean and p95
                  in milliseconds. Embedding is an external API round trip; retrieval is the
                  database query.
                </p>
                <LatencyChart latency={data.latency} />
                <div className="legend-row">
                  <span><i style={{ background: GREEN }} />mean</span>
                  <span><i style={{ background: TERRA }} />p95</span>
                </div>
              </div>
            </section>
          )}

          <div className="dash-footer">
            Evaluation runs offline against a labeled question set. Refresh after re-running it
            to update these numbers.
          </div>
        </div>
      </div>
    </main>
  );
}
