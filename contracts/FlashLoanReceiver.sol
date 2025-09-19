// SPDX-License-Identifier: MIT
pragma solidity ^0.8.10;

// Interfaces da Aave V3
import "@aave/core-v3/contracts/flashloan/interfaces/IFlashLoanReceiver.sol";
import "@aave/core-v3/contracts/interfaces/IPool.sol";
import "@aave/core-v3/contracts/interfaces/IPoolAddressesProvider.sol";

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
    // CORREÇÃO FINAL: A palavra-chave 'public' cria automaticamente a função getter.
    // A palavra-chave 'override' indica que esta variável está a implementar a função da interface.
    IPoolAddressesProvider public immutable override ADDRESSES_PROVIDER;
    IPool public immutable POOL;

    event ArbitrageCompleted(
        address indexed tokenEmprestado,
        address indexed tokenAlvo,
        uint256 lucro,
        bool successful
    );

    constructor(address _poolProvider) Ownable(msg.sender) {
        ADDRESSES_PROVIDER = IPoolAddressesProvider(_poolProvider);
        POOL = IPool(ADDRESSES_PROVIDER.getPool());
    }

    // A função explícita ADDRESSES_PROVIDER() foi removida porque a variável pública acima já a cria.

    function executeOperation(
        address[] calldata assets,
        uint256[] calldata amounts,
        uint256[] calldata premiums,
        address initiator,
        bytes calldata params
    ) external override returns (bool) {
        require(msg.sender == address(POOL), "FlashLoanReceiver: Caller is not the Aave Pool");
        require(assets.length == 1, "FlashLoanReceiver: Apenas um ativo por vez.");

        (
            address tokenAlvo,
            address dexCompra,
            address dexVenda,
            uint256 amountOutMin1,
            uint256 amountOutMin2,
            uint256 deadline
        ) = abi.decode(
            params,
            (address, address, address, uint256, uint256, uint256)
        );

        address tokenEmprestado = assets[0];
        uint256 quantidadeEmprestada = amounts[0];

    IERC20(tokenEmprestado).approve(dexCompra, quantidadeEmprestada);
    _executeSwap(dexCompra, tokenEmprestado, tokenAlvo, quantidadeEmprestada, amountOutMin1, deadline);

        uint256 saldoTokenAlvo = IERC20(tokenAlvo).balanceOf(address(this));
        require(saldoTokenAlvo > 0, "FlashLoanReceiver: Compra do token alvo falhou.");

    IERC20(tokenAlvo).approve(dexVenda, saldoTokenAlvo);
    _executeSwap(dexVenda, tokenAlvo, tokenEmprestado, saldoTokenAlvo, amountOutMin2, deadline);

        uint256 valorADevolver = quantidadeEmprestada + premiums[0];
        uint256 saldoFinalTokenEmprestado = IERC20(tokenEmprestado).balanceOf(address(this));

        require(saldoFinalTokenEmprestado >= valorADevolver, "FlashLoanReceiver: Lucro insuficiente para cobrir o emprestimo e a taxa.");
        
        IERC20(tokenEmprestado).transfer(address(POOL), valorADevolver);

        uint256 lucro = saldoFinalTokenEmprestado - valorADevolver;

        if (lucro > 0) {
            IERC20(tokenEmprestado).transfer(owner(), lucro);
        }

        emit ArbitrageCompleted(tokenEmprestado, tokenAlvo, lucro, true);

        return true;
    }

    function _executeSwap(
        address dexRouter,
        address tokenIn,
        address tokenOut,
        uint256 amountIn,
        uint256 amountOutMinimum,
        uint256 deadline
    ) internal {
        try ISwapRouter(dexRouter).exactInputSingle(
            ISwapRouter.ExactInputSingleParams({
                tokenIn: tokenIn,
                tokenOut: tokenOut,
                fee: 3000,
                recipient: address(this),
                deadline: deadline,
                amountIn: amountIn,
                amountOutMinimum: amountOutMinimum,
                sqrtPriceLimitX96: 0
            })
        ) {
            return;
        } catch {
            try IUniswapV2Router(dexRouter).swapExactTokensForTokens(
                amountIn,
                amountOutMinimum,
                _getPathFor(tokenIn, tokenOut),
                address(this),
                deadline
            ) {
                return;
            } catch {
                revert("FlashLoanReceiver: Falha na execucao do swap.");
            }
        }
    }

    function _getPathFor(address tokenIn, address tokenOut) private pure returns (address[] memory) {
        address[] memory path = new address[](2);
        path[0] = tokenIn;
        path[1] = tokenOut;
        return path;
    }

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
        modes[0] = 0;

        POOL.flashLoan(
            address(this),
            assets,
            amounts,
            modes,
            address(this),
            _params,
            0
        );
    }

    function withdraw(address _tokenAddress) external onlyOwner {
        IERC20 token = IERC20(_tokenAddress);
        token.transfer(owner(), token.balanceOf(address(this)));
    }

    receive() external payable {}
}
