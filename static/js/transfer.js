/**
 * Dedicated JavaScript module for DID transfer operations.
 * 
 * Handles:
 *  - Fetching subaccounts for dropdown population
 *  - Rendering subaccount dropdown selectors
 *  - Processing DID transfers (single and batch via processInBatches)
 *  - Country auto-detection and manual mode
 */

import { apiFetch, state, processInBatches } from './utils.js';
import { displayResponse, handleFetchError, handleBackendResponse, addOrUpdateOperationStatus, toggleOperationControls } from './ui.js';
import { getAuthPayload } from './credentials.js';

// --- Subaccount Fetching & Dropdown Population ---

/**
 * Fetches subaccounts and populates the from/to dropdown selectors.
 */
export async function handleFetchTransferSubaccounts(event) {
    event.preventDefault();
    displayResponse('Fetching subaccounts for transfer...', 'pending');

    try {
        const auth = getAuthPayload('vonageTransfer');
        const response = await apiFetch('/api/vonage/subaccounts', {
            method: 'POST',
            body: JSON.stringify(auth)
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to fetch subaccounts');

        const subaccounts = data.subaccounts || [];
        if (subaccounts.length === 0) {
            displayResponse('No subaccounts found under this primary account.', 'error');
            return;
        }

        renderTransferSubaccountDropdowns(subaccounts);
        document.getElementById('vonageTransfer_subaccountSelectors').style.display = 'block';
        displayResponse(`Loaded ${subaccounts.length} subaccounts. Select source and destination below.`, 'success');
    } catch (error) {
        handleFetchError(error, 'Fetch Transfer Subaccounts');
    }
}

/**
 * Populates the from/to select elements with subaccount options.
 * Shows subaccount name + masked API key for identification without exposing full keys.
 */
function renderTransferSubaccountDropdowns(subaccounts) {
    const fromSelect = document.getElementById('vonageTransfer_from_api_key');
    const toSelect = document.getElementById('vonageTransfer_to_api_key');

    // Build options HTML
    const defaultOption = '<option value="">-- Select Subaccount --</option>';
    const options = subaccounts.map(acc => {
        // Mask API key: show first 4 and last 3 characters
        const key = acc.api_key || '';
        const maskedKey = key.length > 7 ? `${key.slice(0, 4)}...${key.slice(-3)}` : key;
        const label = `${acc.name} (${maskedKey})`;
        return `<option value="${acc.api_key}">${label}</option>`;
    }).join('');

    fromSelect.innerHTML = defaultOption + options;
    toSelect.innerHTML = defaultOption + options;
}

// --- DID Transfer Processing ---

/**
 * Handles the form submission for transferring DIDs between subaccounts.
 * Implements:
 *  - Double confirmation dialog (intentional UX friction for dangerous operations)
 *  - Input sanitisation (digits-only for MSISDNs)
 *  - Source !== destination validation
 *  - Country auto-detection or manual specification
 *  - Batch processing with per-DID status updates
 */
export async function handleTransferDidsSubmit(event) {
    event.preventDefault();

    // --- Client-side validation ---
    const fromApiKey = document.getElementById('vonageTransfer_from_api_key').value;
    const toApiKey = document.getElementById('vonageTransfer_to_api_key').value;

    if (!fromApiKey || !toApiKey) {
        displayResponse('Error: Please select both a source and destination subaccount.', 'error');
        return;
    }

    if (fromApiKey === toApiKey) {
        displayResponse('Error: Source and destination subaccounts cannot be the same.', 'error');
        return;
    }

    const msisdnsTextarea = document.getElementById('vonageTransfer_msisdns');
    const msisdns = msisdnsTextarea.value.split('\n').map(line => line.trim()).filter(line => line !== '');

    if (msisdns.length === 0) {
        displayResponse('Error: Please enter at least one DID to transfer.', 'error');
        return;
    }

    // --- Double confirmation (security UX friction) ---
    const fromName = document.getElementById('vonageTransfer_from_api_key').selectedOptions[0]?.text || fromApiKey;
    const toName = document.getElementById('vonageTransfer_to_api_key').selectedOptions[0]?.text || toApiKey;

    if (!confirm(
        `⚠️ WARNING: You are about to transfer ${msisdns.length} DID(s) FROM "${fromName}" TO "${toName}".\n\n` +
        `This operation is PERMANENT and IRREVERSIBLE.\n\n` +
        `Are you sure you want to proceed?`
    )) {
        displayResponse('Transfer operation cancelled by user.', 'pending');
        return;
    }

    if (!confirm(
        `FINAL CONFIRMATION: Transfer ${msisdns.length} DID(s)?\n\n` +
        `Please confirm one more time that you want to proceed.`
    )) {
        displayResponse('Transfer operation cancelled by user.', 'pending');
        return;
    }

    // --- Setup status area ---
    const statusArea = document.getElementById('vonageTransferDidStatusArea');
    const statusList = document.getElementById('vonageTransferDidStatusList');
    statusList.innerHTML = '';
    statusArea.style.display = 'block';
    displayResponse(`Starting transfer process for ${msisdns.length} DID(s)...`, 'pending');
    toggleOperationControls('transfer', true);

    // --- Country detection ---
    const isManualCountryMode = document.getElementById('vonageTransfer_country_mode_toggle').checked;
    const manualCountryCode = document.getElementById('vonageTransfer_country_other_input').value.toUpperCase();

    const itemsToProcess = [];
    for (const msisdn of msisdns) {
        addOrUpdateOperationStatus(msisdn, 'Pending...', 'pending', statusList);
        let country = '';

        if (isManualCountryMode) {
            if (manualCountryCode && /^[A-Z]{2}$/.test(manualCountryCode)) {
                country = manualCountryCode;
            } else {
                addOrUpdateOperationStatus(msisdn, 'Failed: Invalid or missing manual Country Code.', 'error', statusList);
                continue;
            }
        } else {
            // Auto-detect US/CA from NPA
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
                continue;
            }
        }
        itemsToProcess.push({ msisdn, country });
    }

    if (itemsToProcess.length === 0) {
        displayResponse('Transfer operation finished. No valid DIDs were processed.', 'error');
        toggleOperationControls('transfer', false);
        return;
    }

    // --- Process transfers in batches ---
    const processSingleTransfer = async (item) => {
        try {
            const authPayload = getAuthPayload('vonageTransfer');
            const apiPayload = {
                ...authPayload,
                from_api_key: fromApiKey,
                to_api_key: toApiKey,
                number: item.msisdn,
                country: item.country
            };
            const response = await apiFetch('/api/vonage/dids/transfer', {
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
        processSingleTransfer,
        addOrUpdateOperationStatus,
        statusList,
        item => item.msisdn
    );

    const successCount = results.filter(r => r.status === 'fulfilled' && r.value.status_code >= 200 && r.value.status_code < 300).length;
    const failedCount = results.length - successCount;

    let finalMessage = `Transfer process finished. Success: ${successCount}, Failed: ${failedCount}.`;
    if (state.isOperationCancelled) {
        finalMessage = `Transfer process stopped by user. Processed: ${results.length}, Success: ${successCount}, Failed: ${failedCount}.`;
    }

    displayResponse(finalMessage, failedCount > 0 ? 'error' : 'success');
    toggleOperationControls('transfer', false);
}
