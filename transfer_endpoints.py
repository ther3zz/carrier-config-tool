"""
FastAPI endpoints for programmatic DID transfer between Vonage subaccounts.

Separated from fastapi_app.py for modularity. Uses APIRouter to be included
in the main FastAPI app via app.include_router().

Security:
  - API key + IP whitelist authentication (inherited from main app dependencies)
  - GroupID-based credential resolution (never exposes raw API keys in requests)
  - Pre-transfer ownership verification on source subaccount
  - Mandatory audit logging regardless of user settings
"""

import asyncio
import re
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List

from utils import credentials_manager
from utils import settings_manager
from utils import notification_service
from utils.config_loader import load_config_file
from vendors.vonage import client as vonage_client

import os

# --- Configuration ---
NPA_DATA_CONFIG_FILE = os.path.join('config', 'npa_data.json')
NPA_DATA = load_config_file(NPA_DATA_CONFIG_FILE)

MASTER_KEY = os.environ.get("MASTER_KEY")
VONAGE_PRIMARY_ACCOUNT_NAME = os.environ.get("VONAGE_PRIMARY_ACCOUNT_NAME")

# --- Router Setup ---
# Dependencies are injected when included in the main app
transfer_router = APIRouter(tags=["Transfer"])

# --- Pydantic Models ---

class DIDTransferRequest(BaseModel):
    from_groupid: str = Field(
        ...,
        description="The group ID of the source subaccount (the current owner of the number)."
    )
    to_groupid: str = Field(
        ...,
        description="The group ID of the destination subaccount (the new owner)."
    )
    number: str = Field(
        ...,
        description="The phone number (DID) to transfer.",
        pattern=r'^\d{10,15}$'
    )
    country: Optional[str] = Field(
        None,
        description="Optional 2-letter ISO country code. Auto-detected for US/CA if omitted.",
        min_length=2,
        max_length=2
    )

    @field_validator('country')
    def uppercase_country(cls, v):
        if v is not None:
            return v.upper()
        return v


class DIDTransferResponse(BaseModel):
    status: str = "success"
    message: str
    number: str
    from_subaccount_name: str
    from_subaccount_api_key: str
    to_subaccount_name: str
    to_subaccount_api_key: str


class DIDBatchTransferItem(BaseModel):
    number: str = Field(..., description="The phone number to transfer.", pattern=r'^\d{10,15}$')
    country: Optional[str] = Field(None, min_length=2, max_length=2)


class DIDBatchTransferRequest(BaseModel):
    from_groupid: str = Field(..., description="The group ID of the source subaccount.")
    to_groupid: str = Field(..., description="The group ID of the destination subaccount.")
    numbers: List[DIDBatchTransferItem] = Field(
        ...,
        description="List of numbers to transfer.",
        min_length=1
    )


class BatchTransferResult(BaseModel):
    number: str
    status: str
    detail: str


class DIDBatchTransferResponse(BaseModel):
    message: str
    total_processed: int
    success_count: int
    failed_count: int
    results: List[BatchTransferResult]


# --- Helper Functions ---

def _detect_country(msisdn: str) -> Optional[str]:
    """Auto-detect US/CA country from NPA for 10/11-digit numbers."""
    clean = re.sub(r'\D', '', msisdn)
    national = clean[-10:] if len(clean) >= 10 else clean
    if len(national) == 10:
        npa = national[:3]
        if npa in NPA_DATA.get('US', []):
            return 'US'
        elif npa in NPA_DATA.get('CA', []):
            return 'CA'
    return None


def _resolve_groupid(groupid: str) -> dict:
    """
    Resolves a group ID to its decrypted credentials.
    Raises HTTPException on failure.
    """
    if not MASTER_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MASTER_KEY is not configured on the server."
        )
    try:
        return credentials_manager.find_and_decrypt_credential_by_groupid(groupid, MASTER_KEY)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No credential found for groupid '{groupid}': {e}"
        )


def _get_primary_creds() -> dict:
    """Loads and decrypts the primary account credentials."""
    if not VONAGE_PRIMARY_ACCOUNT_NAME:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="VONAGE_PRIMARY_ACCOUNT_NAME is not configured. Number transfers require a primary account."
        )
    try:
        return credentials_manager.get_decrypted_credentials(VONAGE_PRIMARY_ACCOUNT_NAME, MASTER_KEY)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not load primary account credentials: {e}"
        )


# --- Endpoints ---

@transfer_router.post(
    "/transfer-number",
    response_model=DIDTransferResponse,
    summary="Transfer a single number between subaccounts"
)
async def transfer_number_endpoint(request: DIDTransferRequest, request_obj: Request):
    """
    Transfers a single phone number from one subaccount to another.
    Both subaccounts must be under the same primary account.
    """
    if credentials_manager.STORAGE_MODE != 'db':
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Endpoint not available in 'file' storage mode."
        )

    log_enabled = settings_manager.get_setting('store_logs_enabled')

    # --- Resolve credentials ---
    from_creds = _resolve_groupid(request.from_groupid)
    to_creds = _resolve_groupid(request.to_groupid)
    primary_creds = _get_primary_creds()

    if from_creds['api_key'] == to_creds['api_key']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Source and destination subaccounts cannot be the same."
        )

    # --- Determine country ---
    country = request.country
    msisdn = re.sub(r'\D', '', request.number)
    if not country:
        country = _detect_country(msisdn)
        if not country:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not auto-detect country. Please provide a 2-letter 'country' code."
            )
    # Ensure MSISDN has country prefix for US/CA
    if country in ('US', 'CA') and len(msisdn) == 10:
        msisdn = '1' + msisdn

    # --- Pre-transfer ownership verification ---
    is_owned, _ = await asyncio.to_thread(
        vonage_client._verify_did_ownership,
        username=from_creds['api_key'],
        password=from_creds['api_secret'],
        msisdn=msisdn,
        log_enabled=log_enabled
    )
    if not is_owned:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Number {msisdn} is not owned by source subaccount '{request.from_groupid}'. Transfer aborted."
        )

    # --- Execute transfer ---
    result, status_code = await asyncio.to_thread(
        vonage_client.transfer_number,
        primary_api_key=primary_creds['api_key'],
        primary_api_secret=primary_creds['api_secret'],
        from_api_key=from_creds['api_key'],
        to_api_key=to_creds['api_key'],
        number=msisdn,
        country=country,
        log_enabled=log_enabled
    )

    if status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Vonage API transfer failed: {result.get('error', 'Unknown error')}"
        )

    # --- Notification ---
    notif_payload = {
        "from_groupid": request.from_groupid,
        "to_groupid": request.to_groupid,
        "number": msisdn,
        "country": country,
        "from_subaccount": from_creds['account_name'],
        "to_subaccount": to_creds['account_name']
    }
    notification_service.fire_and_forget("did.transferred", notif_payload)

    return DIDTransferResponse(
        message=f"Successfully transferred number {msisdn} from '{request.from_groupid}' to '{request.to_groupid}'.",
        number=msisdn,
        from_subaccount_name=from_creds['account_name'],
        from_subaccount_api_key=from_creds['api_key'],
        to_subaccount_name=to_creds['account_name'],
        to_subaccount_api_key=to_creds['api_key']
    )


@transfer_router.post(
    "/transfer-numbers-batch",
    response_model=DIDBatchTransferResponse,
    summary="Transfer multiple numbers between subaccounts"
)
async def transfer_numbers_batch_endpoint(request: DIDBatchTransferRequest):
    """
    Transfers multiple phone numbers from one subaccount to another.
    Uses concurrency and delay settings from app configuration.
    """
    if credentials_manager.STORAGE_MODE != 'db':
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Endpoint not available in 'file' storage mode."
        )

    log_enabled = settings_manager.get_setting('store_logs_enabled')
    max_concurrency = int(settings_manager.get_setting('max_concurrent_requests', 5))
    delay_ms = int(settings_manager.get_setting('delay_between_batches_ms', 1000))

    # --- Resolve credentials ---
    from_creds = _resolve_groupid(request.from_groupid)
    to_creds = _resolve_groupid(request.to_groupid)
    primary_creds = _get_primary_creds()

    if from_creds['api_key'] == to_creds['api_key']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Source and destination subaccounts cannot be the same."
        )

    # --- Process in batches ---
    results = []
    items = request.numbers

    for i in range(0, len(items), max_concurrency):
        batch = items[i:i + max_concurrency]
        tasks = [
            _process_single_transfer(
                item=item,
                from_creds=from_creds,
                to_creds=to_creds,
                primary_creds=primary_creds,
                from_groupid=request.from_groupid,
                to_groupid=request.to_groupid,
                log_enabled=log_enabled
            )
            for item in batch
        ]
        batch_results = await asyncio.gather(*tasks)
        results.extend(batch_results)

        if i + max_concurrency < len(items):
            await asyncio.sleep(delay_ms / 1000.0)

    success_count = sum(1 for r in results if r.status == 'success')
    failed_count = len(results) - success_count

    return DIDBatchTransferResponse(
        message="Batch transfer process completed.",
        total_processed=len(results),
        success_count=success_count,
        failed_count=failed_count,
        results=results
    )


async def _process_single_transfer(
    item: DIDBatchTransferItem,
    from_creds: dict,
    to_creds: dict,
    primary_creds: dict,
    from_groupid: str,
    to_groupid: str,
    log_enabled: bool
) -> BatchTransferResult:
    """Processes a single number transfer within a batch."""
    try:
        msisdn = re.sub(r'\D', '', item.number)
        country = item.country.upper() if item.country else _detect_country(msisdn)

        if not country:
            return BatchTransferResult(
                number=item.number,
                status='failed',
                detail="Could not auto-detect country. Provide a 'country' code."
            )

        if country in ('US', 'CA') and len(msisdn) == 10:
            msisdn = '1' + msisdn

        # Ownership verification
        is_owned, _ = await asyncio.to_thread(
            vonage_client._verify_did_ownership,
            username=from_creds['api_key'],
            password=from_creds['api_secret'],
            msisdn=msisdn,
            log_enabled=log_enabled
        )
        if not is_owned:
            return BatchTransferResult(
                number=item.number,
                status='failed',
                detail=f"Number not owned by source subaccount '{from_groupid}'."
            )

        # Execute transfer
        result, status_code = await asyncio.to_thread(
            vonage_client.transfer_number,
            primary_api_key=primary_creds['api_key'],
            primary_api_secret=primary_creds['api_secret'],
            from_api_key=from_creds['api_key'],
            to_api_key=to_creds['api_key'],
            number=msisdn,
            country=country,
            log_enabled=log_enabled
        )

        if status_code >= 400:
            return BatchTransferResult(
                number=item.number,
                status='failed',
                detail=f"Vonage API error: {result.get('error', 'Unknown')}"
            )

        # Fire notification per successful transfer
        notif_payload = {
            "from_groupid": from_groupid,
            "to_groupid": to_groupid,
            "number": msisdn,
            "country": country,
            "from_subaccount": from_creds['account_name'],
            "to_subaccount": to_creds['account_name']
        }
        notification_service.fire_and_forget("did.transferred", notif_payload)

        return BatchTransferResult(
            number=item.number,
            status='success',
            detail=f"Transferred {msisdn} successfully."
        )

    except Exception as e:
        return BatchTransferResult(
            number=item.number,
            status='failed',
            detail=f"Unexpected error: {str(e)}"
        )

