import React, { useRef, useState } from 'react';
import { FileText, Paperclip, Send, X } from 'lucide-react';
import '../../styles/ChatInput.css';

const MAX_CHARS = 1000;

function ChatInput({ onSend, onUpload, isRagMode, awaitingDocument, onStartRag, onExitRag, disabled }) {
  const [message, setMessage] = useState('');
  const fileRef = useRef(null);

  const handleSubmit = (e) => {
    e.preventDefault();
    const text = message.trim();
    if (!text || disabled) return;
    onSend(text);
    setMessage('');
  };

  const handleFile = (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (file) onUpload(file);
  };

  const placeholder = !isRagMode
    ? 'Ask about a stock, e.g. "What is NVDA trading at?"'
    : awaitingDocument
      ? 'Company name or ticker (e.g. Tesla) — or upload a file'
      : 'Ask about this report, e.g. "What are the key risks?"';

  return (
    <div className="chat-input-area">
      <form onSubmit={handleSubmit}>
        {isRagMode ? (
          <button type="button" onClick={onExitRag} className="rag-action-btn exit" title="Leave document analysis">
            <X size={16} /> Exit analysis
          </button>
        ) : (
          <button type="button" onClick={onStartRag} className="rag-action-btn" disabled={disabled}
                  title="Chat with a company's latest SEC annual report">
            <FileText size={16} /> Analyze 10-K
          </button>
        )}
        {isRagMode && awaitingDocument && (
          <>
            <input ref={fileRef} type="file" hidden accept=".pdf,.txt,.md,.htm,.html,.csv" onChange={handleFile} />
            <button type="button" className="icon-btn secondary" aria-label="Upload a document"
                    title="Upload your own PDF/TXT/HTML (max 5 MB)" disabled={disabled}
                    onClick={() => fileRef.current?.click()}>
              <Paperclip size={20} />
            </button>
          </>
        )}
        <input
          type="text"
          value={message}
          maxLength={MAX_CHARS}
          onChange={(e) => setMessage(e.target.value)}
          placeholder={placeholder}
          aria-label="Message"
          autoFocus
        />
        <button type="submit" className="icon-btn" aria-label="Send message" disabled={disabled || !message.trim()}>
          <Send size={20} color="white" />
        </button>
      </form>
    </div>
  );
}

export default ChatInput;
