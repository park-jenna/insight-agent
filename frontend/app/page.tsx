"use client";

import { useState, useRef, useEffect } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type TraceStep = { tool: string; args: Record<string, any>; result?: any; ms?: number };
type Source = { filename: string; type: string; passages: number };
type Run = { trace: TraceStep[]; latency: number; steps: number; sources: Source[] };
type Message = { role: "user" | "assistant"; content: string; run?: Run };

const EXAMPLES = [
  "How does a parent file a state complaint about special education?",
  "How many students are active versus inactive?",
  "What percentage of students are in the ELEVATE program?",
  "Show the monthly enrollment trend.",
];

const CHIPS = [
  "Scholarships for undocumented seniors",
  "Active versus inactive students",
  "Monthly enrollment trend",
];

const PALETTE = ["#33503f", "#c1743f", "#c9c1ad", "#7a9b86", "#e0b27a", "#9c6b3f"];

function colorFor(label: string, i: number): string {
  const k = label.toLowerCase();
  if (k === "active") return "#33503f";
  if (k === "completed") return "#c1743f";
  if (k === "inactive") return "#c9c1ad";
  return PALETTE[i % PALETTE.length];
}

function describeStep(step: TraceStep): string {
  const a = step.args || {};
  switch (step.tool) {
    case "search_documents":
      return `Searched documents for "${a.query ?? ""}"`;
    case "analyze_dataset":
      return a.column
        ? `Analyzed ${a.dataset_name} \u00b7 ${a.column}`
        : `Listed the columns of ${a.dataset_name}`;
    case "detect_trends":
      return `Tracked ${a.metric ?? "counts"} over ${a.date_column} in ${a.dataset_name}`;
    case "find_anomalies":
      return `Scanned ${a.dataset_name} \u00b7 ${a.column} for outliers`;
    case "calculate_ratios":
      return `Computed a ratio in ${a.dataset_name} \u00b7 ${a.column}`;
    case "compare_periods":
      return `Compared ${a.dataset_name} around ${a.split_date}`;
    default:
      return step.tool;
  }
}

function summarizeResult(step: TraceStep): string {
  const t = step.tool;
  const r = step.result || {};
  let s = "";
  if (t === "search_documents") {
    const passages = (r.results || []).length;
    const docs = new Set((r.results || []).map((x: any) => x.source)).size;
    s = `${passages} passage${passages === 1 ? "" : "s"} \u00b7 ${docs} document${docs === 1 ? "" : "s"}`;
  } else if (t === "analyze_dataset") {
    if (r.type === "categorical" && r.top_values) {
      s = Object.entries(r.top_values).slice(0, 3).map(([k, v]) => `${k} ${v}`).join(" \u00b7 ");
    } else if (r.type === "numeric") {
      s = `mean ${r.mean} \u00b7 ${r.min} to ${r.max}`;
    } else if (r.columns) {
      s = `${r.columns.length} columns`;
    }
  } else if (t === "calculate_ratios") {
    if (r.percentage != null) s = `${r.percentage}%`;
  } else if (t === "detect_trends") {
    s = `${(r.points || []).length} periods`;
  } else if (t === "find_anomalies") {
    s = `${r.outlier_count ?? 0} outlier${r.outlier_count === 1 ? "" : "s"}`;
  } else if (t === "compare_periods") {
    s = `before ${r.before} \u00b7 after ${r.after}` + (r.percent_change != null ? ` (${r.percent_change}%)` : "");
  }
  const time = step.ms != null ? `${(step.ms / 1000).toFixed(2)}s` : "";
  return [s, time].filter(Boolean).join(" \u00b7 ");
}

function parseBold(text: string) {
  const parts = text.split("**");
  return parts.map((p, i) =>
    i % 2 === 1 ? <strong key={i}>{p}</strong> : <span key={i}>{p}</span>
  );
}

function SendIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  );
}

function Donut({ data }: { data: Record<string, number> }) {
  const entries = Object.entries(data);
  const total = entries.reduce((a, [, v]) => a + v, 0);
  const C = 2 * Math.PI * 42;
  let acc = 0;
  const segs = entries.map(([label, value], i) => {
    const frac = total ? value / total : 0;
    const seg = { label, value, frac, color: colorFor(label, i), dash: frac * C, offset: -acc * C };
    acc += frac;
    return seg;
  });
  return (
    <div className="donut-wrap">
      <div className="donut">
        <svg viewBox="0 0 120 120">
          <g transform="rotate(-90 60 60)">
            <circle cx="60" cy="60" r="42" fill="none" stroke="#efe9da" strokeWidth="15" />
            {segs.map((s, i) => (
              <circle key={i} cx="60" cy="60" r="42" fill="none" stroke={s.color} strokeWidth="15"
                strokeDasharray={`${s.dash} ${C}`} strokeDashoffset={s.offset} />
            ))}
          </g>
        </svg>
        <div className="donut-center"><b>{total}</b><span>Total</span></div>
      </div>
      <div className="legend">
        {segs.map((s, i) => (
          <div className="leg-row" key={i}>
            <span className="leg-dot" style={{ background: s.color }} />
            <span className="leg-label">{s.label}</span>
            <span className="leg-val">{s.value} ({total ? ((s.value / total) * 100).toFixed(1) : 0}%)</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const lastRun = [...messages].reverse().find((m) => m.run)?.run;
  const catStep = lastRun?.trace.find(
    (s) => s.result?.type === "categorical" && s.result?.top_values
  );

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading]);

  async function send(text?: string) {
    const q = (text ?? input).trim();
    if (!q || loading) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: q }]);
    setLoading(true);
    try {
      const res = await fetch(`${API}/agent/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: q, session_id: sessionId }),
      });
      if (!res.ok) throw new Error(`server responded ${res.status}`);
      const data = await res.json();
      setSessionId(data.session_id);
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: data.answer,
          run: {
            trace: data.tool_trace || [],
            latency: data.latency_ms,
            steps: data.steps,
            sources: data.sources || [],
          },
        },
      ]);
    } catch (e: any) {
      setMessages((m) => [
        ...m,
        { role: "assistant", content: `The assistant is unreachable (${e.message}). Confirm the backend is running at ${API}.` },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function onKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  }

  function reset() { setMessages([]); setSessionId(null); }

  return (
    <main className="app">
      <header className="topbar">
        <div className="logo">iA</div>
        <span className="wordmark">InsightAgent</span>
        <span className="divider" />
        <span className="assistant-label">ChiEAC Assistant</span>
        <span className="spacer" />
        {messages.length > 0 && (
          <button className="newchat" onClick={reset}>New conversation</button>
        )}
      </header>

      <div className="shell">
        <section className="conversation">
          <div className="scroll" ref={scrollRef}>
            <div className="center">
              <div className="crumbs">
                <b>Enrollment records</b> {"\u00b7"} <b>Policy library</b>
              </div>

              <div className="scroll-inner">
                {messages.length === 0 && !loading && (
                  <div className="empty">
                    <p className="lead">Ask across the documents and the data.</p>
                    <p className="empty-sub">
                      Policy and procedure come from your uploaded documents. Counts and
                      trends come from your program records. Every answer shows its work
                      in the panel on the right.
                    </p>
                    <div className="examples">
                      {EXAMPLES.map((ex) => (
                        <button key={ex} className="example" onClick={() => send(ex)}>
                          <span>Ask</span>{ex}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {messages.map((m, i) =>
                  m.role === "user" ? (
                    <div className="msg user" key={i}>
                      <div className="bubble">{m.content}</div>
                    </div>
                  ) : (
                    <div className="msg assistant" key={i}>
                      <div className="avatar-row">
                        <div className="mini-logo">iA</div>
                        <div className="bubble">{parseBold(m.content)}</div>
                      </div>
                    </div>
                  )
                )}

                {loading && (
                  <div className="msg assistant">
                    <div className="avatar-row">
                      <div className="mini-logo">iA</div>
                      <div className="running"><span className="dot" />Working through documents and data</div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="composer-wrap">
            <div className="center">
              <div className="composer">
                <textarea
                  rows={1}
                  placeholder="Ask anything about enrollment, policy, or compliance..."
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={onKey}
                />
                <button className="send" onClick={() => send()} disabled={loading || !input.trim()} aria-label="Send">
                  <SendIcon />
                </button>
              </div>
              <div className="chips">
                {CHIPS.map((c) => (
                  <button key={c} className="chip" onClick={() => send(c)}>{c}</button>
                ))}
              </div>
            </div>
          </div>
        </section>

        <aside className="rail">
          {loading && (
            <div>
              <div className="panel-label">Run status</div>
              <div className="panel"><div className="running"><span className="dot" />Planning and calling tools</div></div>
            </div>
          )}

          {!loading && lastRun && (
            <>
              <div>
                <div className="panel-label">Run status</div>
                <div className="panel">
                  {lastRun.trace.length === 0 && (
                    <div className="write-step">Answered directly, no tools needed.</div>
                  )}
                  {lastRun.trace.map((s, j) => (
                    <div className="run-step" key={j}>
                      <span className="n">{j + 1}</span>
                      <div className="rs-body">
                        <div className="d">{describeStep(s)}</div>
                        {summarizeResult(s) && <div className="rs-meta">{summarizeResult(s)}</div>}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <div className="panel-label">Write step</div>
                <div className="panel">
                  <div className="write-step">
                    Synthesized the answer
                    <div className="sub">Combined the tool results into a grounded response.</div>
                  </div>
                </div>
              </div>

              <div className="panel total">
                <span>Total time</span>
                <b>{(lastRun.latency / 1000).toFixed(2)}s</b>
              </div>

              {catStep && (
                <div>
                  <div className="panel-label">By {catStep.args.column}</div>
                  <div className="panel">
                    <Donut data={catStep.result.top_values} />
                  </div>
                </div>
              )}

              <div>
                <div className="panel-label">Sources</div>
                {lastRun.sources.length > 0 ? (
                  <div className="sources-list">
                    {lastRun.sources.map((s, i) => (
                      <div className="source-item" key={i}>
                        <span className={`src-type ${s.type}`}>{s.type.toUpperCase()}</span>
                        <div className="src-main">
                          <div className="src-name">{s.filename}</div>
                          <div className="src-sub">{s.passages} passage{s.passages === 1 ? "" : "s"} cited</div>
                        </div>
                        <span className="src-num">{i + 1}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="deferred"><b>No documents used.</b> This answer came from the program data.</div>
                )}
              </div>
            </>
          )}

          {!loading && !lastRun && (
            <div>
              <div className="panel-label">Run details</div>
              <p className="rail-hint">
                Ask a question and this panel shows how the answer was found: which
                tools ran, in what order, what they returned, and how long it took.
              </p>
            </div>
          )}
        </aside>
      </div>
    </main>
  );
}
