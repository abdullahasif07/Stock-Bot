import React, { useMemo } from 'react';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import '../../styles/Message.css';

// Model output can echo text from filings or uploaded files, so it is
// sanitized before rendering. Links open in a new tab.
DOMPurify.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName === 'A') {
    node.setAttribute('target', '_blank');
    node.setAttribute('rel', 'noopener noreferrer');
  }
});

function Message({ role, text, choices, error, onChoice, disabled }) {
  const isBot = role === 'model';
  const html = useMemo(
    () => (isBot ? DOMPurify.sanitize(marked.parse(text || '')) : null),
    [isBot, text],
  );

  return (
    <div className={`message ${isBot ? 'bot-message' : 'user-message'}`}>
      {isBot ? (
        <div className={`message-content ${error ? 'error' : ''}`} dangerouslySetInnerHTML={{ __html: html }} />
      ) : (
        <div className="message-content"><p>{text}</p></div>
      )}
      {choices?.length > 0 && (
        <div className="clarification-choices">
          {choices.map(choice => (
            <button
              key={choice.symbol}
              className="clarification-btn"
              disabled={disabled}
              onClick={() => onChoice(choice)}
            >
              <strong>{choice.symbol}</strong> — {choice.name}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default Message;
