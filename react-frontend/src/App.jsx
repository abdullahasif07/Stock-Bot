import React, { useEffect, useState } from 'react';
import ChatPage from './pages/ChatPage';
import AccessGate from './components/AccessGate';
import { useDemoStatus } from './hooks/useDemoStatus';
import { getAccessCode } from './utils/apiClient';

function App() {
  const { status, refresh } = useDemoStatus();
  const [needsCode, setNeedsCode] = useState(false);

  useEffect(() => {
    if (status?.access_code_required && !getAccessCode()) setNeedsCode(true);
  }, [status]);

  useEffect(() => {
    const onRequired = () => setNeedsCode(true);
    window.addEventListener('stockbot:access-required', onRequired);
    return () => window.removeEventListener('stockbot:access-required', onRequired);
  }, []);

  if (needsCode) {
    return <AccessGate onUnlocked={() => { setNeedsCode(false); refresh(); }} />;
  }
  return <ChatPage status={status} onActivity={refresh} />;
}

export default App;
