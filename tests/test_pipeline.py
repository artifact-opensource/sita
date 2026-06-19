"""SITA — Integration Test"""
import pandas as pd
import numpy as np
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Generate synthetic OHLCV data
np.random.seed(42)
n = 300
dates = pd.date_range('2026-01-01', periods=n, freq='15min')
returns = np.random.normal(0.0001, 0.002, n)
price = 50000 * np.exp(np.cumsum(returns))

ohlcv = pd.DataFrame({
    'timestamp': dates,
    'open': price * (1 + np.random.normal(0, 0.001, n)),
    'high': price * (1 + np.abs(np.random.normal(0, 0.002, n))),
    'low': price * (1 - np.abs(np.random.normal(0, 0.002, n))),
    'close': price,
    'volume': np.random.uniform(100, 1000, n),
})

print(f'Test data: {n} bars, price range ${price.min():.0f} - ${price.max():.0f}')

from sita.signal import StrategySelector
from sita.confluence import EntryConfluenceFilter
from sita.risk import UnifiedRiskManager
from sita.adapters import BacktestEngine, BacktestConfig

# Signal
selector = StrategySelector()
signal = selector.generate_signal(ohlcv, 'BTC/USDT')
print(f'Signal: {signal.primary.summary}')

# Confluence
cf = EntryConfluenceFilter()
atr = ohlcv['high'].sub(ohlcv['low']).rolling(14).mean().iloc[-1]
conf = cf.analyze_entry('long', price[-1], 'BTC/USDT', ohlcv, atr)
print(f'Confluence: {conf.summary}')

# Risk
rm = UnifiedRiskManager()
rm.initialize_balances(10000)
sl = rm.calculate_stop_loss('long', price[-1], atr)
tp = rm.calculate_take_profit('long', price[-1], sl)
dec = rm.approve_trade('BTC/USDT', 'long', price[-1], sl, tp, 10000, conf.position_mult)
print(f'Risk: {dec.action.value}, size={dec.position_size:.4f}, SL={sl:.0f}, TP={tp:.0f}')

# Backtest
print('\nRunning backtest...')
bt = BacktestEngine(BacktestConfig(initial_balance=10000, commission_pct=0.001))
result = bt.run(ohlcv, 'BTC/USDT')

print('\nBacktest Results:')
for k, v in result.summary().items():
    print(f'  {k}: {v}')

# Save results
result.save(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'state', 'test_backtest.json'))
print('\n✓ Full pipeline test passed — results saved')
