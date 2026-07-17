#!/usr/bin/env python3
"""
FOR EDUCATIONAL USE ONLY – Ultimate Optimised Version (All Coins)
FIX: Uses Bip39MnemonicGenerator.FromEntropy() for guaranteed valid mnemonics.
"""

import asyncio
import json
import os
import sys
import time
import signal
import logging
import threading
import secrets
from multiprocessing import Process, Queue, Event, cpu_count, Value
from queue import Empty
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

import aiohttp
import uvloop
from bip_utils import (
    Bip39MnemonicGenerator,
    Bip39SeedGenerator,
    Bip44,
    Bip44Coins,
    Bip44Changes,
)

# ============================================================================
# LOGGING SETUP
# ============================================================================
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION – ALL COINS ENABLED
# ============================================================================
DEFAULT_CONFIG = {
    "threads": 8,
    "producers": 0,
    "chains": [
        "btc", "eth", "bnb", "sol", "trx", "polygon", "avalanche"
    ],
    "output_file": "found_wallets.txt",
    "word_count": 12,
    "btc_address_type": "legacy",
    "check_tokens": True,
    "max_concurrent_requests": 50,
    "priority_chains": ["btc", "eth"],
    "token_contracts": {
        "eth": [
            "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        ],
        "bnb": [
            "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
            "0x55d398326f99059fF775485246999027B3197955",
        ],
        "trx": [
            "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
            "TEkxiTehnzSmSe2XqrBj4w32RUN966rdz8",
        ],
        "polygon": [
            "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
            "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
        ],
        "avalanche": [
            "0xA7D7079b0FEaD91F3e65f86E8915Cb59c1a4C664",
            "0x9702230A8Ea53601f5cD2dc00fDBc13d4dF4A8c7",
        ],
        "sol": [
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
        ]
    },
    "token_decimals": {
        "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48": 6,
        "0xdAC17F958D2ee523a2206206994597C13D831ec7": 6,
        "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d": 18,
        "0x55d398326f99059fF775485246999027B3197955": 18,
        "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t": 6,
        "TEkxiTehnzSmSe2XqrBj4w32RUN966rdz8": 6,
        "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174": 6,
        "0xc2132D05D31c914a87C6611C10748AEb04B58e8F": 6,
        "0xA7D7079b0FEaD91F3e65f86E8915Cb59c1a4C664": 6,
        "0x9702230A8Ea53601f5cD2dc00fDBc13d4dF4A8c7": 6,
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": 6,
        "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": 6,
    }
}

class Config:
    def __init__(self):
        self.config = DEFAULT_CONFIG.copy()
        try:
            with open("config.json", "r") as f:
                file_config = json.load(f)
                for key in file_config:
                    if key not in ("rpc_endpoints", "token_rpc_endpoints"):
                        self.config[key] = file_config[key]
                logger.debug("Loaded config from config.json")
        except FileNotFoundError:
            logger.info("No config.json found, using defaults")
        for key in self.config:
            env_val = os.environ.get(key.upper())
            if env_val is not None:
                if key in ("threads", "word_count", "max_concurrent_requests", "producers"):
                    self.config[key] = int(env_val)
                elif key == "chains" or key == "priority_chains":
                    self.config[key] = [c.strip() for c in env_val.split(",")]
                elif key == "check_tokens":
                    self.config[key] = env_val.lower() in ("true", "1", "yes")
                elif key == "btc_address_type":
                    self.config[key] = env_val.lower()
                else:
                    self.config[key] = env_val
        if self.config["producers"] == 0:
            self.config["producers"] = cpu_count() * 2

    def __getitem__(self, key):
        return self.config[key]

    def get(self, key, default=None):
        return self.config.get(key, default)


# ============================================================================
# FAST MNEMONIC GENERATOR (uses Bip39MnemonicGenerator.FromEntropy)
# ============================================================================
class FastMnemonicGenerator:
    def __init__(self, word_count=12):
        if word_count not in (12, 24):
            raise ValueError("word_count must be 12 or 24")
        self.word_count = word_count
        self.entropy_bytes = 16 if word_count == 12 else 32
        # Pre‑create a generator instance (reused)
        self.generator = Bip39MnemonicGenerator()

    def generate(self) -> str:
        entropy = secrets.token_bytes(self.entropy_bytes)
        # FromEntropy returns a valid mnemonic (with correct checksum)
        return self.generator.FromEntropy(entropy)


# ============================================================================
# WALLET DERIVER (unchanged)
# ============================================================================
class WalletDeriver:
    CHAIN_COINS = {
        'btc': Bip44Coins.BITCOIN,
        'eth': Bip44Coins.ETHEREUM,
        'bnb': Bip44Coins.BINANCE_SMART_CHAIN,
        'sol': Bip44Coins.SOLANA,
        'trx': Bip44Coins.TRON,
        'polygon': Bip44Coins.ETHEREUM,
        'avalanche': Bip44Coins.ETHEREUM,
    }

    def __init__(self, btc_address_type="legacy"):
        self.btc_address_type = btc_address_type

    def derive_all(self, mnemonic: str, chains: list) -> dict:
        seed = Bip39SeedGenerator(mnemonic).Generate()
        result = {}
        for chain in chains:
            coin = self.CHAIN_COINS.get(chain.lower())
            if not coin:
                continue
            bip44_ctx = Bip44.FromSeed(seed, coin)
            bip44_acc = (
                bip44_ctx.Purpose()
                .Coin()
                .Account(0)
                .Change(Bip44Changes.CHAIN_EXT)
                .AddressIndex(0)
            )
            if chain.lower() == 'btc' and self.btc_address_type == "bech32":
                address = bip44_acc.PublicKey().ToAddressP2WPKH()
            else:
                address = bip44_acc.PublicKey().ToAddress()
            private_key = bip44_acc.PrivateKey().Raw().ToHex()
            result[chain] = {
                'address': address,
                'private_key': private_key,
            }
        return result


# ============================================================================
# ASYNC BALANCE CHECKER (identical to previous)
# ============================================================================
class BalanceChecker:
    ENDPOINTS = {
        'btc': [
            "https://blockstream.info/api/address/{address}",
            "https://blockchain.info/q/addressbalance/{address}",
        ],
        'eth': [
            "https://cloudflare-eth.com",
            "https://rpc.ankr.com/eth",
            "https://mainnet.infura.io/v3/9aa3d95b3bc440fa88ea12eaa4456161",
        ],
        'bnb': [
            "https://bsc-dataseed.binance.org",
            "https://bsc-dataseed1.defibit.io",
            "https://bsc-dataseed1.ninicoin.io",
        ],
        'sol': [
            "https://api.mainnet-beta.solana.com",
        ],
        'trx': [
            "https://api.trongrid.io/v1/accounts/{address}",
        ],
        'polygon': [
            "https://polygon-rpc.com",
            "https://rpc-mainnet.maticvigil.com",
        ],
        'avalanche': [
            "https://api.avax.network/ext/bc/C/rpc",
        ],
    }

    TRX_TOKEN_ENDPOINT = "https://api.trongrid.io/v1/accounts/{address}/tokens"

    def __init__(self, check_tokens=True, token_contracts=None, token_decimals=None,
                 max_concurrent=50, priority_chains=None):
        self.check_tokens = check_tokens
        self.token_contracts = token_contracts or {}
        self.token_decimals = token_decimals or {}
        self.max_concurrent = max_concurrent
        self.priority_chains = priority_chains or ["btc", "eth"]

        self.semaphores = {}
        for chain in self.ENDPOINTS:
            self.semaphores[chain] = asyncio.Semaphore(max_concurrent)

        self.endpoint_to_chain = {}
        for chain, lst in self.ENDPOINTS.items():
            self.endpoint_to_chain[tuple(lst)] = chain

    async def check_all_balances(self, derived: dict, session: aiohttp.ClientSession) -> dict:
        balances = {}
        token_balances = {}

        priority_tasks = []
        priority_chains_present = [c for c in self.priority_chains if c in derived]
        for chain in priority_chains_present:
            addr = derived[chain]['address']
            if chain == 'btc':
                priority_tasks.append(self._check_btc(addr, session))
            elif chain == 'eth':
                priority_tasks.append(self._check_evm(addr, self.ENDPOINTS['eth'], session))
            else:
                priority_tasks.append(asyncio.sleep(0, result=0.0))

        priority_results = await asyncio.gather(*priority_tasks, return_exceptions=True)
        for i, chain in enumerate(priority_chains_present):
            if isinstance(priority_results[i], Exception):
                balances[chain] = 0.0
            else:
                balances[chain] = priority_results[i]

        if any(balances.get(c, 0.0) > 0 for c in priority_chains_present):
            logger.debug(f"Positive priority balance found, checking all chains")
            remaining = [c for c in derived if c not in priority_chains_present]
            tasks = []
            for chain in remaining:
                addr = derived[chain]['address']
                if chain == 'btc':
                    tasks.append(self._check_btc(addr, session))
                elif chain in ('eth', 'bnb', 'polygon', 'avalanche'):
                    tasks.append(self._check_evm(addr, self.ENDPOINTS[chain], session))
                elif chain == 'sol':
                    tasks.append(self._check_sol(addr, session))
                elif chain == 'trx':
                    tasks.append(self._check_trx(addr, session))
                else:
                    tasks.append(asyncio.sleep(0, result=0.0))
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for j, chain in enumerate(remaining):
                    if isinstance(results[j], Exception):
                        balances[chain] = 0.0
                    else:
                        balances[chain] = results[j]

            if self.check_tokens:
                token_balances = await self._check_all_tokens(derived, session)

        else:
            for chain in derived:
                if chain not in balances:
                    balances[chain] = 0.0

        if token_balances:
            balances['_tokens'] = token_balances
        return balances

    async def _check_all_tokens(self, derived: dict, session: aiohttp.ClientSession) -> dict:
        all_token_balances = {}
        token_tasks = []
        chains_with_tokens = []

        for chain in ['eth', 'bnb', 'trx', 'polygon', 'avalanche', 'sol']:
            if chain in derived and self.token_contracts.get(chain):
                addr = derived[chain]['address']
                token_list = self.token_contracts[chain]
                if chain == 'trx':
                    token_tasks.append(self._check_trc20(addr, chain, token_list, session))
                elif chain == 'sol':
                    token_tasks.append(self._check_spl_tokens(addr, chain, token_list, session))
                else:
                    token_tasks.append(self._check_evm_tokens_batched(addr, chain, token_list, session))
                chains_with_tokens.append(chain)

        if token_tasks:
            results = await asyncio.gather(*token_tasks, return_exceptions=True)
            for i, chain in enumerate(chains_with_tokens):
                if isinstance(results[i], Exception):
                    logger.debug(f"Token check error for {chain}: {results[i]}")
                    continue
                if results[i]:
                    all_token_balances[chain] = results[i]
        return all_token_balances

    async def _check_btc(self, address: str, session: aiohttp.ClientSession) -> float:
        endpoints = self.ENDPOINTS['btc']
        async with self.semaphores['btc']:
            for endpoint in endpoints:
                try:
                    url = endpoint.format(address=address)
                    async with session.get(url, timeout=5) as resp:
                        if resp.status == 200:
                            if 'blockstream' in endpoint:
                                data = await resp.json()
                                if 'error' not in data:
                                    chain_stats = data.get('chain_stats', {})
                                    mempool_stats = data.get('mempool_stats', {})
                                    balance_sat = (
                                        chain_stats.get('funded_txo_sum', 0) - chain_stats.get('spent_txo_sum', 0)
                                        + mempool_stats.get('funded_txo_sum', 0) - mempool_stats.get('spent_txo_sum', 0)
                                    )
                                    return balance_sat / 1e8
                            else:
                                text = await resp.text()
                                return int(text) / 1e8
                except Exception:
                    continue
            return 0.0

    async def _check_evm(self, address: str, endpoints: list, session: aiohttp.ClientSession) -> float:
        chain_key = self.endpoint_to_chain.get(tuple(endpoints), 'eth')
        async with self.semaphores[chain_key]:
            payload = {
                "jsonrpc": "2.0",
                "method": "eth_getBalance",
                "params": [address, "latest"],
                "id": 1
            }
            for endpoint in endpoints:
                try:
                    async with session.post(endpoint, json=payload, timeout=5) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if 'error' not in data and 'result' in data:
                                return int(data['result'], 16) / 1e18
                except Exception:
                    continue
            return 0.0

    async def _check_sol(self, address: str, session: aiohttp.ClientSession) -> float:
        async with self.semaphores['sol']:
            payload = {
                "jsonrpc": "2.0",
                "method": "getBalance",
                "params": [address],
                "id": 1
            }
            for endpoint in self.ENDPOINTS['sol']:
                try:
                    async with session.post(endpoint, json=payload, timeout=5) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if 'error' not in data and 'result' in data:
                                lamports = data['result'].get('value', 0) if isinstance(data['result'], dict) else data['result']
                                return lamports / 1e9
                except Exception:
                    continue
            return 0.0

    async def _check_trx(self, address: str, session: aiohttp.ClientSession) -> float:
        async with self.semaphores['trx']:
            for endpoint in self.ENDPOINTS['trx']:
                try:
                    url = endpoint.format(address=address)
                    async with session.get(url, timeout=5) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if 'data' in data and data['data']:
                                balance_sun = data['data'][0].get('balance', 0)
                                return balance_sun / 1_000_000
                            else:
                                return 0.0
                except Exception:
                    continue
            return 0.0

    async def _check_evm_tokens_batched(self, address: str, chain: str, token_list: list,
                                        session: aiohttp.ClientSession) -> dict:
        if not token_list:
            return {}
        endpoints = self.ENDPOINTS.get(chain)
        if not endpoints:
            return {}
        chain_key = self.endpoint_to_chain.get(tuple(endpoints), chain)
        sem = self.semaphores[chain_key]

        batch_payload = []
        for i, token_addr in enumerate(token_list):
            data = "0x70a08231" + address[2:].zfill(64)
            batch_payload.append({
                "jsonrpc": "2.0",
                "method": "eth_call",
                "params": [{"to": token_addr, "data": data}, "latest"],
                "id": i
            })

        async with sem:
            for endpoint in endpoints:
                try:
                    async with session.post(endpoint, json=batch_payload, timeout=5) as resp:
                        if resp.status == 200:
                            results = await resp.json()
                            token_balances = {}
                            if isinstance(results, list):
                                for item in results:
                                    if 'error' not in item and 'result' in item:
                                        token_idx = item.get('id', 0)
                                        if token_idx < len(token_list):
                                            balance_hex = item['result']
                                            balance = int(balance_hex, 16)
                                            if balance > 0:
                                                token_balances[token_list[token_idx]] = balance
                            return token_balances
                except Exception:
                    continue
        return {}

    async def _check_trc20(self, address: str, chain: str, token_list: list, session: aiohttp.ClientSession) -> dict:
        if not token_list:
            return {}
        url = self.TRX_TOKEN_ENDPOINT.format(address=address)
        async with self.semaphores['trx']:
            try:
                async with session.get(url, timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if 'data' in data:
                            token_balances = {}
                            for token_info in data['data']:
                                token_addr = token_info.get('tokenId')
                                if token_addr in token_list:
                                    raw_balance = int(token_info.get('balance', 0))
                                    if raw_balance > 0:
                                        token_balances[token_addr] = raw_balance
                            return token_balances
            except Exception:
                pass
        return {}

    async def _check_spl_tokens(self, address: str, chain: str, token_list: list, session: aiohttp.ClientSession) -> dict:
        if not token_list:
            return {}
        endpoints = self.ENDPOINTS.get('sol', [])
        if not endpoints:
            return {}
        payload = {
            "jsonrpc": "2.0",
            "method": "getTokenAccountsByOwner",
            "params": [
                address,
                {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
                {"encoding": "jsonParsed"}
            ],
            "id": 1
        }
        async with self.semaphores['sol']:
            for endpoint in endpoints:
                try:
                    async with session.post(endpoint, json=payload, timeout=5) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if 'error' not in data and 'result' in data:
                                token_balances = {}
                                accounts = data['result'].get('value', [])
                                for account in accounts:
                                    parsed = account.get('account', {}).get('data', {}).get('parsed', {})
                                    info = parsed.get('info', {})
                                    mint = info.get('mint')
                                    if mint in token_list:
                                        token_amount = info.get('tokenAmount', {})
                                        raw_balance = int(token_amount.get('amount', 0))
                                        if raw_balance > 0:
                                            token_balances[mint] = raw_balance
                                return token_balances
                except Exception:
                    continue
        return {}


# ============================================================================
# RESULT SAVER (unchanged)
# ============================================================================
class ResultSaver:
    def __init__(self, filename="found_wallets.txt", token_decimals=None):
        self.filename = filename
        self.token_decimals = token_decimals or {}
        self.lock = threading.Lock()
        if not os.path.exists(filename) or os.path.getsize(filename) == 0:
            with open(filename, "a") as f:
                f.write("# SECURITY WARNING: This file contains private keys. Keep it secure and never share it.\n")
                logger.info(f"Created output file: {filename}")

    def save(self, mnemonic: str, derived: dict, balances: dict):
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "mnemonic": mnemonic,
            "chains": {}
        }
        for chain, info in derived.items():
            entry["chains"][chain] = {
                "address": info["address"],
                "private_key": info["private_key"],
                "balance": balances.get(chain, 0.0),
            }
        if '_tokens' in balances:
            token_data = {}
            for chain, token_dict in balances['_tokens'].items():
                token_data[chain] = {}
                for token_addr, raw_balance in token_dict.items():
                    decimals = self.token_decimals.get(token_addr, 18)
                    scaled = raw_balance / (10 ** decimals)
                    token_data[chain][token_addr] = {
                        "raw": str(raw_balance),
                        "scaled": scaled,
                        "decimals": decimals
                    }
            entry["token_balances"] = token_data
        with self.lock:
            with open(self.filename, "a") as f:
                f.write(json.dumps(entry) + "\n")
                logger.info(f"Saved hit for mnemonic: {mnemonic[:20]}...")


# ============================================================================
# PRODUCER & CONSUMER PROCESSES
# ============================================================================
def has_positive_balance(balances: dict) -> bool:
    for key, val in balances.items():
        if key == '_tokens':
            for token_dict in val.values():
                for raw in token_dict.values():
                    if raw > 0:
                        return True
        elif isinstance(val, (int, float)) and val > 0:
            return True
    return False

def producer_worker(q: Queue, stop_event: Event, config: dict):
    gen = FastMnemonicGenerator(word_count=config['word_count'])
    der = WalletDeriver(btc_address_type=config['btc_address_type'])
    chains = config['chains']
    logger.info(f"Producer started (PID {os.getpid()})")
    while not stop_event.is_set():
        mnemonic = gen.generate()
        derived = der.derive_all(mnemonic, chains)
        if derived:
            q.put((mnemonic, derived))
    logger.info(f"Producer stopped (PID {os.getpid()})")


async def consumer_worker_async(q: Queue, stop_event: Event, config: dict,
                                saver: ResultSaver, stats: dict):
    checker = BalanceChecker(
        check_tokens=config['check_tokens'],
        token_contracts=config['token_contracts'],
        token_decimals=config.get('token_decimals', {}),
        max_concurrent=config.get('max_concurrent_requests', 50),
        priority_chains=config.get('priority_chains', ['btc', 'eth'])
    )
    async with aiohttp.ClientSession() as session:
        while not stop_event.is_set():
            try:
                mnemonic, derived = q.get(timeout=0.5)
            except Empty:
                continue
            try:
                balances = await checker.check_all_balances(derived, session)
                with stats['attempts'].get_lock():
                    stats['attempts'].value += 1

                if has_positive_balance(balances):
                    with stats['hits'].get_lock():
                        stats['hits'].value += 1
                    saver.save(mnemonic, derived, balances)
                    print(f"\n[+] HIT! Mnemonic: {mnemonic}")
                    for chain, info in derived.items():
                        bal = balances.get(chain, 0.0)
                        print(f"    {chain.upper()} address: {info['address']}  balance: {bal:.8f}")
                    if '_tokens' in balances:
                        print("    Token balances:")
                        for chain, tokens in balances['_tokens'].items():
                            for token_addr, raw in tokens.items():
                                decimals = config.get('token_decimals', {}).get(token_addr, 18)
                                scaled = raw / (10 ** decimals)
                                print(f"        {chain.upper()} token {token_addr}: {scaled:.6f} (raw: {raw})")
                    logger.info(f"Found wallet with balance: {mnemonic[:20]}...")
            except Exception as e:
                logger.error(f"Consumer error: {e}")


def consumer_process(q: Queue, stop_event: Event, config: dict,
                     saver: ResultSaver, stats: dict):
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(consumer_worker_async(q, stop_event, config, saver, stats))
    finally:
        loop.close()


def stats_printer(stop_event: Event, stats: dict, start_time: float):
    while not stop_event.is_set():
        time.sleep(2)
        attempts = stats['attempts'].value
        hits = stats['hits'].value
        elapsed = time.time() - start_time
        rate = attempts / elapsed if elapsed > 0 else 0
        print(f"\r[+] Attempts: {attempts:,}  Hits: {hits}  Elapsed: {elapsed:.1f}s  Rate: {rate:.0f} mnemonics/s", end="", flush=True)


# ============================================================================
# MAIN
# ============================================================================
def main():
    config = Config()
    logger.info("Configuration loaded")
    logger.info(f"Producers: {config['producers']}, Consumers: {config['threads']}")
    logger.info(f"Chains: {config['chains']}")
    logger.info(f"Priority chains: {config.get('priority_chains', ['btc','eth'])}")
    logger.info(f"Output file: {config['output_file']}")
    logger.info(f"Word count: {config['word_count']}")
    logger.info(f"BTC address type: {config['btc_address_type']}")
    logger.info(f"Check tokens: {config['check_tokens']}")
    logger.info(f"Max concurrent requests: {config.get('max_concurrent_requests', 50)}")

    q = Queue(maxsize=1000)
    stop_event = Event()
    saver = ResultSaver(config['output_file'], token_decimals=config.get('token_decimals', {}))
    stats = {
        'attempts': Value('i', 0),
        'hits': Value('i', 0),
    }

    def signal_handler(sig, frame):
        logger.info("Interrupt received, stopping...")
        stop_event.set()
    signal.signal(signal.SIGINT, signal_handler)

    start_time = time.time()

    producers = []
    for _ in range(config['producers']):
        p = Process(target=producer_worker, args=(q, stop_event, config.config))
        p.daemon = True
        p.start()
        producers.append(p)

    consumers = []
    for _ in range(config['threads']):
        c = Process(target=consumer_process, args=(q, stop_event, config.config, saver, stats))
        c.daemon = True
        c.start()
        consumers.append(c)

    printer_thread = threading.Thread(target=stats_printer, args=(stop_event, stats, start_time), daemon=True)
    printer_thread.start()

    try:
        while not stop_event.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        stop_event.set()

    for p in producers:
        p.join(timeout=2)
    for c in consumers:
        c.join(timeout=2)

    elapsed = time.time() - start_time
    final_attempts = stats['attempts'].value
    final_hits = stats['hits'].value
    logger.info(f"Final: {final_attempts} attempts, {final_hits} hits in {elapsed:.1f}s")
    print(f"\n[+] Final: {final_attempts} attempts, {final_hits} hits in {elapsed:.1f}s")


if __name__ == "__main__":
    main()