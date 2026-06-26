"use client";

import type {
  WorkspaceFilters,
  WorkspaceSource,
} from "@/app/workspace";
import styles from "@/app/workspace.module.css";

type Props = {
  sources: WorkspaceSource[];
  filters: WorkspaceFilters;
  open: boolean;
  onFiltersChange: (filters: WorkspaceFilters) => void;
  onClose: () => void;
};

function SourceGroup({
  label,
  sources,
}: {
  label: string;
  sources: WorkspaceSource[];
}) {
  return (
    <div className={styles.sourceSection}>
      <div className={styles.sourceSectionLabel}>
        {label}
        <span className={styles.sourceCountBadge}>{sources.length}</span>
      </div>
      <div className={styles.sourceList}>
        {sources.map((source) => (
          <div className={styles.sourceRow} key={source.id}>
            <span className={styles.sourceCheck} aria-hidden="true">
              ✓
            </span>
            <div>
              <div className={styles.sourceName}>{source.name}</div>
              <div className={styles.sourceMeta}>
                <span>
                  {source.count.toLocaleString()} {source.countLabel}
                </span>
                <span>·</span>
                <span>{source.status}</span>
              </div>
            </div>
            <span
              className={`${styles.typeBadge} ${
                source.format === "CSV" ? styles.csvBadge : ""
              }`}
            >
              {source.format}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function SourceSidebar({
  sources,
  filters,
  open,
  onFiltersChange,
  onClose,
}: Props) {
  const documents = sources.filter((source) => source.group === "documents");
  const datasets = sources.filter((source) => source.group === "datasets");

  return (
    <aside
      id="source-drawer"
      className={`${styles.sourceSidebar} ${
        open ? styles.sourceDrawerOpen : ""
      }`}
      aria-label="Workspace sources and preview filters"
    >
      <div className={styles.drawerHeader}>
        <strong>Sources & filters</strong>
        <button type="button" onClick={onClose} aria-label="Close sources">
          ×
        </button>
      </div>

      <div className={styles.sidebarScroll}>
        <section className={styles.panel}>
          <div className={styles.panelHead}>
            <h2 className={styles.panelTitle}>Sources</h2>
            <span className={styles.panelNote}>{sources.length} loaded</span>
          </div>
          <div className={styles.panelBody}>
            <SourceGroup label="Documents" sources={documents} />
            <SourceGroup label="Datasets" sources={datasets} />
          </div>
        </section>

        <section className={styles.panel}>
          <div className={styles.panelHead}>
            <h2 className={styles.panelTitle}>Filters</h2>
            <span className={styles.panelNote}>optional</span>
          </div>
          <div className={styles.panelBody}>
            <div className={styles.filterStack}>
              <label>
                <span className={styles.filterLabel}>Search scope</span>
                <select
                  value={filters.scope}
                  onChange={(event) =>
                    onFiltersChange({
                      ...filters,
                      scope: event.target.value as WorkspaceFilters["scope"],
                    })
                  }
                >
                  <option value="all">All workspace sources</option>
                  <option value="documents">Policy documents only</option>
                  <option value="data">Student data only</option>
                </select>
              </label>

              <label>
                <span className={styles.filterLabel}>Program</span>
                <select
                  value={filters.program}
                  onChange={(event) =>
                    onFiltersChange({
                      ...filters,
                      program: event.target.value as WorkspaceFilters["program"],
                    })
                  }
                >
                  <option value="any">Any program</option>
                  <option value="ELEVATE">ELEVATE</option>
                  <option value="IMPACT">IMPACT</option>
                </select>
              </label>

              <label>
                <span className={styles.filterLabel}>Student status</span>
                <select
                  value={filters.status}
                  onChange={(event) =>
                    onFiltersChange({
                      ...filters,
                      status: event.target.value as WorkspaceFilters["status"],
                    })
                  }
                >
                  <option value="any">Any status</option>
                  <option value="Active">Active</option>
                  <option value="Inactive">Inactive</option>
                  <option value="Completed">Completed</option>
                </select>
              </label>

              <label>
                <span className={styles.filterLabel}>Keyword</span>
                <input
                  type="text"
                  value={filters.keyword}
                  placeholder="complaint, consent, IEP…"
                  onChange={(event) =>
                    onFiltersChange({
                      ...filters,
                      keyword: event.target.value,
                    })
                  }
                />
              </label>
            </div>
            <p className={styles.previewNotice}>
              <b>UI preview</b>
              Results are not filtered yet.
            </p>
          </div>
        </section>
      </div>
    </aside>
  );
}
