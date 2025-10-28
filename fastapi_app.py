# --- START OF FILE fastapi_app.py ---

import os
import asyncio
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, Security, status, Request
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field, field_validator, model_validator, ValidationError
from typing import Optional, List, Dict, Any

# --- Import Core Application Logic ---
from utils.config_loader import load_config_file
from utils import credentials_manager
from utils import settings_manager
from utils import logger
from utils import notification_service
from vendors.vonage import client as vonage_client
from utils import db_manager

# --- Environment and Configuration ---
load_dotenv()
app = FastAPI(
    title="DID Provisioning Service",
    description="A secure, high-performance API for provisioning and releasing DIDs.",
    version="1.3.0"
)

# --- Add Middleware ---
TRUSTED_PROXY_IPS = os.environ.get("TRUSTED_PROXY_IPS")
if TRUSTED_PROXY_IPS:
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=TRUSTED_PROXY_IPS)


# --- Configuration Loading ---
NPA_DATA_CONFIG_FILE = os.path.join('config', 'npa_data.json')
NPA_DATA = load_config_file(NPA_DATA_CONFIG_FILE)

# --- Security and Authentication ---
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=True)
MASTER_KEY = os.environ.get("MASTER_KEY")
if not MASTER_KEY:
    raise RuntimeError("CRITICAL: MASTER_KEY environment variable not set.")
PROVISIONING_API_KEY = os.environ.get("FASTAPI_PROVISIONING_KEY")
if not PROVISIONING_API_KEY:
    raise RuntimeError("CRITICAL: FASTAPI_PROVISIONING_KEY environment variable not set.")
IP_WHITELIST_STR = os.environ.get("FASTAPI_IP_WHITELIST")
IP_WHITELIST = set(IP_WHITELIST_STR.split(',')) if IP_WHITELIST_STR else set()
VONAGE_PRIMARY_ACCOUNT_NAME = os.environ.get("VONAGE_PRIMARY_ACCOUNT_NAME")

async def verify_ip_address(request: Request):
    if not IP_WHITELIST: return
    client_ip = request.client.host
    if client_ip not in IP_WHITELIST:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"IP address {client_ip} is not allowed.")

async def verify_api_key(api_key_header: str = Security(API_KEY_HEADER)):
    if api_key_header != PROVISIONING_API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API Key")

def _get_national_number(msisdn: str, country: str) -> str:
    if country in ('US', 'CA') and len(msisdn) == 11 and msisdn.startswith('1'):
        return msisdn[1:]
    return msisdn

# --- Pydantic Data Models ---
class DIDProvisionRequest(BaseModel):
    groupid: str = Field(..., description="The unique group ID to match against a subaccount name.")
    npa: str = Field(..., description="The 3-digit NPA (Numbering Plan Area) to search for a DID in.", min_length=3, max_length=3, pattern=r'^\d{3}$')
    voice_callback_type: Optional[str] = Field(None, description="Optional. The voice callback type (e.g., 'sip', 'tel'). If provided, this will override the stored default for the group.")
    voice_callback_value: Optional[str] = Field(None, description="Optional. The voice callback value (e.g., 'sbc.domain.com'). If provided, this will override the stored default for the group.")
    create_subaccount_if_not_found: bool = Field(False, description="If true, a new Vonage subaccount will be created if no existing credential matches the groupid. Requires `VONAGE_PRIMARY_ACCOUNT_NAME` to be set on the server.")
    
class ProvisioningResponse(BaseModel):
    status: str = "success"
    message: str
    provisioned_did: str
    country: str
    subaccount_name: str
    subaccount_api_key: str
    configuration_status: str

class DIDReleaseRequest(BaseModel):
    groupid: str = Field(..., description="The unique group ID to match against the subaccount that owns the DID.")
    did: str = Field(..., description="The phone number (DID) to be released.", pattern=r'^\d{10,15}$')
    country: Optional[str] = Field(None, description="Optional. The 2-letter ISO country code of the DID (e.g., 'US', 'CA'). If omitted, the system will attempt to auto-detect the country for US/CA numbers based on the NPA.", min_length=2, max_length=2)
    @field_validator('country')
    def uppercase_country_code(cls, v):
        if v is not None: return v.upper()
        return v

class ReleaseResponse(BaseModel):
    status: str = "success"
    message: str
    released_did: str
    subaccount_name: str

class DIDUpdateRequest(BaseModel):
    groupid: str = Field(..., description="The unique group ID to match against the subaccount that owns the DID.")
    did: str = Field(..., description="The phone number (DID) to be updated.", pattern=r'^\d{10,15}$')
    country: Optional[str] = Field(None, description="Optional. The 2-letter ISO country code of the DID (e.g., 'US', 'CA'). If omitted, the system will attempt to auto-detect the country for US/CA numbers.", min_length=2, max_length=2)
    voice_callback_type: Optional[str] = Field(None, description="The voice callback type to set (e.g., 'sip', 'tel'). To unset a callback, provide an empty string ''.")
    voice_callback_value: Optional[str] = Field(None, description="The voice callback value to set (e.g., 'sbc.domain.com'). To unset a callback, provide an empty string ''.")
    update_group_defaults: bool = Field(False, description="If true, the provided callback values will also be saved as the new defaults for this groupid for future provisioning.")
    @field_validator('country')
    def uppercase_country_code(cls, v):
        if v is not None: return v.upper()
        return v
    @model_validator(mode='after')
    def check_callback_fields(self):
        type_provided = self.voice_callback_type is not None
        value_provided = self.voice_callback_value is not None
        if type_provided != value_provided:
            raise ValueError("Both 'voice_callback_type' and 'voice_callback_value' must be provided together, or both must be omitted.")
        return self

class DIDUpdateResponse(BaseModel):
    status: str = "success"
    message: str
    updated_did: str
    subaccount_name: str
    applied_configuration: dict

class GroupDefaultsUpdateRequest(BaseModel):
    groupid: str = Field(..., description="The unique group ID to match against a subaccount name.")
    voice_callback_type: str = Field(..., description="The default voice callback type to store for this group (e.g., 'sip', 'tel', or an empty string '' to unset).")
    voice_callback_value: str = Field(..., description="The default voice callback value to store for this group (e.g., 'sbc.domain.com', or an empty string '' to unset).")

class UpdateSuccessResponse(BaseModel):
    status: str = "success"
    message: str

class DIDUpdateItem(BaseModel):
    did: str = Field(..., description="The phone number (DID) to be updated.", pattern=r'^\d{10,15}$')
    country: Optional[str] = Field(None, description="Optional. The 2-letter ISO country code of the DID.", min_length=2, max_length=2)

class DIDBatchUpdateRequest(BaseModel):
    groupid: str = Field(..., description="The group ID for the account that owns all DIDs in the list.")
    dids: List[Dict[str, Any]] = Field(..., description="A list of DIDs to update.", min_length=1)
    voice_callback_type: str = Field(..., description="The voice callback type to apply to all DIDs in the list.")
    voice_callback_value: str = Field(..., description="The voice callback value to apply to all DIDs in the list.")
    update_group_defaults: bool = Field(False, description="If true, also save these settings as the new defaults for the group.")

class BatchResult(BaseModel):
    did: str
    status: str
    detail: str

class DIDBatchUpdateResponse(BaseModel):
    message: str
    total_requested: int
    success_count: int
    failed_count: int
    results: Optional[List[BatchResult]] = Field(None, description="Detailed results of each operation. Only present if 'debug=true' is in the query string.")
    
class DIDBatchProvisionRequest(BaseModel):
    groupid: str = Field(..., description="The group ID for the account that will own the provisioned DIDs.")
    npas: List[str] = Field(..., description="A list of 3-digit NPAs to provision one number from each.", min_length=1)
    voice_callback_type: str = Field(..., description="The voice callback type to apply to all newly provisioned DIDs.")
    voice_callback_value: str = Field(..., description="The voice callback value to apply to all newly provisioned DIDs.")
    create_subaccount_if_not_found: bool = Field(False, description="If true, create a subaccount if one is not found for the groupid.")
    update_group_defaults: bool = Field(False, description="If true, save the callback settings as the new defaults for the groupid.")

class BatchProvisionResult(BaseModel):
    npa: str
    status: str
    detail: str
    provisioned_did: Optional[str] = None

class DIDBatchProvisionResponse(BaseModel):
    message: str
    total_processed: int
    success_count: int
    failed_count: int
    results: List[BatchProvisionResult]

class DIDReleaseItem(BaseModel):
    did: str = Field(..., description="The phone number (DID) to be released.", pattern=r'^\d{10,15}$')
    country: Optional[str] = Field(None, description="Optional. The 2-letter ISO country code of the DID.", min_length=2, max_length=2)

class DIDBatchReleaseRequest(BaseModel):
    groupid: str = Field(..., description="The group ID for the account that owns all DIDs in the list.")
    dids: List[Dict[str, Any]] = Field(..., description="A list of DIDs to release.", min_length=1)

class DIDBatchReleaseResponse(BaseModel):
    message: str
    total_requested: int
    success_count: int
    failed_count: int
    results: Optional[List[BatchResult]] = Field(None, description="Detailed results of each operation. Only present if 'debug=true' is in the query string.")

# --- API Endpoints ---
@app.on_event("startup")
async def startup_event():
    logger.setup_logging()
    if credentials_manager.STORAGE_MODE == 'db':
        print("FastAPI starting up, initializing database connection...")
        db_manager.init_db()
        settings_manager.get_all_settings()
        print("Application settings loaded into cache.")
    else:
        print("FastAPI starting up in 'file' mode. Endpoints will not be available.")
    if IP_WHITELIST: print(f"FastAPI IP Whitelist is active. Allowed IPs: {IP_WHITELIST}")
    else: print("FastAPI IP Whitelist is not configured. Allowing all IP addresses.")
    if credentials_manager.STORAGE_MODE == 'db' and not VONAGE_PRIMARY_ACCOUNT_NAME:
        print("WARNING: `VONAGE_PRIMARY_ACCOUNT_NAME` is not set. The auto-create subaccount feature will be disabled.")

@app.post("/provision-did", response_model=ProvisioningResponse, dependencies=[Depends(verify_ip_address), Depends(verify_api_key)], tags=["Provisioning"])
async def provision_did_endpoint(request: DIDProvisionRequest, request_obj: Request):
    logger.log_incoming_request(request_obj, request.model_dump())
    if credentials_manager.STORAGE_MODE != 'db': raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Endpoint not available in 'file' storage mode.")
    log_enabled = settings_manager.get_setting('store_logs_enabled')
    try:
        subaccount_creds = credentials_manager.find_and_decrypt_credential_by_groupid(request.groupid, MASTER_KEY)
    except ValueError:
        if not request.create_subaccount_if_not_found:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No credential found for groupid '{request.groupid}' and auto-create was not requested.")
        if not VONAGE_PRIMARY_ACCOUNT_NAME:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Auto-create subaccount failed: `VONAGE_PRIMARY_ACCOUNT_NAME` is not configured on the server.")
        try:
            primary_creds = credentials_manager.get_decrypted_credentials(VONAGE_PRIMARY_ACCOUNT_NAME, MASTER_KEY)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Auto-create failed: Could not load primary account credentials specified on server: {e}")
        new_subaccount_name = f"GroupId [{request.groupid}]"
        create_payload = {"name": new_subaccount_name, "use_primary_account_balance": True}
        create_result, create_status = vonage_client.create_subaccount(primary_api_key=primary_creds['api_key'], primary_api_secret=primary_creds['api_secret'], payload=create_payload, log_enabled=log_enabled)
        if create_status >= 400:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Failed to create new subaccount via Vonage API: {create_result.get('error', 'Unknown error')}")
        new_api_key, new_secret = create_result.get('api_key'), create_result.get('secret')
        if not new_api_key or not new_secret:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Vonage API created subaccount but did not return complete credentials.")
        try:
            credentials_manager.save_credential(name=new_subaccount_name, api_key=new_api_key, api_secret=new_secret, master_key=MASTER_KEY)
            notif_payload = { "primary_account": VONAGE_PRIMARY_ACCOUNT_NAME, "subaccount_name": new_subaccount_name, "subaccount_api_key": new_api_key, "use_primary_balance": create_payload['use_primary_account_balance'], "created_by": "FastAPI Provisioning Endpoint" }
            notification_service.fire_and_forget("subaccount.created", notif_payload)
            subaccount_creds = credentials_manager.find_and_decrypt_credential_by_groupid(request.groupid, MASTER_KEY)
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to save or re-fetch new subaccount credentials: {e}")
    
    country = 'US' if request.npa in NPA_DATA.get('US', []) else 'CA' if request.npa in NPA_DATA.get('CA', []) else None
    if not country: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"NPA '{request.npa}' not found in US or CA data.")
    
    search_params = { 'country': country, 'features': 'VOICE', 'pattern': f"1{request.npa}", 'search_pattern': 0, 'size': 1 }
    search_result, search_status = vonage_client.search_dids(subaccount_creds['api_key'], subaccount_creds['api_secret'], search_params, log_enabled=log_enabled)
    if search_status >= 400 or not search_result.get('numbers'): raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Failed to find an available DID for NPA {request.npa}. Vonage API error: {search_result.get('error', 'Unknown error')}")
    
    did_to_buy = search_result['numbers'][0]
    msisdn = did_to_buy.get('msisdn')
    buy_result, buy_status = vonage_client.buy_did(username=subaccount_creds['api_key'], password=subaccount_creds['api_secret'], country=country, msisdn=msisdn, log_enabled=log_enabled, treat_420_as_success=settings_manager.get_setting('treat_420_as_success_buy'), verify_on_420=settings_manager.get_setting('verify_on_420_buy'))
    if buy_status >= 400: raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Failed to purchase DID {msisdn}. Vonage API error: {buy_result.get('error', 'Unknown error')}")
    
    configuration_status, callback_type_to_use, callback_value_to_use, source_of_config = "Skipped", None, None, None
    if request.voice_callback_type and request.voice_callback_value: callback_type_to_use, callback_value_to_use, source_of_config = request.voice_callback_type, request.voice_callback_value, "request payload"
    else:
        stored_callback_type, stored_callback_value = subaccount_creds.get('default_voice_callback_type'), subaccount_creds.get('default_voice_callback_value')
        if stored_callback_type and stored_callback_value: callback_type_to_use, callback_value_to_use, source_of_config = stored_callback_type, stored_callback_value, "stored default settings"
    
    update_config = {}
    if callback_type_to_use and callback_value_to_use:
        final_callback_value = callback_value_to_use
        if callback_type_to_use == 'sip' and '@' not in final_callback_value: final_callback_value = f"{_get_national_number(msisdn, country)}@{final_callback_value}"
        update_config = {'voiceCallbackType': callback_type_to_use, 'voiceCallbackValue': final_callback_value}
        update_result, update_status = vonage_client.update_did(username=subaccount_creds['api_key'], password=subaccount_creds['api_secret'], country=country, msisdn=msisdn, config=update_config, log_enabled=log_enabled, treat_420_as_success=settings_manager.get_setting('treat_420_as_success_configure'))
        if update_status < 400: configuration_status = f"Applied successfully from {source_of_config}."
        else: configuration_status = f"Failed to apply settings from {source_of_config}: {update_result.get('error', 'Unknown error')}"
    else: configuration_status = "Skipped: No settings provided in request and no defaults configured for this group."
    
    notif_payload = { "groupid": request.groupid, "did": msisdn, "country": country, "subaccount_name": subaccount_creds['account_name'], "subaccount_api_key": subaccount_creds['api_key'], "configuration": update_config, "configuration_status": configuration_status }
    notification_service.fire_and_forget("did.provisioned", notif_payload)

    return ProvisioningResponse(message=f"Successfully provisioned DID {msisdn} for groupid '{request.groupid}'.", provisioned_did=msisdn, country=country, subaccount_name=subaccount_creds['account_name'], subaccount_api_key=subaccount_creds['api_key'], configuration_status=configuration_status)

@app.post("/update-did", response_model=DIDUpdateResponse, dependencies=[Depends(verify_ip_address), Depends(verify_api_key)], tags=["Provisioning"])
async def update_did_endpoint(request: DIDUpdateRequest, request_obj: Request):
    logger.log_incoming_request(request_obj, request.model_dump())
    if credentials_manager.STORAGE_MODE != 'db': raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Endpoint not available in 'file' storage mode.")
    log_enabled = settings_manager.get_setting('store_logs_enabled')
    try:
        subaccount_creds = credentials_manager.find_and_decrypt_credential_by_groupid(request.groupid, MASTER_KEY)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Could not find or access credentials for groupid '{request.groupid}': {e}")
    
    country_to_use = request.country
    msisdn_to_use = "".join(filter(str.isdigit, request.did))
    if not country_to_use:
        national_number = msisdn_to_use[-10:]
        if len(national_number) == 10:
            npa = national_number[:3]
            if npa in NPA_DATA.get('US', []): country_to_use = 'US'
            elif npa in NPA_DATA.get('CA', []): country_to_use = 'CA'
            if country_to_use and not msisdn_to_use.startswith('1'): msisdn_to_use = '1' + national_number
        if not country_to_use:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not auto-detect country from DID. Please provide a 2-letter 'country' code for non-US/CA numbers.")
    
    update_config = {}
    if request.voice_callback_type is not None and request.voice_callback_value is not None:
        update_config['voiceCallbackType'] = request.voice_callback_type
        final_callback_value = request.voice_callback_value
        if request.voice_callback_type == 'sip' and '@' not in final_callback_value and final_callback_value != '':
             final_callback_value = f"{_get_national_number(msisdn_to_use, country_to_use)}@{final_callback_value}"
        update_config['voiceCallbackValue'] = final_callback_value
    if not update_config:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No update parameters provided. Please specify fields to update, e.g., 'voice_callback_type'.")
    
    update_result, update_status = vonage_client.update_did(username=subaccount_creds['api_key'], password=subaccount_creds['api_secret'], country=country_to_use, msisdn=msisdn_to_use, config=update_config, log_enabled=log_enabled, treat_420_as_success=settings_manager.get_setting('treat_420_as_success_configure'))
    if update_status >= 400:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Failed to update DID {request.did}. Vonage API error: {update_result.get('error', 'Unknown error')}")
    
    update_message = f"Successfully updated DID {request.did} for groupid '{request.groupid}'."
    if request.update_group_defaults:
        try:
            credentials_manager.save_credential(name=subaccount_creds['account_name'], api_key=subaccount_creds['api_key'], api_secret=subaccount_creds['api_secret'], master_key=MASTER_KEY, voice_callback_type=request.voice_callback_type, voice_callback_value=request.voice_callback_value)
            update_message += " Stored defaults for the group were also updated."
        except Exception as e:
            update_message += f" However, failed to update the stored defaults for the group: {e}"
    
    return DIDUpdateResponse(message=update_message, updated_did=request.did, subaccount_name=subaccount_creds['account_name'], applied_configuration=update_config)

@app.post("/release-did", response_model=ReleaseResponse, dependencies=[Depends(verify_ip_address), Depends(verify_api_key)], tags=["Provisioning"])
async def release_did_endpoint(request: DIDReleaseRequest, request_obj: Request):
    logger.log_incoming_request(request_obj, request.model_dump())
    if credentials_manager.STORAGE_MODE != 'db': raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Endpoint not available in 'file' storage mode.")
    log_enabled = settings_manager.get_setting('store_logs_enabled')
    try:
        subaccount_creds = credentials_manager.find_and_decrypt_credential_by_groupid(request.groupid, MASTER_KEY)
    except ValueError as e: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Could not find or access credentials for groupid '{request.groupid}': {e}")
    
    country_to_use = request.country
    msisdn_to_use = "".join(filter(str.isdigit, request.did))
    if not country_to_use:
        national_number = msisdn_to_use[-10:]
        if len(national_number) == 10:
            npa = national_number[:3]
            if npa in NPA_DATA.get('US', []): country_to_use = 'US'
            elif npa in NPA_DATA.get('CA', []): country_to_use = 'CA'
            if country_to_use and not msisdn_to_use.startswith('1'): msisdn_to_use = '1' + national_number
        if not country_to_use: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not auto-detect country from DID. Please provide a 2-letter 'country' code for non-US/CA numbers.")
    
    result_data, status_code = vonage_client.cancel_did(username=subaccount_creds['api_key'], password=subaccount_creds['api_secret'], country=country_to_use, msisdn=msisdn_to_use, log_enabled=log_enabled)
    if status_code >= 400: raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Failed to release DID {request.did}. Vonage API error: {result_data.get('error', 'Unknown error')}")
    
    notif_payload = { "groupid": request.groupid, "did": request.did, "country": country_to_use, "subaccount_name": subaccount_creds['account_name'], "subaccount_api_key": subaccount_creds['api_key'] }
    notification_service.fire_and_forget("did.released", notif_payload)

    return ReleaseResponse(message=f"Successfully released DID {request.did} from account for groupid '{request.groupid}'.", released_did=request.did, subaccount_name=subaccount_creds['account_name'])

@app.post("/update-group-defaults", response_model=UpdateSuccessResponse, dependencies=[Depends(verify_ip_address), Depends(verify_api_key)], tags=["Configuration"])
async def update_group_defaults_endpoint(request: GroupDefaultsUpdateRequest, request_obj: Request):
    logger.log_incoming_request(request_obj, request.model_dump())
    if credentials_manager.STORAGE_MODE != 'db':
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Endpoint not available in 'file' storage mode.")
    try:
        credential_data = credentials_manager.find_and_decrypt_credential_by_groupid(request.groupid, MASTER_KEY)
        credentials_manager.save_credential(name=credential_data['account_name'], api_key=credential_data['api_key'], api_secret=credential_data['api_secret'], master_key=MASTER_KEY, voice_callback_type=request.voice_callback_type, voice_callback_value=request.voice_callback_value)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Could not find or access credentials for groupid '{request.groupid}': {e}")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred while saving the new defaults: {e}")
    return UpdateSuccessResponse(message=f"Successfully updated stored defaults for groupid '{request.groupid}'.")

# --- START: MODIFICATION ---
@app.post("/update-dids-batch", response_model=DIDBatchUpdateResponse, dependencies=[Depends(verify_ip_address), Depends(verify_api_key)], tags=["Provisioning"])
async def update_dids_batch_endpoint(request: DIDBatchUpdateRequest, request_obj: Request, debug: bool = False):
    logger.log_incoming_request(request_obj, request.model_dump())
    if credentials_manager.STORAGE_MODE != 'db':
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Endpoint not available in 'file' storage mode.")
    
    log_enabled = settings_manager.get_setting('store_logs_enabled')
    max_concurrency = int(settings_manager.get_setting('max_concurrent_requests', 5))
    delay_ms = int(settings_manager.get_setting('delay_between_batches_ms', 1000))
    treat_420_as_success = settings_manager.get_setting('treat_420_as_success_configure', False)
    
    try:
        subaccount_creds = credentials_manager.find_and_decrypt_credential_by_groupid(request.groupid, MASTER_KEY)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Could not find or access credentials for groupid '{request.groupid}': {e}")

    all_results = []
    dids_to_process = []
    
    for item_dict in request.dids:
        try:
            valid_item = DIDUpdateItem.model_validate(item_dict)
            sanitized_did = "".join(filter(str.isdigit, valid_item.did))
            if valid_item.country is None and len(sanitized_did) != 10:
                all_results.append(BatchResult(did=valid_item.did, status='failed', detail="Invalid format. A 10-digit number is required for auto-detection when 'country' is omitted."))
            else:
                dids_to_process.append(valid_item)
        except ValidationError as e:
            error_detail = e.errors()[0]
            field = ".".join(map(str, error_detail['loc']))
            msg = error_detail['msg']
            all_results.append(BatchResult(did=item_dict.get('did', 'N/A'), status='failed', detail=f"Invalid item format for field '{field}': {msg}"))

    if dids_to_process:
        for i in range(0, len(dids_to_process), max_concurrency):
            batch = dids_to_process[i:i + max_concurrency]
            tasks = [_process_single_did_update(did_item=item, subaccount_creds=subaccount_creds, request=request, log_enabled=log_enabled, treat_420_as_success=treat_420_as_success) for item in batch]
            api_batch_results = await asyncio.gather(*tasks)
            all_results.extend(api_batch_results)
            if i + max_concurrency < len(dids_to_process):
                await asyncio.sleep(delay_ms / 1000.0)

    success_count = sum(1 for r in all_results if r.status == 'success')
    failed_count = len(all_results) - success_count
    final_message = "Batch update process completed."

    if request.update_group_defaults and success_count > 0:
        try:
            credentials_manager.save_credential(name=subaccount_creds['account_name'], api_key=subaccount_creds['api_key'], api_secret=subaccount_creds['api_secret'], master_key=MASTER_KEY, voice_callback_type=request.voice_callback_type, voice_callback_value=request.voice_callback_value)
            final_message += " Stored defaults for the group were also updated."
        except Exception as e:
            final_message += f" However, failed to update the stored defaults for the group: {e}"
            
    if success_count > 0:
        successful_dids = [{'did': r.did, 'detail': r.detail} for r in all_results if r.status == 'success']
        notif_payload = {
            "groupid": request.groupid, "subaccount_name": subaccount_creds['account_name'], "subaccount_api_key": subaccount_creds['api_key'],
            "total_successful": success_count, "total_failed": failed_count,
            "updated_dids": successful_dids,
            "applied_configuration": {'voice_callback_type': request.voice_callback_type, 'voice_callback_value': request.voice_callback_value}
        }
        notification_service.fire_and_forget("did.updated.batch", notif_payload)

    response_payload = DIDBatchUpdateResponse(message=final_message, total_requested=len(request.dids), success_count=success_count, failed_count=failed_count)
    if debug:
        response_payload.results = all_results
    return response_payload

@app.post("/release-dids-batch", response_model=DIDBatchReleaseResponse, dependencies=[Depends(verify_ip_address), Depends(verify_api_key)], tags=["Provisioning"])
async def release_dids_batch_endpoint(request: DIDBatchReleaseRequest, request_obj: Request, debug: bool = False):
    logger.log_incoming_request(request_obj, request.model_dump())
    if credentials_manager.STORAGE_MODE != 'db':
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Endpoint not available in 'file' storage mode.")
    
    log_enabled = settings_manager.get_setting('store_logs_enabled')
    max_concurrency = int(settings_manager.get_setting('max_concurrent_requests', 5))
    delay_ms = int(settings_manager.get_setting('delay_between_batches_ms', 1000))
    
    try:
        subaccount_creds = credentials_manager.find_and_decrypt_credential_by_groupid(request.groupid, MASTER_KEY)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Could not find or access credentials for groupid '{request.groupid}': {e}")
        
    all_results = []
    dids_to_process = []
    
    for item_dict in request.dids:
        try:
            valid_item = DIDReleaseItem.model_validate(item_dict)
            sanitized_did = "".join(filter(str.isdigit, valid_item.did))
            if valid_item.country is None and len(sanitized_did) != 10:
                all_results.append(BatchResult(did=valid_item.did, status='failed', detail="Invalid format. A 10-digit number is required for auto-detection when 'country' is omitted."))
            else:
                dids_to_process.append(valid_item)
        except ValidationError as e:
            error_detail = e.errors()[0]
            field = ".".join(map(str, error_detail['loc']))
            msg = error_detail['msg']
            all_results.append(BatchResult(did=item_dict.get('did', 'N/A'), status='failed', detail=f"Invalid item format for field '{field}': {msg}"))
    
    successful_releases_for_notif = []
    if dids_to_process:
        for i in range(0, len(dids_to_process), max_concurrency):
            batch = dids_to_process[i:i + max_concurrency]
            tasks = [_process_single_did_release(did_item=item, subaccount_creds=subaccount_creds, log_enabled=log_enabled) for item in batch]
            api_batch_results = await asyncio.gather(*tasks)
            for i, res in enumerate(api_batch_results):
                if res['status'] == 'success':
                    successful_releases_for_notif.append({'did': res['did'], 'country': res['country']})
                all_results.append(BatchResult(did=res['did'], status=res['status'], detail=res['detail']))
            if i + max_concurrency < len(dids_to_process):
                await asyncio.sleep(delay_ms / 1000.0)
            
    success_count = sum(1 for r in all_results if r.status == 'success')
    failed_count = len(all_results) - success_count
    
    if successful_releases_for_notif:
        notif_payload = {
            "groupid": request.groupid, "subaccount_name": subaccount_creds['account_name'], "subaccount_api_key": subaccount_creds['api_key'],
            "total_successful": len(successful_releases_for_notif), "total_failed": failed_count,
            "released_dids": successful_releases_for_notif
        }
        notification_service.fire_and_forget("did.released.batch", notif_payload)

    response_payload = DIDBatchReleaseResponse(message="Batch release process completed.", total_requested=len(request.dids), success_count=success_count, failed_count=failed_count)
    if debug:
        response_payload.results = all_results
    return response_payload

@app.post("/provision-dids-batch", response_model=DIDBatchProvisionResponse, dependencies=[Depends(verify_ip_address), Depends(verify_api_key)], tags=["Provisioning"])
async def provision_dids_batch_endpoint(request: DIDBatchProvisionRequest, request_obj: Request):
    logger.log_incoming_request(request_obj, request.model_dump())
    if credentials_manager.STORAGE_MODE != 'db': raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Endpoint not available in 'file' storage mode.")
    settings_manager.get_all_settings()
    log_enabled = settings_manager.get_setting('store_logs_enabled')
    max_concurrency = int(settings_manager.get_setting('max_concurrent_requests', 5))
    delay_ms = int(settings_manager.get_setting('delay_between_batches_ms', 1000))
    api_settings = { "log_enabled": log_enabled, "treat_420_as_success_buy": settings_manager.get_setting('treat_420_as_success_buy', False), "verify_on_420_buy": settings_manager.get_setting('verify_on_420_buy', False), "treat_420_as_success_configure": settings_manager.get_setting('treat_420_as_success_configure', False) }
    try:
        subaccount_creds = credentials_manager.find_and_decrypt_credential_by_groupid(request.groupid, MASTER_KEY)
    except ValueError:
        if not request.create_subaccount_if_not_found: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No credential found for groupid '{request.groupid}' and auto-create was not requested.")
        if not VONAGE_PRIMARY_ACCOUNT_NAME: raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Auto-create subaccount failed: `VONAGE_PRIMARY_ACCOUNT_NAME` is not configured on the server.")
        try: primary_creds = credentials_manager.get_decrypted_credentials(VONAGE_PRIMARY_ACCOUNT_NAME, MASTER_KEY)
        except ValueError as e: raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Auto-create failed: Could not load primary account credentials: {e}")
        new_subaccount_name = f"GroupId [{request.groupid}]"
        create_payload = {"name": new_subaccount_name, "use_primary_account_balance": True}
        create_result, create_status = vonage_client.create_subaccount(primary_api_key=primary_creds['api_key'], primary_api_secret=primary_creds['api_secret'], payload=create_payload, log_enabled=log_enabled)
        if create_status >= 400: raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Failed to create subaccount: {create_result.get('error', 'Unknown')}")
        new_api_key, new_secret = create_result.get('api_key'), create_result.get('secret')
        if not new_api_key or not new_secret: raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Created subaccount but did not receive credentials.")
        try:
            credentials_manager.save_credential(name=new_subaccount_name, api_key=new_api_key, api_secret=new_secret, master_key=MASTER_KEY)
            notification_service.fire_and_forget("subaccount.created", {"primary_account": VONAGE_PRIMARY_ACCOUNT_NAME, "subaccount_name": new_subaccount_name, "subaccount_api_key": new_api_key, "use_primary_balance": True, "created_by": "FastAPI Batch Provisioning Endpoint"})
            subaccount_creds = credentials_manager.find_and_decrypt_credential_by_groupid(request.groupid, MASTER_KEY)
        except Exception as e: raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to save or re-fetch new credentials: {e}")

    final_results, dids_to_buy, dids_to_configure = [], [], []
    provisioned_for_notif = []

    # Search Stage
    npas_to_process, npas_for_retry = request.npas, []
    for i in range(0, len(npas_to_process), max_concurrency):
        batch_results = await asyncio.gather(*[_process_single_did_search(npa, subaccount_creds, api_settings) for npa in npas_to_process[i:i + max_concurrency]])
        for res in batch_results:
            if res['status'] == 'found': dids_to_buy.append(res['data'])
            elif res.get('status_code') == 429: npas_for_retry.append(res['npa'])
            else: final_results.append(BatchProvisionResult(npa=res['npa'], status='failed', detail=res['detail']))
        if i + max_concurrency < len(npas_to_process): await asyncio.sleep(delay_ms / 1000.0)
    if npas_for_retry:
        await asyncio.sleep(delay_ms / 1000.0)
        for i in range(0, len(npas_for_retry), max_concurrency):
            batch_results = await asyncio.gather(*[_process_single_did_search(npa, subaccount_creds, api_settings) for npa in npas_for_retry[i:i + max_concurrency]])
            for res in batch_results:
                if res['status'] == 'found': dids_to_buy.append(res['data'])
                else: final_results.append(BatchProvisionResult(npa=res['npa'], status='failed', detail=f"Failed on retry: {res['detail']}"))
            if i + max_concurrency < len(npas_for_retry): await asyncio.sleep(delay_ms / 1000.0)

    # Buy Stage
    if dids_to_buy:
        await asyncio.sleep(delay_ms / 1000.0)
        dids_to_buy_process, dids_for_retry = dids_to_buy, []
        for i in range(0, len(dids_to_buy_process), max_concurrency):
            batch_results = await asyncio.gather(*[_process_single_did_buy(did, subaccount_creds, api_settings) for did in dids_to_buy_process[i:i+max_concurrency]])
            for res in batch_results:
                if res['status'] == 'bought': dids_to_configure.append(res['data'])
                elif res.get('status_code') == 429: dids_for_retry.append(res['data'])
                else: final_results.append(BatchProvisionResult(npa=res['data']['npa'], status='failed', detail=res['detail'], provisioned_did=res['data']['msisdn']))
            if i + max_concurrency < len(dids_to_buy_process): await asyncio.sleep(delay_ms / 1000.0)
        if dids_for_retry:
            await asyncio.sleep(delay_ms / 1000.0)
            for i in range(0, len(dids_for_retry), max_concurrency):
                batch_results = await asyncio.gather(*[_process_single_did_buy(did, subaccount_creds, api_settings) for did in dids_for_retry[i:i+max_concurrency]])
                for res in batch_results:
                    if res['status'] == 'bought': dids_to_configure.append(res['data'])
                    else: final_results.append(BatchProvisionResult(npa=res['data']['npa'], status='failed', detail=f"Failed on retry: {res['detail']}", provisioned_did=res['data']['msisdn']))
                if i + max_concurrency < len(dids_for_retry): await asyncio.sleep(delay_ms / 1000.0)

    # Configure Stage
    if dids_to_configure:
        await asyncio.sleep(delay_ms / 1000.0)
        dids_to_configure_process, dids_for_retry = dids_to_configure, []
        for i in range(0, len(dids_to_configure_process), max_concurrency):
            batch_results = await asyncio.gather(*[_process_single_did_configure(did, subaccount_creds, request, api_settings) for did in dids_to_configure_process[i:i+max_concurrency]])
            for res in batch_results:
                provisioned_for_notif.append({"did": res['data']['msisdn'], "country": res['data']['country'], "npa": res['data']['npa'], "configuration": res['config_applied'], "configuration_status": res['detail']})
                if res['status'] == 'configured': final_results.append(BatchProvisionResult(npa=res['data']['npa'], status='success', provisioned_did=res['data']['msisdn'], detail=res['detail']))
                elif res.get('status_code') == 429: dids_for_retry.append(res['data'])
                else: final_results.append(BatchProvisionResult(npa=res['data']['npa'], status='partial_success', provisioned_did=res['data']['msisdn'], detail=res['detail']))
            if i + max_concurrency < len(dids_to_configure_process): await asyncio.sleep(delay_ms / 1000.0)
        if dids_for_retry:
            await asyncio.sleep(delay_ms / 1000.0)
            for i in range(0, len(dids_for_retry), max_concurrency):
                batch_results = await asyncio.gather(*[_process_single_did_configure(did, subaccount_creds, request, api_settings) for did in dids_for_retry[i:i+max_concurrency]])
                for res in batch_results:
                    provisioned_for_notif.append({"did": res['data']['msisdn'], "country": res['data']['country'], "npa": res['data']['npa'], "configuration": res['config_applied'], "configuration_status": f"Success on retry: {res['detail']}"})
                    if res['status'] == 'configured': final_results.append(BatchProvisionResult(npa=res['data']['npa'], status='success', provisioned_did=res['data']['msisdn'], detail=f"Success on retry: {res['detail']}"))
                    else: final_results.append(BatchProvisionResult(npa=res['data']['npa'], status='partial_success', provisioned_did=res['data']['msisdn'], detail=f"Failed on retry: {res['detail']}"))
                if i + max_concurrency < len(dids_for_retry): await asyncio.sleep(delay_ms / 1000.0)

    # Finalize and respond
    success_count = sum(1 for r in final_results if r.status in ['success', 'partial_success'])
    failed_count = len(request.npas) - success_count
    if provisioned_for_notif:
        notif_payload = {"groupid": request.groupid, "subaccount_name": subaccount_creds['account_name'], "subaccount_api_key": subaccount_creds['api_key'], "total_successful": len(provisioned_for_notif), "provisioned_dids": provisioned_for_notif}
        notification_service.fire_and_forget("did.provisioned.batch", notif_payload)
    final_message = "Batch provisioning process completed."
    if request.update_group_defaults and success_count > 0:
        try:
            credentials_manager.save_credential(name=subaccount_creds['account_name'], api_key=subaccount_creds['api_key'], api_secret=subaccount_creds['api_secret'], master_key=MASTER_KEY, voice_callback_type=request.voice_callback_type, voice_callback_value=request.voice_callback_value)
            final_message += " Stored defaults for the group were also updated."
        except Exception as e: final_message += f" However, failed to update the stored defaults for the group: {e}"
    return DIDBatchProvisionResponse(message=final_message, total_processed=len(request.npas), success_count=success_count, failed_count=failed_count, results=final_results)

# --- HELPER FUNCTIONS ---

async def _process_single_did_release(did_item: DIDReleaseItem, subaccount_creds: dict, log_enabled: bool) -> dict:
    msisdn_to_use = "".join(filter(str.isdigit, did_item.did))
    country_to_use = did_item.country
    try:
        if not country_to_use:
            national_number = msisdn_to_use[-10:]
            if len(national_number) == 10:
                npa = national_number[:3]
                if npa in NPA_DATA.get('US', []): country_to_use = 'US'
                elif npa in NPA_DATA.get('CA', []): country_to_use = 'CA'
                if country_to_use and not msisdn_to_use.startswith('1'): msisdn_to_use = '1' + national_number
            if not country_to_use:
                return {'did': did_item.did, 'status': 'failed', 'detail': "Could not auto-detect country.", 'country': None}
        result_data, status_code = await asyncio.to_thread(vonage_client.cancel_did, username=subaccount_creds['api_key'], password=subaccount_creds['api_secret'], country=country_to_use, msisdn=msisdn_to_use, log_enabled=log_enabled)
        if status_code >= 400:
            return {'did': did_item.did, 'status': 'failed', 'detail': f"Vonage API error: {result_data.get('error', 'Unknown error')}", 'country': country_to_use}
        return {'did': did_item.did, 'status': 'success', 'detail': "DID released successfully.", 'country': country_to_use}
    except Exception as e:
        return {'did': did_item.did, 'status': 'failed', 'detail': f"An unexpected internal error occurred: {str(e)}", 'country': country_to_use}

async def _process_single_did_search(npa: str, subaccount_creds: dict, settings: dict) -> dict:
    try:
        country = 'US' if npa in NPA_DATA.get('US', []) else 'CA' if npa in NPA_DATA.get('CA', []) else None
        if not country: return {'npa': npa, 'status': 'failed', 'detail': f"NPA not found in US or CA data.", 'status_code': 400}
        search_params = {'country': country, 'features': 'VOICE', 'pattern': f"1{npa}", 'search_pattern': 0, 'size': 1}
        search_result, search_status = await asyncio.to_thread(vonage_client.search_dids, subaccount_creds['api_key'], subaccount_creds['api_secret'], search_params, log_enabled=settings['log_enabled'])
        if search_status >= 400 or not search_result.get('numbers'):
            return {'npa': npa, 'status': 'failed', 'detail': f"No available numbers found. API error: {search_result.get('error', 'Unknown')}", 'status_code': search_status}
        did_info = search_result['numbers'][0]
        return {'npa': npa, 'status': 'found', 'data': {'npa': npa, 'msisdn': did_info.get('msisdn'), 'country': country}}
    except Exception as e:
        return {'npa': npa, 'status': 'failed', 'detail': f"An unexpected internal error occurred during search: {str(e)}", 'status_code': 500}

async def _process_single_did_buy(did_info: dict, subaccount_creds: dict, settings: dict) -> dict:
    msisdn, country = did_info['msisdn'], did_info['country']
    try:
        buy_result, buy_status = await asyncio.to_thread(vonage_client.buy_did, username=subaccount_creds['api_key'], password=subaccount_creds['api_secret'], country=country, msisdn=msisdn, log_enabled=settings['log_enabled'], treat_420_as_success=settings['treat_420_as_success_buy'], verify_on_420=settings['verify_on_420_buy'])
        if buy_status >= 400:
            return {'status': 'failed', 'data': did_info, 'detail': f"Failed to purchase. API error: {buy_result.get('error', 'Unknown')}", 'status_code': buy_status}
        return {'status': 'bought', 'data': did_info}
    except Exception as e:
        return {'status': 'failed', 'data': did_info, 'detail': f"An unexpected internal error occurred during purchase: {str(e)}", 'status_code': 500}

async def _process_single_did_configure(did_info: dict, subaccount_creds: dict, request: DIDBatchProvisionRequest, settings: dict) -> dict:
    msisdn, country = did_info['msisdn'], did_info['country']
    final_callback_value = request.voice_callback_value
    if request.voice_callback_type == 'sip' and '@' not in final_callback_value:
        final_callback_value = f"{_get_national_number(msisdn, country)}@{final_callback_value}"
    update_config = {'voiceCallbackType': request.voice_callback_type, 'voiceCallbackValue': final_callback_value}
    try:
        update_result, update_status = await asyncio.to_thread(vonage_client.update_did, username=subaccount_creds['api_key'], password=subaccount_creds['api_secret'], country=country, msisdn=msisdn, config=update_config, log_enabled=settings['log_enabled'], treat_420_as_success=settings['treat_420_as_success_configure'])
        detail_message, status = "Applied successfully.", 'configured'
        if update_status >= 400:
            detail_message = f"Provisioned but failed to apply configuration: {update_result.get('error', 'Unknown')}"
            status = 'failed_config'
        return {'status': status, 'data': did_info, 'detail': detail_message, 'config_applied': update_config, 'status_code': update_status}
    except Exception as e:
        return {'status': 'failed_config', 'data': did_info, 'detail': f"An unexpected internal error occurred during configuration: {str(e)}", 'config_applied': update_config, 'status_code': 500}
# --- END: MODIFICATION ---
