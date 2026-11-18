import React, { useState } from 'react';
import { apiFetch, setAccessCode } from '../utils/apiClient';
import '../styles/AccessGate.css';

function AccessGate({ onUnlocked }) {
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    setAccessCode(code.trim());
    try {
      await apiFetch('/access-check');
      onUnlocked();
    } catch {
      setError('That code did not work.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="access-gate">
      <form onSubmit={submit} className="access-card">
        <h1>StockBot</h1>
        <p>This demo is protected to keep API usage in check. Enter the access code you were given.</p>
        <input value={code} onChange={(e) => setCode(e.target.value)} placeholder="Access code" autoFocus aria-label="Access code" />
        {error && <div className="access-error">{error}</div>}
        <button type="submit" disabled={busy || !code.trim()}>{busy ? 'Checking…' : 'Enter demo'}</button>
      </form>
    </div>
  );
}

export default AccessGate;
