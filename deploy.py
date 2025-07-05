# deploy.py
import json
import os
import sys
from web3 import Web3
from dotenv import load_dotenv
import logging
from utils.gas_utils import obter_taxa_gas
from utils.address_utils import validar_e_converter_endereco

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Adicionar o diretório raiz ao PYTHONPATH
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)

# Carregar variáveis de ambiente do arquivo .env
load_dotenv()

# Conectar ao provedor Infura
w3 = Web3(Web3.HTTPProvider(os.getenv("INFURA_URL")))
if not w3.is_connected():
    logger.error("Falha ao conectar ao provedor Infura")
    raise Exception("Falha ao conectar ao provedor Infura")

# Caminho do arquivo ABI e bytecode do contrato FlashLoanReceiver
abis_dir = os.path.join(os.path.dirname(__file__), 'abis')
json_path = os.path.join(abis_dir, "FlashLoanReceiver.json")

# Verificar se o arquivo existe
if not os.path.exists(json_path):
    logger.error(f"Arquivo ABI não encontrado: {json_path}")
    raise FileNotFoundError(f"Arquivo ABI não encontrado: {json_path}")

# Carregar o ABI e bytecode do contrato diretamente no deploy.py
with open(json_path) as f:
    contract_json = json.load(f)
    # Acessa apenas o campo 'abi' que deve conter uma lista, e o 'bytecode' (a chave deve estar presente)
    contract_abi = contract_json.get("abi")
    contract_bytecode = contract_json.get("bytecode")

    # Verifique se a ABI e bytecode estão em um formato esperado
    if not isinstance(contract_abi, list) or not isinstance(contract_bytecode, str):
        raise ValueError("Formato inválido: 'abi' deve ser uma lista e 'bytecode' deve ser uma string.")

# Criar o contrato FlashLoanReceiver
FlashLoanReceiver = w3.eth.contract(abi=contract_abi, bytecode=contract_bytecode)

# Carregar e validar endereços diretamente do .env
provider_address = validar_e_converter_endereco(os.getenv("POOL_ADDRESSES_PROVIDER") or "")
usdt_address = validar_e_converter_endereco(os.getenv("USDT_ADDRESS") or "")
wmatic_address = validar_e_converter_endereco(os.getenv("WMATIC_ADDRESS") or "")
uniswap_router_address = validar_e_converter_endereco(os.getenv("UNISWAP_V3_ROUTER_ADDRESS") or "")
quickswap_router_address = validar_e_converter_endereco(os.getenv("QUICKSWAP_ROUTER_ADDRESS") or "")
wallet_address = validar_e_converter_endereco(os.getenv("WALLET_ADDRESS") or "")
private_key = os.getenv("PRIVATE_KEY")

# Definir o limite de gás fixo diretamente no deploy.py
gas_limit = 2100000  # Defina o valor de limite de gás desejado

# Verificar saldo da conta
balance = w3.eth.get_balance(Web3.to_checksum_address(wallet_address))
logger.info(f"Saldo da conta: {w3.from_wei(balance, 'ether')} ETH")

# Construir a transação de deploy do contrato
try:
    logger.info("Construindo a transação para implantar o contrato FlashLoanReceiver...")

    # Obter a taxa de gás
    gas_price = obter_taxa_gas(w3, logger)

    # Verificar se o saldo cobre o custo do gás
    required_gas = gas_limit * Web3.to_wei(gas_price, 'gwei')
    if balance < required_gas:
        logger.error("Saldo insuficiente para cobrir o custo de gás estimado.")
        raise Exception("Saldo insuficiente para cobrir o custo de gás estimado.")

    transaction = FlashLoanReceiver.constructor(
        provider_address,
        usdt_address,
        wmatic_address,
        uniswap_router_address,
        quickswap_router_address
    ).build_transaction({
        'from': wallet_address,
        'nonce': w3.eth.get_transaction_count(Web3.to_checksum_address(wallet_address)),
        'gas': gas_limit,
        'gasPrice': Web3.to_wei(gas_price, 'gwei')
    })

    logger.info("Transação construída com sucesso. Assinando a transação...")

    # Assinar a transação
    signed_txn = w3.eth.account.sign_transaction(transaction, private_key=private_key)

    logger.info("Transação assinada. Enviando a transação...")

    # Enviar a transação
    tx_hash = w3.eth.send_raw_transaction(signed_txn.rawTransaction)

    logger.info(f"Transação enviada. Hash da transação: {tx_hash.hex()}. Aguardando confirmação...")

    # Confirmar a transação
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    logger.info(f"Contrato implantado com sucesso em: {tx_receipt['contractAddress']}")

except Exception as e:
    logger.error(f"Erro ao implantar o contrato FlashLoanReceiver: {str(e)}")
    raise
