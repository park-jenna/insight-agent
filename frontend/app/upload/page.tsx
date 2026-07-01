"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { apiBase, apiKeyHeader } from "@/lib/api";

const API = apiBase();

type DatasetSummary = {
  dataset_id: string;
  name: string;
  original_filename: string;
  row_count: number;
  uploaded_at: string;
};

type DocumentSummary = {
  document_id: string;
  filename: string;
  total_chunks: number;
  uploaded_at: string;
};

type UploadStatus =
  | { state: "idle" }
  | { state: "uploading" }
  | { state: "success"; message: string }
  | { state: "error"; message: string };

/** Pull a readable message out of a failed response: FastAPI's
 * HTTPException bodies are {"detail": "..."}, auth failures get a
 * dedicated message since there's no body to parse for those. */
async function errorMessage(response: Response): Promise<string> {
  if (response.status === 401) {
    return "Authentication failed. Check that NEXT_PUBLIC_API_KEY is set and the dev server was restarted after setting it.";
  }
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // response wasn't JSON, fall through to the generic message
  }
  return `Upload failed (server responded ${response.status}).`;
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleString([], {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export default function UploadPage() {
  const [datasets, setDatasets] = useState<DatasetSummary[] | null>(null);
  const [documents, setDocuments] = useState<DocumentSummary[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);

  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvName, setCsvName] = useState("");
  const [csvStatus, setCsvStatus] = useState<UploadStatus>({ state: "idle" });

  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [pdfStatus, setPdfStatus] = useState<UploadStatus>({ state: "idle" });

  const refreshLists = useCallback(async () => {
    try {
      const [datasetsRes, documentsRes] = await Promise.all([
        fetch(`${API}/datasets`, { headers: { ...apiKeyHeader() } }),
        fetch(`${API}/documents`, { headers: { ...apiKeyHeader() } }),
      ]);
      if (!datasetsRes.ok) throw new Error(await errorMessage(datasetsRes));
      if (!documentsRes.ok) throw new Error(await errorMessage(documentsRes));
      const datasetsBody = await datasetsRes.json();
      const documentsBody = await documentsRes.json();
      setDatasets(datasetsBody.datasets);
      setDocuments(documentsBody.documents);
      setListError(null);
    } catch (err) {
      setListError(err instanceof Error ? err.message : "Could not load your uploads.");
    }
  }, []);

  useEffect(() => {
    // deferred so the effect body doesn't directly call a function that
    // sets state, which trips react-hooks/set-state-in-effect
    Promise.resolve().then(() => refreshLists());
  }, [refreshLists]);

  async function handleCsvUpload(event: React.FormEvent) {
    event.preventDefault();
    if (!csvFile) return;
    setCsvStatus({ state: "uploading" });

    const form = new FormData();
    form.append("file", csvFile);
    if (csvName.trim()) form.append("name", csvName.trim());

    try {
      const res = await fetch(`${API}/datasets/upload`, {
        method: "POST",
        headers: { ...apiKeyHeader() },
        body: form,
      });
      if (!res.ok) throw new Error(await errorMessage(res));
      const body = await res.json();
      setCsvStatus({
        state: "success",
        message: `"${body.name}" uploaded (${body.row_count} rows).`,
      });
      setCsvFile(null);
      setCsvName("");
      refreshLists();
    } catch (err) {
      setCsvStatus({
        state: "error",
        message: err instanceof Error ? err.message : "Upload failed.",
      });
    }
  }

  async function handlePdfUpload(event: React.FormEvent) {
    event.preventDefault();
    if (!pdfFile) return;
    setPdfStatus({ state: "uploading" });

    const form = new FormData();
    form.append("file", pdfFile);

    try {
      const res = await fetch(`${API}/documents/upload`, {
        method: "POST",
        headers: { ...apiKeyHeader() },
        body: form,
      });
      if (!res.ok) throw new Error(await errorMessage(res));
      const body = await res.json();
      setPdfStatus({
        state: "success",
        message: `"${body.filename}" uploaded (${body.total_chunks} chunks).`,
      });
      setPdfFile(null);
      refreshLists();
    } catch (err) {
      setPdfStatus({
        state: "error",
        message: err instanceof Error ? err.message : "Upload failed.",
      });
    }
  }

  return (
    <main className="app">
      <header className="topbar">
        <Link className="brand-link" href="/" aria-label="Go to InsightAgent home">
          <div className="logo">iA</div>
          <span className="wordmark">InsightAgent</span>
        </Link>
        <span className="divider" />
        <span className="assistant-label">Upload</span>
        <span className="spacer" />
        <Link className="navlink" href="/">Assistant</Link>
        <Link className="navlink" href="/dashboard">Dashboard</Link>
      </header>

      <div className="dash-scroll">
        <div className="dash-center">
          <div className="dash-head">
            <h1 className="dash-title">Add documents and datasets</h1>
            <p className="dash-lead">
              Upload a CSV for the data analysis tools or a PDF for document
              search. Everything here is scoped to your API key, only you can
              see or query what you add.
            </p>
          </div>

          {listError && (
            <div className="dash-error" style={{ marginBottom: 24 }}>
              Could not load your uploads ({listError}).
            </div>
          )}

          <section className="dash-section">
            <div className="section-label">Dataset (CSV)</div>
            <div className="panel-card">
              <form className="upload-form" onSubmit={handleCsvUpload}>
                <label className="upload-field">
                  <span className="upload-field-label">CSV file</span>
                  <input
                    type="file"
                    accept=".csv"
                    onChange={(e) => setCsvFile(e.target.files?.[0] ?? null)}
                    disabled={csvStatus.state === "uploading"}
                  />
                </label>
                <label className="upload-field">
                  <span className="upload-field-label">Name (optional)</span>
                  <input
                    type="text"
                    value={csvName}
                    placeholder="Defaults to the filename"
                    onChange={(e) => setCsvName(e.target.value)}
                    disabled={csvStatus.state === "uploading"}
                  />
                </label>
                <button
                  className="upload-button"
                  type="submit"
                  disabled={!csvFile || csvStatus.state === "uploading"}
                >
                  {csvStatus.state === "uploading" ? "Uploading…" : "Upload dataset"}
                </button>
              </form>
              {csvStatus.state === "success" && (
                <p className="upload-status upload-status-success">{csvStatus.message}</p>
              )}
              {csvStatus.state === "error" && (
                <p className="upload-status upload-status-error">{csvStatus.message}</p>
              )}
            </div>

            <div className="panel-card upload-list-card">
              <div className="upload-list-head">
                <span className="section-label" style={{ marginBottom: 0 }}>
                  Your datasets
                </span>
                <span className="upload-list-count">{datasets?.length ?? "…"}</span>
              </div>
              {datasets && datasets.length === 0 && (
                <p className="section-note" style={{ margin: 0 }}>
                  No datasets uploaded yet.
                </p>
              )}
              {datasets && datasets.length > 0 && (
                <ul className="upload-list">
                  {datasets.map((d) => (
                    <li key={d.dataset_id} className="upload-list-row">
                      <span className="upload-list-name">{d.name}</span>
                      <span className="upload-list-meta">{formatDate(d.uploaded_at)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>

          <section className="dash-section">
            <div className="section-label">Document (PDF)</div>
            <div className="panel-card">
              <form className="upload-form" onSubmit={handlePdfUpload}>
                <label className="upload-field">
                  <span className="upload-field-label">PDF file</span>
                  <input
                    type="file"
                    accept=".pdf"
                    onChange={(e) => setPdfFile(e.target.files?.[0] ?? null)}
                    disabled={pdfStatus.state === "uploading"}
                  />
                </label>
                <button
                  className="upload-button"
                  type="submit"
                  disabled={!pdfFile || pdfStatus.state === "uploading"}
                >
                  {pdfStatus.state === "uploading" ? "Uploading…" : "Upload document"}
                </button>
              </form>
              {pdfStatus.state === "success" && (
                <p className="upload-status upload-status-success">{pdfStatus.message}</p>
              )}
              {pdfStatus.state === "error" && (
                <p className="upload-status upload-status-error">{pdfStatus.message}</p>
              )}
            </div>

            <div className="panel-card upload-list-card">
              <div className="upload-list-head">
                <span className="section-label" style={{ marginBottom: 0 }}>
                  Your documents
                </span>
                <span className="upload-list-count">{documents?.length ?? "…"}</span>
              </div>
              {documents && documents.length === 0 && (
                <p className="section-note" style={{ margin: 0 }}>
                  No documents uploaded yet.
                </p>
              )}
              {documents && documents.length > 0 && (
                <ul className="upload-list">
                  {documents.map((d) => (
                    <li key={d.document_id} className="upload-list-row">
                      <span className="upload-list-name">{d.filename}</span>
                      <span className="upload-list-meta">{formatDate(d.uploaded_at)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>
        </div>
      </div>
    </main>
  );
}
