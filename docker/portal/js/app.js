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
        const res = await fetch('/api/aws/health-raw');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        body.innerText = JSON.stringify(data, null, 2);
      } catch (err) {
        // Fallback: show summarised status from existing status endpoint
        try {
          const res2 = await fetch('/api/aws/status');
          if (!res2.ok) throw new Error(`HTTP ${res2.status}`);
          const data2 = await res2.json();
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
