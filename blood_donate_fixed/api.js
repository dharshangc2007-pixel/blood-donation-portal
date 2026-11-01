/* ============================================================
   api.js – Centralized API configuration for LifeFlow Portal
   All pages import this to get the correct backend base URL.
   ============================================================ */

// Auto-detect: if opened through the Python server, use relative URLs.
// If opened directly as a file://, fall back to localhost:5000.
const API_BASE = (location.protocol === 'file:')
  ? 'http://localhost:5000'
  : '';

/**
 * Thin fetch wrapper with JSON response.
 * @param {string} path    - API path, e.g. '/api/stats'
 * @param {object} opts    - fetch options
 * @param {string} [token] - optional Bearer token
 */
async function apiFetch(path, opts, token) {
  opts  = opts  || {};
  token = token || '';
  var headers = Object.assign({ 'Content-Type': 'application/json' }, opts.headers || {});
  if (token) headers['Authorization'] = 'Bearer ' + token;
  var res = await fetch(API_BASE + path, Object.assign({}, opts, { headers: headers }));
  return res.json();
}

/**
 * Escapes HTML special characters to prevent XSS.
 */
function htmlEsc(s) {
  if (!s && s !== 0) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * Show a dismissible toast notification.
 * @param {string} msg
 * @param {'success'|'error'|'info'} type
 */
function showToast(msg, type) {
  type = type || 'success';
  var wrap = document.getElementById('lf-toast-wrap');
  if (!wrap) {
    wrap = document.createElement('div');
    wrap.id = 'lf-toast-wrap';
    wrap.style.cssText = 'position:fixed;bottom:24px;right:24px;z-index:99999;display:flex;flex-direction:column;gap:10px;pointer-events:none';
    document.body.appendChild(wrap);
  }

  var colors = {
    success: { bg: 'rgba(34,197,94,0.15)',  border: 'rgba(34,197,94,0.4)',  text: '#4ade80' },
    error:   { bg: 'rgba(220,20,60,0.15)',  border: 'rgba(220,20,60,0.4)',  text: '#ff8fa3' },
    info:    { bg: 'rgba(99,102,241,0.15)', border: 'rgba(99,102,241,0.4)', text: '#a5b4fc' }
  };
  var c = colors[type] || colors.info;

  var toast = document.createElement('div');
  toast.textContent = msg;
  toast.style.cssText = 'background:' + c.bg + ';border:1px solid ' + c.border + ';color:' + c.text + ';padding:12px 20px;border-radius:12px;font-size:0.875rem;font-weight:600;backdrop-filter:blur(12px);pointer-events:auto;box-shadow:0 8px 24px rgba(0,0,0,0.4);max-width:340px;font-family:Inter,sans-serif;opacity:0;transition:opacity 0.3s ease,transform 0.3s ease;transform:translateY(10px)';

  wrap.appendChild(toast);
  // Trigger transition
  requestAnimationFrame(function() {
    requestAnimationFrame(function() {
      toast.style.opacity = '1';
      toast.style.transform = 'translateY(0)';
    });
  });

  setTimeout(function() {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    setTimeout(function() { toast.remove(); }, 320);
  }, 3500);
}
