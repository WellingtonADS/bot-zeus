// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@aave/core-v3/contracts/interfaces/IPoolAddressesProvider.sol";
import "@aave/core-v3/contracts/interfaces/IPool.sol";
import "@aave/core-v3/contracts/flashloan/interfaces/IFlashLoanReceiver.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/Address.sol";
import "@uniswap/v3-periphery/contracts/interfaces/ISwapRouter.sol";
import "@uniswap/v3-periphery/contracts/libraries/TransferHelper.sol";

interface IDEXRouter {
    function getAmountsOut(
        uint amountIn,
        address[] calldata path
    ) external view returns (uint[] memory amounts);

    function swapExactTokensForTokens(
        uint amountIn,
        uint amountOutMin,
        address[] calldata path,
        address to,
        uint deadline
    ) external returns (uint[] memory amounts);
}

contract FlashLoanReceiver is IFlashLoanReceiver, Ownable {
    using Address for address;

    IPoolAddressesProvider public immutable ADDRESSES_PROVIDER;
    IPool public immutable POOL;

    address public USDC;
    address public WETH;

    ISwapRouter public uniswapV3Router;
    IDEXRouter public sushiswapRouter;

    event OperationCompleted(
        address indexed asset,
        uint256 profit,
        bool successful
    );

    constructor(
        IPoolAddressesProvider provider,
        address _usdc,
        address _weth,
        address _uniswapV3Router,
        address _sushiswapRouter
    ) Ownable(msg.sender) {
        ADDRESSES_PROVIDER = provider;
        POOL = IPool(provider.getPool());

        USDC = _usdc;
        WETH = _weth;

        uniswapV3Router = ISwapRouter(_uniswapV3Router);
        sushiswapRouter = IDEXRouter(_sushiswapRouter);
    }

    function executeOperation(
        address[] calldata assets,
        uint256[] calldata amounts,
        uint256[] calldata premiums,
        address,
        bytes calldata params
    ) external override returns (bool) {
        require(msg.sender == address(POOL), "Caller is not the pool");

        (address dexRouter, bytes memory dexCallData, uint256 expectedProfit) = abi.decode(
            params,
            (address, bytes, uint256)
        );

        _approveTokens(assets, amounts, dexRouter);
        _executeDexSwap(dexRouter, dexCallData);
        _repayLoanAndCalculateProfit(assets, amounts, premiums, expectedProfit);

        return true;
    }

    function _approveTokens(
        address[] calldata assets,
        uint256[] calldata amounts,
        address dexRouter
    ) internal {
        for (uint256 i = 0; i < assets.length; i++) {
            if (IERC20(assets[i]).allowance(address(this), dexRouter) < amounts[i]) {
                IERC20(assets[i]).approve(dexRouter, type(uint256).max);
            }
        }
    }

    function _executeDexSwap(
        address dexRouter,
        bytes memory dexCallData
    ) internal {
        (bool success, bytes memory returndata) = dexRouter.call(dexCallData);
        require(success, _getRevertMsg(returndata));
    }

    function _repayLoanAndCalculateProfit(
        address[] calldata assets,
        uint256[] calldata amounts,
        uint256[] calldata premiums,
        uint256 expectedProfit
    ) internal {
        for (uint256 i = 0; i < assets.length; i++) {
            uint256 amountOwing = amounts[i] + premiums[i];
            require(
                IERC20(assets[i]).balanceOf(address(this)) >= amountOwing,
                "Insufficient balance to cover loan and premium"
            );
            IERC20(assets[i]).transfer(address(POOL), amountOwing);

            uint256 profit = IERC20(assets[i]).balanceOf(address(this)) - amountOwing;
            require(profit >= expectedProfit, "Insufficient arbitrage profit");

            if (profit > 0) {
                IERC20(assets[i]).transfer(owner(), profit);
                emit OperationCompleted(assets[i], profit, true);
            }
        }
    }

    function initiateFlashLoan(
        address[] calldata assets,
        uint256[] calldata amounts,
        uint256[] calldata modes,
        bytes calldata params
    ) external onlyOwner {
        require(
            assets.length == amounts.length && amounts.length == modes.length,
            "Assets, amounts, and modes length mismatch"
        );

        POOL.flashLoan(
            address(this),
            assets,
            amounts,
            modes,
            address(this),
            params,
            0
        );
    }

    function _getRevertMsg(bytes memory _returnData) internal pure returns (string memory) {
        if (_returnData.length < 68) return "Transaction reverted silently";
        assembly {
            _returnData := add(_returnData, 0x04)
        }
        return abi.decode(_returnData, (string));
    }
}
