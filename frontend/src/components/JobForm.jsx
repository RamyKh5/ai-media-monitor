// ============================================================
// JobForm.jsx — Form to submit a new pipeline job
// ============================================================
// This component handles:
// 1. User input (source type, keywords, file/URL)
// 2. Pre-flight validation (no empty submissions)
// 3. Real file upload via <input type="file"> + FormData
// 4. Loading / success / error feedback
// 5. Calling the backend via createJob()

import { useState } from "react";
import { createJob } from "../services/api";

// CONSTANTS
// ------------------------------------------------------------
// Available source types (must match backend 'input_types' values)
const INPUT_TYPES = [
  { value: "scanned_journal", label: "Journal scanné (OCR)" },
  { value: "web",             label: "Article web" },
  { value: "social",          label: "Réseaux sociaux" },
  { value: "tv_broadcast",    label: "Diffusion TV" },
];

// Maximum file size allowed (20 MB) — prevents backend overload
const MAX_FILE_SIZE_MB = 20;


export default function JobForm({ onJobCreated }) {
  // STATE
  // ------------------------------------------------------------
  const [inputType, setInputType]         = useState("scanned_journal");
  const [keywordsInput, setKeywordsInput] = useState("");
  const [filePath, setFilePath]           = useState("");   // For URL / text input
  const [file, setFile]                   = useState(null); // Actual File object
  const [status, setStatus]               = useState("idle");
  const [errorMessage, setErrorMessage]   = useState("");

  // HANDLE FILE SELECTION
  // ------------------------------------------------------------
  function handleFileChange(event) {
    const selected = event.target.files?.[0];
    if (!selected) return;

    if (selected.size > MAX_FILE_SIZE_MB * 1024 * 1024) {
      setStatus("error");
      setErrorMessage(`Fichier trop volumineux (max ${MAX_FILE_SIZE_MB} Mo).`);
      setFile(null);
      return;
    }

    setFile(selected);
    setErrorMessage("");
  }

  // SUBMIT HANDLER
  // ------------------------------------------------------------
  async function handleSubmit(event) {
    event.preventDefault();

    // --- Pre-flight validation ---
    if (!keywordsInput.trim()) {
      setStatus("error");
      setErrorMessage("Veuillez entrer au moins un mot-clé.");
      return;
    }

    if (inputType === "scanned_journal" && !file) {
      setStatus("error");
      setErrorMessage("Veuillez sélectionner un fichier à analyser.");
      return;
    }

    setStatus("loading");
    setErrorMessage("");

    // --- Build keyword array ---
    const keywords = keywordsInput
      .split(",")
      .map((k) => k.trim())
      .filter(Boolean);

    // BUILD PAYLOAD
    // ------------------------------------------------------------
    // If a file is present, we use FormData (multipart upload).
    // Otherwise, we send plain JSON.
    let payload;

    if (file) {
      payload = new FormData();

      // FIX: Backend expects a JSON array string for input_types.
      // We wrap inputType in an array and stringify it.
      payload.append("input_types", JSON.stringify([inputType]));

      // FIX: Backend also expects a JSON array string for keywords.
      payload.append("keywords", JSON.stringify(keywords));

      // Actual binary file upload
      payload.append("file", file);

    } else {
      // JSON mode — backend receives a regular JSON body
      payload = {
        input_types: [inputType],
        keywords: keywords,
        file_path: filePath.trim() || null,
      };
    }

    // --- Call the backend ---
    try {
      const response = await createJob(payload);

      setStatus("success");
      setKeywordsInput("");
      setFilePath("");
      setFile(null);

      if (onJobCreated) {
        onJobCreated(response.job_id);
      }
    } catch (err) {
      setStatus("error");
      setErrorMessage(err.message || "Erreur de connexion au serveur.");
    }
  }

  // RENDER
  // ------------------------------------------------------------
  return (
    <form
      onSubmit={handleSubmit}
      className="bg-slate-800 p-6 rounded-lg border border-slate-700 shadow-lg space-y-5 max-w-xl mx-auto"
    >
      <h2 className="text-xl font-bold text-slate-100">
        Nouvelle Analyse
      </h2>

      {/* ---------- Source Type Dropdown ---------- */}
      <div>
        <label className="block text-sm font-medium text-slate-300 mb-1">
          Source de données
        </label>
        <select
          value={inputType}
          onChange={(e) => setInputType(e.target.value)}
          className="w-full bg-slate-900 border border-slate-700 text-slate-100 rounded px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:outline-none"
        >
          {INPUT_TYPES.map((type) => (
            <option key={type.value} value={type.value}>
              {type.label}
            </option>
          ))}
        </select>
      </div>

      {/* ---------- Keywords Input ---------- */}
      <div>
        <label className="block text-sm font-medium text-slate-300 mb-1">
          Mots-clés (séparés par des virgules)
        </label>
        <input
          type="text"
          value={keywordsInput}
          onChange={(e) => setKeywordsInput(e.target.value)}
          placeholder="pénurie, carburant, grève"
          className="w-full bg-slate-900 border border-slate-700 text-slate-100 rounded px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:outline-none"
        />
      </div>

      {/* ---------- File Upload (for scanned_journal) ---------- */}
      {inputType === "scanned_journal" && (
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-1">
            Fichier à analyser (PDF, PNG, JPG)
          </label>
          <input
            type="file"
            accept=".pdf,.png,.jpg,.jpeg"
            onChange={handleFileChange}
            className="w-full bg-slate-900 border border-slate-700 text-slate-100 rounded px-3 py-2 file:mr-3 file:py-1 file:px-3 file:rounded file:border-0 file:bg-blue-600 file:text-white hover:file:bg-blue-500"
          />
          {file && (
            <p className="text-xs text-slate-400 mt-1">
              Sélectionné : {file.name} ({(file.size / 1024 / 1024).toFixed(2)} Mo)
            </p>
          )}
        </div>
      )}

      {/* ---------- URL Input (for web) ---------- */}
      {inputType === "web" && (
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-1">
            URL de l'article
          </label>
          <input
            type="url"
            value={filePath}
            onChange={(e) => setFilePath(e.target.value)}
            placeholder="https://..."
            className="w-full bg-slate-900 border border-slate-700 text-slate-100 rounded px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:outline-none"
          />
        </div>
      )}

      {/* ---------- Submit Button ---------- */}
      <button
        type="submit"
        disabled={status === "loading"}
        className="w-full bg-blue-600 text-white font-medium py-2 rounded hover:bg-blue-500 disabled:opacity-50 transition-colors"
      >
        {status === "loading" ? "Analyse en cours..." : "Lancer l'analyse"}
      </button>

      {/* ---------- Feedback Messages ---------- */}
      {status === "success" && (
        <p className="text-emerald-400 text-sm mt-2">
          ✅ Tâche soumise avec succès.
        </p>
      )}
      {status === "error" && (
        <p className="text-rose-400 text-sm mt-2">
          ❌ {errorMessage}
        </p>
      )}
    </form>
  );
}