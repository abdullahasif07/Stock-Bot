// Empty = same origin (FastAPI serves the SPA, or Vite proxies /api in dev).
// Set VITE_API_BASE_URL only when the frontend is hosted separately (e.g. Vercel).
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

export default API_BASE_URL;
