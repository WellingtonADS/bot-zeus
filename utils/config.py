import os
import sys
import json
import logging
from decimal import Decimal
from dotenv import load_dotenv
from web3 import Web3
from web3.middleware.geth_poa import geth_poa_middleware
# from uniswap import Uniswap # REMOVIDO: SDK não será utilizado

# --- 1. CONFIGURAÇÃO DE CAMINHOS E LOGGER ---

# Adiciona o diretório raiz ao path para garantir que todos os módulos sejam encontrados
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

# A dependência do NonceManager é mantida, pois é uma classe com estado
from utils.nonce_utils import NonceManager

def configurar_logger():
    """Configura um logger centralizado para o projeto."""
    log_dir = os.path.join(BASE_DIR, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_filename = os.path.join(log_dir, "bot_zeus.log")

    logger = logging.getLogger("bot_zeus")
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        # Handler para o ficheiro de log
        file_handler = logging.FileHandler(log_filename)
        file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(module)s - %(message)s")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # Handler para a consola
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger

logger = configurar_logger()


# --- 2. CARREGAMENTO DE VARIÁVEIS DE AMBIENTE E CONFIGURAÇÕES WEB3 ---

load_dotenv()

def obter_variavel_ambiente(nome_variavel: str) -> str:
    """Obtém uma variável de ambiente ou lança um erro crítico."""
    valor = os.getenv(nome_variavel)
    if not valor:
        logger.critical(f"Variável de ambiente '{nome_variavel}' não definida. Verifique o ficheiro .env.")
        raise ValueError(f"'{nome_variavel}' não está definida.")
    return valor

try:
    # Configurações da carteira e do provedor
    WALLET_ADDRESS = Web3.to_checksum_address(obter_variavel_ambiente("WALLET_ADDRESS"))
    PRIVATE_KEY = obter_variavel_ambiente("PRIVATE_KEY")
    PROVIDER_URL = obter_variavel_ambiente("INFURA_URL")

    # Endereços dos contratos
    FLASHLOAN_CONTRACT_ADDRESS = Web3.to_checksum_address(obter_variavel_ambiente("FLASHLOAN_CONTRACT_ADDRESS"))
    UNISWAP_V3_ROUTER_ADDRESS = Web3.to_checksum_address(obter_variavel_ambiente("UNISWAP_V3_ROUTER_ADDRESS"))
    QUOTER_ADDRESS = Web3.to_checksum_address(obter_variavel_ambiente("QUOTER_ADDRESS"))
    SUSHISWAP_ROUTER_ADDRESS = Web3.to_checksum_address(obter_variavel_ambiente("SUSHISWAP_ROUTER_ADDRESS"))
    QUICKSWAP_ROUTER_ADDRESS = Web3.to_checksum_address(obter_variavel_ambiente("QUICKSWAP_ROUTER_ADDRESS"))

    # Endereços dos tokens
    USDC_ADDRESS = Web3.to_checksum_address(obter_variavel_ambiente("USDC_ADDRESS"))
    WETH_ADDRESS = Web3.to_checksum_address(obter_variavel_ambiente("WETH_ADDRESS"))
    DAI_ADDRESS = Web3.to_checksum_address(obter_variavel_ambiente("DAI_ADDRESS"))
    WMATIC_ADDRESS = Web3.to_checksum_address(obter_variavel_ambiente("WMATIC_ADDRESS"))
    USDT_ADDRESS = Web3.to_checksum_address(obter_variavel_ambiente("USDT_ADDRESS"))

except ValueError as e:
    logger.critical(f"Erro ao carregar configuração inicial: {e}")
    sys.exit(1)

# Instância Web3
web3_instance = Web3(Web3.HTTPProvider(PROVIDER_URL))
web3_instance.middleware_onion.inject(geth_poa_middleware, layer=0)

if not web3_instance.is_connected():
    logger.critical("Falha na conexão com o nó da Polygon.")
    raise ConnectionError("Não foi possível conectar à rede Polygon.")
logger.info("Conexão com a rede Polygon estabelecida com sucesso.")


# --- 3. FUNÇÕES UTILITÁRIAS E CARREGAMENTO DE CONTRATOS ---

ABIS_DIR = os.path.join(BASE_DIR, 'abis')

def carregar_abi_localmente(nome_ficheiro_abi: str) -> list:
    """Carrega um ficheiro JSON de ABI do diretório 'abis'."""
    caminho_abi = os.path.join(ABIS_DIR, nome_ficheiro_abi)
    try:
        with open(caminho_abi, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.critical(f"Ficheiro ABI não encontrado: {caminho_abi}")
        raise
    except json.JSONDecodeError:
        logger.critical(f"Erro ao decodificar o JSON do ABI: {caminho_abi}")
        raise

def carregar_contrato(abi_nome: str, endereco: str, nome_legivel: str):
    """Carrega uma instância de contrato, garantindo o formato correto do endereço."""
    try:
        checksum_address = Web3.to_checksum_address(endereco)
        abi = carregar_abi_localmente(abi_nome)
        contrato = web3_instance.eth.contract(address=checksum_address, abi=abi)
        logger.info(f"Contrato {nome_legivel} em {checksum_address} carregado.")
        return contrato
    except Exception as e:
        logger.critical(f"Falha ao carregar o contrato {nome_legivel}: {e}")
        raise

# Dicionário de Tokens com seus decimais
TOKENS = {
    "usdc": {"address": USDC_ADDRESS, "decimals": 6},
    "usdt": {"address": USDT_ADDRESS, "decimals": 6},
    "weth": {"address": WETH_ADDRESS, "decimals": 18},
    "dai": {"address": DAI_ADDRESS, "decimals": 18},
    "wmatic": {"address": WMATIC_ADDRESS, "decimals": 18},
}

_token_decimals_cache = {}
def obter_decimais_token(w3: Web3, token_address: str) -> int:
    """Obtém dinamicamente os decimais de um token ERC20, com cache."""
    token_address_cs = Web3.to_checksum_address(token_address)
    if token_address_cs in _token_decimals_cache:
        return _token_decimals_cache[token_address_cs]
    for token_info in TOKENS.values():
        if token_info["address"] == token_address_cs:
            _token_decimals_cache[token_address_cs] = token_info["decimals"]
            return token_info["decimals"]
    try:
        erc20_abi = carregar_abi_localmente("ERC20.json")
        token_contract = w3.eth.contract(address=token_address_cs, abi=erc20_abi)
        decimals = token_contract.functions.decimals().call()
        _token_decimals_cache[token_address_cs] = decimals
        return decimals
    except Exception:
        logger.warning(f"Não foi possível obter decimais para {token_address_cs}. Assumindo 18.")
        return 18

def converter_para_unidade_base(w3: Web3, quantidade: float, token_address: str) -> int:
    decimais = obter_decimais_token(w3, token_address)
    fator = Decimal(10) ** decimais
    return int(Decimal(str(quantidade)) * fator)

def converter_de_unidade_base(w3: Web3, quantidade: int, token_address: str) -> Decimal:
    decimais = obter_decimais_token(w3, token_address)
    fator = Decimal(10) ** decimais
    return Decimal(quantidade) / fator


# --- 4. INSTANCIAÇÃO DE OBJETOS E CRIAÇÃO DO DICIONÁRIO DE CONFIGURAÇÃO ---

# Gerenciador de Nonce
nonce_manager = NonceManager(web3_instance, WALLET_ADDRESS)

# Contratos das DEXs
dex_contracts = {
    "UniswapV3": {
        "router": carregar_contrato("ISwapRouter.json", UNISWAP_V3_ROUTER_ADDRESS, "Uniswap V3 Router"),
        "quoter": carregar_contrato("IQuoter.json", QUOTER_ADDRESS, "Uniswap V3 Quoter"),
    },
    "SushiSwapV2": {
        "router": carregar_contrato("SushiswapV2Router02.json", SUSHISWAP_ROUTER_ADDRESS, "SushiSwap V2 Router"),
    },
    "QuickSwapV2": {
        "router": carregar_contrato("QuickswapV2Router02.json", QUICKSWAP_ROUTER_ADDRESS, "QuickSwap V2 Router"),
    }
}

# Contrato de Flash Loan
flashloan_contract = carregar_contrato("FlashLoanReceiver.json", FLASHLOAN_CONTRACT_ADDRESS, "FlashLoan Receiver")

# REMOVIDO: Cliente Uniswap não é mais necessário
# uniswap_client = Uniswap(WALLET_ADDRESS, PRIVATE_KEY, PROVIDER_URL, version=3)


# Dicionário de configuração final para ser importado por outros módulos
config = {
    "web3": web3_instance,
    "logger": logger,
    "nonce_manager": nonce_manager,
    "dex_contracts": dex_contracts,
    "wallet_address": WALLET_ADDRESS,
    "private_key": PRIVATE_KEY,
    "flashloan_contract": flashloan_contract,
    "TOKENS": TOKENS,
    
    # Funções utilitárias
    "to_base": converter_para_unidade_base,
    "from_base": converter_de_unidade_base,
    
    # Parâmetros de execução
    "gas_limit": 3000000,
    "min_balance_matic": Decimal(20),
}
