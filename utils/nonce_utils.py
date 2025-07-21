"""
Este módulo fornece uma classe robusta para gerenciar nonces em transações Ethereum,
prevenindo erros de nonce duplicado ou "nonce too low".

Classes:
    NonceManager: Gerencia o nonce para um endereço de carteira, com sincronização
                  automática e manual com a rede.
"""
import logging
from web3 import Web3
# CORREÇÃO: Importar ChecksumAddress diretamente da sua biblioteca de origem (eth-typing)
# para garantir a máxima compatibilidade com linters como o Pylance.
from eth_typing import ChecksumAddress
from web3.types import TxReceipt

# Usa o logger centralizado configurado em utils.config
logger = logging.getLogger("bot_zeus")

class NonceManager:
    """
    Uma classe para gerenciar o nonce de uma carteira de forma segura.

    Mantém um contador de nonce local que é incrementado após cada transação bem-sucedida
    e pode ser ressincronizado com a rede para garantir consistência.
    """

    def __init__(self, web3: Web3, wallet_address: str):
        """
        Inicializa o NonceManager.

        Args:
            web3: Uma instância Web3 conectada à rede.
            wallet_address: O endereço da carteira para gerenciar o nonce.
        """
        self.web3 = web3
        # A anotação de tipo agora usa o import direto de eth_typing, que resolve o erro.
        self.wallet_address: ChecksumAddress = Web3.to_checksum_address(wallet_address)
        self.nonce: int = -1  # Inicializa com -1 para indicar que ainda não foi sincronizado
        self.sync_with_network() # Sincroniza o nonce na inicialização

    def get_nonce(self, refresh: bool = False) -> int:
        """
        Retorna o nonce atual.

        Args:
            refresh: Se True, força uma nova sincronização com a rede antes de retornar.

        Returns:
            O nonce atual.
        """
        if refresh:
            self.sync_with_network()
        return self.nonce

    def increment_nonce(self) -> None:
        """Incrementa o nonce local em 1."""
        self.nonce += 1
        logger.debug(f"Nonce incrementado localmente para: {self.nonce}")

    def incrementar_se_confirmado(self, tx_receipt: TxReceipt) -> None:
        """
        Incrementa o nonce somente se a transação for confirmada com sucesso.
        Se a transação falhar, ressincroniza com a rede para evitar inconsistências.
        """
        if tx_receipt and tx_receipt.get('status') == 1:
            self.increment_nonce()
        else:
            logger.warning("A transação falhou ou o recibo é inválido. Nonce não será incrementado.")
            self.sync_with_network()

    def sync_with_network(self) -> None:
        """
        Sincroniza o nonce local com o nonce atual da rede.
        Esta é a única função para buscar o nonce da blockchain.
        """
        try:
            self.nonce = self.web3.eth.get_transaction_count(self.wallet_address)
            logger.info(f"Nonce sincronizado com a rede: {self.nonce}")
        except Exception as e:
            logger.critical(f"Erro crítico ao sincronizar nonce com a rede para o endereço {self.wallet_address}: {e}", exc_info=True)
            # Em caso de falha crítica, não podemos prosseguir com transações
            raise RuntimeError("Não foi possível obter o nonce da rede.")

# A função 'reset_nonce' foi removida por ser redundante com 'sync_with_network'.
