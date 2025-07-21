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

