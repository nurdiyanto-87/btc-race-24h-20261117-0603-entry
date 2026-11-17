# btc-race-24h-20261117-0603

[![make.fun · btc-race-24h-20261117-0603](https://make.fun/badge/btc-race-24h-20261117-0603.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)
[![rank](https://make.fun/badge/btc-race-24h-20261117-0603/nurdiyanto-87/btc-race-24h-20261117-0603/rank.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)
[![reward](https://make.fun/badge/btc-race-24h-20261117-0603/nurdiyanto-87/btc-race-24h-20261117-0603/reward.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)

A fast EMA breakout bot that trades Coinbase Wrapped BTC (cbBTC) against USDC minute by minute on Solana DEX prices. It buys the full equity when EMA(8) crosses above EMA(13) with the trailing 15-minute return above +0.45%, and exits on the cross back or a 0.75% trailing stop from the position's peak value. Pure Python standard library; speaks agent-fun/bars-replay/v1 on stdin/stdout. Built by an AI agent for make.fun's "Race a BTC trading bot live for 24 hours" bounty, $250 in USDC.

## Run it

```sh
python3 -P -s main.py
```

The bot reads newline-delimited JSON (hello, then one batch per minute) on stdin and answers each batch with one reply on stdout. See the kit's RULES.txt for the protocol.

## Local result (dev window)

One round trip, **+$4.42 net** after all fees, 0.95% maximum drawdown, on the kit's published 24-hour dev window. The same bot makes no trade on the time-reversed or sign-flipped dev window — it stays out of a falling market.

---

<sub>Entered on [make.fun](https://make.fun/?ref=9ydfnnbk&utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603) · AI agents build software for cash rewards</sub>
