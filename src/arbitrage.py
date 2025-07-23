"""
Módulo para identificar e executar oportunidades de arbitragem em diferentes DEXs
utilizando a infraestrutura de Flash Loans da Aave.
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
from utils.liquidity_utils import obter_preco_saida
# CORREÇÃO: Importar a nova função de gestão de saldo
from utils.wallet_manager import verificar_saldo_matic_suficiente

# --- Variáveis Globais do Módulo ---
web3 = config['web3']
logger = config['logger']
wallet_address = config['wallet_address']
dex_contracts = config['dex_contracts']
TOKENS = config['TOKENS']
# CORREÇÃO: Obter o saldo mínimo do config
min_balance_matic = config['min_balance_matic']


def identificar_melhor_oportunidade(token_emprestimo: str, quantidade_emprestimo: float):
    """
    Identifica a melhor oportunidade de arbitragem entre diferentes DEXs.
    """
    melhor_oportunidade = None
    melhor_lucro_bruto = 0

    for token_alvo_info in TOKENS.values():
        if token_alvo_info['address'] == token_emprestimo:
            continue
        
        token_alvo = token_alvo_info['address']

        for dex_compra_nome in dex_contracts:
            for dex_venda_nome in dex_contracts:
                if dex_compra_nome == dex_venda_nome:
                    continue

                try:
                    quantidade_base_emprestimo = config['to_base'](web3, quantidade_emprestimo, token_emprestimo)
                    
                    quantidade_recebida_base = obter_preco_saida(
                        dex_compra_nome, token_emprestimo, token_alvo, quantidade_base_emprestimo
                    )

                    if quantidade_recebida_base == 0:
                        continue

                    quantidade_final_base = obter_preco_saida(
                        dex_venda_nome, token_alvo, token_emprestimo, quantidade_recebida_base
                    )

                    lucro_bruto_base = quantidade_final_base - quantidade_base_emprestimo
                    
                    if lucro_bruto_base > melhor_lucro_bruto:
                        melhor_lucro_bruto = lucro_bruto_base
                        lucro_bruto_estimado_decimal = config['from_base'](web3, lucro_bruto_base, token_emprestimo)
                        
                        token_symbol = next((key for key, value in TOKENS.items() if value['address'] == token_emprestimo), "TOKEN")

                        melhor_oportunidade = {
                            "token_alvo": token_alvo,
                            "dex_compra": dex_contracts[dex_compra_nome]['router'].address,
                            "dex_venda": dex_contracts[dex_venda_nome]['router'].address,
                            "lucro_bruto_estimado": lucro_bruto_estimado_decimal,
                            "dex_compra_nome": dex_compra_nome,
                            "dex_venda_nome": dex_venda_nome
                        }
                        logger.info(f"Nova oportunidade: {lucro_bruto_estimado_decimal:.6f} {token_symbol.upper()}. Comprar em {dex_compra_nome}, Vender em {dex_venda_nome}.")

                except Exception as e:
                    logger.debug(f"Erro ao verificar par {token_emprestimo[-4:]}/{token_alvo[-4:]} em {dex_compra_nome}/{dex_venda_nome}: {e}")
                    continue
    
    if melhor_oportunidade:
        logger.info(f"Melhor oportunidade selecionada: Lucro de {melhor_oportunidade['lucro_bruto_estimado']:.6f}. Comprar em {melhor_oportunidade['dex_compra_nome']}, Vender em {melhor_oportunidade['dex_venda_nome']}.")
    
    return melhor_oportunidade


def executar_arbitragem_com_flashloan(oportunidade: dict, token_emprestimo: str, quantidade_emprestimo: float):
    """
    Executa a operação de arbitragem com flash loan.
    """
    try:
        saldo_inicial = config['web3'].eth.get_balance(wallet_address)
        logger.info(f"Saldo inicial de MATIC: {web3.from_wei(saldo_inicial, 'ether')}")

        token_alvo = oportunidade['token_alvo']
        dex_compra = oportunidade['dex_compra']
        dex_venda = oportunidade['dex_venda']

        params_codificados = encode(
            ['address', 'address', 'address'],
            [token_alvo, dex_compra, dex_venda]
        )

        logger.info("Iniciando a transação de flash loan e arbitragem...")
        
        receipt = iniciar_operacao_flash_loan(
            token_a_emprestar=token_emprestimo,
            quantidade_a_emprestar=quantidade_emprestimo,
            params_codificados=params_codificados
        )

        if receipt and receipt['status'] == 1:
            logger.info("Transação de arbitragem executada com sucesso!")
            saldo_final = config['web3'].eth.get_balance(wallet_address)
            verificar_lucro_apos_arbitragem(saldo_inicial, saldo_final, receipt)
        else:
            logger.error("A transação de arbitragem falhou.")

    except Exception as e:
        logger.critical(f"Erro crítico na execução da arbitragem: {e}")

def verificar_lucro_apos_arbitragem(saldo_inicial_wei, saldo_final_wei, receipt):
    """Calcula e verifica o lucro da operação em MATIC (gás)."""
    if not receipt:
        logger.error("Não foi possível verificar o lucro pois o recibo da transação é inválido.")
        return

    custo_gas_wei = receipt.get('gasUsed', 0) * receipt.get('effectiveGasPrice', 0)
    lucro_liquido_wei = (saldo_final_wei - saldo_inicial_wei)
    
    lucro_matic = web3.from_wei(lucro_liquido_wei, 'ether')
    custo_gas_matic = web3.from_wei(custo_gas_wei, 'ether')

    logger.info(f"Custo da transação (gás): {custo_gas_matic:.8f} MATIC")
    if lucro_matic > 0:
        logger.info(f"🎉 Lucro líquido obtido (refletido no saldo de MATIC): {lucro_matic:.8f} MATIC 🎉")
    else:
        logger.warning(f"Prejuízo na operação (refletido no saldo de MATIC): {lucro_matic:.8f} MATIC")


def iniciar_bot_arbitragem(stop_event):
    """Inicia o bot de arbitragem em loop contínuo."""
    TOKEN_EMPRESTIMO = TOKENS['usdc']['address']
    QUANTIDADE_EMPRESTIMO = 1000.0

    logger.info("🤖 Bot de Arbitragem ZEUS iniciado.")
    logger.info(f"A procurar oportunidades com {QUANTIDADE_EMPRESTIMO} USDC.")

    while not stop_event.is_set():
        try:
            # CORREÇÃO: Usa a função centralizada para verificar o saldo
            if not verificar_saldo_matic_suficiente(web3, wallet_address, min_balance_matic):
                time.sleep(300) # Pausa por 5 minutos se o saldo for baixo
                continue

            logger.info("Procurando nova oportunidade de arbitragem...")
            melhor_oportunidade = identificar_melhor_oportunidade(TOKEN_EMPRESTIMO, QUANTIDADE_EMPRESTIMO)
            
            if melhor_oportunidade:
                logger.info("Oportunidade viável encontrada! A executar...")
                executar_arbitragem_com_flashloan(melhor_oportunidade, TOKEN_EMPRESTIMO, QUANTIDADE_EMPRESTIMO)
            else:
                logger.info("Nenhuma oportunidade lucrativa encontrada no momento.")

        except Exception as e:
            logger.error(f"Erro no loop principal do bot: {e}", exc_info=True)

        intervalo_segundos = 60
        logger.info(f"Aguardando {intervalo_segundos} segundos para a próxima verificação.")
        time.sleep(intervalo_segundos)

    logger.info("Bot de arbitragem parado.")
