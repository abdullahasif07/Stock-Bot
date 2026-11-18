import { useCallback, useEffect, useState } from 'react';

// Conversations live in the visitor's browser (no accounts needed). Each
// visitor only ever sees their own chats; nothing is stored server-side.
const STORAGE_KEY = 'stockbot_sessions_v2';
const MAX_SESSIONS = 30;

function load() {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

const newId = () => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`);

export function useChatSessions() {
  const [sessions, setSessions] = useState(load);
  const [activeId, setActiveId] = useState(() => load()[0]?.id ?? null);

  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions.slice(0, MAX_SESSIONS))); }
    catch { /* quota exceeded / private mode: keep in memory */ }
  }, [sessions]);

  const activeSession = sessions.find(s => s.id === activeId) || null;

  const createSession = useCallback((title) => {
    const session = { id: newId(), title: title.slice(0, 40) || 'New chat', createdAt: Date.now(), messages: [], rag: null };
    setSessions(prev => [session, ...prev]);
    setActiveId(session.id);
    return session.id;
  }, []);

  const updateSession = useCallback((id, updater) => {
    setSessions(prev => prev.map(s => (s.id === id ? { ...s, ...updater(s) } : s)));
  }, []);

  const addMessage = useCallback((id, message) => {
    const msg = { id: newId(), ...message };
    updateSession(id, s => ({ messages: [...s.messages, msg] }));
    return msg.id;
  }, [updateSession]);

  const patchMessage = useCallback((sessionId, messageId, patch) => {
    updateSession(sessionId, s => ({
      messages: s.messages.map(m => (m.id === messageId ? { ...m, ...patch } : m)),
    }));
  }, [updateSession]);

  const deleteSession = useCallback((id) => {
    const idx = sessions.findIndex(s => s.id === id);
    const remaining = sessions.filter(s => s.id !== id);
    setSessions(prev => prev.filter(s => s.id !== id));
    if (activeId === id) setActiveId(remaining[Math.min(idx, remaining.length - 1)]?.id ?? null);
  }, [sessions, activeId]);

  return {
    sessions, activeId, activeSession, setActiveId,
    createSession, updateSession, addMessage, patchMessage, deleteSession,
  };
}
