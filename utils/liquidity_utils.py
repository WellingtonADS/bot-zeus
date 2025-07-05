from decimal import Decimal
from web3 import Web3
from utils.abi_utils import carregar_abi
from utils.config import config, logger, converter_para_uint256

# Instância da Web3 e variáveis principais
web3_instance = config['web3']
amount_in = config['amount_in']

# Endereços dos Tokens
tokens = {
    "usdc": config["usdc_address"],
    "weth": config["weth_address"],
    "dai": config["dai_address"],
    "wmatic": config["wmatic_address"],
    "usdt": config["usdt_address"]
}

# Faixas de taxa (fee tiers) comuns no Uniswap V3
fee_tiers = [500, 3000, 10000]

# Cache para ABIs para evitar carregamento redundante
_abi_cache = {}

def carregar_abi_cache(nome_arquivo):
    """Carrega a ABI do arquivo com cache."""
    if nome_arquivo not in _abi_cache:
        _abi_cache[nome_arquivo] = carregar_abi(nome_arquivo)
    return _abi_cache[nome_arquivo]

def obter_liquidez_uniswap_v3(token_in_name, token_out_name, amount_in, web3=None):
    """
    Obtém dados de liquidez e preço para um par de tokens no Uniswap V3 em diferentes faixas de taxa.
    """
    web3 = web3 or config['web3']
    dex_data = config['dex_contracts']['UniswapV3']

    # Obtenção direta dos endereços dos tokens
    token_in = tokens.get(token_in_name.lower())
    token_out = tokens.get(token_out_name.lower())
    if not token_in or not token_out:
        logger.error(f"Token {token_in_name} ou {token_out_name} inválido.")
        return {"liquidity": 0, "price": 0, "quoted_price": 0, "fee": None}

    for fee in fee_tiers:
        try:
            logger.info(f"UniswapV3: Buscando dados para {token_in} - {token_out} com taxa {fee}.")
            factory_contract = dex_data['factory']
            pool_address = factory_contract.functions.getPool(token_in, token_out, fee).call()

            if not Web3.is_address(pool_address) or pool_address == "0x0000000000000000000000000000000000000000":
                logger.warning(f"UniswapV3: Pool inexistente para taxa {fee}.")
                continue

            pool_contract = web3.eth.contract(address=pool_address, abi=carregar_abi_cache('V3Pool.json'))
            liquidity = pool_contract.functions.liquidity().call()
            slot_0 = pool_contract.functions.slot0().call()
            sqrt_price_x96 = Decimal(slot_0[0])
            price = (sqrt_price_x96 ** 2) / (2 ** 192)
            price_scaled = price * Decimal(10 ** 18)

            logger.info(f"Liquidez: {liquidity}, Preço: {price_scaled}")

            quoter_contract = web3.eth.contract(
                address=dex_data['quoter'].address,
                abi=carregar_abi_cache('IQuoter.json')
            )
            amount_in_uint256 = int(amount_in * (10 ** 18))
            quoted_price = quoter_contract.functions.quoteExactInputSingle(
                token_in, token_out, fee, amount_in_uint256, 0
            ).call()

            return formatar_resultado({
                "liquidity": liquidity,
                "price": price_scaled,
                "quoted_price": quoted_price,
                "fee": fee
            }, config['slippage_tolerance'])

        except Exception as e:
            logger.error(f"Erro na taxa {fee}: {e}")
            continue

    logger.warning(f"UniswapV3: Nenhuma liquidez encontrada para o par {token_in_name} e {token_out_name}.")
    return {"liquidity": 0, "price": 0, "quoted_price": 0, "fee": None}

def formatar_resultado(dex_data, slippage_tolerance):
    """
    Formata o resultado de acordo com a tolerância de slippage.
    """
    quoted_price = dex_data.get('quoted_price', 0)
    if quoted_price <= 0:
        logger.warning("`quoted_price` inválido.")
        amount_out_min = 0
    else:
        amount_out_min = int(quoted_price * (1 - slippage_tolerance))

    return {
        'liquidity': converter_para_uint256(dex_data['liquidity']),
        'price': converter_para_uint256(dex_data['price']),
        'quoted_price': converter_para_uint256(quoted_price),
        'amount_out_min': amount_out_min,
        'fee': dex_data['fee']
    }
