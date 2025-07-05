#utils\address_utils.py
"""
Valida se um endereço Ethereum é válido e o converte para o formato de checksum.

Parâmetros:
    endereco (str): O endereço Ethereum a ser validado e convertido.
    
Retorna:
    str: O endereço Ethereum no formato de checksum.
    
Lança:
    ValueError: Se o endereço não for uma string, for uma string vazia ou não for um endereço Ethereum válido.
    
Exemplo:
    endereco_checksum = validar_e_converter_endereco('0xabc123...')
"""

import logging
from web3 import Web3

# Obter o logger do módulo principal configurado em bot_main.py
logger = logging.getLogger("arbitrage_bot")

def validar_e_converter_endereco(endereco: str) -> str:

    if not isinstance(endereco, str):
        raise ValueError("O endereço deve ser uma string.")
    if not endereco:
        raise ValueError("O endereço não pode ser uma string vazia.")
    if not Web3.is_address(endereco):
        raise ValueError(f"Endereço inválido: {endereco}")
    return Web3.to_checksum_address(endereco)
