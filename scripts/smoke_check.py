import os
import sys
from decimal import Decimal

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)

from utils.config import config
from utils.price_oracle import obter_preco_matic_em_usdc

logger = config['logger']
web3 = config['web3']

def main():
    logger.info("Iniciando smoke check do Bot-ZEUS...")

    # 1) RPC / Chain
    assert web3.is_connected(), "Web3 não conectado"
    logger.info(f"RPC OK. ChainId={web3.eth.chain_id}")

    # 2) Variáveis essenciais
    required_keys = [
        'wallet_address','private_key','dex_contracts','flashloan_contract','TOKENS'
    ]
    for k in required_keys:
        assert k in config, f"Chave ausente no config: {k}"
    logger.info("Config básico OK.")

    # 3) Saldos de tokens/ETH
    balance_wei = web3.eth.get_balance(config['wallet_address'])
    logger.info(f"Saldo nativo: {web3.from_wei(balance_wei,'ether'):.6f}")

    # 4) Contratos carregados
    for nome, dex in config['dex_contracts'].items():
        if 'router' in dex:
            logger.info(f"{nome} Router: {dex['router'].address}")
        if 'factory' in dex:
            logger.info(f"{nome} Factory: {dex['factory'].address}")

    logger.info(f"FlashLoanReceiver: {config['flashloan_contract'].address}")

    # 5) Oráculo de preço
    preco = obter_preco_matic_em_usdc()
    assert isinstance(preco, Decimal), "Preço deve ser Decimal"
    logger.info(f"Preço MATIC/USDC: {preco} USDC")

    logger.info("Smoke check concluído com sucesso.")

if __name__ == "__main__":
    main()
