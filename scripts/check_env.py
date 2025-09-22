from dotenv import load_dotenv
import os

REQUIRED = [
    "WALLET_ADDRESS",
    "PRIVATE_KEY",
    "FLASHLOAN_CONTRACT_ADDRESS",
    "UNISWAP_V3_ROUTER_ADDRESS",
    "QUOTER_ADDRESS",
    "SUSHISWAP_ROUTER_ADDRESS",
    "QUICKSWAP_ROUTER_ADDRESS",
    "USDC_ADDRESS",
    "WETH_ADDRESS",
    "DAI_ADDRESS",
    "WMATIC_ADDRESS",
    "USDT_ADDRESS",
]

if __name__ == "__main__":
    load_dotenv()
    missing = []
    for k in REQUIRED:
        v = os.getenv(k)
        print(f"{k}={'<set>' if v else '<missing>'}")
        if not v:
            missing.append(k)
    if missing:
        print("FALTANDO VARIÁVEIS:", ", ".join(missing))
        raise SystemExit(2)
    print(".env OK: todas as variáveis obrigatórias estão definidas.")
