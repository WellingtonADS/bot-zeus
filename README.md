# Bot ZEUS - v2.0

## Visão Geral

O Bot ZEUS é um sistema de software para a automação de estratégias de arbitragem na blockchain Polygon. O seu objetivo é a identificação e execução de discrepâncias de preço para um mesmo ativo criptográfico entre múltiplas corretoras descentralizadas (DEXs).

Para capitalizar estas oportunidades, o sistema utiliza **Flash Loans** do protocolo Aave V3, permitindo a utilização de um capital de operação elevado sem a necessidade de fundos próprios. Esta versão implementa uma lógica avançada que **calcula dinamicamente o volume ótimo** de cada operação com base na liquidez disponível no mercado em tempo real.

## Funcionalidades Principais

* **Arbitragem Multi-DEX:** Monitoriza continuamente os preços em várias DEXs (Uniswap V3, Sushiswap V2, Quickswap V2) para encontrar oportunidades de arbitragem.
* **Otimização Dinâmica de Liquidez:** Em vez de usar um valor fixo, o bot analisa a profundidade dos pools de liquidez para calcular o tamanho ideal de cada transação, maximizando o lucro e minimizando o impacto no preço (*slippage*).
* **Cálculo de Lucratividade Líquida:** Antes de executar qualquer transação, o sistema simula a operação completa e subtrai todos os custos (taxa do Flash Loan, taxas de negociação das DEXs e o custo do gás da transação) para garantir que apenas operações genuinamente lucrativas sejam executadas.
* **Execução Atómica com Flash Loans:** Utiliza um contrato inteligente (`FlashLoanReceiver.sol`) para receber um empréstimo da Aave, executar os dois swaps da arbitragem e devolver o empréstimo, tudo numa única e indivisível transação na blockchain.
* **Gestão de Carteira:** Monitoriza o saldo de MATIC da carteira operacional para garantir que há sempre fundos suficientes para as taxas de gás.

## Como Funciona

O sistema é dividido em duas componentes que trabalham em harmonia:

1.  **Bot Off-Chain (Python):** O "cérebro" que corre localmente. Ele analisa os dados da blockchain, identifica oportunidades, calcula a estratégia ótima (quantidade e lucro) e envia a ordem de execução.
2.  **Contrato Inteligente On-Chain (Solidity):** O "ator" que vive na blockchain. Ele recebe a ordem do bot, pede o Flash Loan, executa os swaps de forma atómica e segura, paga o empréstimo e transfere o lucro para a carteira do operador.

## Estrutura do Projeto

```

/bot-zeus
│
├── /abis/              \# ABIs dos contratos para interação
├── /contracts/         \# Código fonte dos contratos inteligentes (.sol)
├── /logs/              \# Ficheiros de log gerados pelo bot
├── /src/               \# Código fonte principal do bot (Python)
│   ├── arbitrage.py
│   ├── bot\_main.py
│   ├── flash\_loan.py
│   └── dex\_operations.py
│
├── /utils/             \# Módulos de utilidades (Python)
│   ├── config.py
│   ├── gas\_utils.py
│   ├── liquidity\_utils.py
│   ├── nonce\_utils.py
│   ├── optimization\_utils.py
│   ├── price\_oracle.py
│   └── wallet\_manager.py
│
├── .env                \# Ficheiro de variáveis de ambiente (NÃO versionar)
├── .gitignore
├── deploy.py           \# Script para implantar o contrato inteligente
├── hardhat.config.js   \# Ficheiro de configuração do Hardhat
├── package.json        \# Dependências de desenvolvimento (Node.js)
└── requirements.txt    \# Dependências do bot (Python)

````

## Instalação e Configuração

**Pré-requisitos:**

* [Node.js](https://nodejs.org/) (versão LTS recomendada)
* [Python](https://www.python.org/) (versão 3.10 ou superior)
* [Yarn](https://yarnpkg.com/) (instalado via `npm install -g yarn`)

**Passos:**

1.  **Clone o repositório:**
    ```bash
    git clone [https://github.com/WellingtonADS/bot-zeus.git](https://github.com/WellingtonADS/bot-zeus.git)
    cd bot-zeus
    ```
2.  **Instale as dependências de desenvolvimento (Hardhat):**
    ```bash
    yarn install
    ```
3.  **Crie e ative um ambiente virtual Python:**
    ```bash
    python -m venv .venv
    # No Windows (PowerShell):
    .\.venv\Scripts\Activate.ps1
    # No macOS/Linux:
    # source .venv/bin/activate
    ```
4.  **Instale as dependências Python:**
    ```bash
    pip install -r requirements.txt
    ```
5.  **Configure as Variáveis de Ambiente:**
    * Crie uma cópia do ficheiro `.env.example` (se existir) ou crie um novo ficheiro chamado `.env`.
    * Preencha todas as variáveis necessárias: `INFURA_URL`, `WALLET_ADDRESS`, `PRIVATE_KEY`, e os endereços dos contratos das DEXs e dos tokens.

## Uso

O processo de execução é dividido em duas etapas principais:

1.  **Compilar e Implantar o Contrato Inteligente:**
    * Primeiro, compile o contrato:
        ```bash
        yarn hardhat compile
        ```
    * Copie o ficheiro `FlashLoanReceiver.json` gerado em `artifacts/contracts/` para a sua pasta `abis/`.
    * Execute o script de implantação. Isto irá colocar o seu contrato na blockchain e imprimir o seu endereço.
        ```bash
        python deploy.py
        ```
2.  **Iniciar o Bot:**
    * Depois de o contrato ser implantado, copie o seu endereço e cole-o na variável `FLASHLOAN_CONTRACT_ADDRESS` no seu ficheiro `.env`.
    * Execute o bot:
        ```bash
        python src/bot_main.py
        ```
    * Na interface de comando, digite `start` para iniciar a busca por oportunidades.

## Licença

Este projeto está licenciado sob a Licença MIT. Veja o ficheiro `LICENSE` para mais detalhes.
````
