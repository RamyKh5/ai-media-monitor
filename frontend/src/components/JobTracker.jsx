// ============================================================
// JobTracker.jsx — Tracks MULTIPLE active jobs with ONE interval
// ============================================================
// Industry-standard pattern:
// - One global interval (not one per job)
// - A Set tracks completed/failed jobs (avoids re-polling)
// - useRef holds the "live" set of active jobs (avoids stale closure)
// - Markdown results are rendered as formatted documents
// - Each result can be downloaded as a .md file
// ============================================================

import { useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import { getJobStatus, getJobResult } from "../services/api";

// Polling interval (ms). 2s balances responsiveness and server load.
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
  const isPollingRef    = useRef(false);      // Guard: only ONE interval ever

  // ------------------------------------------------------------
  // MARKDOWN EXPORT HANDLER
  // ------------------------------------------------------------
  // Packages the raw Markdown string into a virtual file and triggers
  // a browser download — no library needed.
  //
  // How it works:
  //   1. Wrap the string in a Blob (a virtual file in memory)
  //   2. Create a temporary object URL pointing to the Blob
  //   3. Create an invisible <a> tag with `download` attribute
  //   4. Programmatically click it → browser downloads the file
  //   5. Clean up: remove the link and revoke the object URL
  //
  // Why this approach?
  // - Native browser API, no extra dependency
  // - Works with any text content (Markdown, JSON, plain text)
  // - Doesn't require rendering to PDF or canvas
  function handleDownloadMarkdown(jobId, content) {
    // 1. Wrap the string in a Blob (type: text/markdown)
    const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });

    // 2. Create a temporary URL for the Blob
    const url = URL.createObjectURL(blob);

    // 3. Create an invisible anchor element
    const link = document.createElement("a");
    link.href = url;
    link.download = `veille-synthese-${jobId.slice(0, 8)}.md`;

    // 4. Trigger the download
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    // 5. Free the memory used by the Blob URL
    URL.revokeObjectURL(url);
  }

  // ------------------------------------------------------------
  // MAIN POLLING LOOP (single interval for ALL jobs)
  // ------------------------------------------------------------
  useEffect(() => {
    if (!jobIds || jobIds.length === 0) return;

    // --- Start the interval ONLY ONCE ---
    if (isPollingRef.current) return;
    isPollingRef.current = true;

    const interval = setInterval(async () => {
      // --- Find jobs that still need polling ---
      const activeIds = jobIds.filter(
        (id) => !finishedJobsRef.current.has(id)
      );

      if (activeIds.length === 0) return;

      // --- Poll all active jobs in parallel ---
      const results = await Promise.allSettled(
        activeIds.map(async (jobId) => {
          const status = await getJobStatus(jobId);
          return { jobId, status };
        })
      );

      // --- Update state with new statuses ---
      const updates = {};

      for (const r of results) {
        if (r.status !== "fulfilled") {
          console.error("Poll failed:", r.reason);
          continue;
        }

        const { jobId, status } = r.value;
        updates[jobId] = { ...updates[jobId], status };

        // --- Job completed → fetch result, then mark finished ---
        if (status.status === "completed") {
          finishedJobsRef.current.add(jobId);

          try {
            const fileContent = await getJobResult(jobId);
            updates[jobId] = { ...updates[jobId], result: fileContent };
          } catch (err) {
            console.error(`Failed to fetch result for ${jobId}:`, err);
          }
        }
        // --- Job failed → mark finished (no result to fetch) ---
        else if (status.status === "failed") {
          finishedJobsRef.current.add(jobId);
        }
      }

      // --- Merge updates into state ---
      setJobs((prev) => {
        const merged = { ...prev };
        for (const [jobId, data] of Object.entries(updates)) {
          merged[jobId] = { ...merged[jobId], ...data };
        }
        return merged;
      });
    }, POLL_INTERVAL_MS);

    // --- Cleanup on unmount ---
    return () => {
      clearInterval(interval);
      isPollingRef.current = false;
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

            {/* ---------- Result Panel ---------- */}
            {result && (
              <div className="mt-3 space-y-2">
                {/* ---------- Header with Markdown Download Button ---------- */}
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

                {/*
                  Screen Preview — keeps dark-mode prose formatting.
                  `prose prose-invert` = beautiful typography on dark bg.
                */}
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