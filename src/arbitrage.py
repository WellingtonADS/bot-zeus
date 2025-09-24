"""
Módulo para identificar e executar oportunidades de arbitragem em diferentes DEXs
utilizando a infraestrutura de Flash Loans da Aave.
Versão 2.0: Implementa a otimização de quantidade com base na liquidez do mercado.
"""

import os
import sys
import time
from decimal import Decimal
from eth_abi.abi import encode

# --- Configuração de Caminhos e Importações ---
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)

from src.flash_loan import iniciar_operacao_flash_loan
from utils.config import config
# Funções são importadas diretamente
from utils.liquidity_utils import (
    obter_reservas_pool_v2,
    obter_preco_saida,
    obter_preco_saida_e_fee,
    obter_melhor_caminho_v2_e_quote,
    quote_v3_multihop,
    encode_v3_path,
)
from utils.optimization_utils import calcular_quantidade_otima
from utils.wallet_manager import verificar_saldo_matic_suficiente, verificar_saldo_stables_minimo
from utils.price_oracle import obter_preco_matic_em_usdc
from utils.gas_utils import obter_taxa_gas
from utils.rpc_utils import maybe_failover_if_stale, maybe_return_to_preferred, record_ping, log_metrics_if_due

# --- Variáveis Globais do Módulo ---
web3 = config['web3']
logger = config['logger']
wallet_address = config['wallet_address']
dex_contracts = config['dex_contracts']
TOKENS = config['TOKENS']
ACTIVE_TOKENS = config.get('ACTIVE_TOKENS', list(TOKENS.values()))
min_balance_matic = config['min_balance_matic']
TAXA_FLASH_LOAN = Decimal("0.0009")
MIN_PROFIT_USDC = Decimal(os.getenv("MIN_PROFIT_USDC", "0"))
# Modo seguro: evita enviar transações reais quando ativo
DRY_RUN = os.getenv("DRY_RUN", "1").lower() in ("1", "true", "yes", "on")
LOG_V2_PATHS = os.getenv("LOG_V2_PATHS", "0").lower() in ("1", "true", "yes", "on")
TRIANGULAR_MODE = bool(config.get('triangular_mode', False))
TRIANGULAR_ONLY = bool(config.get('triangular_only', False))
TRIANGULAR_LOG_TOPK = int(config.get('triangular_log_topk', 3))

# Monitor leve de saúde do RPC (detecta blocos estagnados)
_last_block_state = {"num": None, "ts": 0.0}
# Heurísticas anti-saturação/volatilidade
_last_block_time = None
_ema_block_time = None  # ms

def _addr_to_sym(addr: str) -> str:
    try:
        a = web3.to_checksum_address(addr)
    except Exception:
        return addr
    for sym, info in TOKENS.items():
        try:
            if web3.to_checksum_address(info['address']) == a:
                return sym.upper()
        except Exception:
            continue
    return addr[:6] + "…" + addr[-4:] if addr.startswith("0x") and len(addr) > 10 else addr

def calcular_lucro_liquido_esperado(
    lucro_bruto_base: int,
    quantidade_emprestimo_base: int,
    token_emprestimo_address: str,
    override_gas_units: int | None = None
) -> Decimal:
    """
    Calcula o lucro líquido esperado de uma operação, descontando todos os custos.
    """
    lucro_bruto = config['from_base'](web3, lucro_bruto_base, token_emprestimo_address)
    quantidade_emprestimo = config['from_base'](web3, quantidade_emprestimo_base, token_emprestimo_address)

    custo_flash_loan = quantidade_emprestimo * TAXA_FLASH_LOAN

    # CORREÇÃO: Chamar a função obter_taxa_gas diretamente
    preco_gas_gwei = Decimal(obter_taxa_gas(web3, logger))
    # Usar override de gas units se fornecido; caso contrário, limite padrão
    gas_limit_units = Decimal(override_gas_units if override_gas_units is not None else int(config['gas_limit']))
    preco_matic_usdc = obter_preco_matic_em_usdc()
    
    if preco_matic_usdc == 0:
        logger.warning("Não foi possível obter o preço do MATIC. O cálculo do custo do gás será impreciso.")
        custo_gas_usdc = Decimal("inf")
    else:
        # Correção: converter corretamente gwei->wei e depois wei->MATIC
        gas_price_wei = web3.to_wei(preco_gas_gwei, 'gwei')
        custo_gas_wei = int(gas_limit_units) * int(gas_price_wei)
        custo_gas_matic = web3.from_wei(custo_gas_wei, 'ether')
        custo_gas_usdc = custo_gas_matic * preco_matic_usdc

    lucro_liquido = lucro_bruto - custo_flash_loan - custo_gas_usdc
    
    logger.debug(f"Cálculo de Lucro: Bruto={lucro_bruto:.4f}, Custo FlashLoan={custo_flash_loan:.4f}, Custo Gás={custo_gas_usdc:.4f} -> Líquido={lucro_liquido:.4f}")

    return lucro_liquido


def identificar_melhor_oportunidade(token_emprestimo: str):
    """
    Identifica a melhor oportunidade de arbitragem, calculando a quantidade ótima
    e o lucro líquido esperado para cada par.
    """
    melhor_oportunidade = None
    melhor_lucro_liquido = Decimal(0)
    candidatos = []  # coleta para TOP3

    # Orçamento de tempo por varredura
    try:
        # Padrão mais generoso para suportar V3 multi-hop; permite override por ENV
        default_budget = int(config.get('scan_time_budget_seconds', 120))
        budget_sec = int(os.getenv('SCAN_TIME_BUDGET_SECONDS', str(default_budget)))
    except Exception:
        budget_sec = int(config.get('scan_time_budget_seconds', 120))
    inicio = time.time()
    timeout = False

    for token_alvo_info in ACTIVE_TOKENS:
        if token_alvo_info['address'] == token_emprestimo:
            continue
        if time.time() - inicio > budget_sec:
            timeout = True
            break
        token_alvo = token_alvo_info['address']

        dexs_v2 = [dex for dex in dex_contracts if "V2" in dex]
        dexs_compra = dexs_v2 + ["UniswapV3"]
        dexs_venda = dexs_v2 + ["UniswapV3"]
        for dex_compra_nome in dexs_compra:
            if time.time() - inicio > budget_sec:
                timeout = True
                break
            for dex_venda_nome in dexs_venda:
                if dex_compra_nome == dex_venda_nome:
                    continue
                if time.time() - inicio > budget_sec:
                    timeout = True
                    break

                try:
                    # Reservas V2 (para calcular quantidade ótima); V3 usa placeholder
                    reservas_compra = obter_reservas_pool_v2(dex_compra_nome, token_emprestimo, token_alvo) if "V2" in dex_compra_nome else (1, 1)
                    reservas_venda = obter_reservas_pool_v2(dex_venda_nome, token_emprestimo, token_alvo) if "V2" in dex_venda_nome else (1, 1)

                    if not reservas_compra or not reservas_venda:
                        continue

                    quantidade_otima_base = 0
                    if "V2" in dex_compra_nome and "V2" in dex_venda_nome:
                        quantidade_otima_base = calcular_quantidade_otima(
                            reservas_compra[0], reservas_compra[1], reservas_venda[1], reservas_venda[0]
                        )
                    else:
                        # Grid-search para combinações com V3
                        token_decimals = config['TOKENS']['usdc']['decimals'] if token_emprestimo.lower() == config['TOKENS']['usdc']['address'].lower() else 6
                        base_unit = 10 ** token_decimals
                        base_candidates = [100, 200, 350, 500, 750, 1000, 1500, 2000, 3000, 5000, 8000, 12000]
                        candidates_q = [int(x * base_unit) for x in base_candidates]
                        melhor_q = 0
                        melhor_lucro = Decimal(0)
                        last_best_idx = -1
                        for idx, q in enumerate(candidates_q):
                            if time.time() - inicio > budget_sec:
                                timeout = True
                                break
                            # Leg 1
                            if "V2" in dex_compra_nome:
                                out1, _ = obter_melhor_caminho_v2_e_quote(dex_compra_nome, token_emprestimo, token_alvo, q)
                            else:
                                out1, _ = obter_preco_saida_e_fee(dex_compra_nome, token_emprestimo, token_alvo, q)
                            if out1 <= 0:
                                continue
                            # Leg 2
                            if "V2" in dex_venda_nome:
                                out2, _ = obter_melhor_caminho_v2_e_quote(dex_venda_nome, token_alvo, token_emprestimo, out1)
                            else:
                                out2, _ = obter_preco_saida_e_fee(dex_venda_nome, token_alvo, token_emprestimo, out1)
                            if out2 <= 0:
                                continue
                            lucro_bruto_base = out2 - q
                            if lucro_bruto_base <= 0:
                                continue
                            lucro_liquido_tmp = calcular_lucro_liquido_esperado(lucro_bruto_base, q, token_emprestimo)
                            if lucro_liquido_tmp > melhor_lucro:
                                melhor_lucro = lucro_liquido_tmp
                                melhor_q = q
                                last_best_idx = idx
                        # Explorar quantias maiores se topo tocado
                        if not timeout and last_best_idx == len(candidates_q) - 1:
                            for q in [int(x * base_unit) for x in [20000, 30000, 50000]]:
                                if time.time() - inicio > budget_sec:
                                    timeout = True
                                    break
                                if q <= melhor_q:
                                    continue
                                if "V2" in dex_compra_nome:
                                    out1, _ = obter_melhor_caminho_v2_e_quote(dex_compra_nome, token_emprestimo, token_alvo, q)
                                else:
                                    out1, _ = obter_preco_saida_e_fee(dex_compra_nome, token_emprestimo, token_alvo, q)
                                if out1 <= 0:
                                    continue
                                if "V2" in dex_venda_nome:
                                    out2, _ = obter_melhor_caminho_v2_e_quote(dex_venda_nome, token_alvo, token_emprestimo, out1)
                                else:
                                    out2, _ = obter_preco_saida_e_fee(dex_venda_nome, token_alvo, token_emprestimo, out1)
                                if out2 <= 0:
                                    continue
                                lucro_bruto_base = out2 - q
                                if lucro_bruto_base <= 0:
                                    continue
                                lucro_liquido_tmp = calcular_lucro_liquido_esperado(lucro_bruto_base, q, token_emprestimo)
                                if lucro_liquido_tmp > melhor_lucro:
                                    melhor_lucro = lucro_liquido_tmp
                                    melhor_q = q
                        quantidade_otima_base = melhor_q

                    if quantidade_otima_base == 0:
                        logger.debug("Quantidade ótima/estimada resultou em 0. Sem oportunidade para este par/DEX combo.")
                        continue

                    # Quote final com rotas reais/fees para diagnóstico e seleção
                    path1_eval = None
                    path2_eval = None
                    if "V2" in dex_compra_nome:
                        amount_out_swap1, path1_eval = obter_melhor_caminho_v2_e_quote(dex_compra_nome, token_emprestimo, token_alvo, quantidade_otima_base)
                        fee_compra_eval = 0
                        path1_len = len(path1_eval) if path1_eval else 0
                    else:
                        # Comparar single-hop vs multi-hop (diagnóstico)
                        single_out, single_fee = obter_preco_saida_e_fee(dex_compra_nome, token_emprestimo, token_alvo, quantidade_otima_base)
                        mh_out, mh_tokens, mh_fees = (0, [], [])
                        if config.get('enable_v3_multihop_scan', True):
                            mh_out, mh_tokens, mh_fees = quote_v3_multihop(token_emprestimo, token_alvo, quantidade_otima_base)
                        if mh_out > single_out:
                            amount_out_swap1 = mh_out
                            fee_compra_eval = mh_fees[0] if mh_fees else single_fee
                            path1_len = len(mh_tokens)
                            if LOG_V2_PATHS and mh_tokens:
                                logger.info("V3_MULTI-HOP COMPRA: %s", " -> ".join(_addr_to_sym(x) for x in mh_tokens)+f" | fees={mh_fees}")
                        else:
                            amount_out_swap1 = single_out
                            fee_compra_eval = single_fee
                            path1_len = 0
                    if "V2" in dex_venda_nome:
                        amount_out_swap2, path2_eval = obter_melhor_caminho_v2_e_quote(dex_venda_nome, token_alvo, token_emprestimo, amount_out_swap1)
                        fee_venda_eval = 0
                        path2_len = len(path2_eval) if path2_eval else 0
                    else:
                        single_out2, single_fee2 = obter_preco_saida_e_fee(dex_venda_nome, token_alvo, token_emprestimo, amount_out_swap1)
                        mh_out2, mh_tokens2, mh_fees2 = (0, [], [])
                        if config.get('enable_v3_multihop_scan', True):
                            mh_out2, mh_tokens2, mh_fees2 = quote_v3_multihop(token_alvo, token_emprestimo, amount_out_swap1)
                        if mh_out2 > single_out2:
                            amount_out_swap2 = mh_out2
                            fee_venda_eval = mh_fees2[-1] if mh_fees2 else single_fee2
                            path2_len = len(mh_tokens2)
                            if LOG_V2_PATHS and mh_tokens2:
                                logger.info("V3_MULTI-HOP VENDA: %s", " -> ".join(_addr_to_sym(x) for x in mh_tokens2)+f" | fees={mh_fees2}")
                        else:
                            amount_out_swap2 = single_out2
                            fee_venda_eval = single_fee2
                            path2_len = 0

                    lucro_bruto_base = amount_out_swap2 - quantidade_otima_base
                    # Estimar unidades de gás baseadas em hops V2/V3 (aproximação leve)
                    try:
                        hops_v2 = 0
                        hops_v3 = 0
                        if "V2" in dex_compra_nome:
                            hops_v2 += max(1, (path1_len - 1)) if path1_len else 1
                        else:
                            hops_v3 += max(1, (path1_len - 1)) if path1_len else 1
                        if "V2" in dex_venda_nome:
                            hops_v2 += max(1, (path2_len - 1)) if path2_len else 1
                        else:
                            hops_v3 += max(1, (path2_len - 1)) if path2_len else 1
                        # Custos médios aproximados por hop (Polygon): V2~115k, V3~130k
                        gas_units = 50_000  # overhead base
                        gas_units += hops_v2 * 115_000
                        gas_units += hops_v3 * 130_000
                        # Clamp a um teto razoável para evitar extremos
                        gas_units = min(gas_units, int(config.get('gas_limit', 3_000_000)))
                    except Exception:
                        gas_units = None
                    lucro_liquido = calcular_lucro_liquido_esperado(lucro_bruto_base, quantidade_otima_base, token_emprestimo, override_gas_units=gas_units)

                    # Guardar candidato para TOP3
                    try:
                        candidatos.append({
                            "lucro_liquido": lucro_liquido,
                            "lucro_bruto_base": int(lucro_bruto_base),
                            "dex_compra_nome": dex_compra_nome,
                            "dex_venda_nome": dex_venda_nome,
                            "fee_compra": int(fee_compra_eval),
                            "fee_venda": int(fee_venda_eval),
                            "path1_len": int(path1_len),
                            "path2_len": int(path2_len),
                            "path1": path1_eval if LOG_V2_PATHS else None,
                            "path2": path2_eval if LOG_V2_PATHS else None,
                            "quantidade_base": int(quantidade_otima_base),
                            "token_alvo": token_alvo,
                        })
                    except Exception:
                        pass

                    # Seleção se lucro acima do threshold (aplica TRIANGULAR_ONLY se ativo)
                    is_tri_candidate = (path1_len >= 3) or (path2_len >= 3)
                    if TRIANGULAR_ONLY and not is_tri_candidate:
                        continue
                    if lucro_liquido > melhor_lucro_liquido and lucro_liquido >= MIN_PROFIT_USDC:
                        melhor_lucro_liquido = lucro_liquido
                        melhor_oportunidade = {
                            "token_alvo": token_alvo,
                            "dex_compra": dex_contracts[dex_compra_nome]['router'].address,
                            "dex_venda": dex_contracts[dex_venda_nome]['router'].address,
                            "dex_compra_nome": dex_compra_nome,
                            "dex_venda_nome": dex_venda_nome,
                            "quantidade_emprestimo_base": quantidade_otima_base,
                            "quantidade_emprestimo": config['from_base'](web3, quantidade_otima_base, token_emprestimo),
                            "lucro_liquido_estimado": lucro_liquido
                        }
                        tag = " [TRI]" if TRIANGULAR_MODE and is_tri_candidate else ""
                        logger.info(f"Nova oportunidade encontrada{tag}! Lucro líquido estimado: {lucro_liquido:.4f} USDC.")

                except Exception as e:
                    logger.debug(f"Erro ao analisar oportunidade ({dex_compra_nome}->{dex_venda_nome}): {e}", exc_info=True)
                    continue
            if timeout:
                break
        if timeout:
            break

    # Logging de TOPK do ciclo, com marcação de triangulares
    if candidatos:
        try:
            # Quando TRIANGULAR_ONLY, filtramos para candidatos que tenham ao menos um path com 3+ tokens (V2) ou V3 multi-hop indicado
            def _is_tri(c):
                return (c.get("path1_len", 0) >= 3) or (c.get("path2_len", 0) >= 3) or (c.get("path1_len", 0) > 0 and c.get("dex_compra_nome") == 'UniswapV3') or (c.get("path2_len", 0) > 0 and c.get("dex_venda_nome") == 'UniswapV3')

            ordered = sorted(candidatos, key=lambda c: c["lucro_liquido"], reverse=True)
            if TRIANGULAR_ONLY:
                ordered = [c for c in ordered if _is_tri(c)]
            top_k = TRIANGULAR_LOG_TOPK if TRIANGULAR_LOG_TOPK and TRIANGULAR_LOG_TOPK > 0 else 3
            top = ordered[:top_k]
            for idx, c in enumerate(top, start=1):
                token_sym = _addr_to_sym(c.get("token_alvo", ""))
                tri_tag = " TRI" if TRIANGULAR_MODE and ((c.get("path1_len",0) >= 3) or (c.get("path2_len",0) >= 3)) else ""
                logger.info(
                    "TOP%s: rank=%d lucro=%.6f USDC compra=%s venda=%s fee_compra=%s fee_venda=%s path1=%d path2=%d size_base=%d token_alvo=%s%s",
                    str(top_k),
                    idx,
                    float(c["lucro_liquido"]),
                    c["dex_compra_nome"],
                    c["dex_venda_nome"],
                    c.get("fee_compra", 0),
                    c.get("fee_venda", 0),
                    c.get("path1_len", 0),
                    c.get("path2_len", 0),
                    c.get("quantidade_base", 0),
                    token_sym,
                    tri_tag
                )
                if LOG_V2_PATHS:
                    p1 = c.get("path1") or []
                    p2 = c.get("path2") or []
                    if p1:
                        logger.info("TOP3_PATH1[%d]: %s", idx, " -> ".join(_addr_to_sym(x) for x in p1))
                    if p2:
                        logger.info("TOP3_PATH2[%d]: %s", idx, " -> ".join(_addr_to_sym(x) for x in p2))
        except Exception:
            logger.debug("Falha ao registrar TOP3 do ciclo", exc_info=True)

    if melhor_oportunidade:
        logger.info(f"Melhor oportunidade selecionada: Lucro de {melhor_oportunidade['lucro_liquido_estimado']:.4f} USDC.")

    if timeout:
        logger.info("Tempo de varredura esgotado (SCAN_TIME_BUDGET_SECONDS=%s).", budget_sec)

    # Estatísticas de ciclo
    try:
        dur = time.time() - inicio
        total = len(candidatos)
        if TRIANGULAR_MODE:
            tri = sum(1 for c in candidatos if (c.get('path1_len',0) >= 3) or (c.get('path2_len',0) >= 3))
            logger.info("Ciclo: candidatos=%d | triangulares=%d | duração=%.1fs", total, tri, dur)
        else:
            logger.info("Ciclo: candidatos=%d | duração=%.1fs", total, dur)
    except Exception:
        pass

    return melhor_oportunidade


def executar_arbitragem_com_flashloan(oportunidade: dict):
    """
    Executa a operação de arbitragem com a quantidade de empréstimo otimizada.
    """
    try:
        token_emprestimo = config['TOKENS']['usdc']['address']
        quantidade_emprestimo = oportunidade['quantidade_emprestimo']

        logger.info(f"Executando arbitragem com {quantidade_emprestimo:.4f} USDC...")
        
    # Calcular amountOutMinimums com base na DEX de compra/venda selecionada
        slippage_bps = int(config.get('slippage_bps', 50))
        deadline = int(time.time()) + int(config.get('deadline_seconds', 120))

        quantidade_emp_base = oportunidade.get('quantidade_emprestimo_base')
        if not quantidade_emp_base:
            quantidade_emp_base = config['to_base'](web3, float(quantidade_emprestimo), token_emprestimo)

        dex_compra_nome = oportunidade.get('dex_compra_nome', 'QuickSwapV2')
        dex_venda_nome = oportunidade.get('dex_venda_nome', 'QuickSwapV2')

        use_v2_contract = bool(config.get('use_flashloan_v2', False))

        path_compra_v2 = []
        path_venda_v2 = []
        path_compra_v3_bytes = b""
        path_venda_v3_bytes = b""
        # amountOutMin1: tokenEmprestado -> tokenAlvo na DEX de compra
        if dex_compra_nome == 'UniswapV3':
            # comparar single vs multi-hop; usar multi-hop apenas se conseguirmos codificar o path
            single1, fee_single1 = obter_preco_saida_e_fee(dex_compra_nome, token_emprestimo, oportunidade['token_alvo'], quantidade_emp_base)
            mh1, mh_tokens1, mh_fees1 = quote_v3_multihop(token_emprestimo, oportunidade['token_alvo'], quantidade_emp_base)
            quote1 = single1
            fee_compra = fee_single1
            if mh1 > single1 and use_v2_contract and mh_tokens1 and mh_fees1:
                try:
                    encoded = encode_v3_path(mh_tokens1, mh_fees1)
                    # sucesso: usar multi-hop exactInput(bytes); fee_compra é irrelevante
                    path_compra_v3_bytes = encoded
                    quote1 = mh1
                    fee_compra = 0
                except Exception as ex:
                    logger.debug(f"Falha ao codificar path V3 multi-hop (compra). Usando single-hop. Erro: {ex}")
        else:
            quote1, path_compra_v2 = obter_melhor_caminho_v2_e_quote(dex_compra_nome, token_emprestimo, oportunidade['token_alvo'], quantidade_emp_base)
            fee_compra = 0
        amountOutMin1 = int(quote1 * (10_000 - slippage_bps) / 10_000) if quote1 and quote1 > 0 else 0

        # amountOutMin2: tokenAlvo -> tokenEmprestado na DEX de venda
        if dex_venda_nome == 'UniswapV3':
            single2, fee_single2 = obter_preco_saida_e_fee(dex_venda_nome, oportunidade['token_alvo'], token_emprestimo, quote1 if quote1 else 0)
            mh2, mh_tokens2, mh_fees2 = quote_v3_multihop(oportunidade['token_alvo'], token_emprestimo, quote1 if quote1 else 0)
            quote2 = single2
            fee_venda = fee_single2
            if mh2 > single2 and use_v2_contract and mh_tokens2 and mh_fees2:
                try:
                    encoded2 = encode_v3_path(mh_tokens2, mh_fees2)
                    path_venda_v3_bytes = encoded2
                    quote2 = mh2
                    fee_venda = 0
                except Exception as ex:
                    logger.debug(f"Falha ao codificar path V3 multi-hop (venda). Usando single-hop. Erro: {ex}")
        else:
            quote2, path_venda_v2 = obter_melhor_caminho_v2_e_quote(dex_venda_nome, oportunidade['token_alvo'], token_emprestimo, quote1 if quote1 else 0)
            fee_venda = 0
        amountOutMin2 = int(quote2 * (10_000 - slippage_bps) / 10_000) if quote2 and quote2 > 0 else 0

        if amountOutMin1 == 0 or amountOutMin2 == 0:
            logger.warning("Quotes inválidos ou liquidez insuficiente para calcular slippage. Operação abortada.")
            return

        if use_v2_contract:
            params_codificados = encode(
                ['address','address','address','uint256','uint256','uint256','uint24','uint24','address[]','address[]','bytes','bytes'],
                [
                    oportunidade['token_alvo'], oportunidade['dex_compra'], oportunidade['dex_venda'],
                    amountOutMin1, amountOutMin2, deadline,
                    fee_compra, fee_venda,
                    path_compra_v2, path_venda_v2,
                    path_compra_v3_bytes, path_venda_v3_bytes
                ]
            )
        else:
            params_codificados = encode(
                ['address','address','address','uint256','uint256','uint256','uint24','uint24','address[]','address[]'],
                [
                    oportunidade['token_alvo'], oportunidade['dex_compra'], oportunidade['dex_venda'],
                    amountOutMin1, amountOutMin2, deadline,
                    fee_compra, fee_venda,
                    path_compra_v2, path_venda_v2
                ]
            )
        
        if DRY_RUN:
            logger.info(
                "DRY_RUN ativo: transação NÃO será enviada. Resumo: "
                f"dex_compra={dex_compra_nome} fee_compra={fee_compra} amountOutMin1={amountOutMin1} path1_len={len(path_compra_v2)}; "
                f"dex_venda={dex_venda_nome} fee_venda={fee_venda} amountOutMin2={amountOutMin2} path2_len={len(path_venda_v2)}; "
                f"deadline={deadline}"
            )
            if LOG_V2_PATHS:
                if path_compra_v2:
                    logger.info("DRY_RUN PATH1: %s", " -> ".join(_addr_to_sym(x) for x in path_compra_v2))
                if path_venda_v2:
                    logger.info("DRY_RUN PATH2: %s", " -> ".join(_addr_to_sym(x) for x in path_venda_v2))
                if path_compra_v3_bytes:
                    logger.info("DRY_RUN V3_PATH1 bytes len: %d", len(path_compra_v3_bytes))
                if path_venda_v3_bytes:
                    logger.info("DRY_RUN V3_PATH2 bytes len: %d", len(path_venda_v3_bytes))
            return

        receipt = iniciar_operacao_flash_loan(
            token_a_emprestar=token_emprestimo,
            quantidade_a_emprestar=float(quantidade_emprestimo),
            params_codificados=params_codificados
        )

        if receipt and receipt['status'] == 1:
            logger.info("Transação de arbitragem executada com sucesso!")
        else:
            logger.error("A transação de arbitragem falhou (revertida pelo contrato).")

    except Exception as e:
        logger.critical(f"Erro crítico na execução da arbitragem: {e}", exc_info=True)


def iniciar_bot_arbitragem(stop_event):
    """Inicia o bot de arbitragem em loop contínuo."""
    global web3
    TOKEN_EMPRESTIMO = TOKENS['usdc']['address']

    logger.info("Bot de Arbitragem ZEUS v2.0 (Otimizado) iniciado.")

    while not stop_event.is_set():
        try:
            ciclo_inicio = time.time()
            # Monitor RPC: alerta se bloco não avança por >120s
            try:
                bn = int(web3.eth.block_number)
                now = time.time()
                # Telemetria de latência aproximada por diferença de tempo entre blocos
                global _last_block_time, _ema_block_time
                if _last_block_time is not None:
                    dt_ms = (now - _last_block_time) * 1000.0
                    if _ema_block_time is None:
                        _ema_block_time = dt_ms
                    else:
                        _ema_block_time = 0.2 * dt_ms + 0.8 * _ema_block_time
                    record_ping(_ema_block_time or dt_ms)
                _last_block_time = now

                if _last_block_state["num"] is not None and bn <= int(_last_block_state["num"]) and (now - float(_last_block_state["ts"])) > 120:
                    logger.warning("RPC possivelmente estagnado: bloco não avançou por >120s (atual=%s). Tentando failover...", bn)
                    try:
                        if maybe_failover_if_stale(120):
                            # Atualizar web3 local a partir do config global
                            web3 = config['web3']
                            logger.info("Failover aplicado. Novo provider ativo.")
                            # Reset estado para novo provider
                            _last_block_state["num"] = None
                            _last_block_state["ts"] = 0.0
                    except Exception as _e:
                        logger.error("Falha ao tentar failover automático: %s", _e)
                if _last_block_state["num"] != bn:
                    _last_block_state["num"] = bn
                    _last_block_state["ts"] = now
                # Tentar retorno ao provider preferido periodicamente
                try:
                    maybe_return_to_preferred(logger)
                except Exception:
                    pass
            except Exception as e:
                logger.debug("Falha ao ler número do bloco para health-check: %s", e)

            if not verificar_saldo_matic_suficiente(web3, wallet_address, min_balance_matic):
                time.sleep(300)
                continue

            # Checagem de estáveis mínimos (opcional; configurável por .env)
            try:
                from decimal import Decimal as _D
                min_usdc_env = os.getenv("MIN_USDC", "0")
                min_usdt_env = os.getenv("MIN_USDT", "0")
                min_usdc = _D(min_usdc_env) if min_usdc_env else _D("0")
                min_usdt = _D(min_usdt_env) if min_usdt_env else _D("0")
            except Exception:
                min_usdc = Decimal("0")
                min_usdt = Decimal("0")
            if (min_usdc > 0 or min_usdt > 0) and not verificar_saldo_stables_minimo(web3, wallet_address, min_usdc=min_usdc, min_usdt=min_usdt):
                logger.info("Aguardando 5 minutos antes de tentar novamente devido a saldos estáveis insuficientes.")
                time.sleep(300)
                continue

            # Anti-saturação: se orçamento muito apertado no último ciclo, fazer um ciclo de varredura parcial
            try:
                budget_sec = int(os.getenv('SCAN_TIME_BUDGET_SECONDS', str(config.get('scan_time_budget_seconds', 120))))
                fast_scan = False
                if budget_sec <= 60:
                    fast_scan = True
                if _ema_block_time and _ema_block_time > 2000:
                    # latência alta -> fazer uma varredura mais conservadora
                    fast_scan = True
                if fast_scan:
                    logger.info("Orçamento/latência apertados: usando varredura parcial (menos combinações e grid menor).")
                    # Temporariamente reduzir ACTIVE_TOKENS a um subconjunto (ex.: 3 primeiros)
                    old_active = config.get('ACTIVE_TOKENS', [])
                    config['ACTIVE_TOKENS'] = old_active[:3] if len(old_active) > 3 else old_active
            except Exception:
                pass

            logger.info("Procurando nova oportunidade de arbitragem otimizada...")
            melhor_oportunidade = identificar_melhor_oportunidade(TOKEN_EMPRESTIMO)
            
            if melhor_oportunidade:
                executar_arbitragem_com_flashloan(melhor_oportunidade)
            else:
                logger.info("Nenhuma oportunidade lucrativa encontrada no momento.")

        except Exception as e:
            logger.error(f"Erro no loop principal do bot: {e}", exc_info=True)

        try:
            # Padrão alinhado à recomendação; permite override por ENV
            default_interval = int(config.get('scan_interval_seconds', 15))
            intervalo_segundos = int(os.getenv('SCAN_INTERVAL_SECONDS', str(default_interval)))
        except Exception:
            intervalo_segundos = int(config.get('scan_interval_seconds', 15))
        # Autoajuste: se budget >= 90 e intervalo < 15, elevar para 15s
        try:
            budget_sec = int(os.getenv('SCAN_TIME_BUDGET_SECONDS', str(config.get('scan_time_budget_seconds', 120))))
            if budget_sec >= 90 and intervalo_segundos < 15:
                logger.info("Ajustando SCAN_INTERVAL_SECONDS de %ss para 15s (budget=%ss)", intervalo_segundos, budget_sec)
                intervalo_segundos = 15
        except Exception:
            pass
        # Avisos proativos com base no consumo do ciclo e orçamento/intervalo
        try:
            ciclo_duracao = time.time() - ciclo_inicio
            budget_sec = int(os.getenv('SCAN_TIME_BUDGET_SECONDS', '60'))
            # Se o ciclo consumiu >90% do orçamento, sugerir ajuste
            if ciclo_duracao >= 0.9 * budget_sec:
                logger.info(
                    "Ciclo consumiu %.1fs de orçamento (budget=%ss). Considere aumentar SCAN_TIME_BUDGET_SECONDS para 90–120s.",
                    ciclo_duracao, budget_sec
                )
            # Se o intervalo é menor que 15s com orçamento alto, sugerir 15s
            if budget_sec >= 90 and intervalo_segundos < 15:
                logger.info("SCAN_INTERVAL_SECONDS muito baixo (%ss) para budget=%ss. Sugestão: 15s.", intervalo_segundos, budget_sec)
            # Se o ciclo já levou mais que o intervalo, o próximo pode iniciar imediatamente
            if ciclo_duracao >= intervalo_segundos:
                logger.info(
                    "Intervalo (%ss) menor que duração do ciclo (%.1fs). Sugestão: aumentar SCAN_INTERVAL_SECONDS para evitar saturação.",
                    intervalo_segundos, ciclo_duracao
                )
        except Exception:
            pass
        # Ajuste dinâmico leve de slippage/deadline baseado em latência
        try:
            if _ema_block_time and _ema_block_time > 2500:
                os.environ['SLIPPAGE_BPS'] = str(max(50, int(config.get('slippage_bps', 70))))
                os.environ['DEADLINE_SECONDS'] = str(max(240, int(config.get('deadline_seconds', 180))))
            else:
                # valores padrão do config prevalecem; não forçar
                pass
        except Exception:
            pass

        log_metrics_if_due(logger)

        logger.info(f"Aguardando {intervalo_segundos} segundos para a próxima verificação.")
        time.sleep(intervalo_segundos)

    logger.info("Bot de arbitragem parado.")
