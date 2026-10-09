// ============================================================
// JobTracker.jsx — Tracks MULTIPLE active jobs with a SINGLE
// recursive setTimeout poller (no overlap, no stale closures)
// ============================================================
// Industry-standard patterns applied:
// - Recursive setTimeout instead of setInterval (no request stacking)
// - A Set tracks completed/failed jobs (avoids re-polling)
// - useRef holds the "live" poll state (avoids stale closures)
// - Functional setState updater (no stale `jobs` reads)
// - Ghost-update guard: bails out if unmounted during await
// - Error propagation: failed result fetches surface in the UI
// - Pragmatic memory hygiene: Set grows safely during session
// - Markdown results rendered as formatted documents
// - Each result downloadable as a .md file
// - Alerts (threats/misinfo) rendered as a red card
// ============================================================

import { useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import { getJobStatus, getJobResult } from "../services/api";

// Polling interval (ms). Wait this long AFTER each poll completes.
const POLL_INTERVAL_MS = 2000;

export default function JobTracker({ jobIds }) {
  // ------------------------------------------------------------
  // STATE — Map of jobId → { status, result }
  // ------------------------------------------------------------
  const [jobs, setJobs] = useState({});

  // ------------------------------------------------------------
  // REFS — Live values that DON'T trigger re-renders
  // ------------------------------------------------------------
  const finishedJobsRef = useRef(new Set()); // Jobs we should stop polling
  const isPollingRef    = useRef(false);      // Guard: only ONE poller

  // ------------------------------------------------------------
  // MARKDOWN EXPORT HANDLER
  // ------------------------------------------------------------
  function handleDownloadMarkdown(jobId, content) {
    const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);

    const link = document.createElement("a");
    link.href = url;
    link.download = `veille-synthese-${jobId.slice(0, 8)}.md`;

    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    URL.revokeObjectURL(url);
  }

  // ------------------------------------------------------------
  // POLLING LOOP — Recursive setTimeout + Ghost-update guard
  // ------------------------------------------------------------
  useEffect(() => {
    if (!jobIds || jobIds.length === 0) return;

    // Guard: prevent multiple polling loops
    if (isPollingRef.current) return;
    isPollingRef.current = true;

    let timeoutId; // Store the active timeout so we can cancel on unmount

    const poll = async () => {
      // --- Which jobs still need polling? ---
      const activeIds = jobIds.filter(
        (id) => !finishedJobsRef.current.has(id)
      );

      // --- Nothing left to poll → stop the loop cleanly ---
      if (activeIds.length === 0) {
        isPollingRef.current = false;
        return;
      }

      // --- Poll all active jobs in parallel ---
      const results = await Promise.allSettled(
        activeIds.map(async (jobId) => ({
          jobId,
          status: await getJobStatus(jobId),
        }))
      );

      // ============================================================
      // GHOST-UPDATE GUARD
      // ============================================================
      // If the component unmounted during the `await`, we bail out 
      // BEFORE touching state or scheduling more work.
      if (!isPollingRef.current) return;

      // --- Prepare the state updates ---
      const updates = {};

      for (const r of results) {
        if (r.status !== "fulfilled") {
          console.error("Poll failed:", r.reason);
          continue;
        }

        const { jobId, status } = r.value;
        updates[jobId] = { status };

        // --- Job completed → fetch the Markdown result ---
       if (status.status === "completed") {
  finishedJobsRef.current.add(jobId);

  // If the pipeline completed WITHOUT producing a synthesis file
  // (e.g., no keyword matches), the backend sets result_path to
  // "Path not found". Don't try to fetch — just show a friendly message.
  const hasRealResult =
    status.result_path &&
    status.result_path !== "Path not found";

  if (!hasRealResult) {
    updates[jobId].status = {
      ...status,
      error: "Aucun article correspondant aux mots-clés n'a été trouvé.",
    };
  } else {
    try {
      const fileContent = await getJobResult(jobId);
      updates[jobId].result = fileContent;
    } catch (err) {
      console.error(`Result fetch failed for ${jobId}:`, err);
      updates[jobId].status = {
        ...status,
        error: "Échec du téléchargement du résultat. Veuillez réessayer.",
      };
    }
  }
}

        // --- Job ALERTED → no result file; alert_data is in status ---
        else if (status.status === "alert_triggered") {
          finishedJobsRef.current.add(jobId);
        }

        // --- Job failed → stop polling ---
        else if (status.status === "failed") {
          finishedJobsRef.current.add(jobId);
        }
      }

      // --- Merge into state via functional updater ---
      setJobs((prev) => {
        const merged = { ...prev };
        for (const [jobId, data] of Object.entries(updates)) {
          merged[jobId] = { ...merged[jobId], ...data };
        }
        return merged;
      });

      // --- Schedule the NEXT poll ONLY after this one fully finished ---
      timeoutId = setTimeout(poll, POLL_INTERVAL_MS);
    };

    // Kick off the first poll immediately
    poll();

    // --- Cleanup on unmount or jobIds change ---
    return () => {
      clearTimeout(timeoutId);
      isPollingRef.current = false;
      // Note: We intentionally DO NOT clear finishedJobsRef here. 
      // A Set of strings takes negligible memory. Letting it persist prevents 
      // re-triggering network cascades if the parent component re-renders.
    };
  }, [jobIds]);

  // ------------------------------------------------------------
  // RENDER
  // ------------------------------------------------------------
  if (!jobIds || jobIds.length === 0) return null;

  return (
    <div className="max-w-3xl mx-auto mt-6 space-y-4">
      {jobIds.map((jobId) => {
        const entry  = jobs[jobId];
        const status = entry?.status;
        const result = entry?.result;

        return (
          <div
            key={jobId}
            className="bg-slate-800 p-4 rounded-lg border border-slate-700 text-sm space-y-2"
          >
            <p className="font-semibold text-blue-400">
              Suivi de la Tâche : {jobId}
            </p>

            {/* ---------- Status Panel ---------- */}
            {status ? (
              <>
                <p>
                  Statut :{" "}
                  <span className="font-mono uppercase">{status.status}</span>
                </p>
                <p>Progression : {status.progress}%</p>
                <p>Étape actuelle : {status.current_step}</p>

                {status.error && (
                  <p className="text-rose-400">Erreur : {status.error}</p>
                )}
              </>
            ) : (
              <p className="text-slate-400">
                En attente des premières données...
              </p>
            )}

            {/* ============================================================
                ALERT PANEL — Shown when a threat/misinfo is detected.
                ============================================================ */}
            {status?.status === "alert_triggered" && status.alert_data && (
              <div className="mt-3 p-4 bg-red-950/50 border border-red-500 rounded-lg space-y-3">
                <div className="flex items-center gap-2 text-red-400 font-bold uppercase text-sm">
                  <span className="animate-pulse">🚨</span>
                  ALERTE CRITIQUE DÉTECTÉE
                  <span className="ml-1 text-red-300 font-normal normal-case">
                    ({status.alert_data.count} article
                    {status.alert_data.count > 1 ? "s" : ""})
                  </span>
                </div>

                {status.alert_data.articles.map((a, i) => (
                  <div
                    key={i}
                    className="text-xs text-red-200 border-t border-red-800 pt-3 space-y-1"
                  >
                    <p><strong>Source :</strong> {a.source}</p>
                    <p>
                      <strong>Classification :</strong>{" "}
                      <span className="font-mono">{a.classification}</span>
                    </p>
                    <p>
                      <strong>Confiance :</strong>{" "}
                      {(a.confidence * 100).toFixed(0)}%
                    </p>

                    {a.reasoning && (
                      <p className="italic text-red-300">« {a.reasoning} »</p>
                    )}

                    <p className="mt-2 bg-red-900/50 p-2 rounded border border-red-800">
                      <strong>Extrait suspect :</strong>
                      <br />
                      <span dir="auto">"{a.snippet}…"</span>
                    </p>
                  </div>
                ))}

                <button
                  className="mt-2 w-full py-1.5 bg-red-600 hover:bg-red-500 text-white text-xs font-bold rounded transition-colors"
                >
                  Signaler au Superviseur
                </button>
              </div>
            )}

            {/* ============================================================
                RESULT PANEL — Shown only when the job completed successfully.
                ============================================================ */}
            {result && (
              <div className="mt-3 space-y-2">
                <div className="flex justify-between items-center">
                  <h3 className="text-xs font-bold text-emerald-400">
                    Résultat de l'analyse :
                  </h3>
                  <button
                    onClick={() => handleDownloadMarkdown(jobId, result)}
                    className="px-3 py-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded transition-colors"
                  >
                    Télécharger (.md)
                  </button>
                </div>

                <div className="p-4 bg-slate-900 rounded text-slate-300 prose prose-invert max-w-none text-xs max-h-96 overflow-y-auto border border-slate-700">
                  <ReactMarkdown>{result}</ReactMarkdown>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}