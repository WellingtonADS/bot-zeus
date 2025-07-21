"""
Módulo para operações de DEX standalone.

Este módulo contém funções para interagir com corretoras descentralizadas (DEXs)
fora do fluxo principal de arbitragem com flash loan. Pode ser usado para tarefas
como rebalanceamento de carteira, conversão de lucros, etc.
"""

import os
import sys
import time
import json
from web3 import Web3
from web3.types import TxReceipt, TxParams
from hexbytes import HexBytes
from eth_typing import ChecksumAddress

# --- Configuração de Caminhos e Importações ---
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)

from utils.config import config
from utils.gas_utils import obter_taxa_gas

# --- Variáveis Globais do Módulo ---
web3: Web3 = config['web3']
logger = config['logger']
wallet_address: ChecksumAddress = config['wallet_address']
private_key = config['private_key']
nonce_manager = config['nonce_manager']
dex_contracts = config['dex_contracts']

class SwapError(Exception):
    """Exceção base para erros durante um swap."""
    pass

def _enviar_e_aguardar_transacao(tx: TxParams) -> TxReceipt:
    """Assina, envia e aguarda a confirmação de uma transação."""
    try:
        # OTIMIZAÇÃO DE GÁS: Estima o gás antes de enviar
        gas_estimate = web3.eth.estimate_gas(tx)
        tx['gas'] = int(gas_estimate * 1.2) # Adiciona 20% de margem de segurança
        logger.info(f"Gás estimado para a transação: {tx['gas']}")

        signed_tx = web3.eth.account.sign_transaction(tx, private_key)
        tx_hash = web3.eth.send_raw_transaction(signed_tx.rawTransaction)
        logger.info(f"Transação enviada. Hash: {tx_hash.hex()}. A aguardar recibo...")
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
        nonce_manager.incrementar_se_confirmado(receipt)
        return receipt
    except Exception as e:
        # Em caso de erro, é crucial sincronizar o nonce para evitar falhas futuras
        nonce_manager.sync_with_network()
        raise SwapError(f"Falha na transação: {e}")

def realizar_swap(
    dex_nome: str,
    token_in_address: str,
    token_out_address: str,
    quantidade_in: float
) -> TxReceipt:
    """
    Realiza uma troca de tokens (swap) em uma DEX específica, incluindo a aprovação (approve).
    """
    try:
        token_in_cs: ChecksumAddress = Web3.to_checksum_address(token_in_address)
        token_out_cs: ChecksumAddress = Web3.to_checksum_address(token_out_address)

        logger.info(
            f"Iniciando swap de {quantidade_in} {token_in_cs[-6:]} para {token_out_cs[-6:]} na {dex_nome}."
        )

        dex_info = dex_contracts.get(dex_nome)
        if not dex_info:
            raise SwapError(f"DEX '{dex_nome}' não encontrada na configuração.")
        
        dex_router = dex_info['router']

        quantidade_base_in = config['to_base'](web3, quantidade_in, token_in_cs)

        with open(os.path.join(base_dir, 'abis', 'ERC20.json')) as f:
            erc20_abi = json.load(f)
        
        token_in_contract = web3.eth.contract(address=token_in_cs, abi=erc20_abi)
        
        allowance = token_in_contract.functions.allowance(wallet_address, dex_router.address).call()
        if allowance < quantidade_base_in:
            logger.info(f"Aprovação necessária para {dex_nome}. A aprovar {quantidade_in} de {token_in_cs[-6:]}...")
            
            approve_tx_func = token_in_contract.functions.approve(dex_router.address, quantidade_base_in)
            
            approve_tx = approve_tx_func.build_transaction({
                'from': wallet_address,
                'nonce': nonce_manager.get_nonce(refresh=True),
                'gasPrice': Web3.to_wei(obter_taxa_gas(web3, logger), 'gwei'),
                # O gás será estimado pela função _enviar_e_aguardar_transacao
            })
            
            receipt_approve = _enviar_e_aguardar_transacao(approve_tx)
            if receipt_approve.get('status') != 1:
                raise SwapError("A transação de aprovação (approve) falhou.")
            logger.info("Aprovação concedida com sucesso.")

        if dex_nome == "UniswapV3":
            tx_func = dex_router.functions.exactInputSingle({
                'tokenIn': token_in_cs, 'tokenOut': token_out_cs, 'fee': 3000, 
                'recipient': wallet_address, 'deadline': int(time.time()) + 300, 
                'amountIn': quantidade_base_in, 'amountOutMinimum': 0, 'sqrtPriceLimitX96': 0
            })
        else: # Para DEXs V2
            path = [token_in_cs, token_out_cs]
            tx_func = dex_router.functions.swapExactTokensForTokens(
                quantidade_base_in, 0, path, wallet_address, int(time.time()) + 300
            )

        swap_tx = tx_func.build_transaction({
            'from': wallet_address,
            'nonce': nonce_manager.get_nonce(),
            'gasPrice': Web3.to_wei(obter_taxa_gas(web3, logger), 'gwei'),
            # O gás será estimado pela função _enviar_e_aguardar_transacao
        })

        receipt_swap = _enviar_e_aguardar_transacao(swap_tx)
        if receipt_swap.get('status') != 1:
            raise SwapError("A transação de swap falhou.")
            
        logger.info("Swap realizado com sucesso!")
        return receipt_swap

    except Exception as e:
        logger.error(f"Falha ao realizar o swap: {e}", exc_info=True)
        raise SwapError(f"Falha no swap: {e}")

