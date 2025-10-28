from typing import TypedDict

class EtherscanDict(TypedDict):
    address: str
    balance: str
    block_no: str
    contract_name: str
    contract_type: str
    gas_price: str
    gas_used: str
    nonce: str
    transaction_hash: str