# src/flash_loan.py

import os
import sys
import time
from decimal import Decimal
from web3 import Web3

# Configuração de diretório base e importações
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)

from utils.gas_utils import obter_taxa_gas
from utils.nonce_utils import NonceManager
from utils.address_utils import validar_e_converter_endereco
from utils.config import config, logger, to_base_unit, TOKEN_DECIMALS_BY_ADDRESS
from utils.liquidity_utils import obter_liquidez_uniswap_v3

# Variáveis principais do módulo
web3 = config['web3']
wallet_address = config['wallet_address']
private_key = config['private_key']
dex_contracts = config['dex_contracts']
nonce_manager = config['nonce_manager']
gas_limit = config['gas_limit']
flashloan_contract = config['flashloan_contract']

class UnsupportedDEXFunctionError(Exception):
    """Erro específico para funções não suportadas nos contratos DEX."""
    pass

def definir_funcao_transacao(dex_contract, token_in, token_out, quantidade_uint256, amount_out_min_uint256):
    """Define a função de swap correta com base na função disponível no contrato DEX."""
    if hasattr(dex_contract.functions, 'swapExactTokensForTokens'):
        return dex_contract.functions.swapExactTokensForTokens(
            quantidade_uint256,
            amount_out_min_uint256,
            [token_in, token_out],
            wallet_address,
            int(time.time()) + 300
        )
    elif hasattr(dex_contract.functions, 'exactInputSingle'):
        return dex_contract.functions.exactInputSingle({
            'tokenIn': token_in,
            'tokenOut': token_out,
            'fee': 3000,
            'recipient': wallet_address,
            'deadline': int(time.time()) + 300,
            'amountIn': quantidade_uint256,
            'amountOutMinimum': amount_out_min_uint256,
            'sqrtPriceLimitX96': 0,
        })
    else:
        raise UnsupportedDEXFunctionError("Nenhuma função de swap conhecida encontrada na ABI do contrato DEX.")

def enviar_transacao(signed_tx):
    """Envia uma transação assinada e retorna o hash da transação."""
    try:
        logger.info("Enviando transação.")
        tx_hash = web3.eth.send_raw_transaction(signed_tx.rawTransaction)
        logger.info(f"Transação enviada com sucesso. Hash: {tx_hash.hex()}")
        return tx_hash
    except Exception as e:
        logger.error(f"Erro ao enviar a transação: {e}")
        raise

def verificar_recibo(tx_hash, max_attempts=15):
    """Verifica o recibo da transação com um número máximo de tentativas e tempo de espera de 10 segundos."""
    try:
        logger.info(f"Verificando recibo da transação. Hash: {tx_hash.hex()}")
        receipt, attempt = None, 0
        while receipt is None and attempt < max_attempts:
            receipt = web3.eth.get_transaction_receipt(tx_hash)
            if receipt is None:
                time.sleep(10)
                attempt += 1
                logger.debug(f"Aguardando recibo... Tentativa {attempt}")
        if receipt is None:
            raise TimeoutError("Recibo não encontrado após múltiplas tentativas.")
        logger.info("Transação confirmada." if receipt.status == 1 else "Transação falhou.")
        return receipt
    except Exception as e:
        logger.error(f"Erro ao verificar recibo: {e}")
        raise

def iniciar_flash_loan(tokens, amounts, modes, params):
    """Inicia uma operação de flash loan."""
    nonce_manager.sync_with_network()

    tokens = [str(token) for token in tokens]
    amounts = [int(amount) for amount in amounts]
    modes = [int(mode) for mode in modes]

    try:
        logger.info("Iniciando flash loan.")
        tx = flashloan_contract.functions.initiateFlashLoan(
            tokens, amounts, modes, params
        ).build_transaction({
            'chainId': 137,
            'gas': gas_limit,
            'gasPrice': web3.eth.gas_price,
            'nonce': nonce_manager.get_nonce(),
        })

        signed_tx = web3.eth.account.sign_transaction(tx, private_key)
        tx_hash = enviar_transacao(signed_tx)
        return verificar_recibo(tx_hash)

    except Exception as e:
        logger.error(f"Erro ao executar flash loan: {e}")
        raise

def realizar_transacao(dex_contract, token_in, token_out, quantidade, amount_out_min, tipo_transacao, nonce_manager, tentativas=3, slippage_tolerance=None):
    """Realiza uma transação DEX, incluindo ajuste de slippage e verificação de liquidez."""
    slippage_tolerance = config['slippage_tolerance'] if slippage_tolerance is None else slippage_tolerance

    liquidez = obter_liquidez_uniswap_v3(token_in, token_out, quantidade, web3)
    if liquidez.get('liquidity', 0) <= 0:
        logger.error("Liquidez insuficiente para realizar a transação.")
        return

    try:
        token_in = validar_e_converter_endereco(token_in)
        token_out = validar_e_converter_endereco(token_out)

        # Converte a quantidade para a unidade base usando os decimais do token de entrada
        decimals_in = TOKEN_DECIMALS_BY_ADDRESS[token_in]
        quantidade_uint256 = to_base_unit(quantidade, decimals_in)
        # amount_out_min já vem na unidade base do token de saída, não precisa de conversão
        amount_out_min_uint256 = int(amount_out_min)

        logger.info(f"Construindo transação de {tipo_transacao} para {quantidade_uint256} de {token_in} para {token_out}")

        gas_price = obter_taxa_gas(web3, logger)
        nonce = nonce_manager.get_nonce(refresh=True)
        tx_func = definir_funcao_transacao(dex_contract, token_in, token_out, quantidade_uint256, amount_out_min_uint256)

        tx = tx_func.build_transaction({
            'chainId': 137,
            'gas': gas_limit,
            'gasPrice': int(Web3.to_wei(gas_price, 'gwei')),
            'nonce': nonce,
        })

        signed_tx = web3.eth.account.sign_transaction(tx, private_key)
        tx_hash = enviar_transacao(signed_tx)
        receipt = verificar_recibo(tx_hash)

        if receipt['status'] == 1:
            nonce_manager.increment_nonce()
            logger.info(f"Transação de {tipo_transacao} bem-sucedida: {tx_hash.hex()}")
        return receipt

    except Exception as e:
        logger.error(f"Erro ao realizar transação de {tipo_transacao}: {e}")
        raise

def comprar_token(dex_contract, token_in, token_out, quantidade, amount_out_min, nonce_manager):
    """Realiza uma compra de token via DEX."""
    realizar_transacao(dex_contract, token_in, token_out, quantidade, amount_out_min, 'compra', nonce_manager)

def vender_token(dex_contract, token_in, token_out, quantidade, amount_out_min, nonce_manager):
    """Realiza uma venda de token via DEX."""
    realizar_transacao(dex_contract, token_in, token_out, quantidade, amount_out_min, 'venda', nonce_manager)

def convert_usdt_to_wmatic(dex_contract, usdt_address, quantidade, nonce_manager):
    """Converte USDT para WMATIC utilizando o DEX."""
    try:
        usdt_address = validar_e_converter_endereco(usdt_address)
        wmatic_address = config['wmatic_address']
        liquidez = obter_liquidez_uniswap_v3(usdt_address, wmatic_address, quantidade, web3)
        if liquidez.get('liquidity', 0) <= 0:
            logger.error("Liquidez insuficiente para converter USDT para MATIC.")
            return
        amount_out_min = liquidez['quoted_price']
        comprar_token(dex_contract, usdt_address, wmatic_address, quantidade, amount_out_min, nonce_manager)
    except Exception as e:
        logger.error(f"Erro ao converter USDT para MATIC: {e}")
        raise
