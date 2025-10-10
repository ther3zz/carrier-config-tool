// --- START OF FILE static/js/ui.js ---
import { state, countryData } from './utils.js';

// --- TABS & ACCORDIONS ---

export function openOuterTab(evt, tabName) {
    let i, tabcontent, tablinks;
    tabcontent = document.getElementsByClassName("tab-content");
    for (i = 0; i < tabcontent.length; i++) {
        tabcontent[i].style.display = "none";
    }
    tablinks = document.getElementsByClassName("tab-link");
    for (i = 0; i < tablinks.length; i++) {
        tablinks[i].className = tablinks[i].className.replace(" active", "");
    }
    const targetTab = document.getElementById(tabName);
    if (targetTab) {
        targetTab.style.display = "block";
    } else {
        console.error("Target outer tab not found:", tabName);
        if (tabcontent.length > 0) tabcontent[0].style.display = "block";
        if (tablinks.length > 0) tablinks[0].className += " active";
        return;
    }
    evt.currentTarget.className += " active";
    clearResponse();
    closeAllAccordions(targetTab);
}

export function openInnerTab(evt, tabName, clickedElement) {
    const parentActionContent = clickedElement.closest('.action-content');
    if (!parentActionContent) return;
    let i, tabcontent, tablinks;
    tabcontent = parentActionContent.getElementsByClassName("inner-tab-content");
    for (i = 0; i < tabcontent.length; i++) {
        tabcontent[i].style.display = "none";
    }
    tablinks = parentActionContent.getElementsByClassName("inner-tab-link");
    for (i = 0; i < tablinks.length; i++) {
        tablinks[i].className = tablinks[i].className.replace(" active", "");
    }
    const targetTab = parentActionContent.querySelector(`#${tabName}`);
    if (targetTab) {
        targetTab.style.display = "block";
        clickedElement.className += " active";
        clearResponse();
    } else {
        console.error("Target inner tab content not found:", tabName);
    }
}

export function setupAccordionBehavior() {
    const accordions = document.querySelectorAll('.accordion');
    accordions.forEach(accordion => {
        const mainDetailsElements = accordion.querySelectorAll(':scope > details');
        mainDetailsElements.forEach(details => {
            details.addEventListener('toggle', (event) => {
                if (details.open && event.target === details) {
                    // Close sibling accordions
                    mainDetailsElements.forEach(sibling => {
                        if (sibling !== details && sibling.open) {
                            sibling.removeAttribute('open');
                        }
                    });

                    // If it has inner tabs, ensure the first one is active
                    if (details.querySelector('.inner-tabs')) {
                        const firstInnerTabLink = details.querySelector('.inner-tab-link');
                        const firstInnerTabContentId = firstInnerTabLink?.getAttribute('onclick').match(/'([^']+)'/)[1];
                        const firstInnerTabContent = details.querySelector(`#${firstInnerTabContentId}`);
                        if (firstInnerTabLink && firstInnerTabContent && !firstInnerTabLink.classList.contains('active')) {
                             openInnerTab({ currentTarget: firstInnerTabLink }, firstInnerTabContent.id, firstInnerTabLink);
                        }
                    }
                }
            });
        });
    });
}

function closeAllAccordions(parentElement) {
    parentElement.querySelectorAll('.accordion > details').forEach(details => {
        details.removeAttribute('open');
    });
}


// --- MODALS (Settings, Country Codes) ---

export function setupModalHandlers() {
    const settingsModal = document.getElementById('settingsModal');
    const countryModal = document.getElementById('countryCodesModal');

    // Close buttons
    document.getElementById('settingsModalClose')?.addEventListener('click', () => { settingsModal.style.display = 'none' });
    document.getElementById('cancelSettingsButton')?.addEventListener('click', () => { settingsModal.style.display = 'none' });
    document.getElementById('countryCodesModalClose')?.addEventListener('click', () => { countryModal.style.display = 'none'; });

    // Click outside to close
    window.addEventListener('click', e => {
        if (e.target === settingsModal) settingsModal.style.display = 'none';
        if (e.target === countryModal) countryModal.style.display = 'none';
    });

    // Country code modal triggers
    document.querySelectorAll('.showCountryCodesBtn').forEach(btn => {
        btn.addEventListener('click', () => {
            countryModal.style.display = 'block';
        });
    });

    // Populate and add search to country code modal
    const countryCodeList = document.getElementById('countryCodesList');
    if (countryCodeList) {
        countryCodeList.innerHTML = `<ul style="list-style-type:none;padding:0;">${countryData.sort((a,b)=>a.name.localeCompare(b.name)).map(c=>`<li data-country-name="${c.name.toLowerCase()}" style="padding:5px;border-bottom:1px solid #eee;">${c.name} (<strong>${c.code}</strong>) - +${c.dial}</li>`).join('')}</ul>`;
    }
    document.getElementById('countryCodeSearch')?.addEventListener('keyup', e => {
        const filter = e.target.value.toLowerCase();
        const items = document.getElementById('countryCodesList').getElementsByTagName('li');
        for (let i = 0; i < items.length; i++) {
            items[i].style.display = items[i].textContent.toLowerCase().includes(filter) ? "" : "none";
        }
    });
}


// --- RESPONSE & STATUS DISPLAY ---

export function displayResponse(message, type = '', isHtml = false) {
    const area = document.getElementById('response');
    if (!area) return;
    area.style.display = 'block';
    area.className = type;
    if (isHtml) {
        area.innerHTML = message;
    } else {
        area.textContent = message;
    }
    area.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

export function clearResponse() {
    const area = document.getElementById('response');
    if (area) {
        area.style.display = 'none';
        area.textContent = '';
        area.innerHTML = '';
        area.className = '';
    }
}

export function handleBackendResponse(data) {
    if (data.error) {
        let msg = `Error: ${data.error}\n`;
        if(data.status_code) msg += `Status Code: ${data.status_code}\n`;
        if(data.response_data_json && Object.keys(data.response_data_json).length > 0) {
            msg += "API Error (JSON):\n" + JSON.stringify(data.response_data_json, null, 2);
        } else if (data.response_data_text) {
            msg += "API Error (Text):\n" + data.response_data_text;
        } else if (data.data && typeof data.data === 'object' && data.data.error) {
            msg += "Details: " + data.data.error;
        } else if (data.data && typeof data.data === 'string') {
            msg += "Details: " + data.data;
        }
        displayResponse(msg, 'error');
    } else {
        let msg = `Success! Status: ${data.status_code || 'N/A'}\n\n`;
        if (data.message) {
            msg = `${data.message}\nStatus Code: ${data.status_code || 'N/A'}\n\n`;
        }
        if (data.data && Object.keys(data.data).length > 0 && JSON.stringify(data.data) !== '{}') {
            msg += "Response:\n" + JSON.stringify(data.data, null, 2);
        }
        displayResponse(msg, 'success');
    }
}

export function handleFetchError(error, operation = 'request') {
    console.error(`Error during ${operation}:`, error);
    displayResponse(`Error: Could not connect to the backend or network issue during ${operation}.\n\n${error.message}`, 'error');
}

export function addOrUpdateOperationStatus(id, text, statusClass, listEl) {
    if (!listEl) return;
    let li = listEl.querySelector(`li[data-status-id="${id}"]`);
    let prefix = String(id).startsWith('NPA-FIND-') ? `NPA ${String(id).substring(9)} (Find): ` : `${id}: `;

    if (!li) {
        li = document.createElement('li');
        li.dataset.statusId = id;
        const idSpan = document.createElement('span');
        idSpan.textContent = prefix;
        idSpan.style.fontWeight = 'bold';
        const statusSpan = document.createElement('span');
        li.appendChild(idSpan);
        li.appendChild(statusSpan);
        listEl.appendChild(li);
    }

    const statusSpan = li.querySelector('span:last-child');
    if (statusSpan) {
        statusSpan.textContent = text;
        statusSpan.className = `status-${statusClass}`;
    }
}


// --- OPERATION CONTROLS ---

export function toggleOperationControls(operationName, isStarting) {
    const controls = {
        individual: { startBtn: document.getElementById('vonage_purchase_button'), stopBtn: document.getElementById('stop_individual_purchase_button'), },
        bulk: { startBtn: document.getElementById('vonage_bulk_npa_purchase_button'), stopBtn: document.getElementById('stop_bulk_purchase_button'), reattemptBtn: document.getElementById('vonage_reattempt_npa_button') },
        configure: { startBtn: document.getElementById('vonage_configure_button'), stopBtn: document.getElementById('stop_configure_button'), },
        modify: { startBtn: document.querySelector('#vonageModifyDidForm button[type="submit"]'), stopBtn: document.getElementById('stop_modify_button'), },
        release: { startBtn: document.querySelector('#vonageReleaseDidForm button[type="submit"]'), stopBtn: document.getElementById('stop_release_button'), }
    };

    const op = controls[operationName];
    if (!op) return;

    if (isStarting) {
        state.isOperationCancelled = false;
        if (op.startBtn) op.startBtn.style.display = 'none';
        if (op.stopBtn) {
            op.stopBtn.style.display = 'inline-block';
            op.stopBtn.disabled = false;
            op.stopBtn.textContent = (operationName === 'configure') ? 'Stop Configuration' : (operationName === 'modify') ? 'Stop Update' : (operationName === 'release') ? 'Stop Release' : 'Stop Purchase';
        }
        if (op.reattemptBtn) op.reattemptBtn.style.display = 'none';
    } else {
        if (op.startBtn) op.startBtn.style.display = 'inline-block';
        if (op.stopBtn) op.stopBtn.style.display = 'none';
        if (op.reattemptBtn) {
            if (state.failedNpaPurchases.length > 0) {
                const totalFailed = state.failedNpaPurchases.reduce((sum, item) => sum + item.quantity, 0);
                op.reattemptBtn.textContent = `Re-attempt ${totalFailed} Failed Purchase(s)`;
                op.reattemptBtn.style.display = 'inline-block';
                op.reattemptBtn.disabled = false;
            } else {
                op.reattemptBtn.style.display = 'none';
            }
        }
    }
}

export function stopAllOperations() {
    state.isOperationCancelled = true;
    console.log("Stop requested. isOperationCancelled set to true.");
    document.querySelectorAll('.stop-button').forEach(btn => {
        if (btn.style.display !== 'none') {
            btn.disabled = true;
            btn.textContent = 'Stopping...';
        }
    });
    displayResponse("Stop requested. The current batch of requests will finish, then the process will halt.", 'pending');
}
// --- END OF FILE static/js/ui.js ---