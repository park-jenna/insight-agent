"use client";

import { useState } from "react";
import { SUGGESTED_QUESTIONS } from "@/app/workspace";
import styles from "@/app/workspace.module.css";

type Props = {
  loading: boolean;
  onSend: (query: string) => void;
};

export function Composer({ loading, onSend }: Props) {
  const [input, setInput] = useState("");

  function submit(query = input) {
    const trimmed = query.trim();
    if (!trimmed || loading) return;
    setInput("");
    onSend(trimmed);
  }

  return (
    <div className={styles.composerWrap}>
      <div className={styles.composerInner}>
        <textarea
          className={styles.questionBox}
          rows={3}
          value={input}
          disabled={loading}
          placeholder="Ask about a policy requirement, student count, program trend, or a combined policy + data question…"
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (
              event.key === "Enter" &&
              (event.metaKey || event.ctrlKey)
            ) {
              event.preventDefault();
              submit();
            }
          }}
        />
        <div className={styles.askActions}>
          <div className={styles.scopePill}>
            <span>Scope</span>
            <b>All</b>
          </div>
          <button
            className={styles.askButton}
            type="button"
            disabled={loading || !input.trim()}
            onClick={() => submit()}
          >
            {loading ? "Working…" : "Ask workspace"}
          </button>
        </div>
      </div>

      <div className={styles.suggestionRow}>
        {SUGGESTED_QUESTIONS.map((suggestion) => (
          <button
            className={styles.suggestion}
            type="button"
            disabled={loading}
            key={suggestion.label}
            onClick={() => submit(suggestion.query)}
          >
            {suggestion.label}
          </button>
        ))}
      </div>
      <p className={styles.composerHint}>Press ⌘/Ctrl + Enter to send</p>
    </div>
  );
}
