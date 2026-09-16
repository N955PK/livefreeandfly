// Small persistent key/value store: localStorage, mirrored to the iOS shell's UserDefaults when present
// (the shell injects saved values as window.acroStore before the page runs), so settings survive app closes.
const native = window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.acro;

export function getItem(key) {
  try {
    const v = localStorage.getItem(key);
    if (v !== null) return v;
  } catch (e) { /* storage unavailable */ }
  return (window.acroStore && window.acroStore[key]) || null;
}

export function setItem(key, value) {
  try {
    if (value === null) localStorage.removeItem(key); else localStorage.setItem(key, value);
  } catch (e) { /* storage unavailable */ }
  if (native) native.postMessage(`store:${key}:${value === null ? '' : value}`);
}
