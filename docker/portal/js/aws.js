    // LocalStack AWS Engine Status
    // -------------------------------------------------------------------------
    async function refreshAwsStatus() {
      try {
        const res = await fetch('/api/aws/status');
        const data = await res.json();
        const indicator = document.getElementById('aws-health-indicator');
        const badge = document.getElementById('aws-service-count-badge');
        const tagsContainer = document.getElementById('aws-service-tags');

        if (data.status === 'online') {
          indicator.innerText = `HEALTHY (v${data.version})`;
          indicator.style.color = 'var(--accent-green)';
          badge.innerText = `${data.total_available} Active`;

          if (data.active_services && data.active_services.length > 0) {
            tagsContainer.innerHTML = data.active_services
              .map(s => `<span class="aws-tag">${s}</span>`)
              .join(' ');
          }
        } else {
          indicator.innerText = 'OFFLINE';
          indicator.style.color = 'var(--accent-rose)';
        }
      } catch (err) {
        console.warn('Failed to load AWS status:', err);
      }
    }

    // -------------------------------------------------------------------------
    // S3 Object Explorer
    // -------------------------------------------------------------------------
    async function fetchS3Objects() {
      const tbody = document.getElementById('s3-files-tbody');
      try {
        const res = await fetch('/api/s3/objects');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        const objects = data.objects || [];

        if (objects.length === 0) {
          tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-muted); padding: 24px;">No files currently in bucket. Click "Upload Sample Document" to add one!</td></tr>`;
          return;
        }

        tbody.innerHTML = objects.map(obj => `
          <tr>
            <td class="mono-cell">${escapeHtml(obj.key)}</td>
            <td>${formatBytes(obj.size_bytes)}</td>
            <td style="color: var(--text-muted); font-size: 12.5px;">${new Date(obj.last_modified).toLocaleString()}</td>
            <td style="text-align: right;">
              <a href="/api/s3/file?key=${encodeURIComponent(obj.key)}" target="_blank" class="ctrl-btn" style="padding: 4px 8px; font-size: 11px;">
                Download
              </a>
              <button class="ctrl-btn ctrl-btn-danger" data-action="delete-s3-file" data-key="${escapeHtml(obj.key)}">
                Delete
              </button>
            </td>
          </tr>
        `).join('');
        tbody.onclick = (e) => {
          const btn = e.target.closest('button[data-action]');
          if (!btn) return;
          if (btn.dataset.action === 'delete-s3-file') deleteS3File(btn.dataset.key);
        };
      } catch (err) {
        tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: #fb7185; padding: 20px;">Could not connect to S3: ${err.message}</td></tr>`;
      }
    }

    async function handleRealFileUpload(event) {
      const file = event.target.files[0];
      if (!file) return;

      showToast(`Uploading "${file.name}" to S3...`);
      try {
        const res = await fetch(`/api/s3/upload?filename=${encodeURIComponent(file.name)}`, {
          method: 'POST',
          headers: {
            'Content-Type': file.type || 'application/octet-stream'
          },
          body: file
        });
        if (res.ok) {
          showToast(`Uploaded "${file.name}" (${formatBytes(file.size)}) to S3!`);
          fetchS3Objects();
        } else {
          showToast(`Upload failed (HTTP ${res.status})`);
        }
      } catch (err) {
        showToast(`Upload error: ${err.message}`);
      } finally {
        event.target.value = '';
      }
    }

    async function uploadSampleFile() {
      const filename = `doc_${Math.floor(Date.now() / 1000)}.txt`;
      try {
        const res = await fetch(`/api/s3/upload-sample?filename=${encodeURIComponent(filename)}`, { method: 'POST' });
        if (res.ok) {
          showToast(`Uploaded sample "${filename}" to S3!`);
          fetchS3Objects();
        } else {
          showToast(`Upload failed`);
        }
      } catch (err) {
        showToast(`Error uploading: ${err.message}`);
      }
    }

    async function deleteS3File(key) {
      if (!confirm(`Delete "${key}" from LocalStack S3?`)) return;
      try {
        const res = await fetch(`/api/s3/file?key=${encodeURIComponent(key)}`, { method: 'DELETE' });
        if (res.ok) {
          showToast(`Deleted "${key}"`);
          fetchS3Objects();
        }
      } catch (err) {
        showToast(`Delete failed: ${err.message}`);
      }
    }

    // -------------------------------------------------------------------------
    // SQS Queues & Messages
    // -------------------------------------------------------------------------
    async function fetchSQSQueues() {
      const tbody = document.getElementById('sqs-queues-tbody');
      const select = document.getElementById('sqs-send-queue-select');
      const cardCount = document.getElementById('card-sqs-count');

      try {
        const res = await fetch('/api/aws/sqs/queues');
        const data = await res.json();
        const queues = data.queues || [];

        cardCount.innerText = `${queues.length} Queues`;

        if (queues.length === 0) {
          tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-muted); padding: 20px;">No SQS queues exist yet. Click "Create New Queue" to start!</td></tr>`;
          select.innerHTML = `<option value="">(No queues available)</option>`;
          return;
        }

        tbody.innerHTML = queues.map(q => `
          <tr>
            <td class="mono-cell">${escapeHtml(q.name)}</td>
            <td><span class="aws-tag">${q.messages} msg</span></td>
            <td><span style="color: var(--text-muted);">${q.in_flight}</span></td>
            <td style="text-align: right;">
              <button class="ctrl-btn" style="padding: 4px 8px; font-size: 11px;" data-action="read-sqs" data-name="${escapeHtml(q.name)}">
                Read Messages
              </button>
              <button class="ctrl-btn ctrl-btn-danger" data-action="purge-sqs" data-name="${escapeHtml(q.name)}">
                Purge
              </button>
            </td>
          </tr>
        `).join('');
        tbody.onclick = (e) => {
          const btn = e.target.closest('button[data-action]');
          if (!btn) return;
          if (btn.dataset.action === 'read-sqs') readSQSMessages(btn.dataset.name);
          else if (btn.dataset.action === 'purge-sqs') purgeSQSQueue(btn.dataset.name);
        };

        select.innerHTML = queues.map(q => `<option value="${escapeHtml(q.name)}">${escapeHtml(q.name)}</option>`).join('');
      } catch (err) {
        tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: #fb7185; padding: 20px;">Error: ${err.message}</td></tr>`;
      }
    }

    function openCreateQueueModal() {
      document.getElementById('new-queue-name').value = '';
      document.getElementById('modal-queue').classList.add('active');
    }

    async function submitCreateQueue() {
      const name = document.getElementById('new-queue-name').value.trim();
      if (!name) return;
      try {
        const res = await fetch('/api/aws/sqs/queues', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name })
        });
        if (res.ok) {
          closeModal('modal-queue');
          showToast(`Queue "${name}" created!`);
          fetchSQSQueues();
        }
      } catch (err) {
        showToast(`Failed: ${err.message}`);
      }
    }

    async function sendSQSTestMessage() {
      const q = document.getElementById('sqs-send-queue-select').value;
      const body = document.getElementById('sqs-send-body').value.trim();
      if (!q || !body) return;
      try {
        const res = await fetch('/api/aws/sqs/messages', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ queue_name: q, message_body: body })
        });
        if (res.ok) {
          showToast(`Message enqueued to ${q}!`);
          fetchSQSQueues();
        }
      } catch (err) {
        showToast(`Send failed: ${err.message}`);
      }
    }

    async function readSQSMessages(qName) {
      try {
        const res = await fetch(`/api/aws/sqs/messages?queue_name=${encodeURIComponent(qName)}`);
        const data = await res.json();
        const msgs = data.messages || [];
        if (msgs.length === 0) {
          alert(`Queue "${qName}" has no unread messages.`);
        } else {
          const preview = msgs.map(m => `ID: ${m.id}\nPayload:\n${m.body}`).join('\n\n---\n\n');
          alert(`Messages from ${qName}:\n\n${preview}`);
        }
      } catch (err) {
        showToast(`Read failed: ${err.message}`);
      }
    }

    async function purgeSQSQueue(qName) {
      if (!confirm(`Purge all messages in queue "${qName}"?`)) return;
      try {
        const res = await fetch(`/api/aws/sqs/queues?queue_name=${encodeURIComponent(qName)}`, { method: 'DELETE' });
        if (res.ok) {
          showToast(`Queue "${qName}" purged.`);
          fetchSQSQueues();
        }
      } catch (err) {
        showToast(`Purge failed: ${err.message}`);
      }
    }

    // -------------------------------------------------------------------------
    // DynamoDB Tables & Items
    // -------------------------------------------------------------------------
    let activeDynamoTable = '';
    let activeDynamoPartitionKey = 'id';
    let currentDynamoItems = [];

    async function fetchDynamoTables() {
      const tbody = document.getElementById('dynamo-tables-tbody');
      const cardCount = document.getElementById('card-dynamo-count');

      try {
        const res = await fetch('/api/aws/dynamodb/tables');
        const data = await res.json();
        const tables = data.tables || [];

        cardCount.innerText = `${tables.length} Tables`;

        if (tables.length === 0) {
          tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 20px;">No tables yet. Click "Create Custom Table" or "Sample products Table"!</td></tr>`;
          return;
        }

        tbody.innerHTML = tables.map(t => `
          <tr>
            <td class="mono-cell">${escapeHtml(t.name)}</td>
            <td><span class="aws-tag" style="background: rgba(52, 211, 153, 0.15); color: #34d399;">${escapeHtml(t.status)}</span></td>
            <td><span class="mono-cell" style="color: var(--accent-amber);">${escapeHtml(t.partition_key || 'id')}</span></td>
            <td>${t.item_count} items</td>
            <td style="text-align: right;">
              <button class="ctrl-btn ctrl-btn-primary" style="padding: 4px 8px; font-size: 11px;" data-action="scan-dynamo" data-name="${escapeHtml(t.name)}" data-partition-key="${escapeHtml(t.partition_key || 'id')}">
                Scan Records
              </button>
              <button class="ctrl-btn ctrl-btn-danger" data-action="delete-dynamo-table" data-name="${escapeHtml(t.name)}">
                Delete
              </button>
            </td>
          </tr>
        `).join('');
        tbody.onclick = (e) => {
          const btn = e.target.closest('button[data-action]');
          if (!btn) return;
          if (btn.dataset.action === 'scan-dynamo') scanDynamoTable(btn.dataset.name, btn.dataset.partitionKey);
          else if (btn.dataset.action === 'delete-dynamo-table') deleteDynamoTable(btn.dataset.name);
        };
      } catch (err) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: #fb7185; padding: 20px;">Error: ${err.message}</td></tr>`;
      }
    }

    function openCreateDynamoTableModal() {
      document.getElementById('new-dynamo-table-name').value = '';
      document.getElementById('new-dynamo-key-name').value = 'id';
      document.getElementById('modal-dynamo-table').classList.add('active');
    }

    async function submitCreateDynamoTable() {
      const tableName = document.getElementById('new-dynamo-table-name').value.trim();
      const keyName = document.getElementById('new-dynamo-key-name').value.trim() || 'id';
      if (!tableName) return;
      try {
        const res = await fetch('/api/aws/dynamodb/tables', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ table_name: tableName, key_name: keyName })
        });
        if (res.ok) {
          closeModal('modal-dynamo-table');
          showToast(`DynamoDB table "${tableName}" created!`);
          fetchDynamoTables();
        } else {
          showToast('Failed to create table');
        }
      } catch (err) {
        showToast(`Error: ${err.message}`);
      }
    }

    async function deleteDynamoTable(tName) {
      if (!confirm(`Permanently delete DynamoDB table "${tName}"?`)) return;
      try {
        const res = await fetch(`/api/aws/dynamodb/tables?table_name=${encodeURIComponent(tName)}`, { method: 'DELETE' });
        if (res.ok) {
          showToast(`Table "${tName}" deleted.`);
          if (activeDynamoTable === tName) {
            document.getElementById('dynamo-items-container').style.display = 'none';
          }
          fetchDynamoTables();
        }
      } catch (err) {
        showToast(`Delete failed: ${err.message}`);
      }
    }

    async function createSampleDynamoTable() {
      try {
        const res = await fetch('/api/aws/dynamodb/tables', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ table_name: 'products', key_name: 'id' })
        });
        if (res.ok) {
          showToast('DynamoDB table "products" ready!');
          fetchDynamoTables();
        }
      } catch (err) {
        showToast(`Table creation failed: ${err.message}`);
      }
    }

    async function scanDynamoTable(tName, partitionKey = 'id') {
      activeDynamoTable = tName;
      activeDynamoPartitionKey = partitionKey;
      document.getElementById('dynamo-selected-table').innerText = `${tName} (Key: ${partitionKey})`;
      document.getElementById('dynamo-items-container').style.display = 'block';

      const tbody = document.getElementById('dynamo-records-tbody');
      tbody.innerHTML = `<tr><td colspan="3" style="text-align: center; color: var(--text-muted); padding: 18px;">Scanning table...</td></tr>`;

      try {
        const res = await fetch(`/api/aws/dynamodb/items?table_name=${encodeURIComponent(tName)}`);
        const data = await res.json();
        const items = data.items || [];
        currentDynamoItems = items;

        document.getElementById('dynamo-items-json').innerText = items.length > 0 
          ? JSON.stringify(items, null, 2)
          : '(Table is empty)';

        if (items.length === 0) {
          tbody.innerHTML = `<tr><td colspan="3" style="text-align: center; color: var(--text-muted); padding: 18px;">No records found. Click "Insert Custom JSON Item"!</td></tr>`;
          return;
        }

        tbody.innerHTML = items.map((item, idx) => {
          const keyVal = item[partitionKey] !== undefined ? item[partitionKey] : Object.values(item)[0];
          const otherAttrs = Object.entries(item)
            .filter(([k]) => k !== partitionKey)
            .map(([k, v]) => `<span style="color:#94a3b8;">${escapeHtml(k)}:</span> <span style="color:#e2e8f0;">${escapeHtml(JSON.stringify(v))}</span>`)
            .join(', ');

          return `
            <tr>
              <td class="mono-cell">${escapeHtml(String(keyVal))}</td>
              <td style="font-size: 12.5px;">${otherAttrs || '(No additional attributes)'}</td>
              <td style="text-align: right; white-space: nowrap;">
                <button class="ctrl-btn" style="padding: 4px 8px; font-size: 11px; margin-right: 6px; background: rgba(56, 189, 248, 0.15); border-color: rgba(56, 189, 248, 0.3); color: #38bdf8;" onclick="openEditDynamoItemModal(${idx})">
                  ✏️ Edit
                </button>
                <button class="ctrl-btn ctrl-btn-danger" data-action="delete-dynamo-item" data-key="${escapeHtml(String(keyVal))}">
                  Delete
                </button>
              </td>
            </tr>
          `;
        }).join('');
        tbody.onclick = (e) => {
          const btn = e.target.closest('button[data-action]');
          if (!btn) return;
          if (btn.dataset.action === 'delete-dynamo-item') deleteDynamoItem(btn.dataset.key);
        };
      } catch (err) {
        tbody.innerHTML = `<tr><td colspan="3" style="text-align: center; color: #fb7185; padding: 18px;">Error: ${err.message}</td></tr>`;
        document.getElementById('dynamo-items-json').innerText = `Error: ${err.message}`;
      }
    }

    function openEditDynamoItemModal(itemIndex) {
      if (!activeDynamoTable || !currentDynamoItems[itemIndex]) return;
      const item = currentDynamoItems[itemIndex];
      const keyVal = item[activeDynamoPartitionKey] !== undefined ? item[activeDynamoPartitionKey] : Object.values(item)[0];

      document.getElementById('modal-edit-table-name').innerText = activeDynamoTable;
      document.getElementById('modal-edit-key-name').innerText = activeDynamoPartitionKey;
      document.getElementById('modal-edit-key-value').innerText = String(keyVal);
      document.getElementById('edit-dynamo-item-json').value = JSON.stringify(item, null, 2);
      document.getElementById('modal-edit-dynamo-item').classList.add('active');
    }

    async function submitEditDynamoItem() {
      if (!activeDynamoTable) return;
      const rawJson = document.getElementById('edit-dynamo-item-json').value.trim();
      let parsed;
      try {
        parsed = JSON.parse(rawJson);
      } catch (e) {
        alert('Invalid JSON: ' + e.message);
        return;
      }
      if (parsed[activeDynamoPartitionKey] === undefined) {
        alert(`Document must contain the partition key "${activeDynamoPartitionKey}"`);
        return;
      }
      try {
        const res = await fetch('/api/aws/dynamodb/items', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ table_name: activeDynamoTable, item: parsed })
        });
        if (res.ok) {
          closeModal('modal-edit-dynamo-item');
          showToast(`Item updated in ${activeDynamoTable}!`);
          scanDynamoTable(activeDynamoTable, activeDynamoPartitionKey);
        } else {
          const errData = await res.json().catch(() => ({}));
          showToast(`Update failed: ${errData.detail || res.statusText}`);
        }
      } catch (err) {
        showToast(`Update error: ${err.message}`);
      }
    }

    function openInsertDynamoItemModal() {
      if (!activeDynamoTable) return;
      document.getElementById('modal-item-table-name').innerText = activeDynamoTable;
      document.getElementById('modal-item-key-label').innerText = activeDynamoPartitionKey;
      const template = {};
      template[activeDynamoPartitionKey] = `${activeDynamoTable.slice(0, 4)}_${Math.floor(Date.now() / 1000)}`;
      template["name"] = "Sample Record";
      template["created_at"] = new Date().toISOString();
      document.getElementById('new-dynamo-item-json').value = JSON.stringify(template, null, 2);
      document.getElementById('modal-dynamo-item').classList.add('active');
    }

    async function submitInsertDynamoItem() {
      if (!activeDynamoTable) return;
      const rawJson = document.getElementById('new-dynamo-item-json').value.trim();
      let parsed;
      try {
        parsed = JSON.parse(rawJson);
      } catch (e) {
        alert('Invalid JSON: ' + e.message);
        return;
      }
      if (!parsed[activeDynamoPartitionKey]) {
        alert(`Document must contain the partition key "${activeDynamoPartitionKey}"`);
        return;
      }
      try {
        const res = await fetch('/api/aws/dynamodb/items', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ table_name: activeDynamoTable, item: parsed })
        });
        if (res.ok) {
          closeModal('modal-dynamo-item');
          showToast(`Item inserted into ${activeDynamoTable}!`);
          scanDynamoTable(activeDynamoTable, activeDynamoPartitionKey);
        } else {
          showToast('Insert failed');
        }
      } catch (err) {
        showToast(`Insert error: ${err.message}`);
      }
    }

    async function deleteDynamoItem(keyVal) {
      if (!confirm(`Delete item with ${activeDynamoPartitionKey}="${keyVal}"?`)) return;
      try {
        const res = await fetch(`/api/aws/dynamodb/items?table_name=${encodeURIComponent(activeDynamoTable)}&key_name=${encodeURIComponent(activeDynamoPartitionKey)}&key_value=${encodeURIComponent(keyVal)}`, { method: 'DELETE' });
        if (res.ok) {
          showToast('Item deleted.');
          scanDynamoTable(activeDynamoTable, activeDynamoPartitionKey);
        }
      } catch (err) {
        showToast(`Delete failed: ${err.message}`);
      }
    }

    async function insertSampleDynamoItem() {
      if (!activeDynamoTable) return;
      const sample = {};
      sample[activeDynamoPartitionKey] = `prod_${Math.floor(Date.now() / 1000)}`;
      sample['title'] = 'Ultra Gaming Monitor';
      sample['price'] = 349.99;
      sample['in_stock'] = true;
      sample['created_at'] = new Date().toISOString();

      try {
        const res = await fetch('/api/aws/dynamodb/items', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ table_name: activeDynamoTable, item: sample })
        });
        if (res.ok) {
          showToast(`Inserted item into ${activeDynamoTable}!`);
          scanDynamoTable(activeDynamoTable, activeDynamoPartitionKey);
        }
      } catch (err) {
        showToast(`Insert failed: ${err.message}`);
      }
    }

    // -------------------------------------------------------------------------
    // Secrets Manager
    // -------------------------------------------------------------------------
    async function fetchSecrets() {
      const tbody = document.getElementById('secrets-tbody');
      const cardCount = document.getElementById('card-secrets-count');

      try {
        const res = await fetch('/api/aws/secrets');
        const data = await res.json();
        const secrets = data.secrets || [];

        cardCount.innerText = `${secrets.length} Secrets`;

        if (secrets.length === 0) {
          tbody.innerHTML = `<tr><td colspan="3" style="text-align: center; color: var(--text-muted); padding: 20px;">No secrets found. Click "Store New Secret" to add one!</td></tr>`;
          return;
        }

        tbody.innerHTML = secrets.map(s => `
          <tr>
            <td class="mono-cell">${escapeHtml(s.name)}</td>
            <td style="color: var(--text-muted); font-size: 11.5px; font-family: 'JetBrains Mono', monospace;">${escapeHtml(s.arn || '-')}</td>
            <td style="text-align: right;">
              <button class="ctrl-btn ctrl-btn-primary" style="padding: 4px 8px; font-size: 11px;" data-action="view-secret" data-name="${escapeHtml(s.name)}">
                Reveal
              </button>
            </td>
          </tr>
        `).join('');
        tbody.onclick = (e) => {
          const btn = e.target.closest('button[data-action]');
          if (!btn) return;
          if (btn.dataset.action === 'view-secret') viewSecretValue(btn.dataset.name);
        };
      } catch (err) {
        tbody.innerHTML = `<tr><td colspan="3" style="text-align: center; color: #fb7185; padding: 20px;">Error: ${err.message}</td></tr>`;
      }
    }

    function openCreateSecretModal() {
      document.getElementById('new-secret-name').value = '';
      document.getElementById('new-secret-val').value = '';
      document.getElementById('modal-secret').classList.add('active');
    }

    async function submitCreateSecret() {
      const name = document.getElementById('new-secret-name').value.trim();
      const value = document.getElementById('new-secret-val').value.trim();
      if (!name || !value) return;
      try {
        const res = await fetch('/api/aws/secrets', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, value })
        });
        if (res.ok) {
          closeModal('modal-secret');
          showToast(`Secret "${name}" stored!`);
          fetchSecrets();
        }
      } catch (err) {
        showToast(`Save failed: ${err.message}`);
      }
    }

    async function viewSecretValue(name) {
      try {
        const res = await fetch(`/api/aws/secrets/${encodeURIComponent(name)}`);
        const data = await res.json();
        document.getElementById('view-secret-title').innerText = `Secret: ${name}`;
        document.getElementById('view-secret-body').innerText = data.value || '(Empty string)';
        document.getElementById('modal-view-secret').classList.add('active');
      } catch (err) {
        showToast(`Fetch failed: ${err.message}`);
      }
    }

    // -------------------------------------------------------------------------
    // 5. AWS Lambda
    // -------------------------------------------------------------------------
    let currentLambdaFunctions = [];
    let activeInvokeFnName = '';

    async function fetchLambdaFunctions() {
      const tbody = document.getElementById('lambda-functions-tbody');
      const cardCount = document.getElementById('card-lambda-count');
      try {
        const res = await fetch('/api/aws/lambda/functions');
        const data = await res.json();
        const fns = data.functions || [];
        currentLambdaFunctions = fns;
        if (cardCount) cardCount.innerText = `${fns.length} Functions`;

        if (!tbody) return;
        if (fns.length === 0) {
          tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 20px;">No Lambda functions deployed yet. Click "Deploy Sample Function" or "Deploy Custom Lambda"!</td></tr>`;
          return;
        }

        tbody.innerHTML = fns.map(fn => `
          <tr>
            <td class="mono-cell" style="font-weight: 600; color: var(--accent-amber);">${escapeHtml(fn.name)}</td>
            <td><span class="aws-tag" style="background: rgba(245, 158, 11, 0.15); color: #f59e0b;">${escapeHtml(fn.runtime)}</span></td>
            <td class="mono-cell" style="color: #94a3b8;">${escapeHtml(fn.handler)}</td>
            <td>${Math.round(fn.code_size / 1024)} KB</td>
            <td style="color: var(--text-muted); font-size: 11.5px;">${escapeHtml(fn.last_modified ? fn.last_modified.split('.')[0] : '-')}</td>
            <td style="text-align: right; white-space: nowrap;">
              <button class="ctrl-btn ctrl-btn-primary" style="padding: 4px 8px; font-size: 11px; margin-right: 6px;" data-action="invoke-lambda" data-name="${escapeHtml(fn.name)}">
                ⚡ Invoke
              </button>
              <button class="ctrl-btn ctrl-btn-danger" data-action="delete-lambda" data-name="${escapeHtml(fn.name)}">
                Delete
              </button>
            </td>
          </tr>
        `).join('');
        tbody.onclick = (e) => {
          const btn = e.target.closest('button[data-action]');
          if (!btn) return;
          if (btn.dataset.action === 'invoke-lambda') openInvokeLambdaModal(btn.dataset.name);
          else if (btn.dataset.action === 'delete-lambda') deleteLambdaFunction(btn.dataset.name);
        };
      } catch (err) {
        if (tbody) tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: #fb7185; padding: 20px;">Error: ${err.message}</td></tr>`;
      }
    }

    function openCreateLambdaModal() {
      document.getElementById('new-lambda-name').value = '';
      document.getElementById('new-lambda-code').value = 
`def lambda_handler(event, context):
    name = event.get('name', 'World')
    return {
        'statusCode': 200,
        'message': f'Hello, {name} from LocalStack Lambda!',
        'received': event
    }`;
      document.getElementById('modal-create-lambda').classList.add('active');
    }

    async function submitCreateLambda() {
      const name = document.getElementById('new-lambda-name').value.trim();
      const code = document.getElementById('new-lambda-code').value.trim();
      if (!name || !code) return;

      try {
        const res = await fetch('/api/aws/lambda/functions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, code })
        });
        if (res.ok) {
          closeModal('modal-create-lambda');
          showToast(`Lambda function "${name}" deployed!`);
          fetchLambdaFunctions();
        } else {
          const err = await res.json().catch(() => ({}));
          showToast(`Deploy failed: ${err.detail || res.statusText}`);
        }
      } catch (err) {
        showToast(`Deploy error: ${err.message}`);
      }
    }

    async function deploySampleLambda() {
      try {
        const res = await fetch('/api/aws/lambda/functions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: 'sample_calculator',
            code: 
`def lambda_handler(event, context):
    a = float(event.get('a', 10))
    b = float(event.get('b', 5))
    op = event.get('op', 'add')
    result = (a + b) if op == 'add' else (a * b)
    return {'operation': op, 'a': a, 'b': b, 'result': result}`
          })
        });
        if (res.ok) {
          showToast('Sample Lambda "sample_calculator" deployed!');
          fetchLambdaFunctions();
        }
      } catch (err) {
        showToast(`Deploy failed: ${err.message}`);
      }
    }

    function openInvokeLambdaModal(fnName) {
      activeInvokeFnName = fnName;
      document.getElementById('modal-invoke-fn-name').innerText = fnName;
      document.getElementById('invoke-lambda-payload').value = JSON.stringify({ name: "FastAPI Developer", a: 15, b: 3, op: "multiply" }, null, 2);
      document.getElementById('invoke-result-box').style.display = 'none';
      document.getElementById('modal-invoke-lambda').classList.add('active');
    }

    async function submitInvokeLambda() {
      if (!activeInvokeFnName) return;
      const rawPayload = document.getElementById('invoke-lambda-payload').value.trim();
      let parsed;
      try {
        parsed = JSON.parse(rawPayload);
      } catch (e) {
        alert('Invalid JSON payload: ' + e.message);
        return;
      }

      const submitBtn = document.getElementById('btn-invoke-submit');
      submitBtn.innerText = 'Executing...';
      submitBtn.disabled = true;

      try {
        const res = await fetch('/api/aws/lambda/invoke', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: activeInvokeFnName, payload: parsed })
        });
        const data = await res.json();
        document.getElementById('invoke-result-box').style.display = 'block';
        document.getElementById('invoke-result-output').innerText = JSON.stringify(data.result !== undefined ? data.result : data, null, 2);
        showToast(`Executed ${activeInvokeFnName}!`);
      } catch (err) {
        showToast(`Invoke failed: ${err.message}`);
      } finally {
        submitBtn.innerText = '🚀 Execute Function';
        submitBtn.disabled = false;
      }
    }

    async function deleteLambdaFunction(name) {
      if (!confirm(`Permanently delete Lambda function "${name}"?`)) return;
      try {
        const res = await fetch(`/api/aws/lambda/functions?name=${encodeURIComponent(name)}`, { method: 'DELETE' });
        if (res.ok) {
          showToast(`Lambda "${name}" deleted.`);
          fetchLambdaFunctions();
        }
      } catch (err) {
        showToast(`Delete failed: ${err.message}`);
      }
    }

    // -------------------------------------------------------------------------
    // 6. EventBridge
    // -------------------------------------------------------------------------
    async function fetchEventBuses() {
      const tbody = document.getElementById('event-buses-tbody');
      const cardCount = document.getElementById('card-events-count');
      try {
        const res = await fetch('/api/aws/events/buses');
        const data = await res.json();
        const buses = data.buses || [];
        if (cardCount) cardCount.innerText = `${buses.length} Buses`;

        if (!tbody) return;
        tbody.innerHTML = buses.map(b => `
          <tr>
            <td class="mono-cell" style="font-weight: 600; color: #a78bfa;">${escapeHtml(b.name)}</td>
            <td style="font-size: 11.5px; color: var(--text-muted); font-family: 'JetBrains Mono', monospace;">${escapeHtml(b.arn || '-')}</td>
            <td style="text-align: right;">
              <button class="ctrl-btn ctrl-btn-primary" style="padding: 4px 8px; font-size: 11px;" data-action="put-event" data-name="${escapeHtml(b.name)}">
                📨 Send Event
              </button>
            </td>
          </tr>
        `).join('');
        tbody.onclick = (e) => {
          const btn = e.target.closest('button[data-action]');
          if (!btn) return;
          if (btn.dataset.action === 'put-event') openPutEventModal(btn.dataset.name);
        };

        fetchEventRules();
      } catch (err) {
        if (tbody) tbody.innerHTML = `<tr><td colspan="3" style="text-align: center; color: #fb7185; padding: 20px;">Error: ${err.message}</td></tr>`;
      }
    }

    async function fetchEventRules() {
      const tbody = document.getElementById('event-rules-tbody');
      try {
        const res = await fetch('/api/aws/events/rules?event_bus=default');
        const data = await res.json();
        const rules = data.rules || [];

        if (!tbody) return;
        if (rules.length === 0) {
          tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-muted); padding: 18px;">No custom rules on default bus yet.</td></tr>`;
          return;
        }

        tbody.innerHTML = rules.map(r => `
          <tr>
            <td class="mono-cell">${escapeHtml(r.name)}</td>
            <td><span class="aws-tag">${escapeHtml(r.state || 'ENABLED')}</span></td>
            <td class="mono-cell" style="font-size: 11.5px; color: #38bdf8;">${escapeHtml(r.event_pattern || '{}')}</td>
            <td style="font-size: 12.5px; color: var(--text-muted);">${escapeHtml(r.description || '-')}</td>
          </tr>
        `).join('');
      } catch (err) {
        if (tbody) tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: #fb7185; padding: 18px;">Error: ${err.message}</td></tr>`;
      }
    }

    function openPutEventModal(busName = 'default') {
      document.getElementById('modal-put-event').classList.add('active');
    }

    async function submitPutEvent() {
      const source = document.getElementById('event-source').value.trim();
      const detailType = document.getElementById('event-detail-type').value.trim();
      const rawDetail = document.getElementById('event-detail-json').value.trim();
      let detail;
      try {
        detail = JSON.parse(rawDetail);
      } catch (e) {
        alert('Invalid JSON in event detail: ' + e.message);
        return;
      }

      try {
        const res = await fetch('/api/aws/events/put-event', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ source, detail_type: detailType, detail, event_bus_name: 'default' })
        });
        const data = await res.json();
        if (res.ok) {
          closeModal('modal-put-event');
          showToast(`Event published (ID: ${data.event_id || 'sent'})!`);
        } else {
          showToast('Failed to publish event');
        }
      } catch (err) {
        showToast(`Publish error: ${err.message}`);
      }
    }

    // -------------------------------------------------------------------------
    // 7. Amazon Kinesis
    // -------------------------------------------------------------------------
    let activeKinesisStream = '';

    async function fetchKinesisStreams() {
      const tbody = document.getElementById('kinesis-streams-tbody');
      const cardCount = document.getElementById('card-kinesis-count');
      try {
        const res = await fetch('/api/aws/kinesis/streams');
        const data = await res.json();
        const streams = data.streams || [];
        if (cardCount) cardCount.innerText = `${streams.length} Streams`;

        if (!tbody) return;
        if (streams.length === 0) {
          tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-muted); padding: 20px;">No Kinesis streams yet. Click "Create Stream" or "Sample Stream"!</td></tr>`;
          return;
        }

        tbody.innerHTML = streams.map(s => `
          <tr>
            <td class="mono-cell" style="font-weight: 600; color: #38bdf8;">${escapeHtml(s.name)}</td>
            <td><span class="aws-tag" style="background: rgba(52, 211, 153, 0.15); color: #34d399;">${escapeHtml(s.status)}</span></td>
            <td>${s.open_shards} shard${s.open_shards > 1 ? 's' : ''}</td>
            <td style="text-align: right; white-space: nowrap;">
              <button class="ctrl-btn ctrl-btn-primary" style="padding: 4px 8px; font-size: 11px; margin-right: 6px;" data-action="put-kinesis" data-name="${escapeHtml(s.name)}">
                ➕ Put Record
              </button>
              <button class="ctrl-btn" style="padding: 4px 8px; font-size: 11px; margin-right: 6px;" data-action="read-kinesis" data-name="${escapeHtml(s.name)}">
                📖 Read Records
              </button>
              <button class="ctrl-btn ctrl-btn-danger" data-action="delete-kinesis" data-name="${escapeHtml(s.name)}">
                Delete
              </button>
            </td>
          </tr>
        `).join('');
        tbody.onclick = (e) => {
          const btn = e.target.closest('button[data-action]');
          if (!btn) return;
          if (btn.dataset.action === 'put-kinesis') openPutKinesisRecordModal(btn.dataset.name);
          else if (btn.dataset.action === 'read-kinesis') readKinesisRecords(btn.dataset.name);
          else if (btn.dataset.action === 'delete-kinesis') deleteKinesisStream(btn.dataset.name);
        };
      } catch (err) {
        if (tbody) tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: #fb7185; padding: 20px;">Error: ${err.message}</td></tr>`;
      }
    }

    function openCreateKinesisModal() {
      document.getElementById('new-kinesis-name').value = '';
      document.getElementById('new-kinesis-shards').value = '1';
      document.getElementById('modal-create-kinesis').classList.add('active');
    }

    async function submitCreateKinesisStream() {
      const name = document.getElementById('new-kinesis-name').value.trim();
      const shards = parseInt(document.getElementById('new-kinesis-shards').value, 10) || 1;
      if (!name) return;

      try {
        const res = await fetch('/api/aws/kinesis/streams', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ stream_name: name, shard_count: shards })
        });
        if (res.ok) {
          closeModal('modal-create-kinesis');
          showToast(`Kinesis stream "${name}" created!`);
          fetchKinesisStreams();
        } else {
          showToast('Failed to create stream');
        }
      } catch (err) {
        showToast(`Create error: ${err.message}`);
      }
    }

    async function createSampleKinesisStream() {
      try {
        const res = await fetch('/api/aws/kinesis/streams', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ stream_name: 'telemetry_stream', shard_count: 1 })
        });
        if (res.ok) {
          showToast('Sample Kinesis stream "telemetry_stream" created!');
          fetchKinesisStreams();
        }
      } catch (err) {
        showToast(`Create failed: ${err.message}`);
      }
    }

    function openPutKinesisRecordModal(streamName) {
      activeKinesisStream = streamName;
      document.getElementById('modal-kinesis-put-stream').innerText = streamName;
      document.getElementById('modal-kinesis-put').classList.add('active');
    }

    async function submitPutKinesisRecord() {
      if (!activeKinesisStream) return;
      const partKey = document.getElementById('kinesis-put-partkey').value.trim() || 'p1';
      const data = document.getElementById('kinesis-put-data').value.trim();
      if (!data) return;

      try {
        const res = await fetch('/api/aws/kinesis/records', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ stream_name: activeKinesisStream, partition_key: partKey, data })
        });
        if (res.ok) {
          closeModal('modal-kinesis-put');
          showToast(`Record put to ${activeKinesisStream}!`);
          readKinesisRecords(activeKinesisStream);
        } else {
          showToast('Put record failed');
        }
      } catch (err) {
        showToast(`Put error: ${err.message}`);
      }
    }

    async function readKinesisRecords(streamName) {
      activeKinesisStream = streamName;
      document.getElementById('kinesis-selected-stream').innerText = streamName;
      document.getElementById('kinesis-records-container').style.display = 'block';

      const tbody = document.getElementById('kinesis-records-tbody');
      tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-muted); padding: 18px;">Reading records from shard...</td></tr>`;

      try {
        const res = await fetch(`/api/aws/kinesis/records?stream_name=${encodeURIComponent(streamName)}`);
        const data = await res.json();
        const records = data.records || [];

        if (records.length === 0) {
          tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-muted); padding: 18px;">No records found in stream. Click "Put Record"!</td></tr>`;
          return;
        }

        tbody.innerHTML = records.map(r => `
          <tr>
            <td class="mono-cell" style="font-size: 11px;">${escapeHtml(r.sequence_number ? r.sequence_number.slice(-16) : '-')}...</td>
            <td><span class="aws-tag">${escapeHtml(r.partition_key || '-')}</span></td>
            <td style="color: var(--text-muted); font-size: 11.5px;">${escapeHtml(r.approx_arrival || '-')}</td>
            <td class="mono-cell" style="font-size: 12px; color: #38bdf8;">${escapeHtml(r.data)}</td>
          </tr>
        `).join('');
      } catch (err) {
        tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: #fb7185; padding: 18px;">Error: ${err.message}</td></tr>`;
      }
    }

    async function deleteKinesisStream(name) {
      if (!confirm(`Permanently delete Kinesis stream "${name}"?`)) return;
      try {
        const res = await fetch(`/api/aws/kinesis/streams?name=${encodeURIComponent(name)}`, { method: 'DELETE' });
        if (res.ok) {
          showToast(`Stream "${name}" deleted.`);
          if (activeKinesisStream === name) {
            document.getElementById('kinesis-records-container').style.display = 'none';
          }
          fetchKinesisStreams();
        }
      } catch (err) {
        showToast(`Delete failed: ${err.message}`);
      }
    }

