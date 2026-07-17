📢 Introducing Wallet Scanner – Educational BIP39 Brute‑Force Tool

⚠️ FOR EDUCATIONAL & SECURITY RESEARCH ONLY
This tool demonstrates how BIP39 mnemonics are generated, how HD wallets derive addresses, and how balances are queried on-chain.
Randomly guessing a funded wallet is practically impossible – odds ≈ 1/2^128 for 12‑word seeds.
Unauthorised access to others’ wallets is illegal. The user bears full legal responsibility.

---

🔥 Features

· Multi‑chain – BTC, ETH, BNB, Solana, TRX, Polygon, Avalanche.
· High performance – multiprocessing + asyncio + uvloop for maximum throughput.
· Batch requests – EVM chains use JSON‑RPC batching (10‑50× fewer HTTP calls).
· Early pruning – checks BTC/ETH first; skips other chains if no balance (configurable).
· Optional token checks – ERC‑20, BEP‑20, TRC‑20, SPL tokens (USDC, USDT, etc.).
· Real‑time stats – attempts, hits, elapsed time, mnemonics/second.
· Configurable – all settings via config.json or environment variables.
· Clean output – found wallets saved as JSON with mnemonic, addresses, private keys, and balances.

---

🚀 Quick Start

```bash
# Clone the repo
git clone https://github.com/lucidphantom-777/btc-brute.git
cd btc-brute

# Install dependencies
pip install -r requirements.txt

# Run with default settings
python btc.py
```

---

⚙️ Tune for Speed

Use environment variables to adjust performance:

```bash
export PRODUCERS=8
export THREADS=12
export MAX_CONCURRENT_REQUESTS=200
export BATCH_SIZE=100
export CHAINS=btc,eth,bnb,polygon,avalanche   # reduce for faster scanning
export PRIORITY_CHAINS=btc,eth
export CHECK_TOKENS=false                      # keep off for max speed
python btc.py
```

Or create a config.json file (see example in the repo).

---

📄 Output Example

Found wallets are appended to found_wallets.txt (one JSON per line):

```json
{
  "timestamp": "2026-07-17T02:43:38.123456",
  "mnemonic": "abandon ability able about above absent ...",
  "chains": {
    "btc": {
      "address": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
      "private_key": "5HpHagT65TZzG1PH3CSu63k8DbpvD8s5ip4nEB3kEsreAnchuDf",
      "balance": 0.00000000
    },
    "eth": { ... }
  }
}
```

---

⚠️ Important Disclaimer

· Probability of success is effectively zero – this is a learning tool, not a money‑making scheme.
· Do not use illegally – accessing wallets without permission is a crime.
· Private keys are sensitive – keep output files secure and never share them.
· The author assumes no liability for any misuse or damage.

---

📚 Learn More

· BIP39 – Mnemonic code for generating deterministic keys.
· BIP44 – Multi‑account hierarchy.
· bip_utils – Python library used for derivation.
· aiohttp – Async HTTP client.

---

📥 Get the Code

GitHub: https://github.com/lucidphantom-777/btc-brute
Feel free to star ⭐, fork, and contribute (but keep it educational).

---

Happy learning! Use this knowledge to strengthen blockchain security, not to compromise it.
If you have questions or suggestions, join our chat or open an issue on GitHub.
