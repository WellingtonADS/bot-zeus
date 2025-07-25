"""
Módulo para a otimização matemática de operações de arbitragem.

Este módulo contém as funções que calculam o tamanho ideal de uma transação
para maximizar o lucro, com base na liquidez disponível em dois pools de DEXs.
"""

from decimal import Decimal, getcontext

# Aumenta a precisão para cálculos financeiros
getcontext().prec = 50

def calcular_quantidade_otima(
    reserva_in_dex_a: int,
    reserva_out_dex_a: int,
    reserva_in_dex_b: int,
    reserva_out_dex_b: int
) -> int:
    """
    Calcula a quantidade ótima de 'token_in' para arbitrar entre dois pools de AMM V2.

    A fórmula é derivada do princípio de igualar os preços dos dois pools após a transação,
    maximizando assim o lucro extraído. Ignora as taxas para o cálculo da quantidade ideal,
    pois elas serão subtraídas posteriormente na verificação de lucro líquido.

    Args:
        reserva_in_dex_a: Reserva do token de entrada no pool de compra (DEX A).
        reserva_out_dex_a: Reserva do token de saída no pool de compra (DEX A).
        reserva_in_dex_b: Reserva do token de entrada no pool de venda (DEX B).
        reserva_out_dex_b: Reserva do token de saída no pool de venda (DEX B).

    Returns:
        A quantidade ótima de 'token_in' a ser usada no flash loan, na sua unidade base (wei).
        Retorna 0 se não houver uma oportunidade de arbitragem.
    """
    # Converter para Decimal para precisão
    r_in_a = Decimal(reserva_in_dex_a)
    r_out_a = Decimal(reserva_out_dex_a)
    r_in_b = Decimal(reserva_in_dex_b)
    r_out_b = Decimal(reserva_out_dex_b)

    # Fórmula para a quantidade ótima de entrada (amount_in)
    # amount_in = (sqrt(reserve_in_A * reserve_out_B * reserve_in_B * reserve_out_A) - (reserve_in_A * reserve_out_B)) / (reserve_in_A + reserve_in_B)
    
    numerador = (r_in_a * r_out_b * r_in_b * r_out_a).sqrt() - (r_in_a * r_out_b)
    denominador = r_in_a + r_in_b

    # Se o numerador for negativo, significa que não há oportunidade de arbitragem nessa direção
    if numerador <= 0 or denominador <= 0:
        return 0

    quantidade_otima = numerador / denominador
    
    return int(quantidade_otima)

