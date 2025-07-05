# utils/gas_utils.py
import requests
from web3 import Web3
from time import sleep
import os
import logging

def obter_taxa_gas(web3_instance, logger, retries=3, delay=2, timeout=10, tipo="Fast"):
    api_key = os.getenv("POLYGONSCAN_API_KEY")
    url = f"https://api.polygonscan.com/api?module=gastracker&action=gasoracle&apikey={api_key}"

    if api_key:
        for attempt in range(retries):
            try:
                logger.info(f"Tentativa {attempt + 1} de {retries} para obter a taxa de gás da API Polygonscan...")
                response = requests.get(url, timeout=timeout)
                response.raise_for_status()
                data = response.json()

                if data['status'] == '1' and 'result' in data:
                    taxa_gas = data['result'].get(f'{tipo}GasPrice')
                    if taxa_gas:
                        logger.info(f'Taxa de gás {tipo} obtida da API: {taxa_gas} gwei')
                        return float(taxa_gas)
                    else:
                        raise ValueError("Campos esperados não encontrados na resposta da API.")
                else:
                    raise ValueError(f"Resposta inesperada da API: {data}")

            except (requests.RequestException, ValueError) as e:
                logger.warning(f"Erro ao obter taxa de gás da API Polygonscan: {e}")
                if attempt < retries - 1:
                    sleep(delay)
                else:
                    logger.warning("Tentativas esgotadas. Tentando fallback para Web3.")

    # Fallback para Web3
    try:
        gas_price_wei = web3_instance.eth.gas_price
        gas_price_gwei = Web3.from_wei(gas_price_wei, 'gwei')
        logger.info(f"Taxa de gás obtida via Web3 fallback: {gas_price_gwei} gwei")
        return float(gas_price_gwei)

    except Exception as e:
        logger.error(f"Erro ao obter taxa de gás via Web3: {e}")
        raise RuntimeError("Não foi possível obter a taxa de gás nem pela API Polygonscan nem pela rede Web3.")
