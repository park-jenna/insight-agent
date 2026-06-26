"use client";

import { useEffect, useRef, useState } from "react";
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
        <div className={styles.brand}>
          <div className={styles.logo}>iA</div>
          <div className={styles.brandText}>
            <strong>InsightAgent</strong>
            <span>ChiEAC staff workspace</span>
          </div>
        </div>
        <div className={styles.workspaceStatus}>
          <span className={styles.statusItem}>
            <span className={styles.statusDot} />
            Synced today
          </span>
          <span className={styles.statusItem}>
            {WORKSPACE_METRICS.indexedPassages.toLocaleString()} indexed passages
          </span>
          <span className={styles.statusItem}>
            {WORKSPACE_METRICS.enrollmentRecords.toLocaleString()} enrollment records
          </span>
          <span className={styles.statusItem}>Policy + data mode</span>
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
