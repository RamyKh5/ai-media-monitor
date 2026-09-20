// src/services/api.js — Bridge between Frontend and Backend
// ============================================================
// All HTTP calls to the FastAPI backend live here.
// Keeping them in one file makes the code easier to debug and test.

// Base URL of the FastAPI backend (no trailing slash!)
const API_BASE_URL = "http://localhost:8000";


// Calls GET / to verify the backend is online before doing anything.
export async function checkBackendHealth() {
  const res = await fetch(`${API_BASE_URL}/`);

  if (!res.ok) {
    throw new Error("Backend is unhealthy");
  }

  return res.json();
}

// CREATE JOB
// ============================================================
// Sends a new job to the backend.
// Accepts EITHER:
//   - A FormData object (when a file is uploaded)
//   - A plain JS object (when no file, e.g., web URL)
//
// Why the condition?
// - For FormData: the browser MUST set the Content-Type header itself
//   (it includes a unique boundary string). If we set it manually, the
//   request breaks.
// - For JSON: we set Content-Type: application/json and stringify the body.
export async function createJob(payload) {
  const isFormData = payload instanceof FormData;

  const headers = isFormData
    ? {}                                     // Let the browser set multipart boundary
    : { "Content-Type": "application/json" }; // Standard JSON request

  const body = isFormData
    ? payload                                // Already a FormData object
    : JSON.stringify(payload);               // Convert JS object → JSON string

  const res = await fetch(`${API_BASE_URL}/api/jobs`, {
    method: "POST",
    headers,
    body,
  });

  // --- Error handling ---
  // If the backend returns a 4xx/5xx, read the error message and throw it.
  // FastAPI returns errors in the shape: { "detail": "..." }
  if (!res.ok) {
    let errorMessage = "Failed to create job";
    try {
      const errorBody = await res.json();
      if (errorBody?.detail) {
        errorMessage = typeof errorBody.detail === "string"
          ? errorBody.detail
          : JSON.stringify(errorBody.detail);
      }
    } catch {
      // Ignore JSON parse errors — use default message
    }
    throw new Error(errorMessage);
  }

  return res.json();
}

// GET JOB STATUS
// ============================================================
// Polls the backend for the current status of a job.
// Used by the parent component every 2-5 seconds until status === "completed".
export async function getJobStatus(jobId) {
  const res = await fetch(`${API_BASE_URL}/api/jobs/${jobId}`);

  if (!res.ok) {
    throw new Error("Failed to fetch job status");
  }

  return res.json();
}

// GET JOB RESULT
// ============================================================
// Downloads the final synthesis file (Markdown) for a completed job.
// The backend streams the file via FileResponse.
export async function getJobResult(jobId) {
  const res = await fetch(`${API_BASE_URL}/api/jobs/${jobId}/result`);

  if (!res.ok) {
    let errorMessage = "Failed to fetch job result";
    try {
      const errorBody = await res.json();
      if (errorBody?.detail) {
        errorMessage = typeof errorBody.detail === "string"
          ? errorBody.detail
          : JSON.stringify(errorBody.detail);
      }
    } catch {
      // Ignore JSON parse errors
    }
    throw new Error(errorMessage);
  }

  // The backend returns Markdown content — read it as text, not JSON
  return res.text();
}