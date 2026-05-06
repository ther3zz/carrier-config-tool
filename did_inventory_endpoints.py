"""
FastAPI endpoints for programmatic DID inventory queries.

Separated from fastapi_app.py for modularity. Uses APIRouter to be included
in the main FastAPI app via app.include_router().

Endpoints:
  - GET  /list-account-dids?groupid=xxx     — Single account, synchronous
  - POST /list-all-dids                       — Start async inventory job
  - GET  /list-all-dids/{job_id}              — Poll job status

Security:
  - API key + IP whitelist authentication (inherited from main app dependencies)
  - Uses server-side MASTER_KEY (no secrets in request bodies)
  - API key hints in responses, never full keys
  - Job results auto-expire after 10 minutes
"""

import os
import asyncio
from fastapi import APIRouter, HTTPException, status, Query
from pydantic import BaseModel, Field
from typing import Optional, List

from utils import credentials_manager
from utils import settings_manager
from utils import job_manager
from utils import encryption
from vendors.vonage import client as vonage_client
from vendors.vonage.did_inventory_tasks import fetch_dids_for_accounts

# --- Configuration ---
MASTER_KEY = os.environ.get("MASTER_KEY")

# --- Router Setup ---
inventory_router = APIRouter(tags=["Inventory"])


# --- Pydantic Models ---

class InventoryJobRequest(BaseModel):
    """Request body for starting an async DID inventory job."""
    scope: str = Field(
        "all",
        description="'all' to query every stored account, or 'selected' to specify groupids."
    )
    groupids: Optional[List[str]] = Field(
        None,
        description="List of groupids to query. Required when scope='selected'."
    )
    country: Optional[str] = Field(
        None,
        description="Optional 2-letter ISO country code to filter DIDs.",
        min_length=2, max_length=2
    )
    pattern: Optional[str] = Field(
        None,
        description="Optional number pattern to filter by."
    )
    search_pattern: Optional[int] = Field(
        None,
        description="0=starts with pattern, 1=contains, 2=ends with."
    )


class InventoryJobResponse(BaseModel):
    job_id: str
    status: str
    accounts_total: int


class SingleAccountDIDResponse(BaseModel):
    groupid: str
    account_name: str
    api_key_hint: str
    total_count: int
    numbers: list


# --- Helper Functions ---

def _ensure_master_key():
    """Raises HTTPException if MASTER_KEY is not configured."""
    if not MASTER_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MASTER_KEY is not configured on the server."
        )


def _build_search_params(country=None, pattern=None, search_pattern=None):
    """Builds Vonage search params dict from optional query/body values."""
    params = {}
    if country:
        params['country'] = country.upper()
    if pattern:
        params['pattern'] = pattern
    if search_pattern is not None:
        params['search_pattern'] = search_pattern
    return params if params else None


def _decrypt_all_credentials():
    """Decrypts all stored credentials using the server-side MASTER_KEY."""
    _ensure_master_key()
    all_creds = credentials_manager.get_all_credentials()
    decrypted = []

    for name, cred_data in all_creds.items():
        try:
            encrypted_secret = cred_data.get('encrypted_secret')
            if not encrypted_secret:
                continue
            decrypted_secret = encryption.decrypt_data(encrypted_secret, MASTER_KEY)
            decrypted.append({
                'api_key': cred_data['api_key'],
                'api_secret': decrypted_secret,
                'account_name': name,
                'api_key_hint': cred_data.get('api_key_hint', '')
            })
        except Exception:
            continue

    return decrypted


def _decrypt_selected_credentials(groupids):
    """Decrypts credentials for specific groupids using MASTER_KEY."""
    _ensure_master_key()
    decrypted = []

    for gid in groupids:
        try:
            creds = credentials_manager.find_and_decrypt_credential_by_groupid(gid, MASTER_KEY)
            api_key = creds['api_key']
            decrypted.append({
                'api_key': api_key,
                'api_secret': creds['api_secret'],
                'account_name': creds.get('account_name', f'GroupId [{gid}]'),
                'api_key_hint': f"{api_key[:5]}...{api_key[-4:]}" if len(api_key) > 8 else api_key
            })
        except Exception:
            # Skip groupids that can't be resolved
            continue

    return decrypted


# --- Endpoints ---

@inventory_router.get(
    "/list-account-dids",
    response_model=SingleAccountDIDResponse,
    summary="List DIDs for a single account by groupid (synchronous)"
)
async def list_account_dids(
    groupid: str = Query(..., description="The groupid to look up."),
    country: Optional[str] = Query(None, min_length=2, max_length=2),
    pattern: Optional[str] = Query(None),
    search_pattern: Optional[int] = Query(None)
):
    """
    Returns all DIDs owned by the account matching the given groupid.
    Synchronous — suitable for single-account queries.
    """
    if credentials_manager.STORAGE_MODE != 'db':
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Endpoint not available in 'file' storage mode."
        )

    _ensure_master_key()
    log_enabled = settings_manager.get_setting('store_logs_enabled')

    try:
        creds = credentials_manager.find_and_decrypt_credential_by_groupid(groupid, MASTER_KEY)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No credential found for groupid '{groupid}': {e}"
        )

    search_params = _build_search_params(country, pattern, search_pattern)

    result, api_status = await asyncio.to_thread(
        vonage_client.list_owned_dids,
        creds['api_key'],
        creds['api_secret'],
        search_params=search_params,
        log_enabled=log_enabled
    )

    if api_status >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Vonage API error: {result.get('error', 'Unknown')}"
        )

    api_key = creds['api_key']
    api_key_hint = f"{api_key[:5]}...{api_key[-4:]}" if len(api_key) > 8 else api_key

    return SingleAccountDIDResponse(
        groupid=groupid,
        account_name=creds.get('account_name', ''),
        api_key_hint=api_key_hint,
        total_count=result.get('total_fetched', 0),
        numbers=result.get('numbers', [])
    )


@inventory_router.post(
    "/list-all-dids",
    response_model=InventoryJobResponse,
    summary="Start an async job to list DIDs across accounts",
    status_code=202
)
async def start_list_all_dids(request: InventoryJobRequest):
    """
    Starts a background job to fetch DIDs across all or selected accounts.

    Returns a job_id. Poll GET /list-all-dids/{job_id} for results.
    """
    if credentials_manager.STORAGE_MODE != 'db':
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Endpoint not available in 'file' storage mode."
        )

    _ensure_master_key()

    # Validate scope
    if request.scope not in ('all', 'selected'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="scope must be 'all' or 'selected'."
        )

    # Decrypt credentials based on scope
    if request.scope == 'selected':
        if not request.groupids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="'groupids' list is required when scope is 'selected'."
            )
        decrypted_creds = _decrypt_selected_credentials(request.groupids)
    else:
        decrypted_creds = _decrypt_all_credentials()

    if not decrypted_creds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No credentials could be decrypted."
        )

    search_params = _build_search_params(request.country, request.pattern, request.search_pattern)
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
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=error)

    return InventoryJobResponse(
        job_id=job_id,
        status="pending",
        accounts_total=len(decrypted_creds)
    )


@inventory_router.get(
    "/list-all-dids/{job_id}",
    summary="Poll status of an async DID inventory job"
)
async def get_list_all_dids_status(job_id: str):
    """
    Returns the current status of an inventory job.
    When completed, includes the full DID results.
    Jobs auto-expire after 10 minutes.
    """
    job = job_manager.get_job(job_id)

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found or expired."
        )

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

    return response
