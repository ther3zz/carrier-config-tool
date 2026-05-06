"""
Shared task logic for DID inventory operations.

Contains the background task function used by both Flask and FastAPI
to fetch DIDs across multiple Vonage accounts concurrently.

Security notes:
  - Receives pre-decrypted credentials (never stores master key)
  - API key hints are used in results instead of full API keys
  - All data is transient — never persisted to disk or database
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from vendors.vonage import client as vonage_client


def fetch_dids_for_accounts(update_progress, decrypted_creds_list,
                            search_params=None, max_concurrency=5,
                            log_enabled=False):
    """
    Background task that fetches owned DIDs from multiple accounts concurrently.

    Called by job_manager in a background thread. The update_progress callback
    is provided by the job manager to report progress.

    Args:
        update_progress: Callback fn(progress_text, **extra) from job_manager
        decrypted_creds_list: List of dicts, each with:
            - api_key, api_secret, account_name, api_key_hint
        search_params: Optional Vonage search params dict (country, pattern, etc.)
        max_concurrency: Max parallel Vonage API calls
        log_enabled: Whether to log individual API calls

    Returns:
        Aggregated results dict with per-account DID lists.
    """
    results = []
    errors = []
    total = len(decrypted_creds_list)

    update_progress(f"0/{total} accounts queried", accounts_total=total, accounts_completed=0)

    with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
        future_to_creds = {}
        for creds in decrypted_creds_list:
            future = executor.submit(
                vonage_client.list_owned_dids,
                creds['api_key'],
                creds['api_secret'],
                search_params=search_params,
                log_enabled=log_enabled
            )
            future_to_creds[future] = creds

        completed = 0
        for future in as_completed(future_to_creds):
            creds = future_to_creds[future]
            completed += 1
            update_progress(
                f"{completed}/{total} accounts queried",
                accounts_completed=completed
            )

            try:
                data, status_code = future.result()
                if status_code is not None and status_code < 400:
                    numbers = data.get('numbers', [])
                    results.append({
                        "account_name": creds.get('account_name', 'Unknown'),
                        "api_key_hint": creds.get('api_key_hint', ''),
                        "did_count": len(numbers),
                        "numbers": numbers
                    })
                else:
                    errors.append({
                        "account_name": creds.get('account_name', 'Unknown'),
                        "error": data.get('error', 'Unknown API error') if isinstance(data, dict) else str(data)
                    })
            except Exception as e:
                errors.append({
                    "account_name": creds.get('account_name', 'Unknown'),
                    "error": str(e)
                })

    total_dids = sum(r['did_count'] for r in results)

    return {
        "accounts_queried": total,
        "accounts_succeeded": len(results),
        "accounts_failed": len(errors),
        "total_dids": total_dids,
        "results": results,
        "errors": errors
    }
