// --- START OF FILE static/js/utils.js ---

// --- SHARED STATE & CONFIGURATION ---

// App settings will be populated from the backend
export let appSettings = {
    max_concurrent_requests: 5,
    delay_between_batches_ms: 1000,
    store_logs_enabled: false,
    treat_420_as_success_buy: false,
    verify_on_420_buy: false,
    treat_420_as_success_configure: false,
    notifications_enabled: false,
    notifications_webhook_url: '',
    notifications_secret: '',
    notifications_content_type: 'application/json',
    notifications_on_subaccount_created: false,
    notifications_on_did_provisioned: false,
    notifications_on_did_released: false
};

// Global state variables
export let state = {
    masterKey: null,
    storedCredentials: [],
    vonageStoredIps: [],
    vonageStoredUris: [],
    successfullyPurchasedNumbers: [],
    appliedConfiguration: {},
    failedNpaPurchases: [],
    isOperationCancelled: false,
    npaData: {},
    vonagePsipDomains: [],
    vonageSubaccounts: [],
};

// --- CONSTANTS ---

export const countryData = [
    { name: "United States", code: "US", dial: "1" }, { name: "United Kingdom", code: "GB", dial: "44" },
    { name: "Canada", code: "CA", dial: "1" }, { name: "Afghanistan", code: "AF", dial: "93" },
    { name: "Albania", code: "AL", dial: "355" }, { name: "Algeria", code: "DZ", dial: "213" },
    { name: "American Samoa", code: "AS", dial: "1684" }, { name: "Andorra", code: "AD", dial: "376" },
    { name: "Angola", code: "AO", dial: "244" }, { name: "Argentina", code: "AR", dial: "54" },
    { name: "Australia", code: "AU", dial: "61" }, { name: "Austria", code: "AT", dial: "43" },
    { name: "Bahamas", code: "BS", dial: "1242" }, { name: "Bahrain", code: "BH", dial: "973" },
    { name: "Bangladesh", code: "BD", dial: "880" }, { name: "Belgium", code: "BE", dial: "32" },
    { name: "Brazil", code: "BR", dial: "55" }, { name: "China", code: "CN", dial: "86" },
    { name: "Colombia", code: "CO", dial: "57" }, { name: "Egypt", code: "EG", dial: "20" },
    { name: "France", code: "FR", dial: "33" }, { name: "Germany", code: "DE", dial: "49" },
    { name: "India", code: "IN", dial: "91" }, { name: "Indonesia", code: "ID", dial: "62" },
    { name: "Ireland", code: "IE", dial: "353" }, { name: "Israel", code: "IL", dial: "972" },
    { name: "Italy", code: "IT", dial: "39" }, { name: "Japan", code: "JP", dial: "81" },
    { name: "Mexico", code: "MX", dial: "52" }, { name: "Netherlands", code: "NL", dial: "31" },
    { name: "New Zealand", code: "NZ", dial: "64" }, { name: "Nigeria", code: "NG", dial: "234" },
    { name: "Norway", code: "NO", dial: "47" }, { name: "Pakistan", code: "PK", dial: "92" },
    { name: "Philippines", code: "PH", dial: "63" }, { name: "Poland", code: "PL", dial: "48" },
    { name: "Portugal", code: "PT", dial: "351" }, { name: "Russia", code: "RU", dial: "7" },
    { name: "Saudi Arabia", code: "SA", dial: "966" }, { name: "South Africa", code: "ZA", dial: "27" },
    { name: "South Korea", code: "KR", dial: "82" }, { name: "Spain", code: "ES", dial: "34" },
    { name: "Sweden", code: "SE", dial: "46" }, { name: "Switzerland", code: "CH", dial: "41" },
    { name: "Turkey", code: "TR", dial: "90" }, { name: "United Arab Emirates", code: "AE", dial: "971" }
];

export const countryDialingCodes = countryData.reduce((acc, country) => { acc[country.code] = country.dial; return acc; }, {});


// --- API & DATA HANDLING ---

/**
 * A wrapper for the native fetch API to automatically add required headers.
 * @param {string} url - The URL to fetch.
 * @param {object} options - Fetch options (method, body, etc.).
 * @returns {Promise<Response>} A Promise that resolves to the Response object.
 */
export async function apiFetch(url, options = {}) {
    const headers = new Headers(options.headers || {});
    if (appSettings.store_logs_enabled) {
        headers.set('X-Log-Request', 'true');
    }
    if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
        headers.set('Content-Type', 'application/json');
    }
    options.headers = headers;
    return fetch(url, options);
}

/**
 * Processes an array of items in batches, with concurrency and delay controls.
 * @param {Array<any>} items - The items to process.
 * @param {Function} processFn - An async function that processes a single item.
 * @param {Function} updateStatusFn - A function to update the UI with the status of an item.
 * @param {HTMLElement} targetStatusListElement - The container element for status updates.
 * @param {Function} [getItemIdFn=null] - An optional function to derive a unique ID from an item.
 * @returns {Promise<Array<object>>} A promise that resolves to an array of results.
 */
export async function processInBatches(items, processFn, updateStatusFn, targetStatusListElement, getItemIdFn = null) {
    const maxConcurrent = appSettings.max_concurrent_requests;
    const delayBetween = appSettings.delay_between_batches_ms;
    const results = [];
    let itemIndex = 0;

    while (itemIndex < items.length) {
        if (state.isOperationCancelled) {
            console.log("Operation cancelled by user. Halting batch processing.");
            const remainingItems = items.slice(itemIndex);
            remainingItems.forEach((item, idx) => {
                let itemId = (getItemIdFn) ? getItemIdFn(item, itemIndex + idx) : item.msisdn || item.npa || item.id || `item-${itemIndex + idx}`;
                updateStatusFn(itemId, 'Cancelled by user.', 'error', targetStatusListElement);
            });
            break;
        }

        const batch = items.slice(itemIndex, itemIndex + maxConcurrent);

        const batchPromises = batch.map((item, batchIdx) => {
            const overallIndex = itemIndex + batchIdx;
            let itemId = (getItemIdFn) ? getItemIdFn(item, overallIndex) : item.msisdn || item.npa || item.id || `item-${overallIndex}`;
            return processFn(item, overallIndex)
                .then(value => ({ status: 'fulfilled', value, item, itemId }))
                .catch(reason => ({ status: 'rejected', reason, item, itemId }));
        });

        const batchResults = await Promise.all(batchPromises);
        results.push(...batchResults);

        batchResults.forEach(result => {
            if (result.status === 'fulfilled') {
                if (result.value && (result.value.status_code >= 200 && result.value.status_code < 300)) {
                    let successMsg = result.value.message || (result.value.data ? JSON.stringify(result.value.data) : 'Success');
                    if (result.value.country) {
                        successMsg += ` (Country: ${result.value.country})`;
                    }
                    updateStatusFn(result.itemId, successMsg, 'success', targetStatusListElement);
                } else {
                    const errorMsg = result.value.error || (result.value.data ? JSON.stringify(result.value.data) : 'Failed (no error message)');
                    const statusCode = result.value.status_code || 'N/A';
                    updateStatusFn(result.itemId, `Failed: ${errorMsg} (Status: ${statusCode})`, 'error', targetStatusListElement);
                }
            } else {
                const errorMsg = result.reason.message || result.reason.error || 'Network/Parsing Error';
                updateStatusFn(result.itemId, `Failed: ${errorMsg}`, 'error', targetStatusListElement);
            }
        });

        itemIndex += batch.length;

        if (itemIndex < items.length && delayBetween > 0 && !state.isOperationCancelled) {
            console.log(`Waiting ${delayBetween}ms before next batch...`);
            // Add a visual indicator for the delay
            const lastProcessedItemResult = results[results.length - 1];
            const lastItemWasSuccess = lastProcessedItemResult && lastProcessedItemResult.status === 'fulfilled' && lastProcessedItemResult.value.status_code >= 200 && lastProcessedItemResult.value.status_code < 300;
            if (lastItemWasSuccess) {
                const lastProcessedItemId = lastProcessedItemResult.itemId;
                const statusElement = targetStatusListElement.querySelector(`li[data-status-id="${lastProcessedItemId}"] span:last-child`);
                if (statusElement) {
                    const originalText = statusElement.textContent;
                    updateStatusFn(lastProcessedItemId, `${originalText} (Delaying ${delayBetween / 1000}s...)`, 'pending', targetStatusListElement);
                    await sleep(delayBetween);
                    updateStatusFn(lastProcessedItemId, originalText, 'success', targetStatusListElement);
                } else {
                     await sleep(delayBetween);
                }
            } else {
                 await sleep(delayBetween);
            }
        }
    }
    return results;
}


// --- GENERIC HELPER FUNCTIONS ---

export const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

export function formatMsisdnForApi(msisdn, country) {
    let msisdnForApi = String(msisdn).replace(/\D/g, '');
    if (country.toUpperCase() === 'US' || country.toUpperCase() === 'CA') {
        if (msisdnForApi.length === 10) {
            msisdnForApi = '1' + msisdnForApi;
        }
    }
    return msisdnForApi;
}

export function getNationalNumber(msisdn, country) {
    let nationalNum = String(msisdn).replace(/\D/g, '');
    const countryCodeUpper = country.toUpperCase();
    const dialingCode = countryDialingCodes[countryCodeUpper];
    if (dialingCode && nationalNum.startsWith(dialingCode)) {
        return nationalNum.substring(dialingCode.length);
    }
    if ((countryCodeUpper === 'US' || countryCodeUpper === 'CA') && nationalNum.length === 11 && nationalNum.startsWith('1')) {
        return nationalNum.substring(1);
    }
    return nationalNum;
}
// --- END OF FILE static/js/utils.js ---