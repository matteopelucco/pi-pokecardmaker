#!/usr/bin/env python3
"""
Name-based Portfolio Generator + 5Y Backtest (deterministic)
- Input: nome, cognome, capitale da investire
- Output: portafoglio deterministico + backtest 5 anni (buy & hold)
- Data: Yahoo Finance via yfinance (serve internet)

Install:
  pip install yfinance pandas numpy matplotlib
"""

from __future__ import annotations

import argparse
import hashlib
import random
from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Tuple, Dict, Optional

import numpy as np
import pandas as pd


# Universo titoli (esempio). Puoi ampliarlo.
UNIVERSE: List[Tuple[str, str]] = [
    ("AAPL", "Apple"),
    ("MSFT", "Microsoft"),
    ("GOOGL", "Alphabet"),
    ("AMZN", "Amazon"),
    ("NVDA", "NVIDIA"),
    ("META", "Meta Platforms"),
    ("TSLA", "Tesla"),
    ("BRK-B", "Berkshire Hathaway (use BRK-B on Yahoo)"),
    ("JPM", "JPMorgan Chase"),
    ("V", "Visa"),
    ("MA", "Mastercard"),
    ("KO", "Coca-Cola"),
    ("PEP", "PepsiCo"),
    ("PG", "Procter & Gamble"),
    ("JNJ", "Johnson & Johnson"),
    ("UNH", "UnitedHealth"),
    ("XOM", "Exxon Mobil"),
    ("CVX", "Chevron"),
    ("LLY", "Eli Lilly"),
    ("AVGO", "Broadcom"),
    ("ADBE", "Adobe"),
    ("COST", "Costco"),
    ("WMT", "Walmart"),
    ("DIS", "Disney"),
    ("NFLX", "Netflix"),
    ("ORCL", "Oracle"),
    ("INTC", "Intel"),
    ("CSCO", "Cisco"),
    ("BA", "Boeing"),
    ("CAT", "Caterpillar"),
    ("NKE", "Nike"),
    ("PFE", "Pfizer"),
    ("MRK", "Merck"),
    ("SAP", "SAP"),
    ("ASML", "ASML"),
    ("NESN.SW", "Nestlé"),
    ("NOVN.SW", "Novartis"),
    ("RMS.PA", "Hermès"),
    ("MC.PA", "LVMH"),
    ("SAN.MC", "Banco Santander"),
    ("ENI.MI", "ENI"),
    ("ISP.MI", "Intesa Sanpaolo"),
    ("STLAM.MI", "Stellantis"),
    ("AIR.PA", "Airbus"),
]


@dataclass(frozen=True)
class Portfolio:
    owner: str
    risk_profile: str
    holdings: List[Tuple[str, str, float]]  # (ticker, name, weight in [0..1])


@dataclass(frozen=True)
class BacktestResult:
    portfolio_value: pd.Series
    benchmark_value: Optional[pd.Series]
    stats: Dict[str, float]
    used_holdings: List[Tuple[str, str, float]]


# ---------- deterministic portfolio generation ----------

def _stable_seed_from_name(full_name: str) -> int:
    normalized = " ".join(full_name.strip().lower().split())
    digest = hashlib.sha256(normalized.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=False)


def _risk_profile_from_seed(seed: int) -> str:
    r = seed % 100
    if r < 30:
        return "Conservativo"
    elif r < 70:
        return "Bilanciato"
    return "Dinamico"


def _pick_n_holdings(rng: random.Random, n: int) -> List[Tuple[str, str]]:
    universe = UNIVERSE[:]
    rng.shuffle(universe)
    return universe[:n]


def _dirichlet_weights(rng: random.Random, n: int, concentration: float) -> List[float]:
    samples = [rng.gammavariate(concentration, 1.0) for _ in range(n)]
    s = sum(samples)
    if s == 0:
        return [1.0 / n] * n
    return [x / s for x in samples]


def _apply_constraints(weights: List[float], max_single: float, min_single: float) -> List[float]:
    n = len(weights)
    w = [min(max_single, max(min_single, x)) for x in weights]
    s = sum(w)
    if s == 0:
        return [1.0 / n] * n
    w = [x / s for x in w]

    # small stabilization passes
    for _ in range(2):
        changed = False
        for i, x in enumerate(w):
            if x > max_single:
                w[i] = max_single
                changed = True
            elif x < min_single:
                w[i] = min_single
                changed = True
        if not changed:
            break
        s = sum(w)
        w = [x / s for x in w]
    return w


def generate_portfolio(full_name: str, n_holdings: int = 12) -> Portfolio:
    seed = _stable_seed_from_name(full_name)
    rng = random.Random(seed)
    risk = _risk_profile_from_seed(seed)

    if risk == "Conservativo":
        concentration, max_single, min_single = 2.2, 0.14, 0.03
        n_holdings = max(10, n_holdings)
    elif risk == "Bilanciato":
        concentration, max_single, min_single = 1.6, 0.18, 0.02
    else:
        concentration, max_single, min_single = 1.1, 0.25, 0.01
        n_holdings = min(14, max(8, n_holdings))

    picks = _pick_n_holdings(rng, n_holdings)
    raw_w = _dirichlet_weights(rng, n_holdings, concentration=concentration)
    w = _apply_constraints(raw_w, max_single=max_single, min_single=min_single)

    holdings = [(t, nm, float(weight)) for (t, nm), weight in zip(picks, w)]
    holdings.sort(key=lambda x: x[2], reverse=True)

    owner = " ".join(full_name.strip().split())
    return Portfolio(owner=owner, risk_profile=risk, holdings=holdings)


# ---------- backtest ----------

def _download_adj_close(tickers: List[str], start: str, end: str) -> pd.DataFrame:
    import yfinance as yf  # local import to keep dependency optional

    # auto_adjust=True => prices adjusted; column is "Close" (or directly series)
    data = yf.download(
        tickers=tickers,
        start=start,
        end=end,
        interval="1d",
        auto_adjust=True,
        progress=False,
        group_by="ticker",
        threads=True,
    )

    # Normalize into a DataFrame: columns=tickers, values=adjusted close
    if isinstance(data.columns, pd.MultiIndex):
        # usual: (ticker, field)
        closes = []
        for t in tickers:
            if (t, "Close") in data.columns:
                closes.append(data[(t, "Close")].rename(t))
            elif (t, "Adj Close") in data.columns:
                closes.append(data[(t, "Adj Close")].rename(t))
        if not closes:
            return pd.DataFrame()
        df = pd.concat(closes, axis=1)
    else:
        # single ticker case
        if "Close" in data.columns:
            df = data[["Close"]].rename(columns={"Close": tickers[0]})
        elif "Adj Close" in data.columns:
            df = data[["Adj Close"]].rename(columns={"Adj Close": tickers[0]})
        else:
            df = pd.DataFrame()

    df = df.sort_index().dropna(how="all")
    return df


def backtest_buy_and_hold(
    portfolio: Portfolio,
    capital: float,
    years: int = 5,
    benchmark: Optional[str] = "SPY",
) -> BacktestResult:
    # dates
    end = date.today()
    start = end - timedelta(days=int(years * 365.25) + 5)

    start_s = start.isoformat()
    end_s = (end + timedelta(days=1)).isoformat()  # yahoo end is exclusive-ish

    # tickers
    tickers = [t for t, _, _ in portfolio.holdings]
    df = _download_adj_close(tickers, start=start_s, end=end_s)

    # drop tickers without data and renormalize weights
    available = [c for c in df.columns if df[c].notna().sum() > 10]
    df = df[available].dropna(how="all")
    if df.empty or len(available) < 2:
        raise RuntimeError("Dati insufficienti per fare il backtest (troppi ticker senza serie storica).")

    w_map = {t: w for t, _, w in portfolio.holdings}
    used_holdings = [(t, next((nm for tt, nm, _ in portfolio.holdings if tt == t), t), w_map[t]) for t in available]
    w = np.array([w_map[t] for t in available], dtype=float)
    w = w / w.sum()

    # daily returns
    prices = df.ffill().dropna()
    rets = prices.pct_change().dropna()

    # portfolio daily return (no fees, no taxes, no rebalancing)
    port_ret = (rets.values @ w)
    port_ret = pd.Series(port_ret, index=rets.index, name="portfolio_return")

    # equity curve
    port_value = (1.0 + port_ret).cumprod() * float(capital)
    port_value.name = "Portfolio"

    # benchmark (optional)
    bench_value = None
    if benchmark:
        bdf = _download_adj_close([benchmark], start=start_s, end=end_s)
        if not bdf.empty and benchmark in bdf.columns:
            bprices = bdf[benchmark].ffill().dropna()
            bret = bprices.pct_change().dropna()
            bench_value = (1.0 + bret).cumprod() * float(capital)
            bench_value.name = f"Benchmark ({benchmark})"
            # align indexes for stats comparisons if needed
            # (keep separate series anyway)

    # stats
    # CAGR from first/last
    n_days = port_value.shape[0]
    years_eff = n_days / 252.0
    cagr = (port_value.iloc[-1] / port_value.iloc[0]) ** (1.0 / max(years_eff, 1e-9)) - 1.0

    # annualized vol
    vol = float(port_ret.std() * np.sqrt(252))

    # max drawdown
    peak = port_value.cummax()
    dd = port_value / peak - 1.0
    mdd = float(dd.min())

    stats = {
        "capital_initial": float(capital),
        "capital_final": float(port_value.iloc[-1]),
        "total_return_pct": float((port_value.iloc[-1] / port_value.iloc[0] - 1.0) * 100.0),
        "cagr_pct": float(cagr * 100.0),
        "annual_vol_pct": float(vol * 100.0),
        "max_drawdown_pct": float(mdd * 100.0),
        "tickers_used": float(len(available)),
    }

    return BacktestResult(
        portfolio_value=port_value,
        benchmark_value=bench_value,
        stats=stats,
        used_holdings=used_holdings,
    )


def print_portfolio(portfolio: Portfolio, capital: float) -> None:
    print(f"Portafoglio per: {portfolio.owner}")
    print(f"Profilo rischio: {portfolio.risk_profile}")
    print(f"Capitale: {capital:,.2f}")
    print()
    print(f"{'Ticker':<10} {'Peso %':>8} {'Importo':>14}  Azienda")
    print("-" * 70)
    for t, nm, w in portfolio.holdings:
        amt = capital * w
        print(f"{t:<10} {w*100:>7.2f}% {amt:>14,.2f}  {nm}")
    print("-" * 70)
    print(f"{'Totale':<19} {capital:>14,.2f}")
    print()


def print_stats(stats: Dict[str, float]) -> None:
    print("Backtest (buy & hold, 5 anni):")
    print(f"- Capitale iniziale: {stats['capital_initial']:,.2f}")
    print(f"- Capitale finale:   {stats['capital_final']:,.2f}")
    print(f"- Rendimento totale: {stats['total_return_pct']:.2f}%")
    print(f"- CAGR:             {stats['cagr_pct']:.2f}% annuo")
    print(f"- Volatilità annua: {stats['annual_vol_pct']:.2f}%")
    print(f"- Max drawdown:     {stats['max_drawdown_pct']:.2f}%")
    print(f"- Ticker usati:     {int(stats['tickers_used'])}")
    print()


def plot_equity(result: BacktestResult, out_png: Optional[str] = None) -> None:
    import matplotlib.pyplot as plt

    plt.figure()
    result.portfolio_value.plot()
    if result.benchmark_value is not None:
        # align display window (optional)
        result.benchmark_value.reindex(result.portfolio_value.index).ffill().plot()
    plt.xlabel("Data")
    plt.ylabel("Valore portafoglio")
    plt.title("Equity curve (5 anni)")
    plt.tight_layout()

    if out_png:
        plt.savefig(out_png, dpi=150)
        print(f"Grafico salvato in: {out_png}")
    else:
        plt.show()


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera portafoglio (da nome+cognome) e fa backtest 5 anni.")
    parser.add_argument("nome")
    parser.add_argument("cognome")
    parser.add_argument("capitale", type=float, help="Quanto investire (es: 10000)")
    parser.add_argument("-n", "--num", type=int, default=12, help="Numero titoli (default 12)")
    parser.add_argument("--years", type=int, default=5, help="Anni di backtest (default 5)")
    parser.add_argument("--benchmark", default="SPY", help="Benchmark ticker (default SPY). Usa '' per disabilitare.")
    parser.add_argument("--plot", action="store_true", help="Mostra grafico equity curve")
    parser.add_argument("--out", default=None, help="Salva grafico su PNG (es: equity.png)")
    args = parser.parse_args()

    full_name = f"{args.nome} {args.cognome}"
    portfolio = generate_portfolio(full_name, n_holdings=args.num)

    benchmark = args.benchmark if args.benchmark.strip() else None

    print_portfolio(portfolio, args.capitale)

    result = backtest_buy_and_hold(portfolio, capital=args.capitale, years=args.years, benchmark=benchmark)
    print_stats(result.stats)

    # show what tickers were actually used (after data cleanup)
    if len(result.used_holdings) != len(portfolio.holdings):
        used = [t for t, _, _ in result.used_holdings]
        dropped = [t for t, _, _ in portfolio.holdings if t not in used]
        print(f"Nota: alcuni ticker sono stati esclusi per mancanza dati: {', '.join(dropped)}")
        print()

    if args.plot or args.out:
        plot_equity(result, out_png=args.out)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())