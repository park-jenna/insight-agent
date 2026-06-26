"use client";

import { useEffect, useRef } from "react";
import {
  EXAMPLE_QUESTION_CATEGORIES,
  type AgentMessage,
  type AgentRun,
  type WorkspaceMetrics,
} from "@/app/workspace";
import styles from "@/app/workspace.module.css";
import { Composer } from "./Composer";
import {
  answerTitle,
  renderBoldText,
  resultTable,
} from "./presentation";

type Props = {
  metrics: WorkspaceMetrics;
  messages: AgentMessage[];
  run?: AgentRun;
  loading: boolean;
  onSend: (query: string) => void;
  onOpenSources: (trigger: HTMLButtonElement) => void;
  onOpenEvidence: (trigger: HTMLButtonElement) => void;
};

function EmptyState({ onAsk }: { onAsk: (query: string) => void }) {
  return (
    <div className={styles.categoryGrid}>
      {EXAMPLE_QUESTION_CATEGORIES.map((category) => (
        <section className={styles.categoryCard} key={category.id}>
          <h2 className={styles.categoryLabel}>
            <span
              className={`${styles.categoryDot} ${
                styles[`tone${category.tone[0].toUpperCase()}${category.tone.slice(1)}`]
              }`}
              aria-hidden="true"
            />
            {category.label}
          </h2>
          {category.questions.map((question) => (
            <button
              className={styles.categoryQuestion}
              type="button"
              key={question.query}
              onClick={() => onAsk(question.query)}
            >
              {question.label}
            </button>
          ))}
        </section>
      ))}
    </div>
  );
}

function StructuredResult({ run }: { run?: AgentRun }) {
  const table = resultTable(run);
  if (!table) return null;

  return (
    <div className={styles.tableScroll}>
      <table className={styles.dataTable}>
        <thead>
          <tr>
            {table.headings.map((heading) => (
              <th key={heading}>{heading}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, rowIndex) => (
            <tr key={`${row[0]}-${rowIndex}`}>
              {row.map((cell, cellIndex) => (
                <td key={`${cell}-${cellIndex}`}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AssistantMessage({ message }: { message: AgentMessage }) {
  const sourceCount = message.run?.sources.length ?? 0;
  const stepCount = message.run?.trace.length ?? 0;

  return (
    <div className={styles.assistantMessage}>
      <div className={styles.miniLogo}>iA</div>
      {message.content === "" && message.streaming ? (
        <div className={styles.thinking}>
          <span className={styles.pulseDot} />
          Working through documents and data…
        </div>
      ) : (
        <article className={styles.answerCard}>
          <header className={styles.answerToolbar}>
            <div className={styles.answerToolbarLeft}>
              <b>{answerTitle(message.run)}</b>
              <span>
                {sourceCount > 0
                  ? `Grounded in ${sourceCount} document source${
                      sourceCount === 1 ? "" : "s"
                    }`
                  : stepCount > 0
                    ? `Grounded in ${stepCount} data step${
                        stepCount === 1 ? "" : "s"
                      }`
                    : "Answered from conversation context"}
              </span>
            </div>
            <div className={styles.metaPills}>
              <span className={styles.tinyPill}>
                {message.streaming ? "Streaming" : `${stepCount} steps`}
              </span>
              {message.run?.latency ? (
                <span className={styles.tinyPill}>
                  {(message.run.latency / 1000).toFixed(2)}s
                </span>
              ) : null}
            </div>
          </header>
          <div className={styles.answerBody}>
            <p>
              {renderBoldText(message.content)}
              {message.streaming ? (
                <span className={styles.cursor} aria-hidden="true" />
              ) : null}
            </p>
            {!message.streaming ? <StructuredResult run={message.run} /> : null}
          </div>
        </article>
      )}
    </div>
  );
}

export function ChatWorkspace({
  metrics,
  messages,
  run,
  loading,
  onSend,
  onOpenSources,
  onOpenEvidence,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, loading]);

  return (
    <section className={styles.chatColumn}>
      <header className={styles.chatHeader}>
        <div className={styles.chatHeaderTopline}>
          <div>
            <p className={styles.pageKicker}>ChiEAC Staff Workspace</p>
            <h1>Ask across policy and enrollment data.</h1>
          </div>
          <div className={styles.drawerActions}>
            <button
              className={styles.sourceDrawerButton}
              type="button"
              aria-controls="source-drawer"
              onClick={(event) => onOpenSources(event.currentTarget)}
            >
              Sources
            </button>
            <button
              className={styles.evidenceDrawerButton}
              type="button"
              aria-controls="evidence-drawer"
              onClick={(event) => onOpenEvidence(event.currentTarget)}
            >
              Evidence
              {run?.trace.length ? (
                <span>{run.trace.length}</span>
              ) : null}
            </button>
          </div>
        </div>
        <div className={styles.metricsRow}>
          <div className={styles.metricPill}>
            <strong>{metrics.policyDocuments}</strong>
            <span>policy PDFs</span>
          </div>
          <div className={styles.metricPill}>
            <strong>{metrics.indexedPassages.toLocaleString()}</strong>
            <span>passages</span>
          </div>
          <div className={styles.metricPill}>
            <strong>{metrics.enrollmentRecords.toLocaleString()}</strong>
            <span>enrollment records</span>
          </div>
        </div>
      </header>

      <div className={styles.chatScroll} ref={scrollRef}>
        {messages.length === 0 ? <EmptyState onAsk={onSend} /> : null}
        {messages.map((message) =>
          message.role === "user" ? (
            <div className={styles.userMessage} key={message.id}>
              <div className={styles.userBubble}>{message.content}</div>
            </div>
          ) : (
            <AssistantMessage message={message} key={message.id} />
          ),
        )}
      </div>

      <Composer loading={loading} onSend={onSend} />
    </section>
  );
}
