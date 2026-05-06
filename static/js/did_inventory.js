/**
 * DID Inventory module — handles single-account and all-accounts DID listing.
 *
 * Single Account: Synchronous fetch + render.
 * All Accounts:   Starts async job → polls for completion → renders results.
 */

import { apiFetch, state } from './utils.js';
import { displayResponse, handleFetchError } from './ui.js';
import { getAuthPayload } from './credentials.js';


// --- Module State ---
let _pollingInterval = null;
let _allDidsData = [];  // Flat array of all DID rows for CSV export and filtering


// --- Single Account (Synchronous) ---

export async function handleListDidsSingleSubmit(event) {
    event.preventDefault();
    displayResponse('Fetching DIDs for selected account...', 'pending');
    _hideResults();

    try {
        const auth = getAuthPayload('vonage_list_dids_single');
        const searchPatternVal = document.getElementById('vonageListDids_single_search_pattern').value;
        const payload = {
            ...auth,
            country: document.getElementById('vonageListDids_single_country').value || undefined,
            pattern: document.getElementById('vonageListDids_single_pattern').value || undefined,
            search_pattern: searchPatternVal !== '' ? searchPatternVal : undefined
        };

        const response = await apiFetch('/api/vonage/dids/inventory/single', {
            method: 'POST',
            body: JSON.stringify(payload)
        });

        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to fetch DIDs.');

        // Wrap in the multi-account results format for unified rendering
        const wrappedResults = {
            accounts_queried: 1,
            accounts_succeeded: 1,
            accounts_failed: 0,
            total_dids: data.total_count,
            results: [{
                account_name: data.account_name,
                api_key_hint: data.api_key_hint,
                did_count: data.total_count,
                numbers: data.numbers
            }],
            errors: []
        };

        _renderResults(wrappedResults);
        displayResponse(`Found ${data.total_count} DID(s) for ${data.account_name}.`, 'success');

    } catch (error) {
        handleFetchError(error, 'List DIDs (Single)');
    }
}


// --- All Accounts (Async Job) ---

export async function handleListDidsAllSubmit(event) {
    event.preventDefault();

    if (!state.masterKey) {
        displayResponse("Master Key is not set. Please set it in 'Credential Management' first.", 'error');
        return;
    }

    _hideResults();
    _showProgress('Starting inventory job...', 0);

    const startBtn = document.getElementById('vonageListDidsAllStartBtn');
    if (startBtn) startBtn.disabled = true;

    try {
        const searchPatternVal = document.getElementById('vonageListDids_all_search_pattern').value;
        const payload = {
            master_key: state.masterKey,
            country: document.getElementById('vonageListDids_all_country').value || undefined,
            pattern: document.getElementById('vonageListDids_all_pattern').value || undefined,
            search_pattern: searchPatternVal !== '' ? searchPatternVal : undefined
        };

        const response = await apiFetch('/api/vonage/dids/inventory/start', {
            method: 'POST',
            body: JSON.stringify(payload)
        });

        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to start inventory job.');

        displayResponse(`Inventory job started. Querying ${data.accounts_total} account(s)...`, 'pending');
        _startPolling(data.job_id, data.accounts_total);

    } catch (error) {
        _hideProgress();
        if (startBtn) startBtn.disabled = false;
        handleFetchError(error, 'Start Inventory');
    }
}


function _startPolling(jobId, accountsTotal) {
    _stopPolling();

    _pollingInterval = setInterval(async () => {
        try {
            const response = await apiFetch(`/api/vonage/dids/inventory/status/${jobId}`);
            const data = await response.json();

            if (!response.ok) {
                _stopPolling();
                _hideProgress();
                _enableStartBtn();
                displayResponse(`Error polling job: ${data.error || 'Unknown error'}`, 'error');
                return;
            }

            const completed = data.accounts_completed || 0;
            const total = data.accounts_total || accountsTotal;
            const pct = total > 0 ? Math.round((completed / total) * 100) : 0;

            if (data.status === 'running' || data.status === 'pending') {
                _showProgress(data.progress || `${completed}/${total} accounts...`, pct);
            } else if (data.status === 'completed') {
                _stopPolling();
                _hideProgress();
                _enableStartBtn();
                _renderResults(data.results);
                displayResponse(
                    `Inventory complete. ${data.results.total_dids} DID(s) found across ${data.results.accounts_succeeded} account(s).`,
                    data.results.accounts_failed > 0 ? 'error' : 'success'
                );
            } else if (data.status === 'failed') {
                _stopPolling();
                _hideProgress();
                _enableStartBtn();
                displayResponse(`Inventory job failed: ${data.error || 'Unknown error'}`, 'error');
            }

        } catch (error) {
            _stopPolling();
            _hideProgress();
            _enableStartBtn();
            console.error('Polling error:', error);
            displayResponse('Lost connection while polling job status.', 'error');
        }
    }, 2000);
}

function _stopPolling() {
    if (_pollingInterval) {
        clearInterval(_pollingInterval);
        _pollingInterval = null;
    }
}

function _enableStartBtn() {
    const btn = document.getElementById('vonageListDidsAllStartBtn');
    if (btn) btn.disabled = false;
}


// --- Results Rendering ---

function _renderResults(data) {
    const resultsArea = document.getElementById('vonageListDids_resultsArea');
    const summaryEl = document.getElementById('vonageListDids_summary');
    const tbody = document.getElementById('vonageListDids_tableBody');
    const statusEl = document.getElementById('vonageListDids_tableStatus');

    // Build summary cards
    summaryEl.innerHTML = '';
    summaryEl.appendChild(_createSummaryCard(data.total_dids, 'Total DIDs', 'card-info'));
    summaryEl.appendChild(_createSummaryCard(data.accounts_succeeded, 'Accounts Queried', 'card-success'));
    if (data.accounts_failed > 0) {
        summaryEl.appendChild(_createSummaryCard(data.accounts_failed, 'Accounts Failed', 'card-error'));
    }

    // Flatten all numbers into a single array for table + CSV
    _allDidsData = [];
    (data.results || []).forEach(acct => {
        (acct.numbers || []).forEach(num => {
            _allDidsData.push({
                msisdn: num.msisdn || '',
                country: num.country || '',
                type: num.type || '',
                features: Array.isArray(num.features) ? num.features.join(', ') : (num.features || ''),
                voiceCallbackType: num.voiceCallbackType || '',
                voiceCallbackValue: num.voiceCallbackValue || '',
                account_name: acct.account_name || ''
            });
        });
    });

    _renderTableRows(_allDidsData, tbody);
    statusEl.textContent = `Showing ${_allDidsData.length} DID(s)`;

    // Show errors if any
    if (data.errors && data.errors.length > 0) {
        const errorList = data.errors.map(e => `${e.account_name}: ${e.error}`).join('\n');
        statusEl.textContent += ` | ${data.errors.length} account(s) failed. Check response area for details.`;
        console.warn('Inventory errors:', errorList);
    }

    resultsArea.style.display = 'block';
}

function _renderTableRows(rows, tbody) {
    tbody.innerHTML = '';
    if (rows.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;">No DIDs found.</td></tr>';
        return;
    }

    rows.forEach(row => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${_escapeHtml(row.msisdn)}</td>
            <td>${_escapeHtml(row.country)}</td>
            <td>${_escapeHtml(row.type)}</td>
            <td>${_escapeHtml(row.features)}</td>
            <td>${_escapeHtml(row.voiceCallbackType)}</td>
            <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${_escapeAttr(row.voiceCallbackValue)}">${_escapeHtml(row.voiceCallbackValue)}</td>
            <td>${_escapeHtml(row.account_name)}</td>
        `;
        tbody.appendChild(tr);
    });
}

function _createSummaryCard(value, label, cssClass) {
    const card = document.createElement('div');
    card.className = `did-summary-card ${cssClass}`;
    card.innerHTML = `
        <div class="card-value">${value}</div>
        <div class="card-label">${label}</div>
    `;
    return card;
}


// --- CSV Export ---

export function handleExportDidInventoryCsv() {
    if (_allDidsData.length === 0) {
        displayResponse('No data to export.', 'error');
        return;
    }

    const headers = ['DID', 'Country', 'Type', 'Features', 'Callback Type', 'Callback Value', 'Account'];
    const csvRows = [headers.join(',')];

    _allDidsData.forEach(row => {
        csvRows.push([
            _csvSafe(row.msisdn),
            _csvSafe(row.country),
            _csvSafe(row.type),
            _csvSafe(row.features),
            _csvSafe(row.voiceCallbackType),
            _csvSafe(row.voiceCallbackValue),
            _csvSafe(row.account_name)
        ].join(','));
    });

    const blob = new Blob([csvRows.join('\n')], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `did_inventory_${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);

    displayResponse(`Exported ${_allDidsData.length} DID(s) to CSV.`, 'success');
}


// --- Table Filtering ---

export function handleTableFilter(event) {
    const filter = event.target.value.toLowerCase();
    const tbody = document.getElementById('vonageListDids_tableBody');
    const statusEl = document.getElementById('vonageListDids_tableStatus');

    if (!filter) {
        _renderTableRows(_allDidsData, tbody);
        statusEl.textContent = `Showing ${_allDidsData.length} DID(s)`;
        return;
    }

    const filtered = _allDidsData.filter(row =>
        row.msisdn.toLowerCase().includes(filter) ||
        row.country.toLowerCase().includes(filter) ||
        row.type.toLowerCase().includes(filter) ||
        row.features.toLowerCase().includes(filter) ||
        row.account_name.toLowerCase().includes(filter) ||
        row.voiceCallbackValue.toLowerCase().includes(filter)
    );

    _renderTableRows(filtered, tbody);
    statusEl.textContent = `Showing ${filtered.length} of ${_allDidsData.length} DID(s)`;
}


// --- Table Sorting ---

let _currentSortKey = null;
let _currentSortAsc = true;

export function handleTableSort(event) {
    const th = event.target.closest('th[data-sort]');
    if (!th) return;

    const key = th.dataset.sort;
    if (_currentSortKey === key) {
        _currentSortAsc = !_currentSortAsc;
    } else {
        _currentSortKey = key;
        _currentSortAsc = true;
    }

    // Sort the master data in place so filter + sort work together
    _allDidsData.sort((a, b) => {
        const va = (a[key] || '').toLowerCase();
        const vb = (b[key] || '').toLowerCase();
        if (va < vb) return _currentSortAsc ? -1 : 1;
        if (va > vb) return _currentSortAsc ? 1 : -1;
        return 0;
    });

    // Update header indicators
    document.querySelectorAll('#vonageListDids_table th[data-sort]').forEach(h => {
        const arrow = h.dataset.sort === key ? (_currentSortAsc ? ' ▴' : ' ▾') : ' ▿';
        h.textContent = h.textContent.replace(/\s[▴▾▿]$/, '') + arrow;
    });

    // Re-apply current filter (if any) on the now-sorted data
    const filterEl = document.getElementById('vonageListDids_tableFilter');
    if (filterEl && filterEl.value) {
        filterEl.dispatchEvent(new Event('keyup'));
    } else {
        const tbody = document.getElementById('vonageListDids_tableBody');
        _renderTableRows(_allDidsData, tbody);
    }
}


// --- UI Helpers ---

function _showProgress(text, pct) {
    const area = document.getElementById('vonageListDids_progressArea');
    const textEl = document.getElementById('vonageListDids_progressText');
    const barEl = document.getElementById('vonageListDids_progressBar');
    area.style.display = 'block';
    textEl.textContent = text;
    barEl.style.width = `${pct}%`;
}

function _hideProgress() {
    document.getElementById('vonageListDids_progressArea').style.display = 'none';
}

function _hideResults() {
    document.getElementById('vonageListDids_resultsArea').style.display = 'none';
    _allDidsData = [];
}

function _escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function _escapeAttr(str) {
    return _escapeHtml(str).replace(/"/g, '&quot;');
}

function _csvSafe(val) {
    const s = String(val || '');
    if (s.includes(',') || s.includes('"') || s.includes('\n')) {
        return '"' + s.replace(/"/g, '""') + '"';
    }
    return s;
}
