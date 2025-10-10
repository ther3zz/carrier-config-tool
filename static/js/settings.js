// --- START OF FILE static/js/settings.js ---
import { apiFetch, appSettings } from './utils.js';
import { displayResponse, handleFetchError } from './ui.js';

const settingsModal = document.getElementById('settingsModal');

/**
 * Opens the settings modal and populates it with the latest settings.
 */
export async function openSettingsModal() {
    try {
        const response = await apiFetch('/api/settings');
        const latestSettings = await response.json();
        if (response.ok) {
            // Update the global settings object with the latest from the server
            Object.assign(appSettings, latestSettings);
        } else {
            throw new Error(latestSettings.error || "Failed to fetch settings");
        }
    } catch (error) {
        console.error("Could not fetch latest settings:", error);
        displayResponse(`Error: Could not load settings from database. Displaying last known values.`, 'error');
    }

    // Populate the form with current settings
    document.getElementById('maxConcurrentRequests').value = appSettings.max_concurrent_requests;
    document.getElementById('delayBetweenBatches').value = appSettings.delay_between_batches_ms;
    document.getElementById('storeLogsToggle').checked = String(appSettings.store_logs_enabled).toLowerCase() === 'true';
    document.getElementById('treat420AsSuccess_buy').checked = String(appSettings.treat_420_as_success_buy).toLowerCase() === 'true';
    document.getElementById('verifyOn420_buy').checked = String(appSettings.verify_on_420_buy).toLowerCase() === 'true';
    document.getElementById('treat420AsSuccess_configure').checked = String(appSettings.treat_420_as_success_configure).toLowerCase() === 'true';

    // Notifications
    const notifToggle = document.getElementById('notificationsEnabledToggle');
    notifToggle.checked = String(appSettings.notifications_enabled).toLowerCase() === 'true';
    document.getElementById('notificationsWebhookUrl').value = appSettings.notifications_webhook_url || '';
    document.getElementById('notificationsSecret').value = appSettings.notifications_secret || '';
    document.getElementById('notificationsContentType').value = appSettings.notifications_content_type || 'application/json';
    document.getElementById('notificationsOnSubaccountCreated').checked = String(appSettings.notifications_on_subaccount_created).toLowerCase() === 'true';
    document.getElementById('notificationsOnDidProvisioned').checked = String(appSettings.notifications_on_did_provisioned).toLowerCase() === 'true';
    document.getElementById('notificationsOnDidReleased').checked = String(appSettings.notifications_on_did_released).toLowerCase() === 'true';

    toggleNotificationDetails();
    settingsModal.style.display = 'block';
}

/**
 * Saves the settings from the modal form to the backend.
 */
export async function saveSettings() {
    const newSettings = {
        max_concurrent_requests: parseInt(document.getElementById('maxConcurrentRequests').value, 10),
        delay_between_batches_ms: parseInt(document.getElementById('delayBetweenBatches').value, 10),
        store_logs_enabled: document.getElementById('storeLogsToggle').checked,
        treat_420_as_success_buy: document.getElementById('treat420AsSuccess_buy').checked,
        verify_on_420_buy: document.getElementById('verifyOn420_buy').checked,
        treat_420_as_success_configure: document.getElementById('treat420AsSuccess_configure').checked,
        notifications_enabled: document.getElementById('notificationsEnabledToggle').checked,
        notifications_webhook_url: document.getElementById('notificationsWebhookUrl').value,
        notifications_secret: document.getElementById('notificationsSecret').value,
        notifications_content_type: document.getElementById('notificationsContentType').value,
        notifications_on_subaccount_created: document.getElementById('notificationsOnSubaccountCreated').checked,
        notifications_on_did_provisioned: document.getElementById('notificationsOnDidProvisioned').checked,
        notifications_on_did_released: document.getElementById('notificationsOnDidReleased').checked
    };

    try {
        const response = await apiFetch('/api/settings', {
            method: 'POST',
            body: JSON.stringify(newSettings)
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Failed to save");
        
        // Update the global settings object on successful save
        Object.assign(appSettings, newSettings);

        settingsModal.style.display = 'none';
        displayResponse('Settings saved to database!', 'success');
    } catch (error) {
        console.error("Failed to save settings:", error);
        displayResponse(`Error saving settings: ${error.message}`, 'error');
    }
}

/**
 * Sends a test webhook notification.
 */
export async function sendTestWebhook() {
    displayResponse('Sending test webhook...', 'pending');
    try {
        const response = await apiFetch('/api/notifications/test', { method: 'POST' });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Failed to send test notification.");
        displayResponse(data.message, 'success');
    } catch (error) {
        handleFetchError(error, 'Test Webhook');
    }
}

/**
 * Triggers the download of server logs.
 */
export function downloadLogs() {
    window.location.href = '/api/logs/download';
}

/**
 * Clears all log files on the server.
 */
export function clearLogs() {
    if (confirm('Are you sure you want to permanently delete all log files on the server?')) {
        apiFetch('/api/logs/clear', { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                if (data.error) {
                    displayResponse(`Error: ${data.error}`, 'error');
                } else {
                    displayResponse('All log files have been cleared successfully.', 'success');
                }
            })
            .catch(e => displayResponse(`Failed to clear logs: ${e.message}`, 'error'));
    }
}

/**
 * Toggles the visibility of notification details based on the master toggle.
 */
function toggleNotificationDetails() {
    const notifToggle = document.getElementById('notificationsEnabledToggle');
    const notifDetails = document.getElementById('notificationSettingsDetails');
    notifDetails.style.display = notifToggle.checked ? 'block' : 'none';
}

/**
 * Sets up initial event listeners for the settings modal.
 */
export function setupSettingsEventListeners() {
    document.getElementById('settingsGearIcon')?.addEventListener('click', openSettingsModal);
    document.getElementById('saveSettingsButton')?.addEventListener('click', saveSettings);
    document.getElementById('testWebhookButton')?.addEventListener('click', sendTestWebhook);
    document.getElementById('downloadLogsButton')?.addEventListener('click', downloadLogs);
    document.getElementById('clearLogsButton')?.addEventListener('click', clearLogs);

    // Link 420 handling checkboxes
    document.getElementById('treat420AsSuccess_buy')?.addEventListener('change', e => {
        if (e.target.checked) document.getElementById('verifyOn420_buy').checked = false;
    });
    document.getElementById('verifyOn420_buy')?.addEventListener('change', e => {
        if (e.target.checked) document.getElementById('treat420AsSuccess_buy').checked = false;
    });

    document.getElementById('notificationsEnabledToggle')?.addEventListener('change', toggleNotificationDetails);
}
// --- END OF FILE static/js/settings.js ---