import os
import sys
from web3 import Web3

# Configuração de diretório base e importações
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)

from utils.config import config, logger

# Variáveis principais do módulo
web3 = config['web3']

def obter_preco_saida(dex_nome: str, token_in_address: str, token_out_address: str, quantidade_base_in: int) -> int:
    """
    Obtém a quantidade de saída para uma troca, lidando com diferentes DEXs.

    Args:
        dex_nome: O nome da DEX (ex: "UniswapV3", "SushiSwapV2").
        token_in_address: Endereço do token de entrada.
        token_out_address: Endereço do token de saída.
        quantidade_base_in: A quantidade de entrada na sua unidade base (ex: wei).

    Returns:
        A quantidade de saída na sua unidade base, ou 0 em caso de erro.
    """
    try:
        token_in = Web3.to_checksum_address(token_in_address)
        token_out = Web3.to_checksum_address(token_out_address)

        # Lógica para Roteadores V3 (Uniswap V3)
        if dex_nome == "UniswapV3":
            quoter_contract = config['dex_contracts']['UniswapV3']['quoter']
            # A taxa do pool (fee) é um desafio para arbitragem genérica.
            # 3000 (0.3%) é a mais comum para os principais pares.
            # Para um bot real, seria necessário encontrar a taxa correta do pool.
            fee = 3000
            
            return quoter_contract.functions.quoteExactInputSingle(
                token_in,
                token_out,
                fee,
                quantidade_base_in,
                0  # sqrtPriceLimitX96
            ).call()

        # Lógica para Roteadores V2 (Sushiswap, Quickswap)
        elif dex_nome in ["SushiSwapV2", "QuickSwapV2"]:
            router_contract = config['dex_contracts'][dex_nome]['router']
            path = [token_in, token_out]
            amounts_out = router_contract.functions.getAmountsOut(quantidade_base_in, path).call()
            return amounts_out[1]  # O segundo elemento é a quantidade de saída

        else:
            logger.warning(f"DEX '{dex_nome}' não suportada pela função obter_preco_saida.")
            return 0

    except Exception as e:
        # Erros de "insufficient liquidity" são comuns e podem ser logados como DEBUG
        if 'insufficient liquidity' in str(e).lower():
            logger.debug(f"Liquidez insuficiente para {token_in[-4:]}->{token_out[-4:]} em {dex_nome}.")
        else:
            logger.error(f"Erro ao obter preço de saída em {dex_nome}: {e}")
        return 0

# As funções antigas como formatar_resultado e obter_liquidez_uniswap_v3 podem ser removidas
# se não forem mais utilizadas em outras partes do seu código.
