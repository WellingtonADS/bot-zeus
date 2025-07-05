#utils\abi_utils.py
"""
Módulo utils.abi_utils

Este módulo fornece utilitários para carregar arquivos ABI (Application Binary Interface) 
usados em contratos inteligentes na blockchain.

Funções:
    carregar_abi(abi_filename: str) -> list:
        Carrega um arquivo ABI a partir do diretório 'abis' e retorna seu conteúdo como uma lista.
        Parâmetros:
            abi_filename (str): O nome do arquivo ABI a ser carregado.
        Retorna:
            list: O conteúdo do arquivo ABI como uma lista.
        Exceções:
            TypeError: Se o abi_filename não for uma string.
            FileNotFoundError: Se o arquivo ABI não for encontrado no caminho especificado.
            ValueError: Se o conteúdo do arquivo ABI não for uma lista.
            json.JSONDecodeError: Se ocorrer um erro ao decodificar o arquivo ABI.
            Exception: Para outros erros inesperados durante o carregamento do arquivo ABI.
"""
import json
import logging
import os

logger = logging.getLogger("arbitrage_bot")

def carregar_abi(abi_filename):
    if not isinstance(abi_filename, str):
        logger.error(f"Tipo inválido para abi_filename: {type(abi_filename)}. Esperado uma string.")
        raise TypeError(f"Esperado uma string para abi_filename, mas recebido {type(abi_filename)}.")

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    abi_path = os.path.join(base_dir, 'abis', abi_filename)

    if not os.path.exists(abi_path):
        logger.error(f"Arquivo ABI não encontrado: {abi_path}")
        raise FileNotFoundError(f"Arquivo ABI não encontrado: {abi_path}")

    logger.info(f"Tentando carregar o arquivo ABI de: {abi_path}")

    try:
        with open(abi_path, 'r') as f:
            contract_json = json.load(f)

            if isinstance(contract_json, list):
                logger.info(f"ABI carregada com sucesso do arquivo: {abi_filename} com {len(contract_json)} entradas.")
                return contract_json
            else:
                logger.error(f"Formato inválido de ABI no arquivo: {abi_path}. Esperado uma lista.")
                raise ValueError(f"Formato inválido de ABI no arquivo: {abi_path}. Esperado uma lista.")

    except json.JSONDecodeError as e:
        logger.error(f"Erro ao decodificar o arquivo ABI ({abi_path}): {e}")
        raise

    except Exception as e:
        logger.error(f"Erro inesperado ao carregar o arquivo ABI ({abi_path}): {e}")
        raise
