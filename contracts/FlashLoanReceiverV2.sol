// SPDX-License-Identifier: MIT
pragma solidity ^0.8.10;

// Aave V3
import "@aave/core-v3/contracts/flashloan/interfaces/IFlashLoanReceiver.sol";
import "@aave/core-v3/contracts/interfaces/IPool.sol";
import "@aave/core-v3/contracts/interfaces/IPoolAddressesProvider.sol";

// DEXs e OpenZeppelin
import "@uniswap/v3-periphery/contracts/interfaces/ISwapRouter.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

interface IUniswapV2Router {
    function swapExactTokensForTokens(
        uint amountIn,
        uint amountOutMin,
        address[] calldata path,
        address to,
        uint deadline
    ) external returns (uint[] memory amounts);
}

contract FlashLoanReceiverV2 is IFlashLoanReceiver, Ownable {
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

    function executeOperation(
        address[] calldata assets,
        uint256[] calldata amounts,
        uint256[] calldata premiums,
        address initiator,
        bytes calldata params
    ) external override returns (bool) {
        require(msg.sender == address(POOL), "Caller not Aave Pool");
        require(assets.length == 1, "Apenas um ativo por vez");

        (
            address tokenAlvo,
            address dexCompra,
            address dexVenda,
            uint256 amountOutMin1,
            uint256 amountOutMin2,
            uint256 deadline,
            uint24 feeCompra,
            uint24 feeVenda,
            address[] memory pathCompraV2,
            address[] memory pathVendaV2,
            bytes memory pathCompraV3,
            bytes memory pathVendaV3
        ) = abi.decode(
            params,
            (address,address,address,uint256,uint256,uint256,uint24,uint24,address[],address[],bytes,bytes)
        );

        address tokenEmprestado = assets[0];
        uint256 quantidadeEmprestada = amounts[0];

        IERC20(tokenEmprestado).approve(dexCompra, quantidadeEmprestada);
        _executeSwap(
            dexCompra,
            tokenEmprestado,
            tokenAlvo,
            quantidadeEmprestada,
            amountOutMin1,
            deadline,
            feeCompra,
            pathCompraV2,
            pathCompraV3
        );

        uint256 saldoTokenAlvo = IERC20(tokenAlvo).balanceOf(address(this));
        require(saldoTokenAlvo > 0, "Compra do token alvo falhou");

        IERC20(tokenAlvo).approve(dexVenda, saldoTokenAlvo);
        _executeSwap(
            dexVenda,
            tokenAlvo,
            tokenEmprestado,
            saldoTokenAlvo,
            amountOutMin2,
            deadline,
            feeVenda,
            pathVendaV2,
            pathVendaV3
        );

        uint256 valorADevolver = quantidadeEmprestada + premiums[0];
        uint256 saldoFinalTokenEmprestado = IERC20(tokenEmprestado).balanceOf(address(this));
        require(saldoFinalTokenEmprestado >= valorADevolver, "Lucro insuficiente");

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
        uint256 deadline,
        uint24 fee,
        address[] memory v2Path,
        bytes memory v3Path
    ) internal {
        if (v3Path.length > 0) {
            // Uniswap V3 multi-hop via exactInput(bytes)
            try ISwapRouter(dexRouter).exactInput(
                ISwapRouter.ExactInputParams({
                    path: v3Path,
                    recipient: address(this),
                    deadline: deadline,
                    amountIn: amountIn,
                    amountOutMinimum: amountOutMinimum
                })
            ) {
                return;
            } catch {
                revert("Swap V3 exactInput falhou");
            }
        } else if (fee > 0) {
            // Uniswap V3 single-hop
            try ISwapRouter(dexRouter).exactInputSingle(
                ISwapRouter.ExactInputSingleParams({
                    tokenIn: tokenIn,
                    tokenOut: tokenOut,
                    fee: fee,
                    recipient: address(this),
                    deadline: deadline,
                    amountIn: amountIn,
                    amountOutMinimum: amountOutMinimum,
                    sqrtPriceLimitX96: 0
                })
            ) {
                return;
            } catch {
                revert("Swap V3 single falhou");
            }
        } else {
            // Uniswap V2 com path dinâmico
            address[] memory path = v2Path;
            if (path.length < 2) {
                path = _getPathFor(tokenIn, tokenOut);
            }
            try IUniswapV2Router(dexRouter).swapExactTokensForTokens(
                amountIn,
                amountOutMinimum,
                path,
                address(this),
                deadline
            ) {
                return;
            } catch {
                revert("Swap V2 falhou");
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
