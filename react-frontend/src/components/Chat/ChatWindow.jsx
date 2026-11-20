import React, { useEffect, useRef, useState } from 'react';
import Message from './Message';
import ChatInput from './ChatInput';
import ChatSidebar from './ChatSidebar';
import { useChatSessions } from '../../hooks/useChatSessions';
import { apiFetch, apiJson } from '../../utils/apiClient';
import { readStream } from '../../utils/streamReader';
import '../../styles/ChatWindow.css';

const HISTORY_LIMIT = 8;

const EXAMPLES = [
  { label: "What's Apple's stock price?", text: "What's Apple's stock price right now?" },
  { label: 'Outlook for NVIDIA', text: "What's your outlook for NVIDIA stock?" },
  { label: 'Explain the P/E ratio', text: 'Explain the P/E ratio like I am new to investing.' },
  { label: "Analyze Amazon's 10-K", rag: 'Amazon' },
];

const RAG_SUGGESTIONS = [
  'What are the biggest risk factors?',
  'Summarize revenue and operating income by segment.',
  'How did net income change year over year?',
  'What does management say about AI?',
];

function toHistory(messages, docId = null) {
  return messages
    .filter(m => !m.error && !m.notice && (m.docId ?? null) === docId && m.text)
    .slice(-HISTORY_LIMIT)
    .map(m => ({ role: m.role, text: m.text.slice(0, 4000) }));
}

function docReadyText(doc) {
  const period = doc.report_date ? ` for the period ending **${doc.report_date}**` : '';
  const filed = doc.filing_date ? ` (filed ${doc.filing_date})` : '';
  const link = doc.source_url ? ` · [View on SEC.gov](${doc.source_url})` : '';
  return `📄 **${doc.title}**${period}${filed} is ready — ${doc.chunks} passages indexed${link}.\n\nAsk anything about it, or try one of these:`;
}

function ChatWindow({ status, onActivity }) {
  const {
    sessions, activeId, activeSession, setActiveId,
    createSession, updateSession, addMessage, patchMessage, deleteSession,
  } = useChatSessions();
  const [loading, setLoading] = useState(null); // null | label string
  const chatBoxRef = useRef(null);

  const messages = activeSession?.messages ?? [];
  const rag = activeSession?.rag ?? null;

  useEffect(() => {
    chatBoxRef.current?.scrollTo({ top: chatBoxRef.current.scrollHeight });
  }, [messages, loading]);

  const ensureSession = (title) => activeId ?? createSession(title);

  const fail = (sessionId, err, extra = {}) => {
    addMessage(sessionId, { role: 'model', text: err?.message || 'Something went wrong.', error: true, ...extra });
  };

  const streamInto = async (sessionId, response, extra = {}) => {
    let msgId = null;
    await readStream(response, (text) => {
      if (!msgId) {
        setLoading(null);
        msgId = addMessage(sessionId, { role: 'model', text, ...extra });
      } else {
        patchMessage(sessionId, msgId, { text });
      }
    });
  };

  const run = async (label, fn) => {
    setLoading(label);
    try { await fn(); } finally { setLoading(null); onActivity?.(); }
  };

  // ── General chat ────────────────────────────────────────────────────────
  const sendChat = (sessionId, text, context = {}, priorMessages = messages) =>
    run('Thinking…', async () => {
      try {
        const response = await apiFetch('/chat', {
          method: 'POST',
          json: { message: text, history: toHistory(priorMessages), context },
        });
        if (response.headers.get('content-type')?.includes('application/json')) {
          const data = await response.json();
          addMessage(sessionId, {
            role: 'model', text: data.message, choices: data.choices,
            choiceFor: 'chat', original_intent: data.original_intent,
          });
        } else {
          const ticker = response.headers.get('X-Ticker');
          await streamInto(sessionId, response, ticker ? { ticker } : {});
        }
      } catch (err) {
        fail(sessionId, err);
      }
    });

  // ── Document analysis (RAG) ─────────────────────────────────────────────
  const loadDocument = (sessionId, request, label) =>
    run(label, async () => {
      try {
        const data = await request();
        if (data.response_type === 'clarification') {
          addMessage(sessionId, { role: 'model', text: data.message, choices: data.choices, choiceFor: 'rag', notice: true });
          return;
        }
        const doc = data.document;
        updateSession(sessionId, () => ({ rag: { doc } }));
        addMessage(sessionId, { role: 'model', text: docReadyText(doc), notice: true, suggestions: RAG_SUGGESTIONS });
      } catch (err) {
        fail(sessionId, err, { notice: true });
      }
    });

  const initiateRag = (sessionId, company) =>
    loadDocument(
      sessionId,
      () => apiJson('/rag/initiate', { method: 'POST', json: { company } }),
      'Fetching the latest annual report from SEC EDGAR and indexing it (first time can take ~30s)…',
    );

  const queryRag = (sessionId, doc, question) =>
    run('Searching the report…', async () => {
      try {
        const response = await apiFetch('/rag/query', {
          method: 'POST',
          json: { doc_id: doc.doc_id, question, history: toHistory(messages, doc.doc_id) },
        });
        await streamInto(sessionId, response, { docId: doc.doc_id });
      } catch (err) {
        fail(sessionId, err, { docId: doc.doc_id });
      }
    });

  const startRag = (company) => {
    const sessionId = ensureSession(company ? `${company} 10-K` : 'Document analysis');
    updateSession(sessionId, () => ({ rag: { doc: null } }));
    if (company) {
      addMessage(sessionId, { role: 'user', text: `Analyze ${company}'s latest 10-K`, notice: true });
      initiateRag(sessionId, company);
    } else {
      addMessage(sessionId, {
        role: 'model', notice: true,
        text: "Which company's annual report should I analyze? Type a name or ticker (e.g. **Tesla**, **MSFT**) — I'll pull the latest 10-K straight from SEC EDGAR. You can also upload your own PDF or text file with the 📎 button.",
      });
    }
  };

  const exitRag = () => {
    if (!activeId) return;
    updateSession(activeId, () => ({ rag: null }));
    addMessage(activeId, { role: 'model', text: 'Left document analysis. Ask me anything about the markets.', notice: true });
  };

  // ── Input handlers ──────────────────────────────────────────────────────
  const handleSend = (text) => {
    const sessionId = ensureSession(text);
    if (rag?.doc) {
      addMessage(sessionId, { role: 'user', text, docId: rag.doc.doc_id });
      queryRag(sessionId, rag.doc, text);
    } else if (rag) {
      addMessage(sessionId, { role: 'user', text, notice: true });
      initiateRag(sessionId, text);
    } else {
      addMessage(sessionId, { role: 'user', text });
      sendChat(sessionId, text);
    }
  };

  const handleUpload = (file) => {
    const sessionId = ensureSession(file.name);
    addMessage(sessionId, { role: 'user', text: `📎 ${file.name}`, notice: true });
    const form = new FormData();
    form.append('file', file);
    loadDocument(sessionId, () => apiJson('/rag/upload', { method: 'POST', body: form }), 'Reading and indexing your document…');
  };

  const handleChoice = (msg, choice) => {
    // Clarifications are one-shot: remove the buttons once used.
    patchMessage(activeId, msg.id, { choices: null });
    if (msg.choiceFor === 'rag') {
      addMessage(activeId, { role: 'user', text: `${choice.symbol} — ${choice.name}`, notice: true });
      initiateRag(activeId, choice.symbol);
    } else {
      addMessage(activeId, { role: 'user', text: choice.symbol });
      sendChat(activeId, choice.symbol, { awaiting_clarification: true, original_intent: msg.original_intent });
    }
  };

  const handleSuggestion = (msg, text) => {
    patchMessage(activeId, msg.id, { suggestions: null });
    handleSend(text);
  };

  const handleExample = (ex) => (ex.rag ? startRag(ex.rag) : handleSend(ex.text));

  const aiLeft = status?.budgets?.ai_requests;

  return (
    <div className="full-page-chat-wrapper">
      <ChatSidebar
        sessions={sessions}
        activeChatId={activeId}
        onSelectChat={setActiveId}
        onNewChat={() => setActiveId(null)}
        onDeleteChat={deleteSession}
      />
      <div className="chat-container">
        <header className="chat-header">
          <h1>StockBot <span className="demo-badge">Live demo</span></h1>
          <div className="header-controls">
            <span>
              {rag?.doc ? `Analyzing: ${rag.doc.title}` : 'Live quotes · AI outlooks · 10-K analysis'}
            </span>
            {aiLeft && (
              <span className="quota" title="Shared daily budget for this public demo (resets 00:00 UTC)">
                AI requests left today: {aiLeft.remaining}/{aiLeft.limit}
              </span>
            )}
          </div>
        </header>
        <div className="chat-box" ref={chatBoxRef}>
          {messages.length === 0 && !loading && (
            <div className="welcome">
              <h2>Hi! I'm StockBot.</h2>
              <p>
                I pull live market data from Alpha Vantage, reason over it with Google Gemini, and can
                answer questions about any US company's latest SEC annual report with cited sources.
              </p>
              <div className="example-grid">
                {EXAMPLES.map(ex => (
                  <button key={ex.label} className="example-btn" onClick={() => handleExample(ex)}>{ex.label}</button>
                ))}
              </div>
            </div>
          )}
          {messages.map(msg => (
            <React.Fragment key={msg.id}>
              <Message
                role={msg.role}
                text={msg.text}
                error={msg.error}
                ticker={msg.ticker}
                choices={msg.choices}
                disabled={!!loading}
                onChoice={(choice) => handleChoice(msg, choice)}
              />
              {msg.suggestions?.length > 0 && (
                <div className="suggestions">
                  {msg.suggestions.map(s => (
                    <button key={s} className="example-btn" disabled={!!loading} onClick={() => handleSuggestion(msg, s)}>{s}</button>
                  ))}
                </div>
              )}
            </React.Fragment>
          ))}
          {loading && (
            <div className="message bot-message">
              <div className="message-content typing-indicator">
                <span></span><span></span><span></span>
                {loading.length > 12 && <em className="loading-label">{loading}</em>}
              </div>
            </div>
          )}
        </div>
        <ChatInput
          onSend={handleSend}
          onUpload={handleUpload}
          isRagMode={!!rag}
          awaitingDocument={!!rag && !rag.doc}
          onStartRag={() => startRag(null)}
          onExitRag={exitRag}
          disabled={!!loading}
        />
      </div>
    </div>
  );
}

export default ChatWindow;
