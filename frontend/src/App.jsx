// src/App.jsx
import { useEffect, useState } from 'react';
import { checkBackendHealth } from './services/api';

function App() {
  const [backendStatus, setBackendStatus] = useState("Testing connection...");

  useEffect(() => {
    checkBackendHealth()
      .then((data) => {
        setBackendStatus(`🟢 Connected! System: ${data.system}`);
      })
      .catch((err) => {
        setBackendStatus(`❌ Connection failed: ${err.message}`);
      });
  }, []);

  return (
    <div className="min-h-screen bg-slate-900 text-white flex flex-col items-center justify-center">
      <h1 className="text-3xl font-bold mb-4">Cellule de Veille - Dashboard</h1>
      <div className="p-4 bg-slate-800 rounded-lg border border-slate-700">
        <p className="text-lg">{backendStatus}</p>
      </div>
    </div>
  );
}

export default App;