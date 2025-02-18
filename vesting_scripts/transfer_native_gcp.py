import json
import datetime
from decimal import Decimal
from signer.api_signer import sign
from push_to_api.push_tx import push_tx
from configs.evm_tokens import EVM_TOKEN_CONFIGS
from secret_manager.gcp_secret_manager import access_secret

### FUNCTIONS
def evm_tx_native(evm_chain, native_asset, vault_id, destination, custom_note, value):

    """
    Native ETH or BNB transfer

    """

    sanitized_native_asset_name = native_asset.lower().strip()

    if evm_chain not in EVM_TOKEN_CONFIGS:
        raise ValueError(f"'{evm_chain}' is not implemented yet!")

    token_config = EVM_TOKEN_CONFIGS[evm_chain][sanitized_native_asset_name]
    decimals = token_config["decimals"]
    value = str(int(Decimal(value) * Decimal(10**decimals)))

    print(f"⚙️ Preparing {native_asset} tx for {value}!")

    request_json = {
        "signer_type": "api_signer",
        "vault_id": vault_id,
        "note": custom_note,
        "type": "evm_transaction",
        "details": {
            "type": "evm_transfer",
            "gas": {
                "type": "priority",
                "priority_level": "medium"
            },
            "to": destination,
            "asset_identifier": {
                "type": "evm",
                "details": {
                    "type": "native",
                    "chain": f"evm_{evm_chain}_mainnet"
                }
            },
            "value": {
                "type": "value",
                "value": value
            }
        }
    }
    
    return request_json

### Core logic
def transfer_native_gcp(chain, vault_id, destination, value, note, gcp_project_id, fordefi_api_user_token, api_signer_secret):
    """
    Execute a native token transfer (BNB/ETH) using Fordefi API
    
    Args:
        chain (str): Chain identifier (e.g., "bsc", "eth")
        vault_id (str): Fordefi vault ID
        destination (str): Destination wallet address
        value (str): Amount to transfer in native units (e.g., "0.0001")
        note (str): Transaction note
    
    Returns:
        dict: Response from the Fordefi API
    """

    USER_API_TOKEN = access_secret(gcp_project_id, fordefi_api_user_token, 'latest')
    path = "/api/v1/transactions"

    # Building transaction
    request_json = evm_tx_native(
        evm_chain=chain,
        vault_id=vault_id,
        destination=destination,
        custom_note=note,
        value=value
    )
    request_body = json.dumps(request_json)
    timestamp = datetime.datetime.now().strftime("%s")
    payload = f"{path}|{timestamp}|{request_body}"

    # Sign transaction with API Signer
    signature = sign(payload=payload, project=gcp_project_id, api_signer_secret_name=api_signer_secret)

    # Push tx to Fordefi API
    resp_tx = push_tx(path, USER_API_TOKEN, signature, timestamp, request_body)
    return resp_tx.json()