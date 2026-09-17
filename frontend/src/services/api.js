// src/services/api.js
const API_BASE_URL = "http://localhost:8000";

export async function checkBackendHealth() {
  const res = await fetch(`${API_BASE_URL}/`);
  if (!res.ok) throw new Error("Backend is unhealthy");
  return res.json();
}