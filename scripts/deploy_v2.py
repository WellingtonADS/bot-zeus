import json
import os
import sys
import logging
from web3 import Web3
from web3.middleware.geth_poa import geth_poa_middleware
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from utils.gas_utils import obter_taxa_gas

def get_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Variável de ambiente '{name}' não definida")
    return v

def main():
    # Carrega variáveis de ambiente do .env, se existir
    load_dotenv()
    # Logger simples para o deploy
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger("deploy_v2")
    provider = os.getenv('CUSTOM_RPC_URL') or os.getenv('INFURA_URL')
    if not provider:
        raise RuntimeError("Defina CUSTOM_RPC_URL ou INFURA_URL")
    w3 = Web3(Web3.HTTPProvider(provider))
    w3.middleware_onion.inject(geth_poa_middleware, layer=0)
    if not w3.is_connected():
        raise RuntimeError(f"Falha ao conectar em {provider}")
    print(f"Conectado. chainId={w3.eth.chain_id}")

    wallet_address = Web3.to_checksum_address(get_env('WALLET_ADDRESS'))
    private_key = get_env('PRIVATE_KEY')
    pool_provider = Web3.to_checksum_address(get_env('POOL_ADDRESSES_PROVIDER'))

    artifact = os.path.join(BASE_DIR, 'artifacts', 'contracts', 'FlashLoanReceiverV2.sol', 'FlashLoanReceiverV2.json')
    if not os.path.exists(artifact):
        raise FileNotFoundError(f"Artifact não encontrado: {artifact}. Compile com 'npx hardhat compile'.")
    with open(artifact, 'r') as f:
        art = json.load(f)
    abi = art.get('abi')
    bytecode = art.get('bytecode')
    if not abi or not bytecode:
        raise RuntimeError("Artifact inválido: sem abi/bytecode")

    contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    # Obtém preço do gás (gwei) com fallback interno para web3 no utilitário
    gas_price_gwei = obter_taxa_gas(w3, logger)
    tx = contract.constructor(pool_provider).build_transaction({
        'from': wallet_address,
        'nonce': w3.eth.get_transaction_count(wallet_address),
        'gasPrice': Web3.to_wei(gas_price_gwei, 'gwei'),
    })
    gas_est = w3.eth.estimate_gas(tx)
    tx['gas'] = int(gas_est * 1.2)
    signed = w3.eth.account.sign_transaction(tx, private_key)
    tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
    print(f"Tx enviada: {tx_hash.hex()}")
    rcpt = w3.eth.wait_for_transaction_receipt(tx_hash)
    addr = rcpt['contractAddress']
    print(f"Contrato V2 implantado em: {addr}")

if __name__ == '__main__':
    main()
