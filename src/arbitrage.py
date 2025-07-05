"""
arbitrage.py
Módulo para identificar e executar oportunidades de arbitragem em DEXs usando flash loans.
"""

import os
import sys
import time
from decimal import Decimal
from eth_abi.abi import encode

# Configuração de diretório base e importações
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)

from utils.liquidity_utils import obter_liquidez_uniswap_v3, formatar_resultado
from src.flash_loan import comprar_token, vender_token, iniciar_flash_loan
from utils.config import config, logger, obter_saldo
from utils.nonce_utils import NonceManager

# Configurações principais
web3 = config['web3']
wallet_address = config['wallet_address']
nonce_manager = config['nonce_manager']
min_balance = config['min_balance']
min_profit_ratio = config['min_profit_ratio']
slippage_tolerance = config['slippage_tolerance']
amount_in = config['amount_in']

# Endereços dos tokens
tokens = {
    "usdc": config["usdc_address"],
    "weth": config["weth_address"],
    "dai": config["dai_address"],
    "wmatic": config["wmatic_address"],
    "usdt": config["usdt_address"]
}

def identificar_oportunidades_arbitragem(amount_in):
    """Identifica a melhor oportunidade de arbitragem entre pools do Uniswap V3 para pares de tokens especificados."""
    melhor_oportunidade = None
    melhor_margem = Decimal(0)

    token_pairs = [(token_in, token_out) for token_in in tokens for token_out in tokens if token_in != token_out]
    for token_in, token_out in token_pairs:
        token_in_address = tokens[token_in]
        token_out_address = tokens[token_out]

        liquidez = obter_liquidez_uniswap_v3(token_in, token_out, amount_in, web3)
        if liquidez["quoted_price"] > 0:
            resultado_formatado = formatar_resultado(liquidez, slippage_tolerance)
            margem_alcancada = Decimal(resultado_formatado['quoted_price']) / Decimal(resultado_formatado['price'])

            if margem_alcancada >= min_profit_ratio and margem_alcancada > melhor_margem:
                melhor_oportunidade = (token_in_address, token_out_address, resultado_formatado)
                melhor_margem = margem_alcancada
                logger.info(f"Oportunidade: Comprar {token_in}, vender {token_out} com margem {margem_alcancada}")

    logger.info("Nenhuma oportunidade adequada encontrada." if not melhor_oportunidade else f"Melhor oportunidade selecionada: {melhor_margem}")
    return melhor_oportunidade

def executar_arbitragem_com_flashloan(token_in, token_out, amount_in, dados_arbitragem):
    """Executa uma operação de arbitragem com flash loan usando o melhor par identificado."""
    try:
        nonce_manager.sync_with_network()
        amount_out_min_compra = dados_arbitragem['quoted_price']
        amount_out_min_venda = int(dados_arbitragem['quoted_price'] * (1 - slippage_tolerance))

        margem_alcancada = Decimal(amount_out_min_venda) / Decimal(amount_out_min_compra)
        if margem_alcancada < min_profit_ratio:
            logger.warning(f"Margem insuficiente para {token_in}/{token_out}: {margem_alcancada}")
            return

        expectedProfit = amount_out_min_venda - amount_out_min_compra
        requiredProfit = int(amount_out_min_compra * (min_profit_ratio - 1))
        if expectedProfit < requiredProfit:
            logger.warning(f"Lucro esperado ({expectedProfit}) menor que o necessário ({requiredProfit}).")
            return

        logger.info(f"Executando arbitragem: amount_in: {amount_in}, expectedProfit: {expectedProfit}")

        # Parâmetros de execução
        dexCallData = encode(
            ['address', 'address', 'uint24', 'address', 'uint256', 'uint256', 'uint160'],
            [token_in, token_out, 3000, wallet_address, amount_in, amount_out_min_compra, 0]
        )
        params = encode(
            ['address', 'bytes', 'uint256'],
            [config['dex_contracts']['UniswapV3']['router'].address, dexCallData, expectedProfit]
        )

        # Iniciar flash loan e operações de compra/venda
        iniciar_flash_loan([token_in], [amount_in], [0], params)
        comprar_token(config['dex_contracts']['UniswapV3']['router'], token_in, token_out, amount_in, amount_out_min_compra, nonce_manager)
        nonce_manager.increment_nonce()
        vender_token(config['dex_contracts']['UniswapV3']['router'], token_out, token_in, amount_in, amount_out_min_venda, nonce_manager)
        nonce_manager.increment_nonce()

        verificar_lucro_apos_arbitragem(obter_saldo(wallet_address), obter_saldo(wallet_address))

    except Exception as e:
        logger.error(f"Erro na execução da arbitragem: {str(e)}")

def verificar_lucro_apos_arbitragem(saldo_inicial, saldo_final):
    """Calcula e verifica o lucro da operação."""
    lucro = saldo_final - saldo_inicial
    logger.info(f"Lucro obtido: {lucro} MATIC" if lucro > 0 else "Nenhum lucro obtido.")

def iniciar_bot_arbitragem(stop_event):
    """Inicia o bot de arbitragem em loop contínuo até o stop_event."""
    while not stop_event.is_set():
        try:
            saldo_atual = obter_saldo(wallet_address)
            if saldo_atual < min_balance:
                logger.warning(f"Saldo insuficiente ({saldo_atual} MATIC), requer mínimo de {min_balance} MATIC.")
                time.sleep(60)
                continue

            melhor_oportunidade = identificar_oportunidades_arbitragem(amount_in)
            if melhor_oportunidade:
                token_in_address, token_out_address, dados_arbitragem = melhor_oportunidade
                if not stop_event.is_set():
                    executar_arbitragem_com_flashloan(token_in_address, token_out_address, amount_in, dados_arbitragem)

        except Exception as e:
            logger.error(f"Erro ao identificar oportunidades: {str(e)}")

        intervalo_reinicio = 60
        logger.info(f"Aguardando {intervalo_reinicio} segundos antes de reiniciar.")
        time.sleep(intervalo_reinicio)
