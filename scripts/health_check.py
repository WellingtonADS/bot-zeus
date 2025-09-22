import os
import sys
import time

# Garantir que o diretório raiz do projeto esteja no sys.path
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path:
    sys.path.append(base_dir)

from utils.config import config
from utils.gas_utils import obter_taxa_gas
from utils.price_oracle import obter_preco_matic_em_usdc

logger = config['logger']

def main():
    web3 = config['web3']
    issues = []

    # Orçamento e intervalo
    budget = int(os.getenv('SCAN_TIME_BUDGET_SECONDS', '60'))
    interval = int(os.getenv('SCAN_INTERVAL_SECONDS', '60'))
    if budget < 60:
        issues.append(f"SCAN_TIME_BUDGET_SECONDS baixo ({budget}s). Recom.: 90–120s.")
    if budget >= 90 and interval < 15:
        issues.append(f"SCAN_INTERVAL_SECONDS baixo ({interval}s) para budget={budget}. Recom.: 15s.")

    # Slippage e deadline
    slippage = int(os.getenv('SLIPPAGE_BPS', '50'))
    deadline = int(os.getenv('DEADLINE_SECONDS', '120'))
    if slippage < 30:
        issues.append(f"SLIPPAGE_BPS muito baixo ({slippage}). Recom.: 50–80 bps.")
    if deadline < 120:
        issues.append(f"DEADLINE_SECONDS baixo ({deadline}). Recom.: 180s.")

    # Gas e preço do MATIC
    try:
        gas_gwei = obter_taxa_gas(web3, logger)
        if gas_gwei <= 0:
            issues.append("Gas oracle retornou 0. Verificar POLYGONSCAN_API_KEY / RPC.")
    except Exception as e:
        issues.append(f"Falha ao obter gas price: {e}")

    try:
        preco_matic = obter_preco_matic_em_usdc()
        if not preco_matic or preco_matic <= 0:
            issues.append("Preço WMATIC→USDC indisponível. summarize: ver oráculo QuickSwap/RPC.")
    except Exception as e:
        issues.append(f"Falha no oráculo de preço MATIC: {e}")

    # Contrato V2
    if bool(config.get('use_flashloan_v2', False)):
        addr = config.get('flashloan_contract_v2_address')
        if not addr:
            issues.append("USE_FLASHLOAN_V2=1 mas FLASHLOAN_CONTRACT_ADDRESS_V2 ausente no .env.")

    if issues:
        logger.warning("Health Check: %d alerta(s) encontrado(s):", len(issues))
        for i, it in enumerate(issues, 1):
            logger.warning("%d) %s", i, it)
    else:
        logger.info("Health Check: OK. Parâmetros parecem adequados.")

if __name__ == "__main__":
    main()
