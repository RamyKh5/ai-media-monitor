// ============================================================
// App.jsx — Root Application Layout
// ============================================================
import { useState } from "react";
import JobForm from "./components/JobForm";
import JobTracker from "./components/JobTracker";

export default function App() {
  const [activeJobIds, setActiveJobIds] = useState([]);

  function handleJobCreated(newJobId) {
    setActiveJobIds((prev) => [...prev, newJobId]);
  }

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 p-8">
      <header className="max-w-3xl mx-auto mb-8 text-center">
        <h1 className="text-2xl font-bold">
          Cellule de Veille — Tableau de Bord
        </h1>
      </header>

      <main className="space-y-6">
        <JobForm onJobCreated={handleJobCreated} />
        <JobTracker jobIds={activeJobIds} />
      </main>
    </div>
  );
}