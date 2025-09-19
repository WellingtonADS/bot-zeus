import os
import sys
import json
import logging
from decimal import Decimal
from dotenv import load_dotenv
from web3 import Web3
from web3.middleware.geth_poa import geth_poa_middleware

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

def obter_variavel_ambiente_opcional(nome_variavel: str) -> str | None:
    """Obtém uma variável de ambiente opcional; retorna None se ausente."""
    valor = os.getenv(nome_variavel)
    if not valor:
        logger.warning(f"Variável de ambiente opcional '{nome_variavel}' não definida. Será tentada a inferência automática quando possível.")
        return None
    return valor

try:
    # Configurações da carteira e do provedor
    WALLET_ADDRESS = Web3.to_checksum_address(obter_variavel_ambiente("WALLET_ADDRESS"))
    PRIVATE_KEY = obter_variavel_ambiente("PRIVATE_KEY")
    # Provedores RPC: suporte a múltiplos via fallback
    # Ordem de preferência: INFURA_URL -> RPC_URL -> FORK_RPC_URL -> LOCAL_RPC_URL -> http://127.0.0.1:8545
    PROVIDER_CANDIDATES = [
        os.getenv("INFURA_URL"),
        os.getenv("RPC_URL"),
        os.getenv("FORK_RPC_URL"),
        os.getenv("LOCAL_RPC_URL"),
        "http://127.0.0.1:8545",
    ]

    # Endereços dos contratos
    FLASHLOAN_CONTRACT_ADDRESS = Web3.to_checksum_address(obter_variavel_ambiente("FLASHLOAN_CONTRACT_ADDRESS"))
    UNISWAP_V3_ROUTER_ADDRESS = Web3.to_checksum_address(obter_variavel_ambiente("UNISWAP_V3_ROUTER_ADDRESS"))
    QUOTER_ADDRESS = Web3.to_checksum_address(obter_variavel_ambiente("QUOTER_ADDRESS"))
    SUSHISWAP_ROUTER_ADDRESS = Web3.to_checksum_address(obter_variavel_ambiente("SUSHISWAP_ROUTER_ADDRESS"))
    QUICKSWAP_ROUTER_ADDRESS = Web3.to_checksum_address(obter_variavel_ambiente("QUICKSWAP_ROUTER_ADDRESS"))
    # Factories V2: agora opcionais; se ausentes, serão inferidas via router.factory()
    _qf = obter_variavel_ambiente_opcional("QUICKSWAP_FACTORY_ADDRESS")
    QUICKSWAP_FACTORY_ADDRESS = Web3.to_checksum_address(_qf) if _qf else None
    _sf = obter_variavel_ambiente_opcional("SUSHISWAP_FACTORY_ADDRESS")
    SUSHISWAP_FACTORY_ADDRESS = Web3.to_checksum_address(_sf) if _sf else None

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
last_err = None
web3_instance = None
chosen_url = None
for candidate in [url for url in PROVIDER_CANDIDATES if url]:
    try:
        w3 = Web3(Web3.HTTPProvider(candidate))
        w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        if w3.is_connected():
            web3_instance = w3
            chosen_url = candidate
            break
        else:
            last_err = RuntimeError(f"Não conectou em {candidate}")
    except Exception as e:
        last_err = e

if web3_instance is None:
    logger.critical("Falha na conexão com o nó da Polygon. Verifique sua variável INFURA_URL/RPC_URL ou inicialize seu nó local.")
    if last_err:
        logger.critical(f"Último erro: {last_err}")
    raise ConnectionError("Não foi possível conectar à rede Polygon.")

logger.info(f"Conexão com a rede Polygon estabelecida com sucesso. URL: {chosen_url}")


# --- 3. FUNÇÕES UTILITÁRIAS E CARREGAMENTO DE CONTRATOS ---

ABIS_DIR = os.path.join(BASE_DIR, 'abis')

def carregar_abi_localmente(nome_ficheiro_abi: str) -> list:
    caminho_abi = os.path.join(ABIS_DIR, nome_ficheiro_abi)
    try:
        with open(caminho_abi, 'r') as f:
            data = json.load(f)
            if isinstance(data, dict) and 'abi' in data:
                return data['abi']
            elif isinstance(data, list):
                return data
            else:
                raise ValueError("Formato de ABI inválido.")
    except Exception as e:
        logger.critical(f"Erro ao ler o ficheiro ABI '{nome_ficheiro_abi}': {e}")
        raise

def carregar_contrato(abi_nome: str, endereco: str, nome_legivel: str):
    try:
        if web3_instance is None:
            raise RuntimeError("web3_instance não foi inicializado (sem conexão RPC).")
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

nonce_manager = NonceManager(web3_instance, WALLET_ADDRESS)

# Contratos das DEXs
uniswap_v3_router = carregar_contrato("ISwapRouter.json", UNISWAP_V3_ROUTER_ADDRESS, "Uniswap V3 Router")
uniswap_v3_quoter = carregar_contrato("IQuoter.json", QUOTER_ADDRESS, "Uniswap V3 Quoter")

# Routers V2
sushiswap_router = carregar_contrato("SushiswapV2Router02.json", SUSHISWAP_ROUTER_ADDRESS, "SushiSwap V2 Router")
quickswap_router = carregar_contrato("QuickswapV2Router02.json", QUICKSWAP_ROUTER_ADDRESS, "QuickSwap V2 Router")

# Tentar inferir as factories via router.factory() caso não venham do .env
if SUSHISWAP_FACTORY_ADDRESS is None:
    try:
        inferred = sushiswap_router.functions.factory().call()
        SUSHISWAP_FACTORY_ADDRESS = Web3.to_checksum_address(inferred)
        logger.info(f"SushiSwap V2 Factory inferida via router: {SUSHISWAP_FACTORY_ADDRESS}")
    except Exception as e:
        logger.critical(f"Não foi possível inferir a SushiSwap V2 Factory via router. Defina SUSHISWAP_FACTORY_ADDRESS no .env. Erro: {e}")
        raise

if QUICKSWAP_FACTORY_ADDRESS is None:
    try:
        inferred = quickswap_router.functions.factory().call()
        QUICKSWAP_FACTORY_ADDRESS = Web3.to_checksum_address(inferred)
        logger.info(f"QuickSwap V2 Factory inferida via router: {QUICKSWAP_FACTORY_ADDRESS}")
    except Exception as e:
        logger.critical(f"Não foi possível inferir a QuickSwap V2 Factory via router. Defina QUICKSWAP_FACTORY_ADDRESS no .env. Erro: {e}")
        raise

sushiswap_factory = carregar_contrato("SushiswapV2Factory.json", SUSHISWAP_FACTORY_ADDRESS, "SushiSwap V2 Factory")
quickswap_factory = carregar_contrato("QuickswapV2Factory.json", QUICKSWAP_FACTORY_ADDRESS, "QuickSwap V2 Factory")

dex_contracts = {
    "UniswapV3": {
        "router": uniswap_v3_router,
        "quoter": uniswap_v3_quoter,
    },
    "SushiSwapV2": {
        "router": sushiswap_router,
        "factory": sushiswap_factory,
        # CORREÇÃO: Adicionar o nome do ficheiro ABI do Pair explicitamente
        "pair_abi_name": "SushiswapV2Pair.json"
    },
    "QuickSwapV2": {
        "router": quickswap_router,
        "factory": quickswap_factory,
        # CORREÇÃO: Adicionar o nome do ficheiro ABI do Pair explicitamente
        "pair_abi_name": "QuickswapV2Pair.json"
    }
}

flashloan_contract = carregar_contrato("FlashLoanReceiver.json", FLASHLOAN_CONTRACT_ADDRESS, "FlashLoan Receiver")

# Dicionário de configuração final
config = {
    "web3": web3_instance,
    "logger": logger,
    "nonce_manager": nonce_manager,
    "dex_contracts": dex_contracts,
    "wallet_address": WALLET_ADDRESS,
    "private_key": PRIVATE_KEY,
    "flashloan_contract": flashloan_contract,
    "TOKENS": TOKENS,
    "to_base": converter_para_unidade_base,
    "from_base": converter_de_unidade_base,
    # CORREÇÃO: Expor a função de carregar ABI para outros módulos
    "carregar_abi_localmente": carregar_abi_localmente,
    # Parâmetros operacionais configuráveis via .env
    # GAS_LIMIT: inteiro, limite de gás por transação
    # MIN_BALANCE_MATIC: decimal, saldo mínimo de MATIC exigido
    # SLIPPAGE_BPS: basis points (1% = 100 bps)
    # DEADLINE_SECONDS: segundos adicionados ao timestamp atual para expirar swaps
    "gas_limit": int(os.getenv("GAS_LIMIT", "3000000")),
    "min_balance_matic": Decimal(os.getenv("MIN_BALANCE_MATIC", "5")),
    "slippage_bps": int(os.getenv("SLIPPAGE_BPS", "50")),
    "deadline_seconds": int(os.getenv("DEADLINE_SECONDS", "120")),
}