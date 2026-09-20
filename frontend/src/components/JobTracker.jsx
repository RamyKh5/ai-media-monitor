// ============================================================
// JobTracker.jsx — Tracks MULTIPLE active jobs with ONE interval
// ============================================================
// Industry-standard pattern:
// - One global interval (not one per job)
// - A Set tracks completed/failed jobs (avoids re-polling)
// - useRef holds the "live" set of active jobs (avoids stale closure)
// - Markdown results are rendered as formatted documents
// - Each result can be downloaded as a PDF
// ============================================================

import { useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import html2pdf from "html2pdf.js";
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
  // PDF EXPORT HANDLER
  // ------------------------------------------------------------
  // Converts the rendered Markdown result into a downloadable PDF.
  // How it works:
  //   1. Find the specific job's result DOM node (via its id)
  //   2. Snapshot it with html2canvas (renders HTML → image)
  //   3. Wrap the image into a jsPDF A4 page and download
  //
  // Why target by ID?
  // - Each job has its own result panel, so we need the right one.
  // - Using `result-content-${jobId}` guarantees unique selection.
  function handleDownloadPDF(jobId) {
    // 1. Target the DOM element we want to convert
    const element = document.getElementById(`result-content-${jobId}`);
    if (!element) {
      console.error(`Result element for job ${jobId} not found.`);
      return;
    }

    // 2. Configure the PDF settings
    const opt = {
      margin:       10,                                     // 10mm margin around content
      filename:     `veille-synthese-${jobId.slice(0, 8)}.pdf`, // Short filename from job ID
      image:        { type: "jpeg", quality: 0.98 },        // High-quality JPEG inside PDF
      html2canvas:  { scale: 2 },                           // 2x resolution for crisp text
      jsPDF:        { unit: "mm", format: "a4", orientation: "portrait" }
    };

    // 3. Generate and trigger download
    html2pdf().set(opt).from(element).save();
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
                {/* ---------- Header with Download Button ---------- */}
                <div className="flex justify-between items-center">
                  <h3 className="text-xs font-bold text-emerald-400">
                    Résultat de l'analyse :
                  </h3>
                  <button
                    onClick={() => handleDownloadPDF(jobId)}
                    className="px-3 py-1 bg-red-600 hover:bg-red-500 text-white text-xs font-medium rounded transition-colors"
                  >
                    Télécharger PDF
                  </button>
                </div>

                {/*
                  Why `id={`result-content-${jobId}`}`?
                  - html2pdf needs to locate THIS specific job's result.
                  - Using a unique ID per job ensures we export the right one
                    when multiple jobs are displayed.

                  Why change to `bg-white text-black`?
                  - PDF exports look best on white with black text.
                  - The dark UI is for the screen, but the PDF should look
                    like a real document.

                  Why keep `prose` but NOT `prose-invert`?
                  - `prose` styles headings/lists/paragraphs.
                  - Without `prose-invert`, colors stay dark-on-light,
                    which is correct for a printed document.
                */}
                <div
                  id={`result-content-${jobId}`}
                  className="p-8 bg-white text-black rounded prose max-w-none text-sm max-h-96 overflow-y-auto"
                >
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