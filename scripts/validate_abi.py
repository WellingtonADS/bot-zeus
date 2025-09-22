import os
import sys

# Garantir que o diretório raiz do projeto esteja no sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Suporte a --rpc <url> para definir CUSTOM_RPC_URL antes de importar config
if "--rpc" in sys.argv:
    try:
        idx = sys.argv.index("--rpc")
        rpc_url = sys.argv[idx + 1]
        os.environ["CUSTOM_RPC_URL"] = rpc_url
    except Exception:
        print("Uso: scripts/validate_abi.py --rpc <RPC_URL>")
        raise SystemExit(2)

from utils.config import config

if __name__ == "__main__":
    try:
        c = config
        contract = c["flashloan_contract"]
        print("OK: config carregado")
        w3 = c["web3"]
        endpoint = getattr(getattr(w3, "provider", object()), "endpoint_uri", None)
        print("RPC ativo:", endpoint if endpoint else w3.is_connected())
        try:
            print("chainId:", w3.eth.chain_id)
        except Exception as _:
            print("chainId: desconhecido")
        print("Contrato:", contract.address)
        # listar nomes das funções do contrato via ABI
        fn_names = sorted({item["name"] for item in getattr(contract, "abi", []) if isinstance(item, dict) and item.get("type") == "function"})
        print(f"Funções ({len(fn_names)}):", ", ".join(fn_names))
        # tentativa de chamada simples (se existir)
        if "owner" in fn_names:
            try:
                owner = contract.functions.owner().call()
                print("Owner:", owner)
            except Exception as ce:
                print("Aviso: falha ao chamar owner():", ce)
    except Exception as e:
        import traceback
        print("ERRO AO CARREGAR CONFIG/ABI:", e)
        traceback.print_exc()
        raise
