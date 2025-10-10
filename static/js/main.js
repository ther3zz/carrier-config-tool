// --- START OF FILE static/js/main.js ---
import { apiFetch, appSettings, state } from './utils.js';
import { openOuterTab, openInnerTab, setupAccordionBehavior, setupModalHandlers, stopAllOperations } from './ui.js';
import { setupSettingsEventListeners } from './settings.js';
import {
    handleSetMasterKey, handleAddCredential, handleCredentialListActions,
    handleBulkImportCredentials, handleImportFromFile, handleRekeyCredentials
} from './credentials.js';
import {
    handleFetchSubaccounts, handleCreateSubaccount, handleSubaccountActions,
    setupPsipFeature, previewPsipPayload, generateVonagePsipCurlCommand,
    handleVonagePsipSubmit, handleFetchPsipDomains, handlePsipDomainActions,
    handleVonageSearchSubmit, updateSelectedCount, handlePurchaseButtonClick,
    handleBulkNpaPurchaseClick, handleConfigureClick, handleExportClick,
    handleVonageModifyDidSubmit, handleVonageReleaseDidSubmit,
    renderStoredItems, handleAddStoredItem, populateAllUriDatalists
} from './vonage.js';


/**
 * Fetches initial data required for the application to function.
 */
function loadInitialData() {
    apiFetch('/api/ips')
        .then(res => res.json())
        .then(data => {
            state.vonageStoredIps = data;
            renderStoredItems('ip', 'vonage_psip_storedItemsContainer', 'vonage_psip_noStoredItems', state.vonageStoredIps);
        }).catch(e => console.error('Error fetching IPs:', e));

    apiFetch('/api/uris')
        .then(res => res.json())
        .then(data => {
            state.vonageStoredUris = data;
            renderStoredItems('uri', 'vonage_config_storedItemsContainer', 'vonage_config_noStoredItems', state.vonageStoredUris);
            populateAllUriDatalists();
        }).catch(e => console.error('Error fetching URIs:', e));

    apiFetch('/api/npa-data')
        .then(res => res.json())
        .then(data => {
            state.npaData = data;
            console.log("NPA data loaded.");
        }).catch(e => {
            console.error('CRITICAL: Could not load NPA data.', e);
            displayResponse("Error: Could not load NPA data. Auto-detection will fail.", "error");
        });

    apiFetch('/api/settings')
        .then(res => res.json())
        .then(data => {
            if (data && typeof data === 'object') {
                Object.assign(appSettings, data);
                console.log("Application settings loaded from database.", appSettings);
            }
        }).catch(e => console.error('Error fetching application settings:', e));
}


/**
 * Main DOMContentLoaded event listener. Initializes the application.
 */
document.addEventListener('DOMContentLoaded', () => {
    // Make tab functions globally accessible from HTML onclick attributes
    window.openOuterTab = openOuterTab;
    window.openInnerTab = openInnerTab;
    
    // --- Initial Setup ---
    loadInitialData();
    setupAccordionBehavior();
    setupModalHandlers();
    setupSettingsEventListeners();
    setupPsipFeature();

    // --- Credential Selector Template Population ---
    const selectorTemplate = document.getElementById('credential-selector-template');
    if (selectorTemplate) {
        document.querySelectorAll('.credential-selector-container').forEach(c => {
            const p = c.dataset.idPrefix;
            const cl = selectorTemplate.content.cloneNode(true);
            cl.querySelector('.credential-selector-label').htmlFor = `${p}_selector_value`;
            cl.querySelector('.credential-selector-value').id = `${p}_selector_value`;
            cl.querySelector('.credential-username-label').htmlFor = `${p}_username`;
            cl.querySelector('.credential-username-input').id = `${p}_username`;
            cl.querySelector('.credential-password-label').htmlFor = `${p}_password`;
            cl.querySelector('.credential-password-input').id = `${p}_password`;
            c.appendChild(cl);
        });
    }

    // --- General Event Listeners ---
    const firstTab = document.querySelector('.tab-link');
    if (firstTab) firstTab.click();
    document.querySelectorAll('.stop-button').forEach(btn => btn.addEventListener('click', stopAllOperations));

    // --- Credential Management Listeners ---
    document.getElementById('setMasterKeyButton')?.addEventListener('click', handleSetMasterKey);
    document.getElementById('addCredentialForm')?.addEventListener('submit', handleAddCredential);
    document.getElementById('credentialListContainer')?.addEventListener('click', handleCredentialListActions);
    document.getElementById('importCredentialsButton')?.addEventListener('click', handleBulkImportCredentials);
    document.getElementById('importFromFileButton')?.addEventListener('click', handleImportFromFile);
    document.getElementById('rekeyCredentialsButton')?.addEventListener('click', handleRekeyCredentials);

    // --- Vonage Tab Listeners ---
    // Subaccounts
    document.getElementById('vonageFetchSubaccountsForm')?.addEventListener('submit', handleFetchSubaccounts);
    document.getElementById('vonageCreateSubaccountForm')?.addEventListener('submit', handleCreateSubaccount);
    document.getElementById('vonage-subaccount-list')?.addEventListener('click', handleSubaccountActions);
    document.getElementById('vonage_new_subaccount_use_primary_balance')?.addEventListener('change', function() {
        document.getElementById('vonage_new_subaccount_use_primary_balance_status').textContent = this.checked ? 'On' : 'Off';
    });

    // PSIP
    document.getElementById('vonagePsipForm')?.addEventListener('submit', handleVonagePsipSubmit);
    document.getElementById('vonage_psip_digest_auth')?.addEventListener('change', function() {
        document.getElementById('vonage_psip_digest_auth_status').textContent = this.checked ? 'On' : 'Off';
    });
    document.querySelectorAll('.add-stored-item-btn').forEach(b => b.addEventListener('click', handleAddStoredItem));
    document.getElementById('vonage_psip_previewButton')?.addEventListener('click', previewPsipPayload);
    document.getElementById('vonage_psip_copyButton')?.addEventListener('click', () => {
        const c = generateVonagePsipCurlCommand();
        navigator.clipboard.writeText(c).then(() => displayResponse('cURL copied!\n\n' + c, 'success'), () => displayResponse('Copy failed:\n\n' + c));
    });
    document.getElementById('vonageFetchPsipDomainsForm')?.addEventListener('submit', handleFetchPsipDomains);
    document.getElementById('vonage-psip-domain-list')?.addEventListener('click', handlePsipDomainActions);

    // DIDs
    document.getElementById('vonageSearchForm')?.addEventListener('submit', handleVonageSearchSubmit);
    document.getElementById('vonage_purchase_button')?.addEventListener('click', handlePurchaseButtonClick);
    document.getElementById('vonage_bulk_npa_purchase_button')?.addEventListener('click', handleBulkNpaPurchaseClick);
    document.getElementById('vonage_configure_button')?.addEventListener('click', handleConfigureClick);
    document.getElementById('vonage_export_button')?.addEventListener('click', handleExportClick);
    document.getElementById('search-results-container')?.addEventListener('change', e => {
        if (e.target.classList.contains('did-checkbox')) updateSelectedCount();
    });
    
    // Modify DIDs
    const mdf = document.getElementById('vonageModifyDidForm');
    if (mdf) {
        mdf.addEventListener('submit', handleVonageModifyDidSubmit);
        // Additional setup for the modify form toggles
        document.getElementById('vonageModify_mode_toggle')?.addEventListener('change', function() {
            const c = this.checked;
            document.getElementById('vonageModify_mode_status').textContent = c ? 'CSV Upload' : 'Manual Entry';
            document.getElementById('vonageModify_csv_section').style.display = c ? 'block' : 'none';
            document.getElementById('vonageModify_manual_section').style.display = c ? 'none' : 'block';
        });
        document.getElementById('vonageModify_country_mode_toggle')?.addEventListener('change', function() {
            const m = this.checked;
            document.getElementById('vonageModify_country_other_container').style.display = m ? 'block' : 'none';
            document.querySelector('#vonageModifyDidForm .country-mode-status').textContent = m ? 'Other (Manual)' : 'US/CA (Auto-Detect)';
        });
        mdf.querySelectorAll('.toggle input[data-config-param]').forEach(cb => {
            const t = document.getElementById(cb.dataset.inputTarget);
            if (t) {
                cb.addEventListener('change', () => { t.disabled = !cb.checked; if (t.id.includes('voiceCallback')) document.getElementById('vonageModify_voiceCallbackType').dispatchEvent(new Event('change')); });
                t.disabled = !cb.checked;
            }
        });
    }
    
    // Release DIDs
    document.getElementById('vonageReleaseDidForm')?.addEventListener('submit', handleVonageReleaseDidSubmit);
    document.getElementById('vonageRelease_country_mode_toggle')?.addEventListener('change', function() {
        const isManual = this.checked;
        document.getElementById('vonageRelease_country_other_container').style.display = isManual ? 'block' : 'none';
        document.querySelector('#vonageReleaseDidForm .country-mode-status').textContent = isManual ? 'Other (Manual)' : 'US/CA (Auto-Detect)';
    });
});
// --- END OF FILE static/js/main.js ---