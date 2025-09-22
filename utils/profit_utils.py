from decimal import Decimal
from typing import Callable, Any

# Types for readability
FromBaseFn = Callable[[Any, int, str], Decimal]
GetGasFn = Callable[[Any, Any], float]  # obter_taxa_gas(web3, logger) -> gwei float
GetPriceFn = Callable[[], Decimal]      # obter_preco_matic_em_usdc() -> Decimal


def calcular_lucro_liquido_esperado(
    lucro_bruto_base: int,
    quantidade_emprestimo_base: int,
    token_emprestimo_address: str,
    *,
    from_base: FromBaseFn,
    web3: Any,
    obter_preco_matic_em_usdc: GetPriceFn,
    obter_taxa_gas: Callable[[Any, Any], float],
    gas_limit: int,
    logger: Any,
) -> Decimal:
    """
    Calcula o lucro líquido esperado de uma operação, descontando custos:
    - taxa de flash loan (0.09%)
    - custo de gás (gwei -> MATIC -> USDC via oracle)

    Dependências são injetadas por parâmetro para facilitar testes unitários.
    """
    TAXA_FLASH_LOAN = Decimal("0.0009")

    lucro_bruto = from_base(web3, lucro_bruto_base, token_emprestimo_address)
    quantidade_emprestimo = from_base(web3, quantidade_emprestimo_base, token_emprestimo_address)

    custo_flash_loan = quantidade_emprestimo * TAXA_FLASH_LOAN

    preco_gas_gwei = Decimal(obter_taxa_gas(web3, logger))
    preco_matic_usdc = obter_preco_matic_em_usdc()

    if preco_matic_usdc == 0:
        logger.warning(
            "Não foi possível obter o preço do MATIC. O cálculo do custo do gás será impreciso."
        )
        return Decimal("-inf")  # Sinaliza inviabilidade de cálculo

    gas_price_wei = web3.to_wei(preco_gas_gwei, 'gwei')
    custo_gas_wei = int(gas_limit) * int(gas_price_wei)
    custo_gas_matic = web3.from_wei(custo_gas_wei, 'ether')
    custo_gas_usdc = custo_gas_matic * preco_matic_usdc

    lucro_liquido = lucro_bruto - custo_flash_loan - custo_gas_usdc
    try:
        logger.debug(
            "Cálculo de Lucro: Bruto=%.4f, Custo FlashLoan=%.4f, Custo Gás=%.4f -> Líquido=%.4f",
            float(lucro_bruto), float(custo_flash_loan), float(custo_gas_usdc), float(lucro_liquido)
        )
    except Exception:
        pass
    return lucro_liquido
