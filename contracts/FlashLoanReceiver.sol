// SPDX-License-Identifier: MIT
pragma solidity ^0.8.10;

// Interfaces da Aave V3
import "@aave/core-v3/contracts/flashloan/interfaces/IFlashLoanReceiver.sol";
import "@aave/core-v3/contracts/interfaces/IPool.sol";

// Interfaces das DEXs e OpenZeppelin
import "@uniswap/v3-periphery/contracts/interfaces/ISwapRouter.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title IUniswapV2Router
 * @dev Interface mínima para roteadores compatíveis com Uniswap V2 (Sushiswap, Quickswap).
 */
interface IUniswapV2Router {
    function swapExactTokensForTokens(
        uint amountIn,
        uint amountOutMin,
        address[] calldata path,
        address to,
        uint deadline
    ) external returns (uint[] memory amounts);
}

/**
 * @title FlashLoanReceiver
 * @author Wellington ADS
 * @notice Este contrato recebe um Flash Loan da Aave, executa uma arbitragem
 * entre duas DEXs e devolve o empréstimo com lucro na mesma transação.
 */
contract FlashLoanReceiver is IFlashLoanReceiver, Ownable {
    // Endereço do Pool da Aave
    IPool public immutable POOL;

    // Evento emitido quando uma operação de arbitragem é concluída
    event ArbitrageCompleted(
        address indexed tokenEmprestado,
        address indexed tokenAlvo,
        uint256 lucro,
        bool successful
    );

    /**
     * @param _poolProvider O endereço do PoolAddressesProvider da Aave na rede de destino.
     */
    constructor(address _poolProvider) Ownable(msg.sender) {
        POOL = IPool(IPoolAddressesProvider(_poolProvider).getPool());
    }

    /**
     * @dev Função principal chamada pela Aave para executar o flash loan.
     * A lógica de arbitragem está implementada aqui.
     * @param assets Array de endereços dos tokens emprestados (neste caso, apenas um).
     * @param amounts Array das quantidades emprestadas.
     * @param premiums Array das taxas (prêmios) a serem pagas pelo empréstimo.
     * @param initiator O endereço que iniciou a chamada do flash loan (este contrato).
     * @param params Dados codificados enviados pelo nosso bot Python, contendo as instruções de arbitragem.
     * @return bool Retorna true se a operação foi bem-sucedida.
     */
    function executeOperation(
        address[] calldata assets,
        uint256[] calldata amounts,
        uint256[] calldata premiums,
        address initiator,
        bytes calldata params
    ) external override returns (bool) {
        // Garante que a chamada venha apenas do Pool da Aave
        require(msg.sender == address(POOL), "FlashLoanReceiver: Caller is not the Aave Pool");
        require(assets.length == 1, "FlashLoanReceiver: Apenas um ativo por vez.");

        // 1. Decodificar os parâmetros de arbitragem enviados pelo bot
        (address tokenAlvo, address dexCompra, address dexVenda) = abi.decode(
            params,
            (address, address, address)
        );

        address tokenEmprestado = assets[0];
        uint256 quantidadeEmprestada = amounts[0];

        // 2. Executar a primeira parte da arbitragem (compra)
        // Aprova a DEX de compra para gastar o token emprestado
        IERC20(tokenEmprestado).approve(dexCompra, quantidadeEmprestada);

        // Executa o primeiro swap (ex: USDC -> WETH na Uniswap)
        _executeSwap(dexCompra, tokenEmprestado, tokenAlvo, quantidadeEmprestada);

        // 3. Executar a segunda parte da arbitragem (venda)
        // Obtém o saldo do token que acabamos de comprar
        uint256 saldoTokenAlvo = IERC20(tokenAlvo).balanceOf(address(this));
        require(saldoTokenAlvo > 0, "FlashLoanReceiver: Compra do token alvo falhou.");

        // Aprova a DEX de venda para gastar o token alvo
        IERC20(tokenAlvo).approve(dexVenda, saldoTokenAlvo);
        
        // Executa o segundo swap (ex: WETH -> USDC na Sushiswap)
        _executeSwap(dexVenda, tokenAlvo, tokenEmprestado, saldoTokenAlvo);

        // 4. Pagar o empréstimo e transferir o lucro
        uint256 valorADevolver = quantidadeEmprestada + premiums[0];
        uint256 saldoFinalTokenEmprestado = IERC20(tokenEmprestado).balanceOf(address(this));

        require(saldoFinalTokenEmprestado >= valorADevolver, "FlashLoanReceiver: Lucro insuficiente para cobrir o emprestimo e a taxa.");

        // Devolve o valor emprestado + taxa para o Pool da Aave
        IERC20(tokenEmprestado).approve(address(POOL), valorADevolver);

        // Calcula o lucro
        uint256 lucro = saldoFinalTokenEmprestado - valorADevolver;

        // Transfere o lucro para o dono do contrato
        if (lucro > 0) {
            IERC20(tokenEmprestado).transfer(owner(), lucro);
        }

        emit ArbitrageCompleted(tokenEmprestado, tokenAlvo, lucro, true);

        return true;
    }

    /**
     * @dev Função interna para executar um swap, lidando com roteadores V2 e V3.
     */
    function _executeSwap(address dexRouter, address tokenIn, address tokenOut, uint256 amountIn) internal {
        // Tenta chamar a função de swap do Uniswap V3
        try ISwapRouter(dexRouter).exactInputSingle(
            ISwapRouter.ExactInputSingleParams({
                tokenIn: tokenIn,
                tokenOut: tokenOut,
                fee: 3000, // A taxa do pool (0.3%) é a mais comum, mas idealmente deveria ser dinâmica
                recipient: address(this),
                deadline: block.timestamp,
                amountIn: amountIn,
                amountOutMinimum: 0,
                sqrtPriceLimitX96: 0
            })
        ) {
            // Sucesso na chamada V3
            return;
        } catch {
            // Se falhar, tenta chamar a função de swap do Uniswap V2
            try IUniswapV2Router(dexRouter).swapExactTokensForTokens(
                amountIn,
                0, // amountOutMin - sem verificação de slippage aqui, pois o lucro é verificado no final
                _getPathFor(tokenIn, tokenOut),
                address(this),
                block.timestamp
            ) {
                // Sucesso na chamada V2
                return;
            } catch {
                revert("FlashLoanReceiver: Falha na execucao do swap em ambas as DEXs V2 e V3.");
            }
        }
    }

    /**
     * @dev Cria o caminho (path) para swaps em roteadores V2.
     */
    function _getPathFor(address tokenIn, address tokenOut) private pure returns (address[] memory) {
        address[] memory path = new address[](2);
        path[0] = tokenIn;
        path[1] = tokenOut;
        return path;
    }

    /**
     * @dev Função chamada pelo dono do contrato para iniciar o flash loan.
     */
    function initiateFlashLoan(
        address _asset,
        uint256 _amount,
        bytes calldata _params
    ) external onlyOwner {
        address[] memory assets = new address[](1);
        assets[0] = _asset;

        uint256[] memory amounts = new uint256[](1);
        amounts[0] = _amount;

        uint256[] memory modes = new uint256[](1);
        modes[0] = 0; // 0 = Sem dívida (padrão para flash loan)

        POOL.flashLoan(
            address(this),
            assets,
            amounts,
            modes,
            address(this), // O receiver é este próprio contrato
            _params,
            0 // referralCode
        );
    }

    /**
     * @dev Permite ao dono do contrato resgatar quaisquer tokens ERC20 presos no contrato.
     */
    function withdraw(address _tokenAddress) external onlyOwner {
        IERC20 token = IERC20(_tokenAddress);
        token.transfer(owner(), token.balanceOf(address(this)));
    }

    // Permite que o contrato receba ETH/MATIC (necessário para algumas operações)
    receive() external payable {}
}
