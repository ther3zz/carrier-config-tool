// --- START OF FILE static/js/vonage.js ---
import { apiFetch, state, processInBatches, formatMsisdnForApi, getNationalNumber } from './utils.js';
import { displayResponse, handleFetchError, handleBackendResponse, addOrUpdateOperationStatus, toggleOperationControls } from './ui.js';
import { getAuthPayload } from './credentials.js';

// --- SUBACCOUNT MANAGEMENT ---

export async function handleFetchSubaccounts(event) {
    event.preventDefault();
    displayResponse('Fetching subaccounts...', 'pending');
    const listContainer = document.getElementById('vonage-subaccount-list-container');
    const listEl = document.getElementById('vonage-subaccount-list');
    listEl.innerHTML = '';
    try {
        const auth = getAuthPayload('vonage_manage_subaccounts');
        const response = await apiFetch('/api/vonage/subaccounts', {
            method: 'POST',
            body: JSON.stringify(auth)
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to fetch subaccounts');
        state.vonageSubaccounts = data.subaccounts || [];
        displayResponse(`Successfully fetched ${state.vonageSubaccounts.length} subaccounts.`, 'success');
        renderSubaccounts();
        listContainer.style.display = state.vonageSubaccounts.length > 0 ? 'block' : 'none';
    } catch (error) {
        handleFetchError(error, 'Fetch Subaccounts');
    }
}

export async function handleCreateSubaccount(event) {
    event.preventDefault();
    displayResponse('Creating new subaccount...', 'pending');
    try {
        const auth = getAuthPayload('vonage_create_subaccount');
        const payload = {
            ...auth,
            name: document.getElementById('vonage_new_subaccount_name').value,
            secret: document.getElementById('vonage_new_subaccount_secret').value,
            use_primary_balance: document.getElementById('vonage_new_subaccount_use_primary_balance').checked
        };
        const response = await apiFetch('/api/vonage/subaccounts/create', {
            method: 'POST',
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to create subaccount');
        handleBackendResponse(data);
        document.getElementById('vonageCreateSubaccountForm').reset();
    } catch (error) {
        handleFetchError(error, 'Create Subaccount');
    }
}

export async function handleSubaccountActions(event) {
    const target = event.target;
    if (target.classList.contains('save-subaccount-changes-btn')) {
        event.preventDefault();
        const form = target.closest('.vonage-subaccount-form');
        const apiKey = form.querySelector('.subaccount-api-key').value;
        const payload = {
            ...getAuthPayload('vonage_manage_subaccounts'),
            subaccount_key: apiKey,
            name: form.querySelector('.subaccount-name').value,
            suspended: form.querySelector('.suspended').checked
        };
        displayResponse(`Updating subaccount ${apiKey}...`, 'pending');
        try {
            const response = await apiFetch('/api/vonage/subaccounts/update', {
                method: 'POST',
                body: JSON.stringify(payload)
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Failed to update');
            handleBackendResponse(data);
            // Refresh the list after update
            document.getElementById('vonageFetchSubaccountsForm').requestSubmit();
        } catch (error) {
            handleFetchError(error, 'Update Subaccount');
        }
    } else if (target.classList.contains('cancel-subaccount-edit-btn')) {
        event.preventDefault();
        target.closest('details').open = false;
        // Re-render to discard changes, simple approach
        renderSubaccounts();
    }
}

function renderSubaccounts() {
    const container = document.getElementById('vonage-subaccount-list');
    const template = document.getElementById('vonage-subaccount-template');
    container.innerHTML = '';

    if (!state.vonageSubaccounts || state.vonageSubaccounts.length === 0) {
        container.innerHTML = '<p>No subaccounts found.</p>';
        return;
    }

    state.vonageSubaccounts.forEach(acc => {
        const clone = template.content.cloneNode(true);
        clone.querySelector('.subaccount-name-display').textContent = acc.name;
        clone.querySelector('.subaccount-key-display').textContent = `(${acc.api_key})`;
        const statusTag = clone.querySelector('.subaccount-status-tag');
        statusTag.textContent = acc.suspended ? 'Suspended' : 'Active';
        statusTag.className = acc.suspended ? 'subaccount-status-tag suspended' : 'subaccount-status-tag active';

        const form = clone.querySelector('.vonage-subaccount-form');
        form.querySelector('.subaccount-api-key').value = acc.api_key;
        form.querySelector('.api-key').value = acc.api_key;
        form.querySelector('.created-at').value = new Date(acc.created_at).toLocaleString();
        form.querySelector('.balance').value = `${acc.balance} ${acc.account_currency}`;
        form.querySelector('.credit-limit').value = `${acc.credit_limit} ${acc.account_currency}`;
        form.querySelector('.subaccount-name').value = acc.name;
        form.querySelector('.suspended').checked = acc.suspended;
        form.querySelector('.suspended-status').textContent = acc.suspended ? 'Yes' : 'No';
        form.querySelector('.use-primary-balance').checked = acc.use_primary_account_balance;
        form.querySelector('.use-primary-balance-status').textContent = acc.use_primary_account_balance ? 'Yes' : 'No';
        container.appendChild(clone);
    });
}

// --- PSIP (SIP TRUNK) MANAGEMENT ---

let vonageIncludeStoredIps = true;

export function setupPsipFeature() {
    document.getElementById('vonage_psip_include_stored_ips')?.addEventListener('change', function() {
        vonageIncludeStoredIps = this.checked;
    });
}

function generateVonagePsipPayload() {
    let acl = document.getElementById('vonage_psip_acl').value.split('\n').map(ip => ip.trim()).filter(ip => ip);
    if (vonageIncludeStoredIps) {
        const storedAcl = state.vonageStoredIps.map(item => item.ip);
        acl = [...new Set([...acl, ...storedAcl])]; // Combine and remove duplicates
    }
    return {
        name: document.getElementById('vonage_psip_name').value,
        trunk_name: document.getElementById('vonage_psip_trunk_name').value,
        tls: document.getElementById('vonage_psip_tls').value,
        digest_auth: document.getElementById('vonage_psip_digest_auth').checked,
        srtp: document.getElementById('vonage_psip_srtp').value,
        acl: acl,
        domain_type: document.getElementById('vonage_psip_domain_type').value
    };
}

export function generateVonagePsipCurlCommand() {
    try {
        const auth = getAuthPayload('vonage_psip');
        const payload = generateVonagePsipPayload();
        return `curl -X POST https://api.nexmo.com/v2/psip/domains \\
 -H 'Content-Type: application/json' \\
 -u '${auth.username}:${auth.password}' \\
 -d '${JSON.stringify(payload, null, 2)}'`;
    } catch (error) {
        return `Error generating cURL: ${error.message}`;
    }
}

export function previewPsipPayload() {
    displayResponse('JSON Payload Preview:\n\n' + JSON.stringify(generateVonagePsipPayload(), null, 2));
}

export async function handleVonagePsipSubmit(event) {
    event.preventDefault();
    displayResponse('Sending PSIP domain creation request...', 'pending');
    try {
        const auth = getAuthPayload('vonage_psip');
        const payload = generateVonagePsipPayload();
        const body = { ...auth, ...payload };
        const response = await apiFetch('/api/vonage/psip/create', {
            method: 'POST',
            body: JSON.stringify(body)
        });
        const data = await response.json();
        handleBackendResponse(data);
    } catch (error) {
        handleFetchError(error, 'Create PSIP Domain');
    }
}

export async function handleFetchPsipDomains(event) {
    event.preventDefault();
    displayResponse('Fetching PSIP domains...', 'pending');
    const listContainer = document.getElementById('vonage-psip-domain-list-container');
    const listEl = document.getElementById('vonage-psip-domain-list');
    listEl.innerHTML = '';
    try {
        const auth = getAuthPayload('vonage_manage_psip');
        const response = await apiFetch('/api/vonage/psip', {
            method: 'POST',
            body: JSON.stringify(auth)
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to fetch domains');

        state.vonagePsipDomains = Array.isArray(data) ? data : [];
        renderPsipDomains();

        displayResponse(`Successfully fetched ${state.vonagePsipDomains.length} domains.`, 'success');
        listContainer.style.display = state.vonagePsipDomains.length > 0 ? 'block' : 'none';
    } catch (error) {
        handleFetchError(error, 'Fetch PSIP Domains');
    }
}

function renderPsipDomains() {
    const container = document.getElementById('vonage-psip-domain-list');
    const template = document.getElementById('vonage-psip-domain-template');
    container.innerHTML = '';

    if (!state.vonagePsipDomains || state.vonagePsipDomains.length === 0) {
        container.innerHTML = '<p>No PSIP domains found on this account.</p>';
        return;
    }

    state.vonagePsipDomains.forEach(domain => {
        const clone = template.content.cloneNode(true);
        clone.querySelector('.domain-name-display').textContent = domain.name;
        const typeDisplay = clone.querySelector('.domain-type-display');
        typeDisplay.textContent = domain.domain_type ? `(${domain.domain_type})` : '';

        const form = clone.querySelector('.vonage-psip-domain-form');
        form.querySelector('.original-domain-name').value = domain.name;
        form.querySelector('.domain-name').value = domain.name;
        form.querySelector('.trunk-name').value = domain.trunk_name || '';
        form.querySelector('.tls').value = domain.tls || 'optional';
        form.querySelector('.digest-auth').checked = domain.digest_auth || false;
        form.querySelector('.digest-auth-status').textContent = (domain.digest_auth || false) ? 'On' : 'Off';
        form.querySelector('.srtp').value = domain.srtp || 'optional';
        form.querySelector('.acl').value = (domain.acl || []).join('\n');
        form.querySelector('.domain-type').value = domain.domain_type || 'trunk';

        container.appendChild(clone);
    });
}

// --- START: MODIFICATION ---
export async function handlePsipDomainActions(event) {
    const target = event.target;
    event.preventDefault();

    if (target.classList.contains('save-psip-changes-btn')) {
        const form = target.closest('.vonage-psip-domain-form');
        const originalName = form.querySelector('.original-domain-name').value;
        displayResponse(`Updating PSIP domain '${originalName}'...`, 'pending');

        try {
            const auth = getAuthPayload('vonage_manage_psip');
            const payload = {
                ...auth,
                original_domain_name: originalName,
                name: form.querySelector('.domain-name').value,
                trunk_name: form.querySelector('.trunk-name').value,
                tls: form.querySelector('.tls').value,
                digest_auth: form.querySelector('.digest-auth').checked,
                srtp: form.querySelector('.srtp').value,
                acl: form.querySelector('.acl').value.split('\n').map(ip => ip.trim()).filter(Boolean),
                domain_type: form.querySelector('.domain-type').value
            };

            const response = await apiFetch('/api/vonage/psip/update', {
                method: 'POST',
                body: JSON.stringify(payload)
            });
            const data = await response.json();
            
            if (!response.ok) throw (data);
            
            handleBackendResponse(data);
            // Refresh the list after a successful update
            document.getElementById('vonageFetchPsipDomainsForm').requestSubmit();

        } catch (error) {
            handleBackendResponse(error); // handleBackendResponse can handle error objects
        }
    } else if (target.classList.contains('delete-psip-domain-btn')) {
        const form = target.closest('.vonage-psip-domain-form');
        const domainName = form.querySelector('.domain-name').value;

        if (!confirm(`Are you sure you want to permanently delete the PSIP domain '${domainName}'? This cannot be undone.`)) {
            displayResponse("Delete operation cancelled.", "pending");
            return;
        }

        displayResponse(`Deleting PSIP domain '${domainName}'...`, 'pending');
        try {
            const auth = getAuthPayload('vonage_manage_psip');
            const payload = { ...auth, domain_name: domainName };
            const response = await apiFetch('/api/vonage/psip/delete', {
                method: 'POST',
                body: JSON.stringify(payload)
            });
            const data = await response.json();
            
            if (!response.ok) throw (data);
            
            handleBackendResponse(data);
             // Refresh the list after a successful deletion
            document.getElementById('vonageFetchPsipDomainsForm').requestSubmit();

        } catch (error) {
            handleBackendResponse(error);
        }

    } else if (target.classList.contains('cancel-psip-edit-btn')) {
        // Close the details panel to cancel editing
        target.closest('details').open = false;
        // Re-render the list from state to discard any user changes in the form
        renderPsipDomains();
    }
}
// --- END: MODIFICATION ---


// --- DID MANAGEMENT (Search, Buy, Configure, Modify, Release) ---

export async function handleVonageSearchSubmit(event) {
    event.preventDefault();
    displayResponse('Searching for available numbers...', 'pending');
    document.getElementById('search-results-area').style.display = 'none';
    document.getElementById('purchase-controls').style.display = 'none';
    try {
        const auth = getAuthPayload('vonage_search');
        const payload = {
            ...auth,
            country: document.getElementById('vonage_search_country').value,
            type: document.getElementById('vonage_search_type').value,
            pattern: document.getElementById('vonage_search_pattern').value,
            search_pattern: document.getElementById('vonage_search_search_pattern').value,
            features: document.getElementById('vonage_search_features').value,
        };
        const response = await apiFetch('/api/vonage/dids/search', {
            method: 'POST',
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Search failed');
        renderSearchResults(data.numbers);
    } catch (error) {
        handleFetchError(error, 'DID Search');
    }
}

function renderSearchResults(numbers) {
    const resultsArea = document.getElementById('search-results-area');
    const container = document.getElementById('search-results-container').querySelector('ul');
    const countEl = document.getElementById('search-count');
    const purchaseButton = document.getElementById('vonage_purchase_button');
    container.innerHTML = '';

    if (!numbers || numbers.length === 0) {
        countEl.textContent = '0';
        container.innerHTML = '<li>No numbers found matching your criteria.</li>';
        resultsArea.style.display = 'block';
        purchaseButton.disabled = true;
        return;
    }

    countEl.textContent = numbers.length;
    numbers.forEach(num => {
        const li = document.createElement('li');
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.className = 'did-checkbox';
        checkbox.value = num.msisdn;
        checkbox.dataset.country = document.getElementById('vonage_search_country').value.toUpperCase();
        const label = document.createElement('label');
        label.appendChild(checkbox);
        label.append(` ${num.msisdn} - Features: ${num.features.join(', ')} - Cost: ${num.cost}`);
        li.appendChild(label);
        container.appendChild(li);
    });

    resultsArea.style.display = 'block';
    document.getElementById('purchase-controls').style.display = 'block';
    updateSelectedCount();
}

export function updateSelectedCount() {
    const selected = document.querySelectorAll('#search-results-container .did-checkbox:checked').length;
    document.getElementById('selected-count').textContent = selected;
    document.getElementById('vonage_purchase_button').disabled = selected === 0;
}

export async function handlePurchaseButtonClick() { /* Stub for individual purchase */ }
export async function handleBulkNpaPurchaseClick() { /* Stub for bulk purchase */ }
export async function handleConfigureClick() { /* Stub for configuration */ }
export async function handleExportClick() { /* Stub for export */ }
export async function handleVonageModifyDidSubmit(event) { event.preventDefault(); /* Stub for modify */ }

export async function handleVonageReleaseDidSubmit(event) {
    event.preventDefault();

    if (!confirm("WARNING: You are about to permanently release the specified DIDs from your account. This action cannot be undone. Are you sure you want to proceed?")) {
        displayResponse("Release operation cancelled by user.", "pending");
        return;
    }

    const msisdnsTextarea = document.getElementById('vonageRelease_msisdns');
    const statusArea = document.getElementById('vonageReleaseDidStatusArea');
    const statusList = document.getElementById('vonageReleaseDidStatusList');

    const msisdns = msisdnsTextarea.value.split('\n').map(line => line.trim()).filter(line => line !== '');

    if (msisdns.length === 0) {
        displayResponse("Error: Please enter at least one DID to release.", 'error');
        return;
    }

    statusList.innerHTML = '';
    statusArea.style.display = 'block';
    displayResponse(`Starting release process for ${msisdns.length} DID(s)...`, 'pending');
    toggleOperationControls('release', true);

    const isManualCountryMode = document.getElementById('vonageRelease_country_mode_toggle').checked;
    const manualCountryCode = document.getElementById('vonageRelease_country_other_input').value.toUpperCase();

    const itemsToProcess = [];
    for (const msisdn of msisdns) {
        addOrUpdateOperationStatus(msisdn, 'Pending...', 'pending', statusList);
        let country = '';
        if (isManualCountryMode) {
            if (manualCountryCode && /^[A-Z]{2}$/.test(manualCountryCode)) {
                country = manualCountryCode;
            } else {
                addOrUpdateOperationStatus(msisdn, 'Failed: Invalid or missing manual Country Code.', 'error', statusList);
                continue; // Skip this DID
            }
        } else {
            // Auto-detect US/CA
            const cleanMsisdn = msisdn.replace(/\D/g, '');
            const nationalNumber = cleanMsisdn.slice(-10);
            if (nationalNumber.length === 10) {
                const npa = nationalNumber.substring(0, 3);
                if (state.npaData.US && state.npaData.US.includes(npa)) {
                    country = 'US';
                } else if (state.npaData.CA && state.npaData.CA.includes(npa)) {
                    country = 'CA';
                }
            }
            if (!country) {
                addOrUpdateOperationStatus(msisdn, 'Failed: Could not auto-detect country. Use manual mode for non-US/CA DIDs.', 'error', statusList);
                continue; // Skip this DID
            }
        }
        itemsToProcess.push({ msisdn, country });
    }

    if (itemsToProcess.length === 0) {
        displayResponse('Release operation finished. No valid DIDs were processed.', 'error');
        toggleOperationControls('release', false);
        return;
    }

    const processSingleDidRelease = async (item) => {
        try {
            const authPayload = getAuthPayload('vonageRelease');
            const apiPayload = {
                ...authPayload,
                msisdn: item.msisdn,
                country: item.country
            };
            const response = await apiFetch('/api/vonage/dids/release', {
                method: 'POST',
                body: JSON.stringify(apiPayload)
            });
            const data = await response.json();
            return {
                ...data,
                status_code: response.status,
                country: item.country
            };
        } catch (error) {
            return { error: error.message, status_code: 500 };
        }
    };

    const results = await processInBatches(
        itemsToProcess,
        processSingleDidRelease,
        addOrUpdateOperationStatus,
        statusList,
        item => item.msisdn
    );

    const successCount = results.filter(r => r.status === 'fulfilled' && r.value.status_code >= 200 && r.value.status_code < 300).length;
    const failedCount = results.length - successCount;

    let finalMessage = `Release process finished. Success: ${successCount}, Failed: ${failedCount}.`;
    if (state.isOperationCancelled) {
        finalMessage = `Release process stopped by user. Processed: ${results.length}, Success: ${successCount}, Failed: ${failedCount}.`;
    }

    displayResponse(finalMessage, failedCount > 0 ? 'error' : 'success');
    toggleOperationControls('release', false);
}

// --- STORED IPs & URIs ---

export function renderStoredItems(type, containerId, noItemsMsgId, itemsArray) {
    const container = document.getElementById(containerId);
    const noItemsMsg = document.getElementById(noItemsMsgId);
    if (!container || !noItemsMsg) return;

    container.innerHTML = '';
    if (!itemsArray || itemsArray.length === 0) {
        noItemsMsg.textContent = `No stored ${type}s loaded or found.`;
        noItemsMsg.style.display = 'block';
        return;
    }

    noItemsMsg.style.display = 'none';
    itemsArray.forEach((item, index) => {
        const itemRow = document.createElement('div');
        itemRow.className = 'stored-item-row';
        itemRow.innerHTML = `
            <div class="stored-item-label">${item.label || `Unlabeled ${type.toUpperCase()}`}</div>
            <div class="stored-item-value">${item[type]}</div>
            <button type="button" class="stored-item-delete-btn" title="Remove ${type.toUpperCase()} from session" data-index="${index}" data-type="${type}">✕</button>
        `;
        itemRow.querySelector('.stored-item-delete-btn').addEventListener('click', handleDeleteStoredItem);
        container.appendChild(itemRow);
    });
}

export function handleAddStoredItem(event) {
    const type = event.target.dataset.type; // 'ip' or 'uri'
    const parentContainer = event.target.closest('.action-content, div[style*="padding: 10px"]');
    if (!parentContainer) return;

    const valueInput = parentContainer.querySelector(`#vonage_${type === 'ip' ? 'psip' : 'config'}_newItemValue`);
    const labelInput = parentContainer.querySelector(`#vonage_${type === 'ip' ? 'psip' : 'config'}_newItemLabel`);
    let value = valueInput?.value.trim();
    const label = labelInput?.value.trim();

    if (!value) {
        alert(`Please enter a value for the ${type.toUpperCase()}.`);
        return;
    }

    if (type === 'ip') {
        const ipv4Pattern = /^(\d{1,3}\.){3}\d{1,3}(\/\d{1,2})?$/;
        if (!ipv4Pattern.test(value)) {
            alert('Please enter a valid IPv4 address (e.g. 192.168.1.1 or 192.168.1.1/32)');
            return;
        }
        if (!value.includes('/')) {
            value += '/32';
        }
        state.vonageStoredIps.push({ ip: value, label });
        renderStoredItems('ip', 'vonage_psip_storedItemsContainer', 'vonage_psip_noStoredItems', state.vonageStoredIps);
    } else if (type === 'uri') {
        state.vonageStoredUris.push({ uri: value, label });
        renderStoredItems('uri', 'vonage_config_storedItemsContainer', 'vonage_config_noStoredItems', state.vonageStoredUris);
        populateAllUriDatalists();
    }

    if (valueInput) valueInput.value = '';
    if (labelInput) labelInput.value = '';
}

function handleDeleteStoredItem(event) {
    const index = parseInt(event.target.dataset.index, 10);
    const type = event.target.dataset.type;
    if (isNaN(index)) return;

    if (type === 'ip') {
        state.vonageStoredIps.splice(index, 1);
        renderStoredItems('ip', 'vonage_psip_storedItemsContainer', 'vonage_psip_noStoredItems', state.vonageStoredIps);
    } else if (type === 'uri') {
        state.vonageStoredUris.splice(index, 1);
        renderStoredItems('uri', 'vonage_config_storedItemsContainer', 'vonage_config_noStoredItems', state.vonageStoredUris);
        populateAllUriDatalists();
    }
}

function populateUriDatalist(datalistId) {
    const datalist = document.getElementById(datalistId);
    if (!datalist) return;
    datalist.innerHTML = '';
    state.vonageStoredUris.forEach(item => {
        const option = document.createElement('option');
        option.value = item.uri;
        option.label = item.label ? `${item.label} (${item.uri})` : item.uri;
        datalist.appendChild(option);
    });
}

export function populateAllUriDatalists() {
    populateUriDatalist('stored-uris-list');
    populateUriDatalist('vonageModify_storedUrisDatalist');
}
// --- END OF FILE static/js/vonage.js ---
