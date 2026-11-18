import { useCallback, useEffect, useState } from 'react';
import { apiJson } from '../utils/apiClient';

export function useDemoStatus() {
  const [status, setStatus] = useState(null);
  const refresh = useCallback(() => {
    apiJson('/status').then(setStatus).catch(() => {});
  }, []);
  useEffect(() => { refresh(); }, [refresh]);
  return { status, refresh };
}
