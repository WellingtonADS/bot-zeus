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
from utils.liquidity_utils import obter_reservas_pool_v2, obter_preco_saida
from utils.optimization_utils import calcular_quantidade_otima
from utils.wallet_manager import verificar_saldo_matic_suficiente
from utils.price_oracle import obter_preco_matic_em_usdc
from utils.gas_utils import obter_taxa_gas

# --- Variáveis Globais do Módulo ---
web3 = config['web3']
logger = config['logger']
wallet_address = config['wallet_address']
dex_contracts = config['dex_contracts']
TOKENS = config['TOKENS']
min_balance_matic = config['min_balance_matic']
TAXA_FLASH_LOAN = Decimal("0.0009")

def calcular_lucro_liquido_esperado(
    lucro_bruto_base: int,
    quantidade_emprestimo_base: int,
    token_emprestimo_address: str
) -> Decimal:
    """
    Calcula o lucro líquido esperado de uma operação, descontando todos os custos.
    """
    lucro_bruto = config['from_base'](web3, lucro_bruto_base, token_emprestimo_address)
    quantidade_emprestimo = config['from_base'](web3, quantidade_emprestimo_base, token_emprestimo_address)

    custo_flash_loan = quantidade_emprestimo * TAXA_FLASH_LOAN

    # CORREÇÃO: Chamar a função obter_taxa_gas diretamente
    preco_gas_gwei = Decimal(obter_taxa_gas(web3, logger))
    gas_limit = Decimal(config['gas_limit'])
    preco_matic_usdc = obter_preco_matic_em_usdc()
    
    if preco_matic_usdc == 0:
        logger.warning("Não foi possível obter o preço do MATIC. O cálculo do custo do gás será impreciso.")
        custo_gas_usdc = Decimal("inf")
    else:
        custo_gas_matic = web3.from_wei(int(gas_limit * preco_gas_gwei), 'gwei')
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

    for token_alvo_info in TOKENS.values():
        if token_alvo_info['address'] == token_emprestimo:
            continue
        token_alvo = token_alvo_info['address']

        dexs_v2 = [dex for dex in dex_contracts if "V2" in dex]
        for dex_compra_nome in dexs_v2:
            for dex_venda_nome in dexs_v2:
                if dex_compra_nome == dex_venda_nome:
                    continue

                try:
                    reservas_compra = obter_reservas_pool_v2(dex_compra_nome, token_emprestimo, token_alvo)
                    reservas_venda = obter_reservas_pool_v2(dex_venda_nome, token_emprestimo, token_alvo)

                    if not reservas_compra or not reservas_venda:
                        continue

                    quantidade_otima_base = calcular_quantidade_otima(
                        reservas_compra[0], reservas_compra[1],
                        reservas_venda[1], reservas_venda[0]
                    )

                    if quantidade_otima_base == 0:
                        continue

                    # CORREÇÃO: Chamar a função obter_preco_saida diretamente
                    amount_out_swap1 = obter_preco_saida(dex_compra_nome, token_emprestimo, token_alvo, quantidade_otima_base)
                    # CORREÇÃO: Chamar a função obter_preco_saida diretamente
                    amount_out_swap2 = obter_preco_saida(dex_venda_nome, token_alvo, token_emprestimo, amount_out_swap1)
                    
                    lucro_bruto_base = amount_out_swap2 - quantidade_otima_base

                    if lucro_bruto_base <= 0:
                        continue

                    lucro_liquido = calcular_lucro_liquido_esperado(lucro_bruto_base, quantidade_otima_base, token_emprestimo)

                    if lucro_liquido > melhor_lucro_liquido:
                        melhor_lucro_liquido = lucro_liquido
                        melhor_oportunidade = {
                            "token_alvo": token_alvo,
                            "dex_compra": dex_contracts[dex_compra_nome]['router'].address,
                            "dex_venda": dex_contracts[dex_venda_nome]['router'].address,
                            "quantidade_emprestimo": config['from_base'](web3, quantidade_otima_base, token_emprestimo),
                            "lucro_liquido_estimado": lucro_liquido
                        }
                        logger.info(f"Nova oportunidade encontrada! Lucro líquido estimado: {lucro_liquido:.4f} USDC.")

                except Exception as e:
                    logger.debug(f"Erro ao analisar oportunidade: {e}", exc_info=True)
                    continue
    
    if melhor_oportunidade:
        logger.info(f"Melhor oportunidade selecionada: Lucro de {melhor_oportunidade['lucro_liquido_estimado']:.4f} USDC.")
    
    return melhor_oportunidade


def executar_arbitragem_com_flashloan(oportunidade: dict):
    """
    Executa a operação de arbitragem com a quantidade de empréstimo otimizada.
    """
    try:
        token_emprestimo = config['TOKENS']['usdc']['address']
        quantidade_emprestimo = oportunidade['quantidade_emprestimo']

        logger.info(f"Executando arbitragem com {quantidade_emprestimo:.4f} USDC...")
        
        params_codificados = encode(
            ['address', 'address', 'address'],
            [oportunidade['token_alvo'], oportunidade['dex_compra'], oportunidade['dex_venda']]
        )
        
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
    TOKEN_EMPRESTIMO = TOKENS['usdc']['address']

    logger.info("Bot de Arbitragem ZEUS v2.0 (Otimizado) iniciado.")

    while not stop_event.is_set():
        try:
            if not verificar_saldo_matic_suficiente(web3, wallet_address, min_balance_matic):
                time.sleep(300)
                continue

            logger.info("Procurando nova oportunidade de arbitragem otimizada...")
            melhor_oportunidade = identificar_melhor_oportunidade(TOKEN_EMPRESTIMO)
            
            if melhor_oportunidade:
                executar_arbitragem_com_flashloan(melhor_oportunidade)
            else:
                logger.info("Nenhuma oportunidade lucrativa encontrada no momento.")

        except Exception as e:
            logger.error(f"Erro no loop principal do bot: {e}", exc_info=True)

        intervalo_segundos = 60
        logger.info(f"Aguardando {intervalo_segundos} segundos para a próxima verificação.")
        time.sleep(intervalo_segundos)

    logger.info("Bot de arbitragem parado.")
