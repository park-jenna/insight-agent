"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  DEFAULT_FILTERS,
  WORKSPACE_METRICS,
  WORKSPACE_SOURCES,
  type WorkspaceFilters,
} from "@/app/workspace";
import { useAgentStream } from "@/hooks/useAgentStream";
import styles from "@/app/workspace.module.css";
import { ChatWorkspace } from "./ChatWorkspace";
import { EvidenceRail } from "./EvidenceRail";
import { SourceSidebar } from "./SourceSidebar";

type Drawer = "sources" | "evidence" | null;

export function WorkspaceApp() {
  const [filters, setFilters] = useState<WorkspaceFilters>(DEFAULT_FILTERS);
  const [drawer, setDrawer] = useState<Drawer>(null);
  const returnFocusRef = useRef<HTMLButtonElement | null>(null);
  const { messages, run, loading, send } = useAgentStream();

  function openDrawer(next: Exclude<Drawer, null>, trigger: HTMLButtonElement) {
    returnFocusRef.current = trigger;
    setDrawer(next);
  }

  function closeDrawer() {
    setDrawer(null);
    window.requestAnimationFrame(() => returnFocusRef.current?.focus());
  }

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && drawer) closeDrawer();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [drawer]);

  return (
    <main className={styles.app}>
      <header className={styles.topbar}>
        <Link className={styles.brand} href="/" aria-label="Go to InsightAgent home">
          <div className={styles.logo}>iA</div>
          <span className={styles.wordmark}>InsightAgent</span>
        </Link>
        <div className={styles.brandMeta}>
          <span className={styles.divider} />
          <span className={styles.workspaceLabel}>Workspace</span>
        </div>
        <span className={styles.spacer} />
        <div className={styles.workspaceStatus}>
          <span className={styles.statusItem}>
            <span className={styles.statusDot} />
            Synced today
          </span>
        </div>
      </header>

      <div className={styles.workspace}>
        <SourceSidebar
          sources={WORKSPACE_SOURCES}
          filters={filters}
          open={drawer === "sources"}
          onFiltersChange={setFilters}
          onClose={closeDrawer}
        />
        <ChatWorkspace
          metrics={WORKSPACE_METRICS}
          messages={messages}
          run={run}
          loading={loading}
          onSend={send}
          onOpenSources={(trigger) => openDrawer("sources", trigger)}
          onOpenEvidence={(trigger) => openDrawer("evidence", trigger)}
        />
        <EvidenceRail
          run={run}
          loading={loading}
          open={drawer === "evidence"}
          onClose={closeDrawer}
        />
      </div>

      <button
        className={`${styles.drawerOverlay} ${
          drawer ? styles.drawerOverlayVisible : ""
        }`}
        type="button"
        aria-label="Close open panel"
        tabIndex={drawer ? 0 : -1}
        onClick={closeDrawer}
      />
    </main>
  );
}
