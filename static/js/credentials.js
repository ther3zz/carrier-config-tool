// --- START OF FILE static/js/credentials.js ---
import { apiFetch, state } from './utils.js';
import { displayResponse, handleFetchError } from './ui.js';

// --- CORE FUNCTIONS ---

/**
 * Handles the "Set & Load" button click for the Master Key.
 * Verifies the key with the backend and loads credentials.
 */
export async function handleSetMasterKey() {
    const keyInput = document.getElementById('masterKeyInput');
    const statusDiv = document.getElementById('masterKeyStatus');
    const managerUI = document.getElementById('credentialManagerUI');
    const potentialKey = keyInput.value;

    if (!potentialKey) {
        statusDiv.textContent = 'Please enter a Master Key.';
        statusDiv.className = 'status-error';
        return;
    }

    statusDiv.textContent = 'Verifying key and loading credentials...';
    statusDiv.className = 'status-pending';

    try {
        const response = await apiFetch('/api/credentials/names');
        if (!response.ok) throw new Error(`Server responded with status ${response.status}`);
        const data = await response.json();

        state.masterKey = potentialKey;
        state.storedCredentials = data || [];

        keyInput.style.borderColor = '#4CAF50';
        statusDiv.textContent = `Master Key set for session. ${state.storedCredentials.length} credential(s) loaded.`;
        statusDiv.className = 'status-success';
        managerUI.style.display = 'block';

        renderCredentialList();
        populateAllCredentialSelectors();
    } catch (error) {
        console.error("Failed to set master key or load credentials:", error);
        state.masterKey = null;
        state.storedCredentials = [];
        keyInput.style.borderColor = '#f44336';
        statusDiv.textContent = `Error: Could not load credentials. Check console for details.`;
        statusDiv.className = 'status-error';
        managerUI.style.display = 'none';
        renderCredentialList();
        populateAllCredentialSelectors();
    }
}

/**
 * Handles form submission to add a new credential.
 * @param {Event} event - The form submission event.
 */
export async function handleAddCredential(event) {
    event.preventDefault();
    if (!state.masterKey) {
        displayResponse("Error: Master Key is not set.", "error");
        return;
    }

    const name = document.getElementById('credentialName').value;
    const apiKey = document.getElementById('credentialApiKey').value;
    const apiSecret = document.getElementById('credentialApiSecret').value;
    const voice_callback_type = document.getElementById('credentialVoiceCallbackType').value;
    const voice_callback_value = document.getElementById('credentialVoiceCallbackValue').value;

    if (!name || !apiKey || !apiSecret) {
        alert("Friendly Name, API Key, and API Secret are required for new credentials.");
        return;
    }

    const payload = {
        name,
        api_key: apiKey,
        api_secret: apiSecret,
        master_key: state.masterKey,
        voice_callback_type,
        voice_callback_value
    };

    displayResponse(`Saving new credential '${name}'...`, 'pending');
    try {
        const response = await apiFetch('/api/credentials/save', {
            method: 'POST',
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to save credential');
        displayResponse(data.message, 'success');
        document.getElementById('addCredentialForm').reset();
        await handleSetMasterKey(); // Reload credentials
    } catch (error) {
        handleFetchError(error, `Save Credential`);
    }
}

/**
 * Handles bulk import from the textarea.
 */
export async function handleBulkImportCredentials() {
    if (!state.masterKey) {
        displayResponse("Error: Master Key must be set before importing.", "error");
        return;
    }

    const textArea = document.getElementById('bulkCredentialInput');
    const statusList = document.getElementById('importStatusList');
    const statusArea = document.getElementById('importStatusArea');
    const rawText = textArea.value;

    statusArea.querySelector('p').style.display = 'none';
    statusList.innerHTML = '';

    const lines = rawText.split('\n').filter(line => line.trim() !== '');
    if (lines.length === 0) {
        displayResponse("Import field is empty. Please paste your data.", "error");
        return;
    }

    const credentialsToImport = [];
    const invalidLines = [];

    lines.forEach((line, index) => {
        const parts = line.split('\t');
        if (parts.length === 3 && parts[0].trim() && parts[1].trim() && parts[2].trim()) {
            credentialsToImport.push({
                name: parts[0].trim(),
                apiKey: parts[1].trim(),
                apiSecret: parts[2].trim()
            });
        } else {
            invalidLines.push(index + 1);
        }
    });

    if (invalidLines.length > 0) {
        alert(`Warning: ${invalidLines.length} line(s) were skipped due to incorrect formatting (Line numbers: ${invalidLines.join(', ')}).`);
    }

    if (credentialsToImport.length === 0) {
        displayResponse("No valid credentials to import.", "error");
        return;
    }

    let successCount = 0;
    for (const cred of credentialsToImport) {
        const li = document.createElement('li');
        li.textContent = `Importing '${cred.name}'...`;
        statusList.appendChild(li);

        try {
            const response = await apiFetch('/api/credentials/save', {
                method: 'POST',
                body: JSON.stringify({
                    name: cred.name,
                    api_key: cred.apiKey,
                    api_secret: cred.apiSecret,
                    master_key: state.masterKey
                })
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error);
            li.textContent = `SUCCESS: '${cred.name}' saved.`;
            li.className = 'status-success';
            successCount++;
        } catch (error) {
            li.textContent = `FAILED: '${cred.name}' - ${error.message}`;
            li.className = 'status-error';
        }
    }

    displayResponse(`Bulk import finished. ${successCount} of ${credentialsToImport.length} credentials saved successfully.`, successCount === credentialsToImport.length ? 'success' : 'error');
    textArea.value = '';
    await handleSetMasterKey(); // Reload credentials
}

/**
 * Handles importing credentials from an encrypted file.
 */
export async function handleImportFromFile() {
    const fileInput = document.getElementById('credentialFileUpload');
    const statusList = document.getElementById('importStatusList');
    const statusArea = document.getElementById('importStatusArea');

    if (!state.masterKey) {
        displayResponse("Error: Master Key must be set before importing.", "error");
        return;
    }
    const file = fileInput.files[0];
    if (!file) {
        displayResponse("Error: Please select a credentials.json file to upload.", "error");
        return;
    }

    statusArea.querySelector('p').style.display = 'none';
    statusList.innerHTML = `<li>Uploading and processing '${file.name}'...</li>`;

    const formData = new FormData();
    formData.append('credential_file', file);
    formData.append('master_key', state.masterKey);

    try {
        const response = await apiFetch('/api/credentials/import', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || 'An unknown error occurred during import.');
        }

        statusList.innerHTML = ''; // Clear processing message
        const { success, failed } = data.results;
        success.forEach(name => {
            const li = document.createElement('li');
            li.textContent = `SUCCESS: Migrated '${name}' to database.`;
            li.className = 'status-success';
            statusList.appendChild(li);
        });
        failed.forEach(item => {
            const li = document.createElement('li');
            li.textContent = `FAILED: '${item.name}' - ${item.reason}`;
            li.className = 'status-error';
            statusList.appendChild(li);
        });

        const finalMessage = `File import finished. Success: ${success.length}, Failed: ${failed.length}.`;
        displayResponse(finalMessage, failed.length > 0 ? 'error' : 'success');

        if (success.length > 0) {
            await handleSetMasterKey(); // Reload credentials
        }

    } catch (error) {
        handleFetchError(error, 'File Import');
        statusList.innerHTML = `<li class="status-error">Error during import: ${error.message}</li>`;
    } finally {
        fileInput.value = ''; // Reset file input
    }
}

/**
 * Handles the re-keying of all credentials.
 */
export async function handleRekeyCredentials() {
    const oldKeyInput = document.getElementById('oldMasterKeyInput');
    const newKeyInput = document.getElementById('newMasterKeyInput');
    const statusList = document.getElementById('rekeyStatusList');

    const oldKey = oldKeyInput.value;
    const newKey = newKeyInput.value;

    statusList.innerHTML = '';

    if (!oldKey || !newKey) {
        alert("Both the Old and New Master Keys are required.");
        return;
    }
    if (oldKey === newKey) {
        alert("The new Master Key must be different from the old one.");
        return;
    }

    const confirmation = confirm(
        "--- CRITICAL WARNING ---\n\n" +
        "You are about to re-encrypt ALL stored credentials. If you provide the wrong 'Old Master Key', " +
        "ALL CREDENTIALS WILL BE PERMANENTLY CORRUPTED AND UNRECOVERABLE.\n\n" +
        "There is NO UNDO. Are you absolutely sure you want to proceed?"
    );

    if (!confirmation) {
        displayResponse("Re-keying operation cancelled by user.", "pending");
        return;
    }

    displayResponse("Attempting to re-key all credentials...", "pending");
    statusList.innerHTML = '<li>Processing... This may take a moment.</li>';

    const payload = {
        old_master_key: oldKey,
        new_master_key: newKey
    };

    try {
        const response = await apiFetch('/api/credentials/rekey', {
            method: 'POST',
            body: JSON.stringify(payload)
        });
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'An unknown error occurred during re-keying.');
        }

        statusList.innerHTML = '';
        const { success, failed } = data.results;

        success.forEach(name => {
            const li = document.createElement('li');
            li.textContent = `SUCCESS: '${name}' was re-keyed.`;
            li.className = 'status-success';
            statusList.appendChild(li);
        });
        
        failed.forEach(item => {
            const li = document.createElement('li');
            li.textContent = `FAILED: '${item.name}' - ${item.reason}`;
            li.className = 'status-error';
            statusList.appendChild(li);
        });

        const finalMessage = `Re-keying process finished. Success: ${success.length}, Failed: ${failed.length}.`;
        displayResponse(finalMessage, failed.length > 0 ? 'error' : 'success');
        
        if (failed.length === 0) {
            const instructionLi = document.createElement('li');
            instructionLi.innerHTML = `<strong>IMPORTANT:</strong> Your session key is now outdated. Please enter your <strong>new Master Key</strong> in the 'Session Master Key' field at the top and click 'Set & Load' to continue working.`;
            instructionLi.style.marginTop = '15px';
            instructionLi.style.fontWeight = 'bold';
            instructionLi.className = 'status-pending';
            statusList.appendChild(instructionLi);
            
            // Invalidate current session
            state.masterKey = null;
            document.getElementById('masterKeyInput').value = '';
            document.getElementById('masterKeyStatus').textContent = 'Credentials have been re-keyed. Please set the new Master Key.';
            document.getElementById('masterKeyStatus').className = 'status-pending';
            document.getElementById('credentialManagerUI').style.display = 'none';
        }
        
        oldKeyInput.value = '';
        newKeyInput.value = '';

    } catch (error) {
        const errorMessage = `Re-keying FAILED: ${error.message}`;
        displayResponse(errorMessage, 'error');
        statusList.innerHTML = `<li class="status-error">Operation failed. See main response area for details.</li>`;
    }
}


// --- UI & EVENT HANDLERS for Credential List ---

/**
 * Event delegation for actions within the credential list (save, delete, cancel).
 * @param {Event} event - The click event.
 */
export function handleCredentialListActions(event) {
    const target = event.target;
    const form = target.closest('.credential-edit-form');
    if (!form) return;
    event.preventDefault();

    const originalName = form.querySelector('.original-credential-name').value;
    const originalCredData = state.storedCredentials.find(c => c.name === originalName);

    if (target.classList.contains('save-credential-changes-btn')) {
        handleSaveCredentialChanges(form, originalCredData);
    } else if (target.classList.contains('delete-credential-btn')) {
        handleDeleteCredential(originalName);
    } else if (target.classList.contains('cancel-credential-edit-btn')) {
        // Reset form to original values
        form.querySelector('.edit-credential-name').value = originalCredData.name;
        form.querySelector('.edit-credential-api-key').value = originalCredData.api_key;
        form.querySelector('.edit-credential-api-secret').value = '';
        form.querySelector('.edit-credential-callback-type').value = originalCredData.default_voice_callback_type || '';
        form.querySelector('.edit-credential-callback-value').value = originalCredData.default_voice_callback_value || '';
        form.closest('details').open = false;
    }
}

async function handleSaveCredentialChanges(form, originalCredData) {
    if (!state.masterKey) {
        displayResponse("Error: Master Key is not set.", "error");
        return;
    }

    const newName = form.querySelector('.edit-credential-name').value;
    const newApiKey = form.querySelector('.edit-credential-api-key').value;
    const newApiSecret = form.querySelector('.edit-credential-api-secret').value;
    const newCallbackType = form.querySelector('.edit-credential-callback-type').value;
    const newCallbackValue = form.querySelector('.edit-credential-callback-value').value;

    if (!newName || !newApiKey) {
        alert("Friendly Name and API Key cannot be empty.");
        return;
    }

    const hasIdentifierChanged = newName !== originalCredData.name || newApiKey !== originalCredData.api_key;
    if (hasIdentifierChanged && !newApiSecret) {
        alert("A new API Secret is required when changing the Friendly Name or API Key.");
        return;
    }

    const payload = {
        original_name: originalCredData.name,
        name: newName,
        api_key: newApiKey,
        api_secret: newApiSecret,
        master_key: state.masterKey,
        voice_callback_type: newCallbackType,
        voice_callback_value: newCallbackValue
    };

    displayResponse(`Updating credential '${originalCredData.name}'...`, 'pending');
    try {
        const response = await apiFetch('/api/credentials/save', { method: 'POST', body: JSON.stringify(payload) });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to save changes');
        displayResponse(data.message, 'success');
        await handleSetMasterKey(); // Reload credentials
    } catch (error) {
        handleFetchError(error, `Update Credential`);
    }
}

async function handleDeleteCredential(credentialName) {
    if (!credentialName || !state.masterKey) return;

    if (confirm(`Are you sure you want to delete "${credentialName}"? This action cannot be undone.`)) {
        displayResponse(`Deleting '${credentialName}'...`, 'pending');
        try {
            const response = await apiFetch('/api/credentials/delete', {
                method: 'POST',
                body: JSON.stringify({ name: credentialName })
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Failed to delete');
            displayResponse(data.message, 'success');
            await handleSetMasterKey(); // Reload credentials
        } catch (error) {
            handleFetchError(error, `Delete Credential`);
        }
    }
}

/**
 * Renders the list of saved credentials from the state.
 */
function renderCredentialList() {
    const container = document.getElementById('credentialListContainer');
    const template = document.getElementById('credential-item-template');
    if (!container || !template) return;

    container.innerHTML = state.storedCredentials.length === 0 ? '<p>No credentials saved yet.</p>' : '';

    state.storedCredentials.forEach(cred => {
        const clone = template.content.cloneNode(true);
        clone.querySelector('.original-credential-name').value = cred.name;
        clone.querySelector('.credential-name-display').textContent = cred.name;
        clone.querySelector('.credential-key-hint').textContent = `(${cred.api_key_hint})`;
        
        const form = clone.querySelector('.credential-edit-form');
        form.querySelector('.edit-credential-name').value = cred.name;
        form.querySelector('.edit-credential-api-key').value = cred.api_key;
        form.querySelector('.edit-credential-callback-type').value = cred.default_voice_callback_type || '';
        form.querySelector('.edit-credential-callback-value').value = cred.default_voice_callback_value || '';

        container.appendChild(clone);
    });
}


// --- CREDENTIAL SELECTOR (DROPDOWN) ---

/**
 * Populates a single credential selector dropdown.
 * @param {HTMLElement} container - The container element for the selector.
 */
function populateCredentialSelector(container) {
    const triggerText = container.querySelector('.custom-select-trigger span');
    const optionsContainer = container.querySelector('.custom-options');
    const filterInput = container.querySelector('.credential-filter-input');
    const valueInput = container.querySelector('.credential-selector-value');
    if (!triggerText || !optionsContainer || !filterInput || !valueInput) return;

    // Clear existing options
    optionsContainer.querySelectorAll('.custom-option:not(.filter-option)').forEach(opt => opt.remove());
    filterInput.value = '';

    const createOption = (text, value) => {
        const option = document.createElement('div');
        option.classList.add('custom-option');
        option.dataset.value = value;
        option.textContent = text;
        return option;
    };

    let defaultText, defaultValue;
    if (!state.masterKey || state.storedCredentials.length === 0) {
        defaultText = state.masterKey ? '-- No Credentials Found --' : '-- Set Master Key First --';
        defaultValue = '';
        optionsContainer.appendChild(createOption(defaultText, ''));
    } else {
        defaultText = '-- Select a Credential --';
        defaultValue = '';
        optionsContainer.appendChild(createOption(defaultText, ''));
        state.storedCredentials.forEach(c => {
            optionsContainer.appendChild(createOption(`${c.name} (${c.api_key_hint})`, c.name));
        });
    }

    const manualOpt = createOption('== Manual Entry ==', 'manual');
    manualOpt.style.fontWeight = 'bold';
    optionsContainer.appendChild(manualOpt);

    triggerText.textContent = defaultText;
    valueInput.value = defaultValue;
    container.querySelector('.custom-option')?.classList.add('selected');

    const filterOption = container.querySelector('.filter-option');
    filterOption.style.display = state.storedCredentials.length > 5 ? 'block' : 'none';
}

/**
 * Populates all credential selector dropdowns on the page.
 */
export function populateAllCredentialSelectors() {
    document.querySelectorAll('.credential-selector-container').forEach(populateCredentialSelector);
}

/**
 * Gets the authentication payload (either from stored creds or manual entry).
 * @param {string} idPrefix - The data-id-prefix of the selector container.
 * @returns {object} The authentication payload.
 * @throws {Error} If master key is not set or no credential is selected.
 */
export function getAuthPayload(idPrefix) {
    if (!state.masterKey) {
        throw new Error("Master Key is not set. Please set it in 'Credential Management'.");
    }

    const container = document.querySelector(`.credential-selector-container[data-id-prefix="${idPrefix}"]`);
    if (!container) {
        throw new Error(`Could not find selector container for prefix '${idPrefix}'.`);
    }

    const valueInput = container.querySelector('.credential-selector-value');
    const selectedValue = valueInput.value;

    if (selectedValue === 'manual') {
        const username = container.querySelector('.credential-username-input').value;
        const password = container.querySelector('.credential-password-input').value;
        if (!username || !password) {
            throw new Error('For manual entry, API Key and Secret are required.');
        }
        return { username, password };
    } else if (selectedValue) {
        return { account_name: selectedValue, master_key: state.masterKey };
    } else {
        throw new Error('Please select a credential or choose "Manual Entry".');
    }
}
// --- END OF FILE static/js/credentials.js ---