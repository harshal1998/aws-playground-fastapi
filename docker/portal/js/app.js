    // -------------------------------------------------------------------------
    // Tab Management
    // -------------------------------------------------------------------------
    function setPortalTab(tabName) {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

      const btn = document.getElementById(`tab-btn-${tabName}`);
      const content = document.getElementById(`view-${tabName}`);
      if (btn && content) {
        btn.classList.add('active');
        content.classList.add('active');
      }

      if (tabName === 'aws') {
        refreshAwsStatus();
        fetchS3Objects();
        fetchSQSQueues();
        fetchDynamoTables();
        fetchSecrets();
        fetchLambdaFunctions();
        fetchEventBuses();
        fetchKinesisStreams();
      }
    }

    async function openHealthJsonModal() {
      const modal = document.getElementById('modal-health');
      const body = document.getElementById('health-json-body');

      if (!modal || !body) {
        console.error('[HealthModal] DOM elements not found:', { modal, body });
        return;
      }

      // Force display via both class and inline style to bypass any CSS specificity issues
      modal.classList.add('active');
      modal.style.display = 'flex';
      body.innerText = 'Fetching LocalStack health status...';

      try {
        // Proxy through backend to avoid CORS: browser blocks the LocalStack GET
        // response body even when Network shows 200 (preflight passes but GET lacks ACAO)
        const data = await apiFetch('/api/aws/health-raw');
        body.innerText = JSON.stringify(data, null, 2);
      } catch (err) {
        // Fallback: show summarised status from existing status endpoint
        try {
          const data2 = await apiFetch('/api/aws/status');
          body.innerText = JSON.stringify(data2, null, 2);
        } catch (e) {
          body.innerText = `Could not reach LocalStack.\n\nError: ${e.message}`;
          console.error('[HealthModal] Both endpoints failed:', err, e);
        }
      }
    }


    function setAwsSubtab(subtabName, shouldScroll = false) {
      // Ensure AWS tab is displayed
      setPortalTab('aws');

      document.querySelectorAll('.subnav-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.subtab-panel').forEach(p => p.classList.remove('active'));

      const btn = document.getElementById(`subtab-btn-${subtabName}`);
      const panel = document.getElementById(`subtab-panel-${subtabName}`);
      if (btn && panel) {
        btn.classList.add('active');
        panel.classList.add('active');
        if (shouldScroll) {
          requestAnimationFrame(() => {
            const target = document.getElementById('aws-console-section') || document.querySelector('.aws-console');
            if (target) {
              target.scrollIntoView({ behavior: 'smooth', block: 'start' });
              target.classList.add('focused-section');
              setTimeout(() => target.classList.remove('focused-section'), 1800);
            }
          });
        }
      }
    }

    // -------------------------------------------------------------------------
    // Utilities & Toast
    // -------------------------------------------------------------------------
    function showToast(msg) {
      const t = document.getElementById('toast');
      t.innerText = msg;
      t.style.display = 'block';
      setTimeout(() => { t.style.display = 'none'; }, 3200);
    }

    function copyText(text) {
      navigator.clipboard.writeText(text);
      showToast(`Copied to clipboard: "${text}"`);
    }

    function closeModal(id) {
      const el = document.getElementById(id);
      if (el) {
        el.classList.remove('active');
        el.style.display = '';  // Clear any inline style set by openHealthJsonModal
      }
    }

    // -------------------------------------------------------------------------

    // Helpers
    function formatBytes(bytes) {
      if (!bytes || bytes === 0) return '0 B';
      const k = 1024;
      const sizes = ['B', 'KB', 'MB', 'GB'];
      const i = Math.floor(Math.log(bytes) / Math.log(k));
      return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
    }

    // -------------------------------------------------------------------------
    // API helper: one place for fetch + error handling
    // -------------------------------------------------------------------------
    function isAbortError(err) {
      return Boolean(err) && err.name === 'AbortError';
    }

    function formatApiErrorDetail(detail) {
      if (typeof detail === 'string') return detail;
      if (Array.isArray(detail)) {
        // FastAPI 422 validation errors: [{loc: [...], msg: '...'}, ...]
        return detail
          .map(d => {
            if (!d || typeof d !== 'object') return String(d);
            const loc = Array.isArray(d.loc) ? d.loc.filter(p => p !== 'body').join('.') : '';
            return loc ? `${loc}: ${d.msg}` : String(d.msg);
          })
          .join('; ');
      }
      return JSON.stringify(detail);
    }

    // Fetches a JSON API endpoint. Resolves with the parsed body ({} when the
    // body is empty). On a non-2xx response it throws an Error carrying the
    // server's `detail` (or a clear message when the body isn't JSON, e.g. an
    // nginx 502 HTML page). AbortErrors are re-thrown untouched so callers can
    // ignore superseded requests.
    async function apiFetch(url, options = {}) {
      let res;
      try {
        res = await fetch(url, options);
      } catch (err) {
        if (isAbortError(err)) throw err;
        throw new Error(`Network error: could not reach the API (${err.message})`);
      }

      const contentType = res.headers.get('content-type') || '';
      const isJson = contentType.includes('application/json');
      let body = null;
      let text = '';
      try {
        if (isJson) body = await res.json();
        else text = await res.text();
      } catch (err) {
        if (isAbortError(err)) throw err;
        body = null;
      }

      if (!res.ok) {
        let message;
        if (body && typeof body === 'object' && body.detail !== undefined) {
          message = formatApiErrorDetail(body.detail);
        } else if (isJson) {
          message = `HTTP ${res.status} ${res.statusText}`.trim();
        } else {
          message = `HTTP ${res.status} ${res.statusText}`.trim()
            + ' (non-JSON response from the server; is the API container running?)';
        }
        const error = new Error(message);
        error.status = res.status;
        throw error;
      }

      if (!isJson && text.trim() !== '') {
        const error = new Error(`Expected JSON from ${url} but got ${contentType || 'an unknown content type'} (HTTP ${res.status})`);
        error.status = res.status;
        throw error;
      }
      return body ?? {};
    }

    function escapeHtml(text) {
      if (!text) return '';
      return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
    }

    // Fallback partial loader if viewed without Nginx SSI
    async function checkAndLoadPartialFallback() {
      const container = document.querySelector('.container');
      if (container && container.children.length === 0) {
        try {
          const [header, overview, aws, modals] = await Promise.all([
            fetch('/partials/header.html').then(r => r.text()),
            fetch('/partials/overview.html').then(r => r.text()),
            fetch('/partials/aws-services.html').then(r => r.text()),
            fetch('/partials/modals.html').then(r => r.text()),
          ]);
          container.innerHTML = header + overview + aws;
          const modalWrapper = document.createElement('div');
          modalWrapper.innerHTML = modals;
          document.body.appendChild(modalWrapper);
        } catch (e) {
          console.warn('Fallback partial loading error:', e);
        }
      }
    }

    // Auto-check on load
    window.addEventListener('DOMContentLoaded', async () => {
      await checkAndLoadPartialFallback();
      if (typeof refreshAwsStatus === 'function') {
        refreshAwsStatus();
      }
    });
