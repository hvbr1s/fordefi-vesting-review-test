import json
import datetime
from decimal import Decimal
from signer.api_signer import sign
from push_to_api.push_tx import push_tx
from configs.evm_tokens import EVM_TOKEN_CONFIGS
from secret_manager.gcp_secret_manager import access_secret

### FUNCTIONS
def evm_tx_tokens(evm_chain, vault_id, destination, custom_note, value, token):

    sanitized_token_name = token.lower().strip()

    if evm_chain not in EVM_TOKEN_CONFIGS or sanitized_token_name not in EVM_TOKEN_CONFIGS[evm_chain]:
        raise ValueError(f"Token '{token}' is not supported for chain '{evm_chain}'")
    
    token_config = EVM_TOKEN_CONFIGS[evm_chain][sanitized_token_name]
    decimals = token_config["decimals"]
    contract_address = token_config["contract_address"]
    
    value = str(int(Decimal(value) * Decimal(10**decimals)))

    request_json =  {
    "signer_type": "api_signer",
    "type": "evm_transaction",
    "details": {
        "type": "evm_transfer",
        "gas": {
          "type": "priority",
          "priority_level": "medium"
        },
        "to": destination,
        "value": {
           "type": "value",
           "value": value
        },
        "asset_identifier": {
             "type": "evm",
             "details": {
                 "type": "erc20",
                 "token": {
                     "chain": f"evm_{evm_chain}_mainnet",
                     "hex_repr": contract_address
                 }
             }
        }
    },
    "note": custom_note,
    "vault_id": vault_id
}

    return request_json

### Core logic
def transfer_token_gcp(chain, token_ticker, vault_id, destination, amount, note):
    """
    Execute an ERC20 token transfer using Fordefi API
    
    Args:
        chain (str): Chain identifier (e.g., "bsc", "eth")
        token_address (str): Contract address of the token
        vault_id (str): Fordefi vault ID
        destination (str): Destination wallet address
        amount (str): Amount to transfer in token units (e.g., "123.45")
        note (str): Transaction note
    
    Returns:
        dict: Response from the Fordefi API
    """
    # Set config
    GCP_PROJECT_ID = 'inspired-brand-447513-i8' ## CHANGE to your GCP project name
    FORDEFI_API_USER_TOKEN = 'USER_API_TOKEN'
    USER_API_TOKEN = access_secret(GCP_PROJECT_ID, FORDEFI_API_USER_TOKEN, 'latest')
    path = "/api/v1/transactions"

    # Building transaction
    request_json = evm_tx_tokens(
        evm_chain=chain,
        vault_id=vault_id,
        destination=destination,
        custom_note=note,
        value=amount,
        token=token_ticker
    )
    request_body = json.dumps(request_json)
    timestamp = datetime.datetime.now().strftime("%s")
    payload = f"{path}|{timestamp}|{request_body}"

    # Sign transaction with API Signer
    signature = sign(payload=payload, project=GCP_PROJECT_ID)

    # Push tx to Fordefi API
    resp_tx = push_tx(path, USER_API_TOKEN, signature, timestamp, request_body)
    return resp_tx.json()