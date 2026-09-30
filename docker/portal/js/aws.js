    // Shared helpers for the AWS console
    // -------------------------------------------------------------------------
    function jsonRequest(method, payload) {
      return {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      };
    }

    function errorRow(colspan, message, padding = 20) {
      return `<tr><td colspan="${colspan}" style="text-align: center; color: #fb7185; padding: ${padding}px;">Error: ${escapeHtml(String(message))}</td></tr>`;
    }

    // -------------------------------------------------------------------------
    // LocalStack AWS Engine Status
    // -------------------------------------------------------------------------
    async function refreshAwsStatus() {
      const indicator = document.getElementById('aws-health-indicator');
      try {
        const data = await apiFetch('/api/aws/status');
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
        if (indicator) {
          indicator.innerText = 'UNREACHABLE';
          indicator.style.color = 'var(--accent-rose)';
        }
      }
    }

    // -------------------------------------------------------------------------
    // S3 Object Explorer
    // -------------------------------------------------------------------------
    async function fetchS3Objects() {
      const tbody = document.getElementById('s3-files-tbody');
      try {
        const data = await apiFetch('/api/s3/objects');
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
        tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: #fb7185; padding: 20px;">Could not connect to S3: ${escapeHtml(err.message)}</td></tr>`;
      }
    }

    async function handleRealFileUpload(event) {
      const file = event.target.files[0];
      if (!file) return;

      showToast(`Uploading "${file.name}" to S3...`);
      try {
        await apiFetch(`/api/s3/upload?filename=${encodeURIComponent(file.name)}`, {
          method: 'POST',
          headers: {
            'Content-Type': file.type || 'application/octet-stream'
          },
          body: file
        });
        showToast(`Uploaded "${file.name}" (${formatBytes(file.size)}) to S3!`);
        fetchS3Objects();
      } catch (err) {
        showToast(`Upload failed: ${err.message}`);
      } finally {
        event.target.value = '';
      }
    }

    async function uploadSampleFile() {
      const filename = `doc_${Math.floor(Date.now() / 1000)}.txt`;
      try {
        await apiFetch(`/api/s3/upload-sample?filename=${encodeURIComponent(filename)}`, { method: 'POST' });
        showToast(`Uploaded sample "${filename}" to S3!`);
        fetchS3Objects();
      } catch (err) {
        showToast(`Upload failed: ${err.message}`);
      }
    }

    async function deleteS3File(key) {
      if (!confirm(`Delete "${key}" from LocalStack S3?`)) return;
      try {
        await apiFetch(`/api/s3/file?key=${encodeURIComponent(key)}`, { method: 'DELETE' });
        showToast(`Deleted "${key}"`);
        fetchS3Objects();
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
        const data = await apiFetch('/api/aws/sqs/queues');
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
        if (cardCount) cardCount.innerText = 'Unavailable';
        tbody.innerHTML = errorRow(4, err.message);
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
        await apiFetch('/api/aws/sqs/queues', jsonRequest('POST', { name }));
        closeModal('modal-queue');
        showToast(`Queue "${name}" created!`);
        fetchSQSQueues();
      } catch (err) {
        showToast(`Create queue failed: ${err.message}`);
      }
    }

    async function sendSQSTestMessage() {
      const q = document.getElementById('sqs-send-queue-select').value;
      const body = document.getElementById('sqs-send-body').value.trim();
      if (!q || !body) return;
      try {
        await apiFetch('/api/aws/sqs/messages', jsonRequest('POST', { queue_name: q, message_body: body }));
        showToast(`Message enqueued to ${q}!`);
        fetchSQSQueues();
      } catch (err) {
        showToast(`Send failed: ${err.message}`);
      }
    }

    async function readSQSMessages(qName) {
      try {
        const data = await apiFetch(`/api/aws/sqs/messages?queue_name=${encodeURIComponent(qName)}`);
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
        await apiFetch(`/api/aws/sqs/queues?queue_name=${encodeURIComponent(qName)}`, { method: 'DELETE' });
        showToast(`Queue "${qName}" purged.`);
        fetchSQSQueues();
      } catch (err) {
        showToast(`Purge failed: ${err.message}`);
      }
    }

    // -------------------------------------------------------------------------
    // DynamoDB Tables & Items
    // -------------------------------------------------------------------------
    let activeDynamoTable = '';
    let activeDynamoPartitionKey = 'id';
    // Only the latest scan may render; starting a new one aborts the previous.
    let dynamoScanController = null;

    async function fetchDynamoTables() {
      const tbody = document.getElementById('dynamo-tables-tbody');
      const cardCount = document.getElementById('card-dynamo-count');

      try {
        const data = await apiFetch('/api/aws/dynamodb/tables');
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
        if (cardCount) cardCount.innerText = 'Unavailable';
        tbody.innerHTML = errorRow(5, err.message);
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
        await apiFetch('/api/aws/dynamodb/tables', jsonRequest('POST', { table_name: tableName, key_name: keyName }));
        closeModal('modal-dynamo-table');
        showToast(`DynamoDB table "${tableName}" created!`);
        fetchDynamoTables();
      } catch (err) {
        showToast(`Create table failed: ${err.message}`);
      }
    }

    async function deleteDynamoTable(tName) {
      if (!confirm(`Permanently delete DynamoDB table "${tName}"?`)) return;
      try {
        await apiFetch(`/api/aws/dynamodb/tables?table_name=${encodeURIComponent(tName)}`, { method: 'DELETE' });
        showToast(`Table "${tName}" deleted.`);
        if (activeDynamoTable === tName) {
          if (dynamoScanController) dynamoScanController.abort();
          dynamoScanController = null;
          activeDynamoTable = '';
          document.getElementById('dynamo-items-container').style.display = 'none';
        }
        fetchDynamoTables();
      } catch (err) {
        showToast(`Delete failed: ${err.message}`);
      }
    }

    async function createSampleDynamoTable() {
      try {
        await apiFetch('/api/aws/dynamodb/tables', jsonRequest('POST', { table_name: 'products', key_name: 'id' }));
        showToast('DynamoDB table "products" ready!');
        fetchDynamoTables();
      } catch (err) {
        showToast(`Table creation failed: ${err.message}`);
      }
    }

    async function scanDynamoTable(tName, partitionKey = 'id') {
      if (dynamoScanController) dynamoScanController.abort();
      const controller = new AbortController();
      dynamoScanController = controller;
      activeDynamoTable = tName;
      activeDynamoPartitionKey = partitionKey;
      document.getElementById('dynamo-selected-table').innerText = `${tName} (Key: ${partitionKey})`;
      document.getElementById('dynamo-items-container').style.display = 'block';

      const tbody = document.getElementById('dynamo-records-tbody');
      tbody.innerHTML = `<tr><td colspan="3" style="text-align: center; color: var(--text-muted); padding: 18px;">Scanning table...</td></tr>`;

      try {
        const data = await apiFetch(
          `/api/aws/dynamodb/items?table_name=${encodeURIComponent(tName)}`,
          { signal: controller.signal }
        );
        if (controller !== dynamoScanController) return;  // superseded by a newer scan
        const items = data.items || [];

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

          // Each row carries its own table/key so Edit/Delete never depend on
          // whichever table happens to be selected when the button is clicked.
          return `
            <tr data-table="${escapeHtml(tName)}" data-key-name="${escapeHtml(partitionKey)}" data-key-value="${escapeHtml(String(keyVal))}" data-idx="${idx}">
              <td class="mono-cell">${escapeHtml(String(keyVal))}</td>
              <td style="font-size: 12.5px;">${otherAttrs || '(No additional attributes)'}</td>
              <td style="text-align: right; white-space: nowrap;">
                <button class="ctrl-btn" style="padding: 4px 8px; font-size: 11px; margin-right: 6px; background: rgba(56, 189, 248, 0.15); border-color: rgba(56, 189, 248, 0.3); color: #38bdf8;" data-action="edit-dynamo-item">
                  ✏️ Edit
                </button>
                <button class="ctrl-btn ctrl-btn-danger" data-action="delete-dynamo-item">
                  Delete
                </button>
              </td>
            </tr>
          `;
        }).join('');
        tbody.onclick = (e) => {
          const btn = e.target.closest('button[data-action]');
          if (!btn) return;
          const row = btn.closest('tr');
          if (!row) return;
          const { table, keyName, keyValue, idx } = row.dataset;
          if (btn.dataset.action === 'edit-dynamo-item') {
            const item = items[Number(idx)];
            if (item) openEditDynamoItemModal(table, keyName, keyValue, item);
          } else if (btn.dataset.action === 'delete-dynamo-item') {
            deleteDynamoItem(table, keyName, keyValue);
          }
        };
      } catch (err) {
        if (isAbortError(err) || controller !== dynamoScanController) return;
        tbody.innerHTML = errorRow(3, err.message, 18);
        document.getElementById('dynamo-items-json').innerText = `Error: ${err.message}`;
      }
    }

    function openEditDynamoItemModal(tableName, keyName, keyValue, item) {
      const modal = document.getElementById('modal-edit-dynamo-item');
      modal.dataset.table = tableName;
      modal.dataset.keyName = keyName;

      document.getElementById('modal-edit-table-name').innerText = tableName;
      document.getElementById('modal-edit-key-name').innerText = keyName;
      document.getElementById('modal-edit-key-value').innerText = keyValue;
      document.getElementById('edit-dynamo-item-json').value = JSON.stringify(item, null, 2);
      modal.classList.add('active');
    }

    // Re-scan a table only if it is still the one on screen.
    function rescanIfActive(tableName, keyName) {
      if (activeDynamoTable === tableName) scanDynamoTable(tableName, keyName);
    }

    async function submitEditDynamoItem() {
      const modal = document.getElementById('modal-edit-dynamo-item');
      const tableName = modal.dataset.table;
      const keyName = modal.dataset.keyName;
      if (!tableName || !keyName) return;
      const rawJson = document.getElementById('edit-dynamo-item-json').value.trim();
      let parsed;
      try {
        parsed = JSON.parse(rawJson);
      } catch (e) {
        alert('Invalid JSON: ' + e.message);
        return;
      }
      if (parsed[keyName] === undefined) {
        alert(`Document must contain the partition key "${keyName}"`);
        return;
      }
      try {
        await apiFetch('/api/aws/dynamodb/items', jsonRequest('PUT', { table_name: tableName, item: parsed }));
        closeModal('modal-edit-dynamo-item');
        showToast(`Item updated in ${tableName}!`);
        rescanIfActive(tableName, keyName);
      } catch (err) {
        showToast(`Update failed: ${err.message}`);
      }
    }

    function openInsertDynamoItemModal() {
      if (!activeDynamoTable) return;
      const modal = document.getElementById('modal-dynamo-item');
      modal.dataset.table = activeDynamoTable;
      modal.dataset.keyName = activeDynamoPartitionKey;
      document.getElementById('modal-item-table-name').innerText = activeDynamoTable;
      document.getElementById('modal-item-key-label').innerText = activeDynamoPartitionKey;
      const template = {};
      template[activeDynamoPartitionKey] = `${activeDynamoTable.slice(0, 4)}_${Math.floor(Date.now() / 1000)}`;
      template["name"] = "Sample Record";
      template["created_at"] = new Date().toISOString();
      document.getElementById('new-dynamo-item-json').value = JSON.stringify(template, null, 2);
      modal.classList.add('active');
    }

    async function submitInsertDynamoItem() {
      const modal = document.getElementById('modal-dynamo-item');
      const tableName = modal.dataset.table;
      const keyName = modal.dataset.keyName;
      if (!tableName || !keyName) return;
      const rawJson = document.getElementById('new-dynamo-item-json').value.trim();
      let parsed;
      try {
        parsed = JSON.parse(rawJson);
      } catch (e) {
        alert('Invalid JSON: ' + e.message);
        return;
      }
      if (!parsed[keyName]) {
        alert(`Document must contain the partition key "${keyName}"`);
        return;
      }
      try {
        await apiFetch('/api/aws/dynamodb/items', jsonRequest('POST', { table_name: tableName, item: parsed }));
        closeModal('modal-dynamo-item');
        showToast(`Item inserted into ${tableName}!`);
        rescanIfActive(tableName, keyName);
      } catch (err) {
        showToast(`Insert failed: ${err.message}`);
      }
    }

    async function deleteDynamoItem(tableName, keyName, keyVal) {
      if (!confirm(`Delete item with ${keyName}="${keyVal}" from "${tableName}"?`)) return;
      try {
        await apiFetch(`/api/aws/dynamodb/items?table_name=${encodeURIComponent(tableName)}&key_name=${encodeURIComponent(keyName)}&key_value=${encodeURIComponent(keyVal)}`, { method: 'DELETE' });
        showToast('Item deleted.');
        rescanIfActive(tableName, keyName);
      } catch (err) {
        showToast(`Delete failed: ${err.message}`);
      }
    }

    async function insertSampleDynamoItem() {
      if (!activeDynamoTable) return;
      const tableName = activeDynamoTable;
      const keyName = activeDynamoPartitionKey;
      const sample = {};
      sample[keyName] = `prod_${Math.floor(Date.now() / 1000)}`;
      sample['title'] = 'Ultra Gaming Monitor';
      sample['price'] = 349.99;
      sample['in_stock'] = true;
      sample['created_at'] = new Date().toISOString();

      try {
        await apiFetch('/api/aws/dynamodb/items', jsonRequest('POST', { table_name: tableName, item: sample }));
        showToast(`Inserted item into ${tableName}!`);
        rescanIfActive(tableName, keyName);
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
        const data = await apiFetch('/api/aws/secrets');
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
        if (cardCount) cardCount.innerText = 'Unavailable';
        tbody.innerHTML = errorRow(3, err.message);
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
        await apiFetch('/api/aws/secrets', jsonRequest('POST', { name, value }));
        closeModal('modal-secret');
        showToast(`Secret "${name}" stored!`);
        fetchSecrets();
      } catch (err) {
        showToast(`Save failed: ${err.message}`);
      }
    }

    async function viewSecretValue(name) {
      try {
        const data = await apiFetch(`/api/aws/secrets/${encodeURIComponent(name)}`);
        document.getElementById('view-secret-title').innerText = `Secret: ${name}`;
        document.getElementById('view-secret-body').innerText = data.value || '(Empty string)';
        document.getElementById('modal-view-secret').classList.add('active');
      } catch (err) {
        showToast(`Fetch secret failed: ${err.message}`);
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
        const data = await apiFetch('/api/aws/lambda/functions');
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
        if (cardCount) cardCount.innerText = 'Unavailable';
        if (tbody) tbody.innerHTML = errorRow(6, err.message);
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
        const data = await apiFetch('/api/aws/lambda/functions', jsonRequest('POST', { name, code }));
        closeModal('modal-create-lambda');
        showToast(`Lambda function "${name}" ${data.status === 'updated' ? 'updated' : 'deployed'}!`);
        fetchLambdaFunctions();
      } catch (err) {
        showToast(`Deploy failed: ${err.message}`);
      }
    }

    async function deploySampleLambda() {
      try {
        await apiFetch('/api/aws/lambda/functions', jsonRequest('POST', {
          name: 'sample_calculator',
          code:
`def lambda_handler(event, context):
    a = float(event.get('a', 10))
    b = float(event.get('b', 5))
    op = event.get('op', 'add')
    result = (a + b) if op == 'add' else (a * b)
    return {'operation': op, 'a': a, 'b': b, 'result': result}`
        }));
        showToast('Sample Lambda "sample_calculator" deployed!');
        fetchLambdaFunctions();
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
      const fnName = activeInvokeFnName;
      const rawPayload = document.getElementById('invoke-lambda-payload').value.trim();
      let parsed;
      try {
        parsed = JSON.parse(rawPayload);
      } catch (e) {
        alert('Invalid JSON payload: ' + e.message);
        return;
      }

      const submitBtn = document.getElementById('btn-invoke-submit');
      const output = document.getElementById('invoke-result-output');
      const resultBox = document.getElementById('invoke-result-box');
      submitBtn.innerText = 'Executing...';
      submitBtn.disabled = true;

      try {
        const data = await apiFetch('/api/aws/lambda/invoke', jsonRequest('POST', { name: fnName, payload: parsed }));
        resultBox.style.display = 'block';
        output.innerText = JSON.stringify(data.result !== undefined ? data.result : data, null, 2);
        // executed === false means the handler raised; result holds the error payload.
        const failed = data.executed === false;
        output.style.color = failed ? '#fb7185' : '#34d399';
        if (failed) {
          showToast(`${fnName} raised an error (${data.error || 'FunctionError'})`);
        } else {
          showToast(`Executed ${fnName}!`);
        }
      } catch (err) {
        resultBox.style.display = 'block';
        output.innerText = `Invoke failed: ${err.message}`;
        output.style.color = '#fb7185';
        showToast(`Invoke failed: ${err.message}`);
      } finally {
        submitBtn.innerText = '🚀 Execute Function';
        submitBtn.disabled = false;
      }
    }

    async function deleteLambdaFunction(name) {
      if (!confirm(`Permanently delete Lambda function "${name}"?`)) return;
      try {
        await apiFetch(`/api/aws/lambda/functions?name=${encodeURIComponent(name)}`, { method: 'DELETE' });
        showToast(`Lambda "${name}" deleted.`);
        fetchLambdaFunctions();
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
        const data = await apiFetch('/api/aws/events/buses');
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
        if (cardCount) cardCount.innerText = 'Unavailable';
        if (tbody) tbody.innerHTML = errorRow(3, err.message);
      }
    }

    async function fetchEventRules() {
      const tbody = document.getElementById('event-rules-tbody');
      try {
        const data = await apiFetch('/api/aws/events/rules?event_bus=default');
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
        if (tbody) tbody.innerHTML = errorRow(4, err.message, 18);
      }
    }

    function openPutEventModal(busName = 'default') {
      const modal = document.getElementById('modal-put-event');
      modal.dataset.bus = busName || 'default';
      const busLabel = document.getElementById('modal-put-event-bus');
      if (busLabel) busLabel.innerText = modal.dataset.bus;
      modal.classList.add('active');
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

      const busName = document.getElementById('modal-put-event').dataset.bus || 'default';
      try {
        const data = await apiFetch('/api/aws/events/put-event', jsonRequest('POST', {
          source, detail_type: detailType, detail, event_bus_name: busName
        }));
        closeModal('modal-put-event');
        showToast(`Event published to ${busName} (ID: ${data.event_id || 'sent'})!`);
      } catch (err) {
        showToast(`Publish failed: ${err.message}`);
      }
    }

    // -------------------------------------------------------------------------
    // 7. Amazon Kinesis
    // -------------------------------------------------------------------------
    let activeKinesisStream = '';
    // Only the latest read may render; starting a new one aborts the previous.
    let kinesisReadController = null;

    async function fetchKinesisStreams() {
      const tbody = document.getElementById('kinesis-streams-tbody');
      const cardCount = document.getElementById('card-kinesis-count');
      try {
        const data = await apiFetch('/api/aws/kinesis/streams');
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
        if (cardCount) cardCount.innerText = 'Unavailable';
        if (tbody) tbody.innerHTML = errorRow(4, err.message);
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
        await apiFetch('/api/aws/kinesis/streams', jsonRequest('POST', { stream_name: name, shard_count: shards }));
        closeModal('modal-create-kinesis');
        showToast(`Kinesis stream "${name}" created!`);
        fetchKinesisStreams();
      } catch (err) {
        showToast(`Create stream failed: ${err.message}`);
      }
    }

    async function createSampleKinesisStream() {
      try {
        await apiFetch('/api/aws/kinesis/streams', jsonRequest('POST', { stream_name: 'telemetry_stream', shard_count: 1 }));
        showToast('Sample Kinesis stream "telemetry_stream" created!');
        fetchKinesisStreams();
      } catch (err) {
        showToast(`Create stream failed: ${err.message}`);
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
        await apiFetch('/api/aws/kinesis/records', jsonRequest('POST', {
          stream_name: activeKinesisStream, partition_key: partKey, data
        }));
        closeModal('modal-kinesis-put');
        showToast(`Record put to ${activeKinesisStream}!`);
        readKinesisRecords(activeKinesisStream);
      } catch (err) {
        showToast(`Put record failed: ${err.message}`);
      }
    }

    async function readKinesisRecords(streamName) {
      if (kinesisReadController) kinesisReadController.abort();
      const controller = new AbortController();
      kinesisReadController = controller;
      activeKinesisStream = streamName;
      document.getElementById('kinesis-selected-stream').innerText = streamName;
      document.getElementById('kinesis-records-container').style.display = 'block';

      const tbody = document.getElementById('kinesis-records-tbody');
      tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-muted); padding: 18px;">Reading records from shard...</td></tr>`;

      try {
        const data = await apiFetch(
          `/api/aws/kinesis/records?stream_name=${encodeURIComponent(streamName)}`,
          { signal: controller.signal }
        );
        if (controller !== kinesisReadController) return;  // superseded by a newer read
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
        if (isAbortError(err) || controller !== kinesisReadController) return;
        tbody.innerHTML = errorRow(4, err.message, 18);
      }
    }

    async function deleteKinesisStream(name) {
      if (!confirm(`Permanently delete Kinesis stream "${name}"?`)) return;
      try {
        await apiFetch(`/api/aws/kinesis/streams?name=${encodeURIComponent(name)}`, { method: 'DELETE' });
        showToast(`Stream "${name}" deleted.`);
        if (activeKinesisStream === name) {
          if (kinesisReadController) kinesisReadController.abort();
          kinesisReadController = null;
          activeKinesisStream = '';
          document.getElementById('kinesis-records-container').style.display = 'none';
        }
        fetchKinesisStreams();
      } catch (err) {
        showToast(`Delete failed: ${err.message}`);
      }
    }

