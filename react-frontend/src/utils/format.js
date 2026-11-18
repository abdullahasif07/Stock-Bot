/** Parse Alpha Vantage numeric strings like "12.5", "+3.1%", "-0.42". */
export function toNumber(value) {
  const n = parseFloat(String(value ?? '').replace('%', ''));
  return Number.isFinite(n) ? n : 0;
}

/** Only allow http(s) links from third-party data. */
export function safeUrl(url) {
  return /^https?:\/\//i.test(url || '') ? url : undefined;
}
