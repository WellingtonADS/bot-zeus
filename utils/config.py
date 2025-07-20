# utils/config.py

import os
import sys
import logging
from decimal import Decimal
from dotenv import load_dotenv
from web3 import Web3
from web3.middleware.geth_poa import geth_poa_middleware
from uniswap import Uniswap

# Diretório base e importações adicionais
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)
from utils.abi_utils import carregar_abi
from utils.nonce_utils import NonceManager

# Carregar variáveis de ambiente
load_dotenv()

# Configuração do Logger
def configurar_logger():
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    log_filename = os.path.join(log_dir, "arbitrage_bot.log")

    logger = logging.getLogger("arbitrage_bot")
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        file_handler = logging.FileHandler(log_filename)
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        console_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    return logger

logger = configurar_logger()

# Função para obter variáveis de ambiente
def obter_variavel_ambiente(variable_name):
    valor = os.getenv(variable_name)
    if not valor:
        logger.error(f"{variable_name} não está definida. Verifique o arquivo .env.")
        raise RuntimeError(f"{variable_name} não está definida. Verifique o arquivo .env.")
    logger.debug(f"Variável de ambiente {variable_name} verificada com sucesso.")
    return valor

# Configurações da Web3 e Endereços Importantes
wallet_address = Web3.to_checksum_address(obter_variavel_ambiente("WALLET_ADDRESS"))
private_key = obter_variavel_ambiente("PRIVATE_KEY")
provider_url = obter_variavel_ambiente("INFURA_URL")

# Endereços dos Contratos
pool_provider_address = Web3.to_checksum_address(obter_variavel_ambiente("POOL_ADDRESSES_PROVIDER"))
flashloan_contract_address = Web3.to_checksum_address(obter_variavel_ambiente("FLASHLOAN_CONTRACT_ADDRESS"))
quoter_address = Web3.to_checksum_address(obter_variavel_ambiente("QUOTER_ADDRESS"))

# Endereços de Tokens e Contratos Uniswap
usdc_address = Web3.to_checksum_address(obter_variavel_ambiente("USDC_ADDRESS"))
weth_address = Web3.to_checksum_address(obter_variavel_ambiente("WETH_ADDRESS"))
dai_address = Web3.to_checksum_address(obter_variavel_ambiente("DAI_ADDRESS"))
wmatic_address = Web3.to_checksum_address(obter_variavel_ambiente("WMATIC_ADDRESS"))
usdt_address = Web3.to_checksum_address(obter_variavel_ambiente("USDT_ADDRESS"))
uniswap_v3_factory_address = Web3.to_checksum_address(obter_variavel_ambiente("UNISWAP_V3_FACTORY_ADDRESS"))
uniswap_v3_router_address = Web3.to_checksum_address(obter_variavel_ambiente("UNISWAP_V3_ROUTER_ADDRESS"))
quoter_address = Web3.to_checksum_address(obter_variavel_ambiente("QUOTER_ADDRESS"))

# Dicionário de Tokens com seus decimais
TOKENS = {
    "usdc": {"address": usdc_address, "decimals": 6},
    "usdt": {"address": usdt_address, "decimals": 6},
    "weth": {"address": weth_address, "decimals": 18},
    "dai": {"address": dai_address, "decimals": 18},
    "wmatic": {"address": wmatic_address, "decimals": 18},
}

# Mapeamento reverso para buscar decimais pelo endereço
TOKEN_DECIMALS_BY_ADDRESS = {
    details["address"]: details["decimals"]
    for token, details in TOKENS.items()
}


# Instância Web3
web3_instance = Web3(Web3.HTTPProvider(provider_url))
web3_instance.middleware_onion.inject(geth_poa_middleware, layer=0)

if not web3_instance.is_connected():
    logger.critical("Falha na conexão com a rede Polygon.")
    raise ConnectionError("Falha na conexão com a rede Polygon.")
logger.info("Conexão com a rede Polygon estabelecida com sucesso.")

# Cliente Uniswap
uniswap_client = Uniswap(wallet_address, private_key, provider_url, version=3)

# Nonce Manager
try:
    nonce_manager = NonceManager(web3_instance, wallet_address)
    logger.info(f"NonceManager inicializado com sucesso para o endereço: {wallet_address}")
except ValueError as e:
    logger.error(f"Erro ao inicializar o NonceManager: {str(e)}")
    raise RuntimeError(f"Erro ao inicializar o NonceManager: {str(e)}")

# Função para carregar e validar ABI
def carregar_e_validar_abi(abi_file, contract_address, contract_name):
    if not contract_address:
        logger.error(f"Endereço do contrato {contract_name} não está definido.")
        raise RuntimeError(f"Endereço do contrato {contract_name} não está definido.")

    try:
        abi = carregar_abi(abi_file)
        if not isinstance(abi, list):
            logger.error(f"Erro: O ABI carregado de {abi_file} não é uma lista.")
            raise ValueError(f"ABI inválido para {contract_name}: não é uma lista.")

        contrato = web3_instance.eth.contract(address=contract_address, abi=abi)
        logger.info(f"Contrato {contract_name} instanciado com sucesso.")
        return contrato
    except Exception as e:
        logger.error(f"Erro ao carregar ABI ou instanciar o contrato {contract_name}: {e}")
        raise RuntimeError(f"Erro ao carregar ABI ou instanciar o contrato {contract_name}: {e}")

# Função para converter valores para a unidade base do token (ex: wei)
def to_base_unit(valor, decimals):
    """Converte um valor para sua unidade base, usando o número de decimais especificado."""
    if not isinstance(valor, (Decimal, str, int, float)):
        raise TypeError(f"Valor para conversão deve ser numérico, mas é {type(valor)}")
    # Usar str(valor) para garantir a precisão do Decimal
    return int(Decimal(str(valor)) * (10**decimals))

# Contratos Dex
dex_contracts = {
    "UniswapV3": {
        "factory": carregar_e_validar_abi("UniswapV3Factory.json", uniswap_v3_factory_address, "UniswapV3 Factory"),
        "router": carregar_e_validar_abi("UniswapV3Router.json", uniswap_v3_router_address, "UniswapV3 Router"),
        "quoter": carregar_e_validar_abi("IQuoter.json", quoter_address, "UniswapV3 Quoter"),
    },
}

# Função para obter saldo
def obter_saldo(wallet_address):
    try:
        balance_wei = web3_instance.eth.get_balance(wallet_address)
        saldo_matic = web3_instance.from_wei(balance_wei, "ether")
        return Decimal(saldo_matic)
    except Exception as e:
        logger.error(f"Erro ao obter saldo da carteira {wallet_address}: {e}")
        raise RuntimeError(f"Erro ao obter saldo da carteira: {e}")

# Parâmetros de Configuração
min_profit_ratio = Decimal("1.01")
amount_in = Decimal("0.003")  # Valor em formato legível, a ser convertido sob demanda
gas_limit = 21000000
slippage_tolerance = Decimal("0.05")
min_balance = Decimal(40)

# Contrato de Flashloan
flashloan_contract = carregar_e_validar_abi("FlashLoanReceiver.json", flashloan_contract_address, "FlashLoan Receiver")

# Dicionário de Configuração
config = {
    "web3": web3_instance,
    "TOKENS": TOKENS,
    "TOKEN_DECIMALS_BY_ADDRESS": TOKEN_DECIMALS_BY_ADDRESS,
    "nonce_manager": nonce_manager,
    "dex_contracts": dex_contracts,
    "wallet_address": wallet_address,
    "private_key": private_key,
    "provider_url": provider_url,
    "pool_provider_address": pool_provider_address,
    "flashloan_contract_address": flashloan_contract_address,
    "flashloan_contract": flashloan_contract,
    "uniswap_client": uniswap_client,
    "usdc_address": usdc_address,
    "weth_address": weth_address,
    "dai_address": dai_address,
    "wmatic_address": wmatic_address,
    "usdt_address": usdt_address,
    "quoter_address": quoter_address,
    "min_profit_ratio": min_profit_ratio,
    "amount_in": amount_in,
    "gas_limit": gas_limit,
    "slippage_tolerance": slippage_tolerance,
    "min_balance": min_balance,
    "to_base_unit": to_base_unit,
}
