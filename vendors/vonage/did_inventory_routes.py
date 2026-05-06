"""
Flask Blueprint for DID inventory operations.

Provides endpoints for the UI to:
  - List DIDs for a single account (synchronous)
  - Start an async job to list DIDs across all stored accounts
  - Poll the status of an async inventory job

Security:
  - Master key required for every request (decrypts credentials in-memory only)
  - API key hints returned in responses instead of full keys
  - No DID data is persisted — results are fetched live from Vonage
  - Job results auto-expire after 10 minutes
"""

from flask import Blueprint, request, jsonify
from utils import credentials_manager
from utils import settings_manager
from utils import encryption
from utils import job_manager
from . import client as vonage_client
from .did_inventory_tasks import fetch_dids_for_accounts

vonage_did_inventory_bp = Blueprint(
    'vonage_did_inventory', __name__,
    url_prefix='/api/vonage/dids/inventory'
)


def _build_search_params(data):
    """Extracts optional Vonage search params from the request payload."""
    params = {}
    if data.get('country'):
        params['country'] = data['country'].upper()
    if data.get('pattern'):
        params['pattern'] = data['pattern']
    search_pattern = data.get('search_pattern')
    if search_pattern is not None and str(search_pattern).strip() != '':
        params['search_pattern'] = int(search_pattern)
    return params if params else None


def _decrypt_all_credentials(master_key):
    """
    Decrypts all stored credentials and returns a list of dicts.

    Each dict contains: api_key, api_secret, account_name, api_key_hint.
    Credentials that fail decryption are silently skipped.
    The master key is NOT stored — only used transiently here.
    """
    all_creds = credentials_manager.get_all_credentials()
    decrypted = []

    for name, cred_data in all_creds.items():
        try:
            encrypted_secret = cred_data.get('encrypted_secret')
            if not encrypted_secret:
                continue
            decrypted_secret = encryption.decrypt_data(encrypted_secret, master_key)
            decrypted.append({
                'api_key': cred_data['api_key'],
                'api_secret': decrypted_secret,
                'account_name': name,
                'api_key_hint': cred_data.get('api_key_hint', '')
            })
        except Exception:
            # Skip credentials that can't be decrypted
            continue

    return decrypted


# --- Synchronous: Single Account ---

@vonage_did_inventory_bp.route('/single', methods=['POST'])
def list_dids_single():
    """
    Lists all DIDs owned by a single account. Synchronous response.

    Expects standard auth payload (account_name + master_key, or manual username/password).
    Optional filters: country, pattern, search_pattern.
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON payload"}), 400

    try:
        master_key = data.get('master_key')
        account_name = data.get('account_name')

        if account_name and account_name != 'manual':
            if not master_key:
                raise ValueError("Master Key is required.")
            creds = credentials_manager.get_decrypted_credentials(account_name, master_key)
            api_key = creds['api_key']
            api_secret = creds['api_secret']
            display_name = account_name
        else:
            api_key = data.get('username')
            api_secret = data.get('password')
            if not api_key or not api_secret:
                raise ValueError("API Key and Secret are required for manual entry.")
            display_name = "Manual Entry"

        log_enabled = settings_manager.get_setting('store_logs_enabled')
        search_params = _build_search_params(data)

        result, status_code = vonage_client.list_owned_dids(
            username=api_key,
            password=api_secret,
            search_params=search_params,
            log_enabled=log_enabled
        )

        if status_code >= 400:
            return jsonify(result), status_code

        # Build response with api_key hint instead of full key
        api_key_hint = f"{api_key[:5]}...{api_key[-4:]}" if len(api_key) > 8 else api_key

        response = {
            "account_name": display_name,
            "api_key_hint": api_key_hint,
            "total_count": result.get('total_fetched', 0),
            "numbers": result.get('numbers', [])
        }

        return jsonify(response), 200

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500


# --- Async: All Accounts ---

@vonage_did_inventory_bp.route('/start', methods=['POST'])
def start_inventory_job():
    """
    Starts an async background job to fetch DIDs from all stored accounts.

    Decrypts all credentials immediately (master key is NOT stored in the job),
    then spawns a background thread to query each account via Vonage API.

    Returns a job_id that can be polled via the /status/<job_id> endpoint.
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON payload"}), 400

    master_key = data.get('master_key')
    if not master_key:
        return jsonify({"error": "Master Key is required."}), 400

    try:
        # Decrypt all credentials NOW — master key is not stored in the job
        decrypted_creds = _decrypt_all_credentials(master_key)

        if not decrypted_creds:
            return jsonify({
                "error": "No credentials could be decrypted. Check your Master Key."
            }), 400

        search_params = _build_search_params(data)
        log_enabled = settings_manager.get_setting('store_logs_enabled')
        max_concurrency = int(settings_manager.get_setting('max_concurrent_requests', 5))

        job_id, error = job_manager.create_job(
            fetch_dids_for_accounts,
            decrypted_creds,
            search_params=search_params,
            max_concurrency=max_concurrency,
            log_enabled=log_enabled
        )

        if error:
            return jsonify({"error": error}), 429

        return jsonify({
            "job_id": job_id,
            "status": "pending",
            "accounts_total": len(decrypted_creds)
        }), 202

    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500


@vonage_did_inventory_bp.route('/status/<job_id>', methods=['GET'])
def get_inventory_status(job_id):
    """
    Polls the status of an async inventory job.

    Returns the current status and, when completed, the full results.
    Jobs auto-expire after 10 minutes.
    """
    job = job_manager.get_job(job_id)

    if job is None:
        return jsonify({"error": "Job not found or expired."}), 404

    response = {
        "job_id": job_id,
        "status": job["status"],
        "progress": job.get("progress", ""),
        "accounts_total": job.get("accounts_total", 0),
        "accounts_completed": job.get("accounts_completed", 0),
    }

    if job["status"] == "completed":
        response["results"] = job["results"]
    elif job["status"] == "failed":
        response["error"] = job.get("error", "Unknown error")

    return jsonify(response), 200
