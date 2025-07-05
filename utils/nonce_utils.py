#utils\nonce_utils.py
"""
Este módulo fornece utilitários para gerenciar nonces em transações Ethereum.

Classes:
    NonceManager: Uma classe para gerenciar o nonce para um determinado endereço de carteira Ethereum.

Funções:
    __init__(self, web3, wallet_address): Inicializa o NonceManager com uma instância Web3 e um endereço de carteira.
    get_nonce(self, refresh=False): Retorna o nonce atual, opcionalmente atualizando-o da rede.
    increment_nonce(self): Incrementa o nonce em um.
    sync_with_network(self): Sincroniza o nonce com a rede.

Exemplo de uso:

    web3 = Web3(Web3.HTTPProvider('http://127.0.0.1:8545'))
    wallet_address = '0xSeuEnderecoDeCarteira'
    nonce_manager = NonceManager(web3, wallet_address)

    nonce_atual = nonce_manager.get_nonce()
    nonce_manager.increment_nonce()
    nonce_sincronizado = nonce_manager.sync_with_network()
"""
import logging
from web3 import Web3

logger = logging.getLogger("arbitrage_bot")

class NonceManager:

    def __init__(self, web3, wallet_address):
        self.web3 = web3
        self.wallet_address = Web3.to_checksum_address(wallet_address)

        try:
            self.nonce = self.web3.eth.get_transaction_count(self.wallet_address)
            logger.info(f"Nonce inicializado com valor da rede: {self.nonce}")
        except Exception as e:
            logger.critical(f"Erro ao inicializar o NonceManager: {str(e)}")
            raise RuntimeError("Não foi possível obter o nonce inicial da rede.")

    def get_nonce(self, refresh=False):
        """ Retorna o nonce atual, opcionalmente atualizando da rede. """
        try:
            if refresh:
                self.nonce = self.web3.eth.get_transaction_count(self.wallet_address)
                logger.info(f"Nonce atualizado da rede: {self.nonce}")
            return self.nonce
        except ValueError as e:
            logger.error(f"Erro ao obter nonce da rede: {str(e)}", exc_info=True)
            raise

    def increment_nonce(self):
        """ Incrementa o nonce manualmente. """
        self.nonce += 1
        logger.debug(f"Nonce incrementado localmente para: {self.nonce}")

    def incrementar_se_confirmado(self, tx_receipt):
        """ Incrementa o nonce somente se a transação for confirmada com sucesso. """
        if tx_receipt['status'] == 1:
            self.increment_nonce()
        else:
            logger.error("A transação falhou. Nonce não será incrementado.")
            self.reset_nonce()  # Sincroniza o nonce novamente em caso de falha

    def reset_nonce(self):
        """ Atualiza o nonce diretamente da rede para evitar inconsistências. """
        try:
            self.nonce = self.web3.eth.get_transaction_count(self.wallet_address)
            logger.warning(f"Nonce reiniciado e sincronizado com a rede após falha: {self.nonce}")
        except ValueError as e:
            logger.error(f"Erro ao sincronizar nonce com a rede após falha: {e}", exc_info=True)
            raise

    def sync_with_network(self):
        """ Sincroniza o nonce diretamente com a rede. """
        try:
            self.nonce = self.web3.eth.get_transaction_count(self.wallet_address)
            logger.info(f"Nonce sincronizado com a rede: {self.nonce}")
        except ValueError as e:
            logger.error(f"Erro ao sincronizar nonce com a rede: {e}", exc_info=True)
            raise
