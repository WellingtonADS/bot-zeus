import os
import sys
from web3 import Web3
from web3.types import TxReceipt, TxParams
from hexbytes import HexBytes

# --- Configuração de Caminhos e Importações ---
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)

from utils.config import config
from utils.gas_utils import obter_taxa_gas

# --- Variáveis Globais do Módulo ---
web3: Web3 = config['web3']
logger = config['logger']
private_key = config['private_key']
nonce_manager = config['nonce_manager']
flashloan_contract = config['flashloan_contract']

# --- Funções de Transação ---

def enviar_transacao_assinada(tx: TxParams) -> HexBytes:
    """Assina e envia uma transação, retornando o hash."""
    try:
        logger.info("Enviando transação para a rede...")
        signed_tx = web3.eth.account.sign_transaction(tx, private_key)
        tx_hash = web3.eth.send_raw_transaction(signed_tx.rawTransaction)
        logger.info(f"Transação enviada com sucesso. Hash: {tx_hash.hex()}")
        return tx_hash
    except Exception as e:
        # CORREÇÃO: O log de erro agora mostra a exceção principal, que é mais informativa
        # e evita o AttributeError.
        logger.error(
            f"Erro ao enviar transação. Nonce: {tx.get('nonce')}. "
            f"Causa: {e}"
        )
        raise

def aguardar_recibo_transacao(tx_hash: HexBytes, timeout_segundos: int = 180) -> TxReceipt:
    """Aguarda o recibo da transação."""
    try:
        logger.info(f"Aguardando recibo para a transação {tx_hash.hex()}...")
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout_segundos)
        
        if receipt['status'] == 1:
            logger.info(f"Transação {tx_hash.hex()} confirmada com sucesso no bloco {receipt['blockNumber']}.")
        else:
            logger.warning(f"Transação {tx_hash.hex()} falhou (revertida). Status: 0.")
        
        return receipt
    except Exception as e:
        logger.error(f"Erro ao aguardar o recibo da transação {tx_hash.hex()}: {e}")
        raise

# --- Função Principal do Flash Loan ---

def iniciar_operacao_flash_loan(
    token_a_emprestar: str,
    quantidade_a_emprestar: float,
    params_codificados: bytes
) -> TxReceipt | None:
    """
    Prepara e envia a transação para iniciar a operação de Flash Loan.
    """
    tx = None # Inicializa tx para o bloco except
    try:
        quantidade_em_unidade_base = config['to_base'](web3, quantidade_a_emprestar, token_a_emprestar)
        
        logger.info(
            f"Iniciando Flash Loan de {quantidade_a_emprestar} de {token_a_emprestar[-6:]} "
            f"({quantidade_em_unidade_base} na unidade base)."
        )

        tx_func = flashloan_contract.functions.initiateFlashLoan(
            Web3.to_checksum_address(token_a_emprestar),
            quantidade_em_unidade_base,
            params_codificados
        )

        nonce = nonce_manager.get_nonce(refresh=True)
        gas_price_gwei = obter_taxa_gas(web3, logger)
        
        tx = tx_func.build_transaction({
            'chainId': web3.eth.chain_id,
            'gas': config['gas_limit'],
            'gasPrice': Web3.to_wei(gas_price_gwei, 'gwei'),
            'nonce': nonce,
        })

        tx_hash = enviar_transacao_assinada(tx)
        receipt = aguardar_recibo_transacao(tx_hash)

        nonce_manager.incrementar_se_confirmado(receipt)

        return receipt

    except Exception as e:
        logger.critical(f"Falha crítica ao executar o flash loan: {e}")
        nonce_manager.sync_with_network()
        return None # Retorna None em caso de falha
