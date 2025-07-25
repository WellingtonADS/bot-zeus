"""
Módulo de Oráculo de Preços.

Este módulo fornece funções para obter os preços de ativos em tempo real,
consultando pools de liquidez de alta profundidade em DEXs confiáveis.
É essencial para converter custos (como o gás) para a mesma unidade do lucro.
"""

import os
import sys
from decimal import Decimal
from web3 import Web3
import time

# --- Configuração de Caminhos e Importações ---
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)

from utils.config import config
from utils.liquidity_utils import obter_preco_saida

# --- Variáveis Globais do Módulo ---
web3: Web3 = config['web3']
logger = config['logger']
# Tokens WMATIC e USDC para a consulta de preço
WMATIC_ADDRESS = config['TOKENS']['wmatic']['address']
USDC_ADDRESS = config['TOKENS']['usdc']['address']

# Cache simples para o preço do MATIC para evitar chamadas excessivas à API
_preco_matic_cache = {'preco': Decimal(0), 'timestamp': 0}

def obter_preco_matic_em_usdc() -> Decimal:
    """
    Obtém o preço atual de 1 WMATIC em USDC, consultando uma DEX V2.
    Utiliza um cache de 30 segundos para otimizar o desempenho.

    Returns:
        O preço de 1 WMATIC em USDC como um objeto Decimal, ou Decimal(0) em caso de erro.
    """
    cache_validade_segundos = 30
    agora = int(time.time())

    # Verifica se o cache é válido
    if agora - _preco_matic_cache['timestamp'] < cache_validade_segundos:
        return _preco_matic_cache['preco']

    try:
        # Consultar o preço de 1 WMATIC (10**18) em USDC (que tem 6 decimais)
        # Usamos uma DEX V2 confiável como a QuickSwap para este oráculo
        quantidade_wmatic_base = 10**18 # 1 WMATIC
        preco_usdc_base = obter_preco_saida(
            "QuickSwapV2", WMATIC_ADDRESS, USDC_ADDRESS, quantidade_wmatic_base
        )

        if preco_usdc_base > 0:
            # Converter o resultado (que está em unidade base de USDC) para um valor legível
            preco_usdc = config['from_base'](web3, preco_usdc_base, USDC_ADDRESS)
            
            # Atualizar o cache
            _preco_matic_cache['preco'] = preco_usdc
            _preco_matic_cache['timestamp'] = agora
            
            logger.debug(f"Preço do MATIC atualizado: 1 MATIC = {preco_usdc:.4f} USDC")
            return preco_usdc
        else:
            return Decimal(0)

    except Exception as e:
        logger.error(f"Erro ao obter o preço do MATIC: {e}")
        return Decimal(0)

