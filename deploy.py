import json
import os
import sys
from web3 import Web3
from dotenv import load_dotenv
import logging

# --- Configuração Inicial ---
# Adiciona o diretório raiz ao PYTHONPATH para encontrar os módulos utilitários
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)

# Importa utilitários após a configuração do path
from utils.gas_utils import obter_taxa_gas
# A função 'validar_e_converter_endereco' não é mais necessária neste script
# from utils.address_utils import validar_e_converter_endereco

# Configuração do logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Carregamento de Configurações ---
load_dotenv()

def obter_variavel_essencial(nome_variavel: str) -> str:
    """Obtém uma variável de ambiente essencial ou lança um erro crítico."""
    valor = os.getenv(nome_variavel)
    if not valor:
        raise ValueError(f"Variável de ambiente essencial '{nome_variavel}' não definida no ficheiro .env.")
    return valor

# Conectar ao provedor (ex: Infura, Alchemy)
try:
    provider_url = obter_variavel_essencial("INFURA_URL")
    w3 = Web3(Web3.HTTPProvider(provider_url))
    if not w3.is_connected():
        raise ConnectionError(f"Falha ao conectar ao provedor em {provider_url}")
    logger.info(f"Conectado com sucesso à rede (Chain ID: {w3.eth.chain_id}).")
except (ValueError, ConnectionError) as e:
    logger.critical(e)
    sys.exit(1)

# --- Carregamento do Contrato ---
try:
    # Caminho para o ABI do contrato a ser implantado
    abis_dir = os.path.join(base_dir, 'abis')
    json_path = os.path.join(abis_dir, "FlashLoanReceiver.json")
    
    with open(json_path) as f:
        contract_json = json.load(f)
        contract_abi = contract_json.get("abi")
        contract_bytecode = contract_json.get("bytecode")

    if not isinstance(contract_abi, list) or not contract_bytecode:
        raise ValueError("Formato de ABI/Bytecode inválido no ficheiro JSON.")

    FlashLoanReceiverContract = w3.eth.contract(abi=contract_abi, bytecode=contract_bytecode)
    logger.info("ABI e Bytecode do FlashLoanReceiver carregados com sucesso.")

except (FileNotFoundError, ValueError) as e:
    logger.critical(f"Erro ao carregar o contrato: {e}")
    sys.exit(1)

# --- Preparação da Transação de Deploy ---
try:
    # Carregar e validar endereços e chaves do .env
    # CORREÇÃO: Validar e converter o endereço diretamente no script
    # para garantir a inferência de tipo correta pelo Pylance.
    wallet_address_str = obter_variavel_essencial("WALLET_ADDRESS")
    if not Web3.is_address(wallet_address_str):
        raise ValueError(f"Endereço da carteira inválido no .env: {wallet_address_str}")
    wallet_address = Web3.to_checksum_address(wallet_address_str)
    
    private_key = obter_variavel_essencial("PRIVATE_KEY")
    
    pool_provider_address_str = obter_variavel_essencial("POOL_ADDRESSES_PROVIDER")
    if not Web3.is_address(pool_provider_address_str):
        raise ValueError(f"Endereço do Pool Provider inválido no .env: {pool_provider_address_str}")
    pool_provider_address = Web3.to_checksum_address(pool_provider_address_str)

    # Verificar saldo da carteira (agora sem erros de tipo)
    balance_wei = w3.eth.get_balance(wallet_address)
    logger.info(f"Saldo da carteira {wallet_address}: {w3.from_wei(balance_wei, 'ether')} MATIC")

    # Construir a transação de deploy
    logger.info("Construindo a transação para implantar o contrato...")

    constructor_args = [pool_provider_address]
    
    tx_deploy = FlashLoanReceiverContract.constructor(*constructor_args).build_transaction({
        'from': wallet_address,
        # Obter nonce (agora sem erros de tipo)
        'nonce': w3.eth.get_transaction_count(wallet_address),
        'gasPrice': Web3.to_wei(obter_taxa_gas(w3, logger), 'gwei'),
    })
    
    gas_estimate = w3.eth.estimate_gas(tx_deploy)
    tx_deploy['gas'] = int(gas_estimate * 1.2)
    logger.info(f"Gás estimado para o deploy: {tx_deploy['gas']}")

    tx_cost = tx_deploy['gas'] * tx_deploy['gasPrice']
    if balance_wei < tx_cost:
        logger.critical(f"Saldo insuficiente para o deploy. Necessário: {w3.from_wei(tx_cost, 'ether')} MATIC")
        sys.exit(1)

    # Assinar e enviar a transação
    signed_tx = w3.eth.account.sign_transaction(tx_deploy, private_key=private_key)
    logger.info("Transação assinada. A enviar para a rede...")

    tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
    logger.info(f"Transação enviada! Hash: {tx_hash.hex()}")
    logger.info("A aguardar confirmação do bloco...")

    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    
    contract_address = tx_receipt['contractAddress']
    logger.info(f"🎉 Contrato FlashLoanReceiver implantado com sucesso no endereço: {contract_address} 🎉")
    logger.info(f"Ver no PolygonScan: https://polygonscan.com/address/{contract_address}")

except Exception as e:
    logger.critical(f"Erro durante o processo de deploy: {e}", exc_info=True)
    sys.exit(1)
