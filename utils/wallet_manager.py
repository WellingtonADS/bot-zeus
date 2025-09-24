"""
Módulo para gerenciar a carteira do bot.

Este módulo contém funções para verificar saldos, e futuramente poderá
conter lógica para rebalanceamento de carteira, como converter lucros
de tokens estáveis para a moeda nativa da rede (MATIC) para pagar taxas de gás.
"""

import os
import sys
from decimal import Decimal
from web3 import Web3
from eth_typing import ChecksumAddress

# --- Configuração de Caminhos e Importações ---
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)

from utils.config import config

# --- Variáveis Globais do Módulo ---
logger = config['logger']

def _erc20_balance(web3: Web3, token_address: str, wallet_address: ChecksumAddress) -> int:
    """Obtém saldo base (uint256) de um ERC20 via ABI local."""
    try:
        abi = config['carregar_abi_localmente']('ERC20.json')
        token = web3.eth.contract(address=Web3.to_checksum_address(token_address), abi=abi)
        return token.functions.balanceOf(wallet_address).call()
    except Exception as e:
        logger.error(f"Erro ao obter saldo ERC20 {token_address[-6:]}: {e}")
        return 0

def verificar_saldo_matic_suficiente(
    web3: Web3, 
    wallet_address: ChecksumAddress, 
    min_balance_matic: Decimal
) -> bool:
    """
    Verifica se o saldo de MATIC na carteira é suficiente para operar.

    Args:
        web3: A instância Web3 conectada à rede.
        wallet_address: O endereço da carteira a ser verificado.
        min_balance_matic: O saldo mínimo de MATIC necessário.

    Returns:
        True se o saldo for suficiente, False caso contrário.
    """
    try:
        balance_wei = web3.eth.get_balance(wallet_address)
        balance_matic = web3.from_wei(balance_wei, 'ether')

        if balance_matic < min_balance_matic:
            logger.warning(
                f"Saldo de MATIC ({balance_matic:.4f}) abaixo do mínimo necessário "
                f"de {min_balance_matic} MATIC. O bot irá pausar."
            )
            return False
        
        logger.info(f"Saldo de MATIC verificado: {balance_matic:.4f} MATIC.")
        return True

    except Exception as e:
        logger.error(f"Erro ao verificar o saldo de MATIC: {e}", exc_info=True)
        return False


def verificar_saldo_stables_minimo(
    web3: Web3,
    wallet_address: ChecksumAddress,
    min_usdc: Decimal = Decimal('1.0'),
    min_usdt: Decimal = Decimal('1.0'),
) -> bool:
    """Valida se há saldo mínimo em USDC/USDT para operações.

    Retorna True se ambos os mínimos forem atendidos (quando endereços existem no config),
    ou se o token estiver ausente no config (não bloqueia).
    """
    ok = True
    TOKENS = config.get('TOKENS', {})
    from_base = config.get('from_base')

    # USDC
    try:
        usdc_info = TOKENS.get('usdc')
        if usdc_info:
            bal_base = _erc20_balance(web3, usdc_info['address'], wallet_address)
            if callable(from_base):
                bal = Decimal(str(from_base(web3, bal_base, usdc_info['address'])))
            else:
                # Fallback: converter por decimais conhecidos (6 para USDC)
                bal = Decimal(bal_base) / (Decimal(10) ** int(usdc_info.get('decimals', 6)))
            if bal < min_usdc:
                logger.warning(f"Saldo USDC baixo: {bal} < {min_usdc}")
                ok = False
    except Exception as e:
        logger.error(f"Erro ao verificar saldo USDC: {e}")
        ok = False

    # USDT
    try:
        usdt_info = TOKENS.get('usdt')
        if usdt_info:
            bal_base = _erc20_balance(web3, usdt_info['address'], wallet_address)
            if callable(from_base):
                bal = Decimal(str(from_base(web3, bal_base, usdt_info['address'])))
            else:
                bal = Decimal(bal_base) / (Decimal(10) ** int(usdt_info.get('decimals', 6)))
            if bal < min_usdt:
                logger.warning(f"Saldo USDT baixo: {bal} < {min_usdt}")
                ok = False
    except Exception as e:
        logger.error(f"Erro ao verificar saldo USDT: {e}")
        ok = False

    if ok:
        logger.info("Saldos mínimos de USDC/USDT verificados.")
    return ok

