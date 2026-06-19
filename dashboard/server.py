"""
SITA — Live Dashboard
Real-time web UI for monitoring the trading agent.

Shows:
- Live equity curve
- Open positions with P&L
- Signal feed (last 25 signals)
- Confluence scores
- Risk metrics (drawdown, daily P&L, limits)
- Strategy performance comparison
- Trade history
- Reflection log
- System health

Run: python3 -m sita.dashboard
"""

from __future__ import annotations
import json
import logging
import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any

logger = logging.getLogger("sita.dashboard")

# Dashboard config
DASHBOARD_HOST = os.getenv("SITA_DASHBOARD_HOST", "0.0.0.0")
DASHBOARD_PORT = int(os.getenv("SITA_DASHBOARD_PORT", "8090"))
STATE_DIR = Path(os.getenv("SITA_BASE_DIR", str(Path.home() / "Projects" / "sita"))) / "state"


class DashboardData:
    """Reads SITA state files and prepares data for the dashboard."""

    def __init__(self, state_dir: Path = STATE_DIR):
        self.state_dir = state_dir

    def get_all(self) -> Dict[str, Any]:
        """Get complete dashboard data."""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "goal": self._load_yaml("goal.yaml"),
            "strategy": self._load_yaml("strategy.yaml"),
            "trades": self._load_trades(),
            "hypotheses": self._load_hypotheses(),
            "history": self._load_history(),
            "equity_curve": self._compute_equity_curve(),
            "stats": self._compute_stats(),
            "reflection_log": self._load_reflection_log(),
        }

    def _load_yaml(self, filename: str) -> Dict:
        import yaml
        path = self.state_dir / filename
        if path.exists():
            with open(path) as f:
                return yaml.safe_load(f) or {}
        return {}

    def _load_trades(self) -> List[Dict]:
        path = self.state_dir / "trades.jsonl"
        if not path.exists():
            return []
        trades = []
        with open(path) as f:
            for line in f:
                try:
                    t = json.loads(line)
                    if not t.get("_reflection_marker"):
                        trades.append(t)
                except json.JSONDecodeError:
                    continue
        return trades

    def _load_hypotheses(self) -> List[Dict]:
        path = self.state_dir / "hypotheses.jsonl"
        if not path.exists():
            return []
        hypotheses = []
        with open(path) as f:
            for line in f:
                try:
                    hypotheses.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return hypotheses

    def _load_history(self) -> List[Dict]:
        history = []
        history_dir = self.state_dir / "history"
        if history_dir.exists():
            for f in sorted(history_dir.glob("v*.yaml")):
                data = self._load_yaml(f"history/{f.name}")
                if data:
                    data["_file"] = f.name
                    history.append(data)
        return history

    def _compute_equity_curve(self) -> List[Dict]:
        """Compute equity curve from trades."""
        trades = self._load_trades()
        if not trades:
            return []

        balance = 10000.0  # Initial
        equity = [{"bar": 0, "equity": balance, "timestamp": None}]

        for i, t in enumerate(trades):
            pnl = t.get("pnl", 0)
            balance += pnl
            equity.append({
                "bar": i + 1,
                "equity": round(balance, 2),
                "pnl": round(pnl, 2),
                "timestamp": t.get("timestamp", ""),
                "symbol": t.get("symbol", ""),
                "side": t.get("side", ""),
                "reason": t.get("exit_reason", ""),
            })

        return equity

    def _compute_stats(self) -> Dict:
        trades = self._load_trades()
        if not trades:
            return {
                "total_trades": 0, "wins": 0, "losses": 0,
                "win_rate": 0, "total_pnl": 0, "avg_pnl": 0,
                "max_drawdown": 0, "sharpe": 0, "profit_factor": 0,
                "avg_confluence": 0, "daily_pnl": 0, "weekly_pnl": 0,
            }

        pnls = [t.get("pnl", 0) for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        total_pnl = sum(pnls)
        win_rate = len(wins) / len(pnls) if pnls else 0

        # Max drawdown
        balance = 10000.0
        peak = balance
        max_dd = 0
        for p in pnls:
            balance += p
            if balance > peak:
                peak = balance
            dd = (peak - balance) / peak
            if dd > max_dd:
                max_dd = dd

        # Sharpe
        if len(pnls) > 1:
            returns = [pnls[i] / (10000 + sum(pnls[:i])) for i in range(len(pnls))]
            import numpy as np
            if np.std(returns) > 0:
                sharpe = float(np.mean(returns) / np.std(returns) * np.sqrt(252 * 96))
            else:
                sharpe = 0
        else:
            sharpe = 0

        # Profit factor
        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 0
        pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        # Confluence
        confidences = [t.get("confluence_score", 0) for t in trades if t.get("confluence_score")]
        avg_conf = sum(confidences) / len(confidences) if confidences else 0

        # Daily/Weekly P&L
        now = datetime.now(timezone.utc)
        today_pnl = sum(t.get("pnl", 0) for t in trades if t.get("timestamp") and
                        datetime.fromisoformat(t["timestamp"]).date() == now.date())
        week_start = now - timedelta(days=now.weekday())
        week_pnl = sum(t.get("pnl", 0) for t in trades if t.get("timestamp") and
                       datetime.fromisoformat(t["timestamp"]) >= week_start)

        # Strategy breakdown
        strategies = {}
        for t in trades:
            s = t.get("strategy", "unknown")
            if s not in strategies:
                strategies[s] = {"trades": 0, "wins": 0, "pnl": 0}
            strategies[s]["trades"] += 1
            strategies[s]["pnl"] += t.get("pnl", 0)
            if t.get("pnl", 0) > 0:
                strategies[s]["wins"] += 1

        return {
            "total_trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(win_rate, 4),
            "total_pnl": round(total_pnl, 2),
            "avg_pnl": round(total_pnl / len(trades), 2) if trades else 0,
            "max_drawdown": round(max_dd, 4),
            "sharpe": round(sharpe, 2),
            "profit_factor": round(pf, 2),
            "avg_confluence": round(avg_conf, 1),
            "daily_pnl": round(today_pnl, 2),
            "weekly_pnl": round(week_pnl, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
            "strategies": strategies,
        }

    def _load_reflection_log(self) -> List[Dict]:
        """Load reflection history."""
        hypotheses = self._load_hypotheses()
        return hypotheses[-10:]  # Last 10 reflections


# ─── HTML Template ──────────────────────────────────────────────────────────

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SITA — Live Dashboard</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg:#0a0a0f;--surface:#12121a;--border:#1e1e2e;--text:#e0e0e0;--muted:#666;
  --green:#00e676;--red:#ff5252;--yellow:#ffd740;--blue:#448aff;--purple:#b388ff;
  --orange:#ff9100;--cyan:#18ffff;
}
body{background:var(--bg);color:var(--text);font-family:'SF Mono','Fira Code','Consolas',monospace;font-size:13px;line-height:1.6}
.header{background:var(--surface);border-bottom:1px solid var(--border);padding:16px 24px;display:flex;justify-content:space-between;align-items:center}
.header h1{font-size:18px;color:var(--cyan)}.header h1 span{color:var(--green)}
.header .status{display:flex;gap:16px;font-size:12px}
.header .status span{color:var(--muted)}
.header .status .val{color:var(--text);font-weight:bold}
.container{padding:24px;max-width:1600px;margin:0 auto}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:24px}
.grid-2{grid-template-columns:repeat(2,1fr)}.grid-3{grid-template-columns:repeat(3,1fr)}
.card{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:16px}
.card h3{font-size:11px;text-transform:uppercase;letter-spacing:1px;color:var(--muted);margin-bottom:12px}
.metric{font-size:28px;font-weight:bold;margin-bottom:4px}
.metric.small{font-size:18px}.metric .unit{font-size:14px;color:var(--muted)}
.metric.positive{color:var(--green)}.metric.negative{color:var(--red)}.metric.neutral{color:var(--blue)}
.sub{font-size:11px;color:var(--muted)}
.bar-row{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border);font-size:12px}
.bar-row:last-child{border-bottom:none}
.bar-label{color:var(--muted)}.bar-val{font-weight:bold}
.bar-val.g{color:var(--green)}.bar-val.r{color:var(--red)}.bar-val.y{color:var(--yellow)}
.progress-bar{height:4px;background:var(--border);border-radius:2px;margin-top:4px;overflow:hidden}
.progress-bar .fill{height:100%;border-radius:2px;transition:width 0.3s}
.fill.g{background:var(--green)}.fill.r{background:var(--red)}.fill.y{background:var(--yellow)}.fill.b{background:var(--blue)}
table{width:100%;border-collapse:collapse;font-size:12px}
th{text-align:left;padding:8px;border-bottom:1px solid var(--border);color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:1px}
td{padding:8px;border-bottom:1px solid var(--border)}
tr:hover{background:rgba(255,255,255,0.02)}
.badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:bold;text-transform:uppercase}
.badge.long{background:rgba(0,230,118,0.15);color:var(--green)}
.badge.short{background:rgba(255,82,82,0.15);color:var(--red)}
.badge.premium{background:rgba(179,136,255,0.15);color:var(--purple)}
.badge.good{background:rgba(68,138,255,0.15);color:var(--blue)}
.badge.marginal{background:rgba(255,215,64,0.15);color:var(--yellow)}
.badge.reject{background:rgba(255,82,82,0.15);color:var(--red)}
canvas{width:100%!important;height:200px!important}
.chart-container{height:200px}
.chart-lg{height:300px}
.tabs{display:flex;gap:4px;margin-bottom:16px}
.tab{padding:8px 16px;background:var(--surface);border:1px solid var(--border);border-radius:6px;cursor:pointer;font-size:12px;color:var(--muted)}
.tab.active{background:var(--blue);color:#fff;border-color:var(--blue)}
.tab:hover:not(.active){background:var(--border)}
.refresh-info{text-align:center;color:var(--muted);font-size:11px;margin-top:24px}
</style>
</head>
<body>
<div class="header">
  <h1>SITA <span>v1.0 APEX</span> — Live Dashboard</h1>
  <div class="status">
    <div>Mode: <span class="val" id="mode">paper</span></div>
    <div>Updated: <span class="val" id="updated">—</span></div>
    <div>Status: <span class="val" style="color:var(--green)">● ONLINE</span></div>
  </div>
</div>
<div class="container">

  <!-- Row 1: Key Metrics -->
  <div class="grid">
    <div class="card">
      <h3>Total P&L</h3>
      <div class="metric" id="total-pnl">$0.00</div>
      <div class="sub" id="total-pnl-pct">0.00%</div>
    </div>
    <div class="card">
      <h3>Win Rate</h3>
      <div class="metric" id="win-rate">0%</div>
      <div class="sub"><span id="wins">0</span>W / <span id="losses">0</span>L</div>
    </div>
    <div class="card">
      <h3>Max Drawdown</h3>
      <div class="metric negative" id="max-dd">0.0%</div>
      <div class="sub">Limit: <span id="dd-limit">8%</span></div>
    </div>
    <div class="card">
      <h3>Sharpe Ratio</h3>
      <div class="metric" id="sharpe">0.00</div>
      <div class="sub">Min: <span id="sharpe-min">1.2</span></div>
    </div>
  </div>

  <!-- Row 2: Daily/Weekly + Profit Factor -->
  <div class="grid">
    <div class="card">
      <h3>Daily P&L</h3>
      <div class="metric small" id="daily-pnl">$0.00</div>
      <div class="progress-bar"><div class="fill b" id="daily-bar" style="width:50%"></div></div>
      <div class="sub">Limit: 3% daily loss</div>
    </div>
    <div class="card">
      <h3>Weekly P&L</h3>
      <div class="metric small" id="weekly-pnl">$0.00</div>
      <div class="progress-bar"><div class="fill b" id="weekly-bar" style="width:50%"></div></div>
      <div class="sub">Limit: 6% weekly loss</div>
    </div>
    <div class="card">
      <h3>Profit Factor</h3>
      <div class="metric" id="pf">0.00</div>
      <div class="sub">Gross: <span id="gross-profit">$0</span> / <span id="gross-loss">$0</span></div>
    </div>
    <div class="card">
      <h3>Avg Confluence</h3>
      <div class="metric" id="avg-conf">0</div>
      <div class="sub">Last: <span id="last-conf">0</span>/100</div>
    </div>
  </div>

  <!-- Row 3: Equity Curve + Strategy Breakdown -->
  <div class="grid grid-2">
    <div class="card">
      <h3>Equity Curve</h3>
      <div class="chart-container chart-lg"><canvas id="equity-chart"></canvas></div>
    </div>
    <div class="card">
      <h3>Strategy Performance</h3>
      <div id="strategy-breakdown">
        <div class="bar-row"><span class="bar-label">No data yet</span></div>
      </div>
    </div>
  </div>

  <!-- Row 4: Confluence Distribution + Risk Gauges -->
  <div class="grid grid-2">
    <div class="card">
      <h3>Confluence Score Distribution</h3>
      <div class="chart-container"><canvas id="conf-chart"></canvas></div>
    </div>
    <div class="card">
      <h3>Risk Gauges</h3>
      <div id="risk-gauges">
        <div class="bar-row">
          <span class="bar-label">Positions Open</span>
          <span class="bar-val" id="open-pos">0 / 5</span>
        </div>
        <div class="progress-bar"><div class="fill g" id="pos-bar" style="width:0%"></div></div>
        <div class="bar-row">
          <span class="bar-label">Daily Loss Used</span>
          <span class="bar-val" id="daily-used">0%</span>
        </div>
        <div class="progress-bar"><div class="fill y" id="daily-bar-used" style="width:0%"></div></div>
        <div class="bar-row">
          <span class="bar-label">Weekly Loss Used</span>
          <span class="bar-val" id="weekly-used">0%</span>
        </div>
        <div class="progress-bar"><div class="fill y" id="weekly-bar-used" style="width:0%"></div></div>
        <div class="bar-row">
          <span class="bar-label">Drawdown Used</span>
          <span class="bar-val" id="dd-used">0% / 8%</span>
        </div>
        <div class="progress-bar"><div class="fill r" id="dd-bar-used" style="width:0%"></div></div>
        <div class="bar-row">
          <span class="bar-label">Recovery Mode</span>
          <span class="bar-val" id="recovery-mode">Inactive</span>
        </div>
      </div>
    </div>
  </div>

  <!-- Row 5: Trade History -->
  <div class="card" style="margin-bottom:24px">
    <h3>Trade History</h3>
    <div style="max-height:400px;overflow-y:auto">
    <table>
      <thead><tr>
        <th>Time</th><th>Symbol</th><th>Side</th><th>Entry</th><th>Exit</th>
        <th>Size</th><th>P&L</th><th>Reason</th><th>Strategy</th><th>Conf</th>
      </tr></thead>
      <tbody id="trade-table"><tr><td colspan="10" style="text-align:center;color:var(--muted)">No trades yet</td></tr></tbody>
    </table>
    </div>
  </div>

  <!-- Row 6: Reflection Log + Strategy Evolution -->
  <div class="grid grid-2">
    <div class="card">
      <h3>Reflection Log</h3>
      <div id="reflection-log" style="max-height:300px;overflow-y:auto">
        <div class="bar-row"><span class="bar-label">No reflections yet</span></div>
      </div>
    </div>
    <div class="card">
      <h3>Strategy Evolution</h3>
      <div id="strategy-evolution" style="max-height:300px;overflow-y:auto">
        <div class="bar-row"><span class="bar-label">No strategy changes yet</span></div>
      </div>
    </div>
  </div>

  <!-- Row 7: Current Strategy + Goal -->
  <div class="grid grid-2">
    <div class="card">
      <h3>Current Strategy</h3>
      <pre id="current-strategy" style="font-size:11px;color:var(--cyan);white-space:pre-wrap">Loading...</pre>
    </div>
    <div class="card">
      <h3>Goal Configuration</h3>
      <pre id="goal-config" style="font-size:11px;color:var(--green);white-space:pre-wrap">Loading...</pre>
    </div>
  </div>

  <div class="refresh-info">Auto-refreshes every 10 seconds — SITA Dashboard v1.0</div>
</div>

<script>
const API = '/api/data';

function fmt(n,d=2){return typeof n==='number'?n.toFixed(d):n}
function fmtPct(n){return (n*100).toFixed(1)+'%'}
function pnlClass(n){return n>0?'positive':n<0?'negative':'neutral'}

async function fetchData(){
  try{
    const r = await fetch(API);
    return await r.json();
  }catch(e){console.error(e);return null}
}

function renderEquity(ctx,data){
  const eq=data.equity_curve||[];
  if(eq.length<2)return;
  const c=ctx.canvas;c.width=c.offsetWidth;c.height=c.offsetHeight;
  const w=c.width,h=c.height,pad=40;
  const eqs=eq.map(e=>e.equity);
  const min=Math.min(...eqs)*0.999,max=Math.max(...eqs)*1.001;
  const range=max-min||1;
  ctx.clearRect(0,0,w,h);
  // Grid
  ctx.strokeStyle='#1e1e2e';ctx.lineWidth=1;
  for(let i=0;i<5;i++){const y=pad+(h-2*pad)*i/4;ctx.beginPath();ctx.moveTo(pad,y);ctx.lineTo(w-pad,y);ctx.stroke()}
  // Line
  ctx.beginPath();ctx.strokeStyle='#448aff';ctx.lineWidth=2;
  eq.forEach((e,i)=>{
    const x=pad+(w-2*pad)*i/(eq.length-1);
    const y=h-pad-(e.equity-min)/range*(h-2*pad);
    i===0?ctx.moveTo(x,y):ctx.lineTo(x,y);
  });
  ctx.stroke();
  // Fill
  ctx.lineTo(w-pad,h-pad);ctx.lineTo(pad,h-pad);ctx.closePath();
  const grad=ctx.createLinearGradient(0,pad,0,h-pad);
  grad.addColorStop(0,'rgba(68,138,255,0.2)');grad.addColorStop(1,'rgba(68,138,255,0)');
  ctx.fillStyle=grad;ctx.fill();
  // Labels
  ctx.fillStyle='#666';ctx.font='10px monospace';
  ctx.fillText('$'+fmt(max),4,pad+10);
  ctx.fillText('$'+fmt(min),4,h-pad);
  ctx.fillText('Trades: '+eq.length,4,h-10);
}

function renderConf(ctx,data){
  const trades=data.trades||[];
  if(!trades.length)return;
  const c=ctx.canvas;c.width=c.offsetWidth;c.height=c.offsetHeight;
  const w=c.width,h=c.height,pad=40;
  const confs=trades.map(t=>t.confluence_score||0).filter(c=>c>0);
  if(!confs.length)return;
  // Histogram
  const bins=[0,0,0,0,0,0,0,0,0,0];// 0-10,10-20,...,90-100
  confs.forEach(c=>{const idx=Math.min(Math.floor(c/10),9);bins[idx]++});
  const maxBin=Math.max(...bins)||1;
  const barW=(w-2*pad)/10-4;
  ctx.clearRect(0,0,w,h);
  bins.forEach((count,i)=>{
    const x=pad+i*(barW+4);
    const barH=(count/maxBin)*(h-2*pad);
    const y=h-pad-barH;
    const color=count>0?(i>=8?'#b388ff':i>=7?'#448aff':i>=5?'#ffd740':'#ff5252'):'#1e1e2e';
    ctx.fillStyle=color;ctx.fillRect(x,y,barW,barH);
  });
  ctx.fillStyle='#666';ctx.font='9px monospace';
  for(let i=0;i<10;i++)ctx.fillText(i*10,pad+i*(barW+4),h-pad+12);
}

function updateDashboard(data){
  if(!data)return;
  const s=data.stats||{};
  // Metrics
  const tp=s.total_pnl||0;
  document.getElementById('total-pnl').textContent='$'+fmt(tp);
  document.getElementById('total-pnl').className='metric '+pnlClass(tp);
  document.getElementById('total-pnl-pct').textContent=fmtPct(s.total_pnl/10000);
  document.getElementById('win-rate').textContent=fmtPct(s.win_rate);
  document.getElementById('wins').textContent=s.wins||0;
  document.getElementById('losses').textContent=s.losses||0;
  document.getElementById('max-dd').textContent=fmtPct(s.max_drawdown);
  document.getElementById('sharpe').textContent=fmt(s.sharpe);
  // Daily/Weekly
  const dp=s.daily_pnl||0;
  document.getElementById('daily-pnl').textContent='$'+fmt(dp);
  document.getElementById('daily-pnl').className='metric small '+pnlClass(dp);
  document.getElementById('daily-bar').style.width=Math.min(Math.abs(dp)/10000/0.03*100,100)+'%';
  document.getElementById('daily-bar').className='fill '+(dp>=0?'g':'r');
  const wp=s.weekly_pnl||0;
  document.getElementById('weekly-pnl').textContent='$'+fmt(wp);
  document.getElementById('weekly-pnl').className='metric small '+pnlClass(wp);
  document.getElementById('weekly-bar').style.width=Math.min(Math.abs(wp)/10000/0.06*100,100)+'%';
  document.getElementById('weekly-bar').className='fill '+(wp>=0?'g':'r');
  // PF
  document.getElementById('pf').textContent=fmt(s.profit_factor);
  document.getElementById('gross-profit').textContent='$'+fmt(s.gross_profit);
  document.getElementById('gross-loss').textContent='$'+fmt(s.gross_loss);
  // Confluence
  document.getElementById('avg-conf').textContent=fmt(s.avg_confluence,0);
  const trades=data.trades||[];
  const lastConf=trades.length?(trades[trades.length-1].confluence_score||0):0;
  document.getElementById('last-conf').textContent=fmt(lastConf,0);
  // Strategy breakdown
  const stratDiv=document.getElementById('strategy-breakdown');
  const strats=s.strategies||{};
  if(Object.keys(strats).length===0){
    stratDiv.innerHTML='<div class="bar-row"><span class="bar-label">No data yet</span></div>';
  }else{
    stratDiv.innerHTML=Object.entries(strats).map(([name,st])=>{
      const wr=st.trades>0?st.wins/st.trades:0;
      return `<div class="bar-row">
        <span class="bar-label">${name}</span>
        <span class="bar-val ${st.pnl>=0?'g':'r'}">${st.trades}tr / ${fmtPct(wr)} / $${fmt(st.pnl)}</span>
      </div>`;
    }).join('');
  }
  // Risk gauges
  document.getElementById('open-pos').textContent=`${s.open_positions||0} / 5`;
  document.getElementById('pos-bar').style.width=((s.open_positions||0)/5*100)+'%';
  const ddPct=s.max_drawdown||0;
  document.getElementById('dd-used').textContent=fmtPct(ddPct)+' / 8%';
  document.getElementById('dd-bar-used').style.width=Math.min(ddPct/0.08*100,100)+'%';
  // Trade table
  const tbody=document.getElementById('trade-table');
  if(trades.length===0){
    tbody.innerHTML='<tr><td colspan="10" style="text-align:center;color:var(--muted)">No trades yet</td></tr>';
  }else{
    tbody.innerHTML=trades.slice(-50).reverse().map(t=>{
      const side=t.side==='long'?'<span class="badge long">LONG</span>':'<span class="badge short">SHORT</span>';
      const pnl=t.pnl||0;
      const conf=t.confluence_score||0;
      let confBadge='';
      if(conf>=85)confBadge='<span class="badge premium">PREMIUM</span>';
      else if(conf>=70)confBadge='<span class="badge good">GOOD</span>';
      else if(conf>=50)confBadge='<span class="badge marginal">MARGINAL</span>';
      else confBadge='<span class="badge reject">LOW</span>';
      const time=t.timestamp?new Date(t.timestamp).toLocaleTimeString():'—';
      return `<tr>
        <td>${time}</td><td>${t.symbol||'—'}</td><td>${side}</td>
        <td>$${fmt(t.entry_price||0)}</td><td>$${fmt(t.close_price||t.entry_price||0)}</td>
        <td>${fmt(t.size||0,4)}</td>
        <td class="${pnl>=0?'bar-val g':'bar-val r'}">$${fmt(pnl)}</td>
        <td>${t.exit_reason||'open'}</td><td>${t.strategy||'—'}</td><td>${confBadge}</td>
      </tr>`;
    }).join('');
  }
  // Reflection log
  const refDiv=document.getElementById('reflection-log');
  const refs=data.reflection_log||[];
  if(refs.length===0){
    refDiv.innerHTML='<div class="bar-row"><span class="bar-label">No reflections yet</span></div>';
  }else{
    refDiv.innerHTML=refs.slice().reverse().map(r=>{
      const time=r.timestamp?new Date(r.timestamp).toLocaleString():'—';
      return `<div class="bar-row" style="flex-direction:column;align-items:flex-start;gap:4px">
        <div style="display:flex;justify-content:space-between;width:100%">
          <span class="bar-label">${time}</span>
          <span class="bar-val ${r.score>=0?'g':'r'}">Score: ${fmt(r.score)}</span>
        </div>
        <div style="font-size:11px;color:var(--text)">${r.description||'No change'}</div>
        <div style="font-size:10px;color:var(--muted)">${r.reasoning||''}</div>
      </div>`;
    }).join('');
  }
  // Strategy evolution
  const evoDiv=document.getElementById('strategy-evolution');
  const hist=data.history||[];
  if(hist.length===0){
    evoDiv.innerHTML='<div class="bar-row"><span class="bar-label">No strategy changes yet</span></div>';
  }else{
    evoDiv.innerHTML=hist.slice().reverse().map(h=>{
      const ver=h.version||'?';
      const ind=h.entry?.indicator||'?';
      const thresh=h.entry?.threshold||'?';
      return `<div class="bar-row">
        <span class="bar-label">v${ver}</span>
        <span class="bar-val">${ind} @ ${thresh} | SL: ${h.stop_loss_pct}% | Size: ${h.position_size_r}</span>
      </div>`;
    }).join('');
  }
  // Current strategy + goal
  document.getElementById('current-strategy').textContent=JSON.stringify(data.strategy,null,2);
  document.getElementById('goal-config').textContent=JSON.stringify(data.goal,null,2);
  // Timestamp
  document.getElementById('updated').textContent=new Date().toLocaleTimeString();
  // Charts
  const eqCtx=document.getElementById('equity-chart').getContext('2d');
  renderEquity(eqCtx,data);
  const confCtx=document.getElementById('conf-chart').getContext('2d');
  renderConf(confCtx,data);
}

async function refresh(){
  const data=await fetchData();
  updateDashboard(data);
}

refresh();
setInterval(refresh,10000);
window.addEventListener('resize',()=>refresh());
</script>
</body>
</html>"""


def create_app():
    """Create Flask/FastAPI dashboard app."""
    try:
        from fastapi import FastAPI
        from fastapi.responses import HTMLResponse
        from fastapi.staticfiles import StaticFiles
        import uvicorn

        app = FastAPI(title="SITA Dashboard", version="1.0.0")
        data_provider = DashboardData()

        @app.get("/", response_class=HTMLResponse)
        async def index():
            return DASHBOARD_HTML

        @app.get("/api/data")
        async def api_data():
            return data_provider.get_all()

        @app.get("/api/trades")
        async def api_trades():
            return data_provider._load_trades()

        @app.get("/api/stats")
        async def api_stats():
            return data_provider._compute_stats()

        @app.get("/api/equity")
        async def api_equity():
            return data_provider._compute_equity_curve()

        @app.get("/api/hypotheses")
        async def api_hypotheses():
            return data_provider._load_hypotheses()

        @app.get("/api/strategy")
        async def api_strategy():
            return data_provider._load_yaml("strategy.yaml")

        @app.get("/api/goal")
        async def api_goal():
            return data_provider._load_yaml("goal.yaml")

        logger.info(f"Dashboard created — http://{DASHBOARD_HOST}:{DASHBOARD_PORT}")
        return app

    except ImportError:
        logger.warning("FastAPI not available — using basic HTTP server")
        return None


def run_dashboard(host: str = DASHBOARD_HOST, port: int = DASHBOARD_PORT):
    """Run the dashboard server."""
    app = create_app()

    if app:
        import uvicorn
        uvicorn.run(app, host=host, port=port)
    else:
        # Fallback: basic HTTP server with JSON API
        from http.server import HTTPServer, BaseHTTPRequestHandler
        import threading

        data_provider = DashboardData()

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(DASHBOARD_HTML.encode())
                elif self.path == "/api/data":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(data_provider.get_all(), default=str).encode())
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, format, *args):
                pass  # Suppress logs

        server = HTTPServer((host, port), Handler)
        logger.info(f"Dashboard running at http://{host}:{port}")
        server.serve_forever()


if __name__ == "__main__":
    run_dashboard()
