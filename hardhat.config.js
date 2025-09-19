require("@nomiclabs/hardhat-waffle");
require("@nomiclabs/hardhat-ethers");
require("dotenv").config();

module.exports = {
  defaultNetwork: "hardhat",
  solidity: {
    compilers: [
      {
        version: "0.8.20", // Para contratos que requerem 0.8.0
        settings: {
          optimizer: {
            enabled: true,
            runs: 200,
          },
          viaIR: true,
        },
      },
      {
        version: "0.8.0", // Para contratos que requerem 0.8.0
        settings: {
          optimizer: {
            enabled: true,
            runs: 200,
          },
          // viaIR opcional para 0.8.0 caso encontre "stack too deep" em contratos antigos
          // viaIR: true,
        },
      },
      {
        version: "0.5.16", // Para contratos que requerem 0.5.16
        settings: {
          optimizer: {
            enabled: true,
            runs: 200,
          },
          viaIR: true, // Ativa a otimização baseada em IR
        },
      },
    ],
  },
  paths: {
    sources: "./contracts",
    tests: "./test",
    cache: "./cache",
    artifacts: "./artifacts",
  },
  networks: {
    hardhat: {
      chainId: 31337,
      // Ative o forking para testes realistas contra o estado da mainnet
      forking: process.env.FORK_RPC_URL
        ? {
            url: process.env.FORK_RPC_URL,
          }
        : undefined,
    },
    polygon: {
      url: process.env.INFURA_URL,
      accounts: [process.env.PRIVATE_KEY],
    },
  },
  etherscan: {
    apiKey: {
      polygon: process.env.POLYGONSCAN_API_KEY || "",
    },
  },
  mocha: {
    timeout: 60000,
  },
};
