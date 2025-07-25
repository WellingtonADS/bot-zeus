import os
import sys
from web3 import Web3
from typing import Tuple

# Configuração de diretório base e importações
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)

from utils.config import config, logger

# Variáveis principais do módulo
web3 = config['web3']
# Endereço nulo para verificar se um pool existe
ADDRESS_ZERO = "0x0000000000000000000000000000000000000000"

# --- NOVA FUNCIONALIDADE (Tarefa 1.1) ---
def obter_reservas_pool_v2(dex_nome: str, token_a_address: str, token_b_address: str) -> Tuple[int, int] | None:
    """
    Obtém as reservas de liquidez de um pool V2 (Sushiswap, Quickswap).

    Args:
        dex_nome: O nome da DEX (ex: "SushiSwapV2").
        token_a_address: Endereço do primeiro token.
        token_b_address: Endereço do segundo token.

    Returns:
        Uma tupla com (reserva_a, reserva_b) se o pool existir, ou None caso contrário.
        As reservas são retornadas na mesma ordem dos tokens de entrada.
    """
    try:
        dex_info = config['dex_contracts'][dex_nome]
        factory_contract = dex_info['factory']
        
        # 1. Encontrar o endereço do pool de liquidez
        pool_address = factory_contract.functions.getPair(token_a_address, token_b_address).call()

        if pool_address == ADDRESS_ZERO:
            logger.debug(f"Pool para {token_a_address[-6:]}/{token_b_address[-6:]} não encontrado em {dex_nome}.")
            return None

        # 2. Interagir com o contrato do pool para obter as reservas
        # CORREÇÃO: Obter o nome do ABI do Pair diretamente da configuração
        pair_abi_nome = dex_info['pair_abi_name']
        # CORREÇÃO: Usar a função de carregar ABI exposta pelo config
        pair_abi = config['carregar_abi_localmente'](pair_abi_nome)
        
        pool_contract = web3.eth.contract(address=pool_address, abi=pair_abi)
        
        token0_address = pool_contract.functions.token0().call()
        (reserve0, reserve1, _) = pool_contract.functions.getReserves().call()

        # 3. Retornar as reservas na ordem correta
        if Web3.to_checksum_address(token_a_address) == token0_address:
            return (reserve0, reserve1)
        else:
            return (reserve1, reserve0)

    except Exception as e:
        logger.error(f"Erro ao obter reservas do pool em {dex_nome}: {e}")
        return None


def obter_preco_saida(dex_nome: str, token_in_address: str, token_out_address: str, quantidade_base_in: int) -> int:
    """
    Obtém a quantidade de saída para uma troca, lidando com diferentes DEXs.
    """
    try:
        token_in = Web3.to_checksum_address(token_in_address)
        token_out = Web3.to_checksum_address(token_out_address)

        # Lógica para Roteadores V3 (Uniswap V3)
        if dex_nome == "UniswapV3":
            quoter_contract = config['dex_contracts']['UniswapV3']['quoter']
            fee = 3000 # A taxa do pool (0.3%) é a mais comum
            
            return quoter_contract.functions.quoteExactInputSingle(
                token_in, token_out, fee, quantidade_base_in, 0
            ).call()

        # Lógica para Roteadores V2 (Sushiswap, Quickswap)
        elif dex_nome in ["SushiSwapV2", "QuickSwapV2"]:
            router_contract = config['dex_contracts'][dex_nome]['router']
            path = [token_in, token_out]
            amounts_out = router_contract.functions.getAmountsOut(quantidade_base_in, path).call()
            return amounts_out[1]

        else:
            logger.warning(f"DEX '{dex_nome}' não suportada pela função obter_preco_saida.")
            return 0

    except Exception as e:
        if 'insufficient liquidity' in str(e).lower():
            logger.debug(f"Liquidez insuficiente para {token_in[-4:]}->{token_out[-4:]} em {dex_nome}.")
        else:
            logger.error(f"Erro ao obter preço de saída em {dex_nome}: {e}")
        return 0
