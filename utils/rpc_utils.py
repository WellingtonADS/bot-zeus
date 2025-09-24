"""
Utilitários de RPC: health-check e failover dinâmico de provider.

Este módulo permite trocar o provider (RPC URL) em runtime com hot-rebind
dos contratos e do NonceManager, mantendo o dicionário `config` coerente.
"""

from __future__ import annotations

import os
import time
import json
from typing import Optional, Dict

from web3 import Web3
from web3.middleware.geth_poa import geth_poa_middleware

# Import do módulo de configuração completo para poder atualizar seus globais
import utils.config as cfg
from utils.nonce_utils import NonceManager

_last_failover_ts: float = 0.0
_failover_min_interval_sec: int = 120  # evitar flip-flop
_last_primary_try_ts: float = 0.0
_primary_try_cooldown_sec_default: int = 600

# Telemetria leve
_metrics: Dict[str, dict] = {}
_last_metrics_log: float = 0.0
_metrics_log_period_sec: int = 60
_metrics_persist_default: bool = False
_metrics_persist_period_sec_default: int = 60

# Tornar símbolos explicitamente exportados (ajuda o Pylance)
__all__ = [
	"try_failover",
	"maybe_failover_if_stale",
	"maybe_return_to_preferred",
	"record_switch",
	"record_ping",
	"record_fail",
	"log_metrics_if_due",
	"persist_metrics",
]


def _provider_candidates() -> list[str]:
	# Ordem de preferência: CUSTOM -> INFURA (pode expandir no futuro)
	cands = [
		os.getenv("CUSTOM_RPC_URL"),
		os.getenv("INFURA_URL"),
	]
	return [c for c in cands if c]


def _build_web3(url: str) -> Optional[Web3]:
	try:
		timeout = float(os.getenv("RPC_TIMEOUT_SECONDS", "10"))
		w3 = Web3(Web3.HTTPProvider(endpoint_uri=url, request_kwargs={"timeout": timeout}))
		w3.middleware_onion.inject(geth_poa_middleware, layer=0)
		if not w3.is_connected():
			return None
		# smoke: block number
		_ = w3.eth.block_number
		return w3
	except Exception:
		return None


def _hot_switch(new_w3: Web3, new_url: str) -> bool:
	"""Troca o provider em runtime, reconstroi NonceManager e contratos."""
	logger = cfg.logger
	try:
		# 1) Atualizar instância Web3 global no módulo cfg e no dict config
		cfg.web3_instance = new_w3
		cfg.chosen_url = new_url
		cfg.config["web3"] = new_w3

		# 2) Recriar NonceManager
		nm = NonceManager(new_w3, cfg.WALLET_ADDRESS)
		cfg.nonce_manager = nm
		cfg.config["nonce_manager"] = nm

		# 3) Recarregar contratos
		uniswap_v3_router = cfg.carregar_contrato("ISwapRouter.json", cfg.UNISWAP_V3_ROUTER_ADDRESS, "Uniswap V3 Router")
		uniswap_v3_quoter = cfg.carregar_contrato("IQuoter.json", cfg.QUOTER_ADDRESS, "Uniswap V3 Quoter")
		sushiswap_router = cfg.carregar_contrato("SushiswapV2Router02.json", cfg.SUSHISWAP_ROUTER_ADDRESS, "SushiSwap V2 Router")
		quickswap_router = cfg.carregar_contrato("QuickswapV2Router02.json", cfg.QUICKSWAP_ROUTER_ADDRESS, "QuickSwap V2 Router")
		sushiswap_factory = cfg.carregar_contrato("SushiswapV2Factory.json", cfg.SUSHISWAP_FACTORY_ADDRESS, "SushiSwap V2 Factory")
		quickswap_factory = cfg.carregar_contrato("QuickswapV2Factory.json", cfg.QUICKSWAP_FACTORY_ADDRESS, "QuickSwap V2 Factory")

		dex_contracts = {
			"UniswapV3": {
				"router": uniswap_v3_router,
				"quoter": uniswap_v3_quoter,
			},
			"SushiSwapV2": {
				"router": sushiswap_router,
				"factory": sushiswap_factory,
				"pair_abi_name": "SushiswapV2Pair.json",
			},
			"QuickSwapV2": {
				"router": quickswap_router,
				"factory": quickswap_factory,
				"pair_abi_name": "QuickswapV2Pair.json",
			},
		}
		cfg.dex_contracts = dex_contracts
		cfg.config["dex_contracts"] = dex_contracts

		# 4) Flashloan contract (V2 se ativo)
		if cfg.config.get("use_flashloan_v2", False) and cfg.FLASHLOAN_CONTRACT_ADDRESS_V2:
			fl = cfg.carregar_contrato("FlashLoanReceiverV2.json", cfg.FLASHLOAN_CONTRACT_ADDRESS_V2, "FlashLoan Receiver V2")
			cfg.config["flashloan_contract"] = fl
			cfg.config["active_flashloan_contract_address"] = cfg.FLASHLOAN_CONTRACT_ADDRESS_V2
		else:
			fl = cfg.carregar_contrato("FlashLoanReceiver.json", cfg.FLASHLOAN_CONTRACT_ADDRESS, "FlashLoan Receiver")
			cfg.config["flashloan_contract"] = fl
			cfg.config["active_flashloan_contract_address"] = cfg.FLASHLOAN_CONTRACT_ADDRESS

		logger.info("Failover de RPC aplicado com sucesso. Novo provider: %s", new_url)
		return True
	except Exception as e:
		logger.critical("Falha no hot-switch de RPC: %s", e, exc_info=True)
		return False


def try_failover(logger=None) -> bool:
	"""Tenta alternar para um provider alternativo, respeitando cooldown."""
	global _last_failover_ts
	lg = logger or cfg.logger
	now = time.time()
	if (now - _last_failover_ts) < _failover_min_interval_sec:
		lg.info("Failover ignorado (cooldown ativo).")
		return False

	current = getattr(cfg, "chosen_url", None)
	cands = [c for c in _provider_candidates() if c and c != current]
	if not cands:
		lg.warning("Sem providers alternativos disponíveis para failover.")
		return False

	for url in cands:
		lg.info("Testando provider alternativo: %s", url)
		w3 = _build_web3(url)
		if w3 is None:
			lg.warning("Provider alternativo não conectou: %s", url)
			continue
		if _hot_switch(w3, url):
			_last_failover_ts = now
			return True

	lg.error("Failover não conseguiu alternar para nenhum provider válido.")
	return False


def maybe_failover_if_stale(max_stale_seconds: int = 120) -> bool:
	"""Se o bloco não avançar por mais de N segundos, tenta failover."""
	try:
		w3 = cfg.config["web3"]
		# Leitura simples de bloco; se desconectar, _build_web3 já cuida
		_ = w3.eth.block_number
	except Exception:
		# Desconexão ou erro temporário: tentar failover
		return try_failover()
	# A decisão de 'stale' deve ser tomada no chamador, que acompanha o último bloco.
	# Este helper apenas oferece a ação de failover quando chamada.
	return try_failover()


def maybe_return_to_preferred(logger=None) -> bool:
	"""Se não estamos no provider preferido (CUSTOM), tenta voltar quando ele estiver saudável.
	Respeita um cooldown configurável via RETURN_TO_PRIMARY_COOLDOWN_SEC.
	"""
	global _last_primary_try_ts
	lg = logger or cfg.logger
	preferred = os.getenv("CUSTOM_RPC_URL")
	if not preferred:
		return False
	current = getattr(cfg, "chosen_url", None)
	if current == preferred:
		return False
	cooldown = int(os.getenv("RETURN_TO_PRIMARY_COOLDOWN_SEC", str(_primary_try_cooldown_sec_default)))
	now = time.time()
	if (now - _last_primary_try_ts) < cooldown:
		return False
	_last_primary_try_ts = now
	lg.info("Verificando reentrada no provider preferido...")
	w3 = _build_web3(preferred)
	if w3 is None:
		lg.info("Provider preferido ainda indisponível.")
		return False
	ok = _hot_switch(w3, preferred)
	if ok:
		lg.info("Reentrada aplicada: voltamos ao provider preferido.")
	return ok


def _get_metrics(url: str) -> dict:
	if url not in _metrics:
		_metrics[url] = {"pings": 0, "avg_ms": 0.0, "last_ms": 0.0, "fails": 0, "switches": 0}
	return _metrics[url]


def record_switch(url: Optional[str] = None):
	url_val: str = url if isinstance(url, str) and url else (getattr(cfg, "chosen_url", None) or "unknown")
	m = _get_metrics(url_val)
	m["switches"] += 1


def record_ping(latency_ms: float, url: Optional[str] = None):
	url_val: str = url if isinstance(url, str) and url else (getattr(cfg, "chosen_url", None) or "unknown")
	m = _get_metrics(url_val)
	# EMA simples
	alpha = 0.2
	if m["pings"] == 0:
		m["avg_ms"] = latency_ms
	else:
		m["avg_ms"] = alpha * latency_ms + (1 - alpha) * m["avg_ms"]
	m["last_ms"] = latency_ms
	m["pings"] += 1


def record_fail(url: Optional[str] = None):
	url_val: str = url if isinstance(url, str) and url else (getattr(cfg, "chosen_url", None) or "unknown")
	m = _get_metrics(url_val)
	m["fails"] += 1


def log_metrics_if_due(logger=None, period_sec: Optional[int] = None):
	global _last_metrics_log
	lg = logger or cfg.logger
	# Permitir override via env para sincronizar com persistência
	env_period = os.getenv("METRICS_PERSIST_PERIOD_SEC")
	try:
		env_period_val = int(env_period) if env_period else None
	except Exception:
		env_period_val = None
	period = period_sec or env_period_val or _metrics_log_period_sec
	now = time.time()
	# Se não há métricas ainda, não atualizar o relógio para não bloquear o próximo ciclo
	if not _metrics:
		return
	if (now - _last_metrics_log) < period:
		return
	# Só aqui marcamos o último log
	_last_metrics_log = now
	try:
		lg.info("RPC métricas: %s", {k: {"pings": v["pings"], "avg_ms": round(v["avg_ms"],1), "last_ms": round(v["last_ms"],1), "fails": v["fails"], "switches": v["switches"]} for k,v in _metrics.items()})
	except Exception:
		pass
	# Persistência opcional em JSON
	try:
		persist_enabled = os.getenv("METRICS_PERSIST", "0").lower() in ("1","true","yes","on")
		if persist_enabled:
			persist_metrics()
	except Exception:
		pass


def persist_metrics(path: Optional[str] = None):
	"""Persiste as métricas atuais em logs/rpc_metrics.json (JSON Lines)."""
	try:
		base_dir = getattr(cfg, "BASE_DIR", os.getcwd())
		logs_dir = os.path.join(base_dir, "logs")
		os.makedirs(logs_dir, exist_ok=True)
		file_path = path or os.path.join(logs_dir, "rpc_metrics.json")
		payload = {
			"ts": time.time(),
			"chosen_url": getattr(cfg, "chosen_url", None),
			"metrics": _metrics,
		}
		with open(file_path, "a", encoding="utf-8") as f:
			f.write(json.dumps(payload, ensure_ascii=False) + "\n")
	except Exception:
		# Não falhar o bot por erro de IO de métricas
		pass

# Flush de métricas no encerramento do processo
try:
	import atexit
	atexit.register(lambda: persist_metrics())
except Exception:
	pass

