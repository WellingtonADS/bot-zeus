# Regras de Negócio - Bot ZEUS v2.0

## Visão Geral

O Bot ZEUS é um sistema automatizado de arbitragem de criptomoedas que opera na blockchain Polygon, identificando e explorando oportunidades de diferença de preços entre DEXs (Exchanges Descentralizadas) utilizando Flash Loans da Aave V3.

## 1. Arquitetura e Componentes

### 1.1 Arquitetura Híbrida
- **Componente Off-Chain (Python)**: Análise de mercado, identificação de oportunidades e cálculos de otimização
- **Componente On-Chain (Solidity)**: Execução atômica das operações via smart contract `FlashLoanReceiver`

### 1.2 DEXs Suportadas
- **Uniswap V3**: Roteamento avançado com multi-hop e fees variáveis (100, 500, 3000, 10000 basis points)
- **SushiSwap V2**: AMM clássico com fee fixo de 0.3%
- **QuickSwap V2**: AMM clássico com fee fixo de 0.3%

## 2. Regras de Identificação de Oportunidades

### 2.1 Tokens Suportados
- **USDC** (USD Coin)
- **WETH** (Wrapped Ethereum)
- **DAI** (Dai Stablecoin)
- **WMATIC** (Wrapped Polygon)

### 2.2 Tipos de Arbitragem

#### 2.2.1 Arbitragem Simples (Padrão)
- Compra de token em uma DEX com preço menor
- Venda do mesmo token em outra DEX com preço maior
- Operação entre dois pools diferentes

#### 2.2.2 Arbitragem Triangular (Opcional)
- **Ativação**: Variável `TRIANGULAR_MODE=1`
- **Modo Exclusivo**: Variável `TRIANGULAR_ONLY=1` (apenas triangular)
- **Log Top K**: `TRIANGULAR_LOG_TOPK=3` (logs das 3 melhores oportunidades)
- Sequência de 3 trocas: Token A → Token B → Token C → Token A

### 2.3 Critérios de Seleção de Oportunidades
1. **Diferença de Preço**: Deve existir discrepância significativa entre DEXs
2. **Liquidez Disponível**: Pools devem ter liquidez suficiente para a operação
3. **Lucratividade Líquida**: Lucro final deve superar todos os custos

## 3. Regras de Cálculo Financeiro

### 3.1 Otimização de Quantidade
- **Algoritmo**: Cálculo matemático da quantidade ótima baseado nas reservas dos pools
- **Fórmula**: `amount_in = (sqrt(reserve_in_A * reserve_out_B * reserve_in_B * reserve_out_A) - (reserve_in_A * reserve_out_B)) / (reserve_in_A + reserve_in_B)`
- **Objetivo**: Maximizar o lucro considerando o impacto no preço (slippage)

### 3.2 Estrutura de Custos

#### 3.2.1 Taxa de Flash Loan
- **Percentual**: 0.09% (0.0009) do valor emprestado
- **Provedor**: Aave V3
- **Cálculo**: `custo_flash_loan = quantidade_emprestimo * 0.0009`

#### 3.2.2 Taxas de Negociação
- **Uniswap V3**: Fees variáveis (0.01%, 0.05%, 0.3%, 1.0%)
- **SushiSwap V2**: 0.3% por swap
- **QuickSwap V2**: 0.3% por swap

#### 3.2.3 Custo de Gás
- **Fonte**: API Polygonscan + fallback Web3
- **Conversão**: Gwei → Wei → MATIC → USDC
- **Estratégia**: EIP-1559 (maxFeePerGas/maxPriorityFeePerGas) quando disponível
- **Priority Fee**: 1.5 Gwei (configurável via `PRIORITY_FEE_GWEI`)

### 3.3 Cálculo de Lucratividade
```
Lucro Líquido = Lucro Bruto - Taxa Flash Loan - Custo Gás - Taxas DEXs
```

## 4. Regras de Execução

### 4.1 Pré-condições para Execução

#### 4.1.1 Saldo Mínimo MATIC
- **Valor Padrão**: 5 MATIC (configurável via `MIN_BALANCE_MATIC`)
- **Função**: Cobrir taxas de gás das transações
- **Comportamento**: Bot pausa se saldo insuficiente

#### 4.1.2 Lucro Mínimo
- **Configurável**: `MIN_PROFIT_USDC` (padrão: 0)
- **Moeda**: USDC
- **Validação**: Lucro líquido deve ser positivo e superior ao mínimo

#### 4.1.3 Verificação de Liquidez
- Pools devem ter reservas suficientes para suportar a operação
- Validação de existência dos pools nos contratos factory

### 4.2 Modo de Operação

#### 4.2.1 Modo Produção
- **Ativação**: `DRY_RUN=0`
- **Comportamento**: Executa transações reais na blockchain
- **Riscos**: Transações irreversíveis com custos reais

#### 4.2.2 Modo Simulação (Dry Run)
- **Ativação**: `DRY_RUN=1` (padrão)
- **Comportamento**: Simula operações sem executar transações
- **Uso**: Testes e validação de lógica

### 4.3 Gerenciamento de Nonce
- **Sistema**: NonceManager com sincronização automática
- **Incremento**: Apenas após confirmação de transação
- **Recovery**: Sincronização com rede em caso de falha

## 5. Regras de Segurança e Controle

### 5.1 Proteção contra Instâncias Múltiplas
- **Mecanismo**: Arquivo lock (`bot_zeus.lock`)
- **TTL**: 5 minutos
- **Override**: Variável `ALLOW_MULTIPLE=1`

### 5.2 Controle de Smart Contract
- **Ownership**: Apenas owner pode iniciar flash loans
- **Withdraw**: Função para retirada de fundos residuais
- **Revert Protection**: Validações de saldo antes de devolver empréstimo

### 5.3 Monitoramento RPC
- **Health Check**: Detecção de blocos estagnados
- **Failover**: Sistema de RPC backup
- **Métricas**: Log de performance e ping dos RPCs

## 6. Regras de Configuração

### 6.1 Variáveis de Ambiente Obrigatórias
```env
# Carteira
WALLET_ADDRESS=0x...
PRIVATE_KEY=0x...

# RPCs
CUSTOM_RPC_URL=https://...
# ou INFURA_URL, ALCHEMY_URL, RPC_URL

# Contratos
FLASHLOAN_CONTRACT_ADDRESS=0x...
UNISWAP_V3_ROUTER_ADDRESS=0x...
QUOTER_ADDRESS=0x...
SUSHISWAP_ROUTER_ADDRESS=0x...
QUICKSWAP_ROUTER_ADDRESS=0x...

# Tokens
USDC_ADDRESS=0x...
WETH_ADDRESS=0x...
DAI_ADDRESS=0x...
WMATIC_ADDRESS=0x...
```

### 6.2 Variáveis Opcionais com Padrões
```env
# Operação
DRY_RUN=1                    # Modo simulação
MIN_PROFIT_USDC=0            # Lucro mínimo
MIN_BALANCE_MATIC=5          # Saldo mínimo MATIC
ALLOW_MULTIPLE=0             # Permitir múltiplas instâncias

# Flash Loan V2
USE_FLASHLOAN_V2=0           # Usar contrato V2
FLASHLOAN_CONTRACT_ADDRESS_V2=0x...

# Triangular
TRIANGULAR_MODE=0            # Ativar arbitragem triangular
TRIANGULAR_ONLY=0            # Apenas triangular
TRIANGULAR_LOG_TOPK=3        # Top K para logs

# Gas e Performance
PRIORITY_FEE_GWEI=1.5        # Priority fee
QUOTE_CACHE_TTL_SEC=2        # Cache TTL para quotes
V3_MAX_HOPS=1                # Máximo de hops V3
```

## 7. Regras de Logging e Monitoramento

### 7.1 Níveis de Log
- **DEBUG**: Detalhes de cálculos e cache
- **INFO**: Operações principais e status
- **WARNING**: Problemas não críticos
- **CRITICAL**: Erros que impedem operação

### 7.2 Arquivos de Log
- **Localização**: `logs/bot_zeus.log`
- **RPC Metrics**: `logs/rpc_metrics.json`
- **Rotação**: Manual (não automática)

### 7.3 Métricas Monitoradas
- Performance de RPCs (ping, falhas)
- Oportunidades identificadas vs executadas
- Lucros e custos por operação
- Status de saúde da blockchain

## 8. Regras de Manutenção

### 8.1 Atualização de ABIs
- Localização: `abis/` directory
- Validação: Script `validate_abi.py`
- Sincronização com contratos atualizados

### 8.2 Health Checks
- Script: `health_check.py`
- Validações: Conectividade, saldos, contratos
- Frequência: Sob demanda

### 8.3 Deploy de Contratos
- Script: `deploy.py` e `deploy_v2.py`
- Network: Polygon mainnet/testnet
- Verificação: Etherscan/Polygonscan

## 9. Tratamento de Exceções

### 9.1 Falhas de RPC
- **Ação**: Failover automático para RPC backup
- **Log**: Registro de falha e troca
- **Recovery**: Retorno ao RPC preferencial quando disponível

### 9.2 Falhas de Transação
- **Revert**: Log do motivo e rollback do nonce
- **Timeout**: Aguardo configurável (180s padrão)
- **Gas Issues**: Ajuste automático de gas limit

### 9.3 Insuficiência de Fundos
- **MATIC**: Pausa do bot até recarga
- **Tokens**: Skip da oportunidade
- **Flash Loan**: Impossibilidade de devolver empréstimo = revert

## 10. Limites e Restrições

### 10.1 Limites Técnicos
- **Gas Limit**: Configurável (padrão baseado na rede)
- **Slippage**: Calculado dinamicamente baseado em liquidez
- **Timeout**: 180 segundos para confirmação de transação

### 10.2 Limites Financeiros
- **Valor Mínimo**: Sem limite inferior (além de cobrir custos)
- **Valor Máximo**: Limitado pela liquidez disponível nos pools
- **Exposição**: Zero (operações atômicas com flash loans)

### 10.3 Restrições Operacionais
- **Rede**: Apenas Polygon
- **Tokens**: Lista fechada (USDC, WETH, DAI, WMATIC)
- **DEXs**: Lista fechada (Uniswap V3, SushiSwap V2, QuickSwap V2)
- **Frequência**: Sem limite (dependente de oportunidades de mercado)

---

**Versão do Documento**: v2.0  
**Última Atualização**: 24/09/2025  
**Autor**: Wellington ADS  
**Projeto**: Bot ZEUS - Sistema de Arbitragem Automatizada