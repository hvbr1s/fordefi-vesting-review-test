import json
import datetime
from decimal import Decimal
from signer.api_signer import sign
from push_to_api.push_tx import push_tx
from configs.evm_tokens import TOKEN_CONFIGS
from secret_manager.gcp_secret_manager import access_secret

### FUNCTIONS
def evm_tx_tokens(evm_chain, vault_id, destination, custom_note, value, token):

    sanitized_token_name = token.lower().strip()

    if evm_chain not in TOKEN_CONFIGS or sanitized_token_name not in TOKEN_CONFIGS[evm_chain]:
        raise ValueError(f"Token '{token}' is not supported for chain '{evm_chain}'")
    
    token_config = TOKEN_CONFIGS[evm_chain][sanitized_token_name]
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

def sol_tx_tokens(chain, vault_id, destination, custom_note, value, token):

    sanitized_token_name = token.lower().strip()

    if chain not in TOKEN_CONFIGS or sanitized_token_name not in TOKEN_CONFIGS[chain]:
        raise ValueError(f"Token '{token}' is not supported for chain '{chain}'")
    
    token_config = TOKEN_CONFIGS[chain][sanitized_token_name]
    decimals = token_config["decimals"]
    contract_address = token_config["contract_address"]
    
    value = str(int(Decimal(value) * Decimal(10**decimals)))

    request_json = {
        "signer_type": "api_signer",
        "type": "solana_transaction",
        "details": {
            "type": "solana_transfer",
            "to": destination,
            "value": {
                "type": "value",
                "value": value
            },
            "asset_identifier": {
                "type": "solana",
                "details": {
                    "type": "spl_token",
                    "token": {
                        "chain": "solana_mainnet",
                        "base58_repr": contract_address
                    }
                }
            }
        },
        "note": custom_note,
        "vault_id": vault_id
    }


    return request_json

### Core logic
def transfer_token_gcp(chain, vault_id, destination, note, amount, token_ticker, gcp_project_id, fordefi_api_user_token, api_signer_secret):
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
    USER_API_TOKEN = access_secret(gcp_project_id, fordefi_api_user_token, 'latest')
    path = "/api/v1/transactions"

    if chain in ["ethereum", "bsc"]:
    # Building transaction
        request_json = evm_tx_tokens(
            evm_chain=chain,
            vault_id=vault_id,
            destination=destination,
            custom_note=note,
            value=amount,
            token=token_ticker
        )
    else:
        request_json = sol_tx_tokens(
            chain=chain,
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
    signature = sign(payload=payload, project=gcp_project_id, api_signer_secret_name=api_signer_secret)

    # Push tx to Fordefi API
    resp_tx = push_tx(path, USER_API_TOKEN, signature, timestamp, request_body)
    return resp_tx.json()