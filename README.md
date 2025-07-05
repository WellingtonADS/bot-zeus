# Bot-ZEUS

Bot-ZEUS é um bot de arbitragem de criptomoedas projetado para identificar e explorar oportunidades de arbitragem em várias exchanges descentralizadas (DEXs) na rede Polygon. Ele utiliza flash loans para maximizar o potencial de lucro, emprestando e devolvendo fundos em uma única transação.

## Funcionalidades

- **Arbitragem Automatizada**: Identifica e executa oportunidades de arbitragem em tempo real.
- **Flash Loans**: Utiliza flash loans da AAVE para realizar arbitragem sem necessidade de capital inicial.
- **Verificação de Liquidez**: Assegura que há liquidez suficiente nas DEXs antes de executar qualquer operação.
- **Gestão de Saldo**: Monitora e mantém um saldo mínimo de MATIC na carteira para cobrir taxas de transação.

## Estrutura do Projeto

```plaintext
/projeto
│
├── /contracts
│   ├── AToken.json                         # ABI do token AAVE
│   ├── dex_contracts.json                  # Arquivo JSON contendo informações sobre contratos de DEXs
│   ├── LendingPool.json                    # ABI do LendingPool da AAVE
│   ├── LendingPoolAddressesProvider.json   # ABI do endereço do provedor de pool de endereços da AAVE
│   ├── LendingPoolCore.json                # ABI do núcleo do LendingPool da AAVE
│   ├── quickswap_router_abi.json           # ABI do roteador da QuickSwap
│   ├── sushiswap_router_abi.json           # ABI do roteador da SushiSwap
│   ├── tokens.json                         # Lista de tokens com endereços na rede Polygon
│   ├── uniswap_router_abi.json             # ABI do roteador da Uniswap
│
├── /node_modules                           # Diretório para dependências do Node.js
│
├── /src
│   ├── arbitrage.py                        # Lógica de arbitragem, incluindo identificação e execução
│   ├── bot_main.py                         # Ponto de entrada principal do bot de arbitragem
│   ├── dex_operations.py                   # Operações relacionadas às DEXs, como comprar e vender tokens
│   ├── flash_loan.py                       # Funções relacionadas aos flash loans da AAVE
│
├── /test
│   ├── test_contract_function.py           # Testes de funções de contratos
│   ├── test_simulacao_liquidez.py          # Testes de simulação de liquidez
│   ├── teste_gas.py                        # Testes de taxas de gás
│   ├── teste_saldo.py                      # Testes de saldo
│   ├── verificar_conexao.py                # Verificação de conexão com a rede
│
├── /utils
│   ├── gas_utils.py                        # Funções para obter a taxa de gás
│   ├── liquidity_utils.py                  # Funções para obter a liquidez disponível e calcular a quantidade ideal de tokens
│   ├── price_utils.py                      # Funções para obter preços dos tokens nas DEXs
│
├── .env                                    # Arquivo de variáveis de ambiente contendo informações sensíveis
├── .gitignore                              # Arquivo para excluir arquivos e diretórios do controle de versão
├── package-lock.json                       # Arquivo de bloqueio de dependências do Node.js
├── package.json                            # Arquivo de dependências do Node.js
├── rascunho.txt                            # Provavelmente um arquivo de rascunho
└── requirements.txt                        # Arquivo de dependências do Python

```

## Instalação

1. Clone o repositório:

    ```bash
    git clone https://github.com/seu-usuario/bot-zeus.git
    cd bot-zeus
    ```

2. Crie um ambiente virtual e ative-o:

    ```bash
    python -m venv venv
    source venv/bin/activate  # No Windows use `venv\Scripts\activate`
    ```

3. Instale as dependências:

    ```bash
    pip install -r requirements.txt
    ```

4. Configure suas variáveis de ambiente. Crie um arquivo `.env` com base no `.env.example` e preencha os valores necessários.

## Uso

1. Inicie o bot de arbitragem:

    ```bash
    python src/bot_main.py
    ```

## Estrutura dos Arquivos

### /contracts

Contém os arquivos ABI necessários para interagir com os contratos inteligentes na rede Polygon.

### /src

Código fonte principal do bot de arbitragem:

- **arbitrage.py**: Lógica de arbitragem.
- **bot_main.py**: Ponto de entrada principal do bot.
- **dex_operations.py**: Operações relacionadas às DEXs.
- **flash_loan.py**: Funções relacionadas aos flash loans.

### /test

Scripts de teste para verificar a funcionalidade do bot.

### /utils

Funções utilitárias para obter taxas de gás, liquidez e preços.

## Contribuição

Contribuições são bem-vindas! Sinta-se à vontade para abrir issues e pull requests no repositório GitHub.

## Licença

Este projeto está licenciado sob a Licença MIT. Veja o arquivo `LICENSE` para mais detalhes.

## Agradecimentos

Agradecemos à comunidade de desenvolvedores de blockchain e arbitragem por suas contribuições e suporte contínuos.
