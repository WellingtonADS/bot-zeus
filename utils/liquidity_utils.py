import os
import sys
from web3 import Web3
from typing import Tuple, List

# Configuração de diretório base e importações
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)

from utils.config import config, logger
from utils.rpc_utils import record_fail
import time

# Cache TTL simples para evitar chamadas repetidas no mesmo ciclo
_quote_cache: dict[tuple, tuple[float, int]] = {}
_CACHE_TTL_SEC = float(os.getenv("QUOTE_CACHE_TTL_SEC", "2"))

def _cache_get(key: tuple) -> int | None:
    ent = _quote_cache.get(key)
    if not ent:
        return None
    ts, val = ent
    if time.time() - ts > _CACHE_TTL_SEC:
        return None
    return val

def _cache_set(key: tuple, value: int):
    _quote_cache[key] = (time.time(), value)

# Variáveis principais do módulo
web3 = config['web3']
TOKENS = config['TOKENS']
# Endereço nulo para verificar se um pool existe
ADDRESS_ZERO = "0x0000000000000000000000000000000000000000"

# --- Helpers para Uniswap V3 multi-hop ---
# O path V3 codifica sequências de (token, fee, token, fee, ..., token)
def _encode_v3_path(tokens: List[str], fees: List[int]) -> bytes:
    """Codifica um caminho V3: tokens (N) e fees (N-1) para bytes conforme especificação Uniswap V3.
    tokens: lista de endereços (str)
    fees: lista de uint24 (int) com len = len(tokens) - 1
    """
    if len(tokens) < 2:
        raise ValueError("Path V3 requer pelo menos 2 tokens")
    if len(fees) != len(tokens) - 1:
        raise ValueError("fees deve ter N-1 elementos para N tokens")
    # Cada token é 20 bytes; cada fee é 3 bytes (uint24 big-endian)
    out = bytearray()
    for i, t in enumerate(tokens):
        # append token
        t_bytes = bytes.fromhex(Web3.to_checksum_address(t)[2:])
        out.extend(t_bytes)
        if i < len(fees):
            f = fees[i]
            if f not in (100, 500, 3000, 10000):
                # ainda permitir qualquer uint24, mas avisar
                logger.debug(f"Fee V3 incomum no path: {f}")
            out.extend(int(f).to_bytes(3, byteorder='big'))
    return bytes(out)

def quote_v3_multihop(token_in: str, token_out: str, amount_in: int, fee_choices: List[int] | None = None) -> tuple[int, List[str], List[int]]:
    """Tenta cotar multi-hop no V3 usando hubs comuns (WMATIC/WETH/USDT/DAI) combinando fees.
    Retorna (best_out, best_tokens, best_fees) onde fees tem len=N-1.
    """
    quoter = config['dex_contracts']['UniswapV3']['quoter']
    token_in = Web3.to_checksum_address(token_in)
    token_out = Web3.to_checksum_address(token_out)
    hubs: List[str] = []
    for key in ['wmatic', 'weth', 'usdt', 'dai']:
        try:
            hubs.append(Web3.to_checksum_address(TOKENS[key]['address']))
        except Exception:
            continue
    from utils.config import config as _cfg
    # Permitir configurar fee tiers via .env; fallback para parâmetros explícitos
    try:
        fees_all = fee_choices or _cfg.get('V3_FEE_CHOICES', [500, 3000])
    except Exception:
        fees_all = fee_choices or [500, 3000]
    try:
        max_hops = int(_cfg.get('V3_MAX_HOPS', 1))
    except Exception:
        max_hops = 1

    candidates: List[tuple[List[str], List[int]]] = []
    # Direto (equivalente ao single-hop)
    for f in fees_all:
        candidates.append(([token_in, token_out], [f]))
    # 1-hop via hub
    for h in hubs:
        if h in (token_in, token_out):
            continue
        for f1 in fees_all:
            for f2 in fees_all:
                candidates.append(([token_in, h, token_out], [f1, f2]))
    # 2-hops via dois hubs distintos (apenas se permitido)
    if max_hops >= 2:
        for i in range(len(hubs)):
            for j in range(len(hubs)):
                if i == j:
                    continue
                h1, h2 = hubs[i], hubs[j]
                if h1 in (token_in, token_out) or h2 in (token_in, token_out):
                    continue
                for f1 in fees_all:
                    for f2 in fees_all:
                        for f3 in fees_all:
                            candidates.append(([token_in, h1, h2, token_out], [f1, f2, f3]))

    best_out = 0
    best_tokens: List[str] = []
    best_fees: List[int] = []
    for toks, fees in candidates:
        # limitar path a (max_hops + 2) tokens: exemplo, max_hops=1 permite [in, hub, out] (3 tokens)
        if len(toks) > (max_hops + 2):
            continue
        try:
            path_bytes = _encode_v3_path(toks, fees)
            out = quoter.functions.quoteExactInput(path_bytes, amount_in).call()
            if out > best_out:
                best_out = out
                best_tokens = toks
                best_fees = fees
        except Exception:
            continue
    return best_out, best_tokens, best_fees

# Expor função pública para consumo externo
def encode_v3_path(tokens: List[str], fees: List[int]) -> bytes:
    return _encode_v3_path(tokens, fees)

# --- NOVA FUNCIONALIDADE (Tarefa 1.1) ---
def obter_reservas_pool_v2(dex_nome: str, token_a_address: str, token_b_address: str) -> Tuple[int, int] | None:
    """
    Obtém as reservas de liquidez de um pool V2 (Sushiswap, Quickswap).

    Args:
        dex_nome: O nome da DEX (ex: "SushiSwapV2").
        token_a_address: Endereço do primeiro token.
        token_b_address: Endereço do segundo token.

    Returns:
        Uma tupla com (reserva_a, reserva_b) se o pool existir, ou None caso contrário.
        As reservas são retornadas na mesma ordem dos tokens de entrada.
    """
    try:
        dex_info = config['dex_contracts'][dex_nome]
        factory_contract = dex_info['factory']
        
        # 1. Encontrar o endereço do pool de liquidez
        pool_address = factory_contract.functions.getPair(token_a_address, token_b_address).call()

        if pool_address == ADDRESS_ZERO:
            logger.debug(f"Pool para {token_a_address[-6:]}/{token_b_address[-6:]} não encontrado em {dex_nome}.")
            return None

        # 2. Interagir com o contrato do pool para obter as reservas
        # CORREÇÃO: Obter o nome do ABI do Pair diretamente da configuração
        pair_abi_nome = dex_info['pair_abi_name']
        # CORREÇÃO: Usar a função de carregar ABI exposta pelo config
        pair_abi = config['carregar_abi_localmente'](pair_abi_nome)
        
        pool_contract = web3.eth.contract(address=pool_address, abi=pair_abi)
        
        token0_address = pool_contract.functions.token0().call()
        (reserve0, reserve1, _) = pool_contract.functions.getReserves().call()

        # 3. Retornar as reservas na ordem correta
        if Web3.to_checksum_address(token_a_address) == token0_address:
            return (reserve0, reserve1)
        else:
            return (reserve1, reserve0)

    except Exception as e:
        logger.error(f"Erro ao obter reservas do pool em {dex_nome}: {e}")
        return None


def obter_preco_saida(dex_nome: str, token_in_address: str, token_out_address: str, quantidade_base_in: int) -> int:
    """
    Obtém a quantidade de saída para uma troca, lidando com diferentes DEXs.
    """
    try:
        token_in = Web3.to_checksum_address(token_in_address)
        token_out = Web3.to_checksum_address(token_out_address)

        # Lógica para Roteadores V3 (Uniswap V3)
        if dex_nome == "UniswapV3":
            quoter_contract = config['dex_contracts']['UniswapV3']['quoter']
            # Considerar múltiplos fee tiers e escolher o maior retorno disponível
            fees = [100, 500, 3000, 10000]
            melhor = 0
            for fee in fees:
                try:
                    cache_key = ("v3_single", token_in, token_out, fee, quantidade_base_in)
                    cached = _cache_get(cache_key)
                    if cached is not None:
                        out = cached
                    else:
                        # retries leves
                        out = 0
                        for _ in range(2):
                            try:
                                out = quoter_contract.functions.quoteExactInputSingle(
                                    token_in, token_out, fee, quantidade_base_in, 0
                                ).call()
                                break
                            except Exception:
                                record_fail()
                                time.sleep(0.1)
                        if out:
                            _cache_set(cache_key, out)
                    if out > melhor:
                        melhor = out
                except Exception as e:
                    # Ignorar erros de pools inexistentes neste fee tier
                    continue
            return melhor

        # Lógica para Roteadores V2 (Sushiswap, Quickswap)
        elif dex_nome in ["SushiSwapV2", "QuickSwapV2"]:
            router_contract = config['dex_contracts'][dex_nome]['router']
            path = [token_in, token_out]
            cache_key = ("v2_path", tuple(path), quantidade_base_in)
            cached = _cache_get(cache_key)
            if cached is not None:
                amounts_out_1 = cached
            else:
                amounts_out_1 = 0
                for _ in range(2):
                    try:
                        amounts_out = router_contract.functions.getAmountsOut(quantidade_base_in, path).call()
                        amounts_out_1 = amounts_out[1]
                        break
                    except Exception:
                        record_fail()
                        time.sleep(0.1)
                if amounts_out_1:
                    _cache_set(cache_key, amounts_out_1)
            return amounts_out_1

        else:
            logger.warning(f"DEX '{dex_nome}' não suportada pela função obter_preco_saida.")
            return 0

    except Exception as e:
        if 'insufficient liquidity' in str(e).lower():
            logger.debug(f"Liquidez insuficiente para {token_in[-4:]}->{token_out[-4:]} em {dex_nome}.")
        else:
            logger.error(f"Erro ao obter preço de saída em {dex_nome}: {e}")
        return 0


def obter_preco_saida_e_fee(dex_nome: str, token_in_address: str, token_out_address: str, quantidade_base_in: int) -> tuple[int, int]:
    """
    Versão que também retorna o fee escolhido quando a DEX é Uniswap V3.
    Para V2, retorna (amountOut, 0).
    """
    try:
        token_in = Web3.to_checksum_address(token_in_address)
        token_out = Web3.to_checksum_address(token_out_address)

        if dex_nome == "UniswapV3":
            quoter_contract = config['dex_contracts']['UniswapV3']['quoter']
            fees = [100, 500, 3000, 10000]
            melhor = 0
            melhor_fee = 3000
            for fee in fees:
                try:
                    cache_key = ("v3_single_fee", token_in, token_out, fee, quantidade_base_in)
                    cached = _cache_get(cache_key)
                    if cached is not None:
                        out = cached
                    else:
                        out = 0
                        for _ in range(2):
                            try:
                                out = quoter_contract.functions.quoteExactInputSingle(
                                    token_in, token_out, fee, quantidade_base_in, 0
                                ).call()
                                break
                            except Exception:
                                record_fail()
                                time.sleep(0.1)
                        if out:
                            _cache_set(cache_key, out)
                    if out > melhor:
                        melhor = out
                        melhor_fee = fee
                except Exception:
                    continue
            return melhor, melhor_fee
        elif dex_nome in ["SushiSwapV2", "QuickSwapV2"]:
            router_contract = config['dex_contracts'][dex_nome]['router']
            path = [token_in, token_out]
            cache_key = ("v2_path_fee", tuple(path), quantidade_base_in)
            cached = _cache_get(cache_key)
            if cached is not None:
                outv = cached
            else:
                outv = 0
                for _ in range(2):
                    try:
                        amounts_out = router_contract.functions.getAmountsOut(quantidade_base_in, path).call()
                        outv = amounts_out[1]
                        break
                    except Exception:
                        record_fail()
                        time.sleep(0.1)
                if outv:
                    _cache_set(cache_key, outv)
            return outv, 0
        else:
            logger.warning(f"DEX '{dex_nome}' não suportada pela função obter_preco_saida_e_fee.")
            return 0, 0
    except Exception as e:
        if 'insufficient liquidity' in str(e).lower():
            logger.debug(f"Liquidez insuficiente para {token_in[-4:]}->{token_out[-4:]} em {dex_nome} (com fee)")
        else:
            logger.error(f"Erro ao obter preço de saída/fee em {dex_nome}: {e}")
        return 0, 0


def _candidate_v2_paths(token_in: str, token_out: str) -> List[List[str]]:
    """Gera caminhos candidatos para V2 (multi-hop):
    - Direto [in, out]
    - 1 hub: via WMATIC/WETH/USDT/DAI (se aplicável)
    - 2 hubs: combinações entre os hubs (ex: in->WMATIC->WETH->out)

    Limita o comprimento do path a 4 nós (3 swaps) para manter custo/risco sob controle.
    """
    token_in = Web3.to_checksum_address(token_in)
    token_out = Web3.to_checksum_address(token_out)
    paths: List[List[str]] = []

    # Sempre considerar o direto
    paths.append([token_in, token_out])

    hubs: List[str] = []
    for key in ['wmatic', 'weth', 'usdt', 'dai']:
        try:
            addr = Web3.to_checksum_address(TOKENS[key]['address'])
            hubs.append(addr)
        except Exception:
            continue

    # 1 intermediário
    for h in hubs:
        if h != token_in and h != token_out:
            paths.append([token_in, h, token_out])

    # 2 intermediários (ordem importa; limitar combinações) — controlado via V2_MAX_HOPS
    try:
        from utils.config import V2_MAX_HOPS as _V2_MAX_HOPS
    except Exception:
        _V2_MAX_HOPS = 1
    if _V2_MAX_HOPS >= 2:
        for i in range(len(hubs)):
            for j in range(len(hubs)):
                if i == j:
                    continue
                h1 = hubs[i]
                h2 = hubs[j]
                if h1 in (token_in, token_out) or h2 in (token_in, token_out):
                    continue
                # Evitar repetições tipo [h1,h2] e [h2,h1] sendo ambos incluídos em excesso
                paths.append([token_in, h1, h2, token_out])

    # Remover duplicados mantendo ordem e limitar a 4 nós
    unique: List[List[str]] = []
    seen = set()
    for p in paths:
        if len(p) < 2 or len(p) > 4:
            continue
        key = tuple(p)
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def obter_melhor_caminho_v2_e_quote(dex_nome: str, token_in_address: str, token_out_address: str, quantidade_base_in: int) -> tuple[int, List[str]]:
    """
    Para V2, testa caminhos candidatos (single-hop e multi-hop) e retorna (melhorAmountOut, melhorPath).
    Para DEXs não V2, retorna (0, []).
    """
    try:
        if dex_nome not in ["SushiSwapV2", "QuickSwapV2"]:
            return 0, []
        router_contract = config['dex_contracts'][dex_nome]['router']
        best_out = 0
        best_path: List[str] = []
        for path in _candidate_v2_paths(token_in_address, token_out_address):
            try:
                cache_key = ("v2_best", tuple(path), quantidade_base_in)
                cached = _cache_get(cache_key)
                if cached is not None:
                    out = cached
                else:
                    out = 0
                    for _ in range(2):
                        try:
                            amounts = router_contract.functions.getAmountsOut(quantidade_base_in, path).call()
                            out = amounts[-1]
                            break
                        except Exception:
                            record_fail()
                            time.sleep(0.1)
                    if out:
                        _cache_set(cache_key, out)
                if out > best_out:
                    best_out = out
                    best_path = path
            except Exception:
                continue
        return best_out, best_path
    except Exception as e:
        logger.error(f"Erro ao obter melhor caminho V2 em {dex_nome}: {e}")
        return 0, []
