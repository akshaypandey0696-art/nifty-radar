from flask import Flask, jsonify, render_template_string
import yfinance as yf
import pandas as pd
import requests
import threading
import time
from datetime import datetime

app = Flask(__name__)

BOT_TOKEN = "8653503406:AAEBUGdQ70vDvgG42MjLh8vjPUJOzR_QZZA"
CHAT_ID = "5425316856"

NIFTY_50 = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "BHARTIARTL.NS",
    "INFY.NS", "ITC.NS", "SBIN.NS", "LT.NS", "HINDUNILVR.NS",
    "BAJFINANCE.NS", "HCLTECH.NS", "MARUTI.NS", "SUNPHARMA.NS", "ONGC.NS",
    "TATAMOTORS.NS", "NTPC.NS", "AXISBANK.NS", "KOTAKBANK.NS", "TITAN.NS",
    "ADANIENT.NS", "ADANIPORTS.NS", "COALINDIA.NS", "POWERGRID.NS", "TATASTEEL.NS",
    "BAJAJFINSV.NS", "ULTRACEMCO.NS", "ASIANPAINT.NS", "JSWSTEEL.NS", "GRASIM.NS",
    "M&M.NS", "TECHM.NS", "HDFCLIFE.NS", "WIPRO.NS", "DRREDDY.NS",
    "CIPLA.NS", "SBILIFE.NS", "BAJAJ-AUTO.NS", "EICHERMOT.NS", "BPCL.NS",
    "DIVISLAB.NS", "APOLLOHOSP.NS", "TATACONSUM.NS", "BRITANNIA.NS", "SHRIRAMFIN.NS",
    "INDUSINDBK.NS", "HEROMOTOCO.NS", "LTIM.NS", "HINDALCO.NS", "BEL.NS"
]

NIFTY_NEXT_50 = [
    "DMART.NS", "HAL.NS", "VBL.NS", "IOC.NS", "DLF.NS",
    "CHOLAFIN.NS", "SIEMENS.NS", "PIDILITIND.NS", "TVSMOTOR.NS", "GAIL.NS",
    "AMBUJACEM.NS", "BANKBARODA.NS", "INDIGO.NS", "PNB.NS", "VEDL.NS",
    "PFC.NS", "RECLTD.NS", "ABB.NS", "HAVELLS.NS", "ICICIPRULI.NS",
    "DABUR.NS", "GODREJCP.NS", "SHREECEM.NS", "BOSCHLTD.NS", "MOTHERSON.NS",
    "CANBK.NS", "TORNTPHARM.NS", "COLPAL.NS", "NAUKRI.NS", "ZYDUSLIFE.NS",
    "IRCTC.NS", "IRFC.NS", "LODHA.NS", "JINDALSTEL.NS", "JSWENERGY.NS",
    "CGPOWER.NS", "BSE.NS", "POLICYBZR.NS", "TRENT.NS", "ZOMATO.NS"
]

cached_data = {"nifty50": [], "next50": [], "updated": "Syncing..."}
alerted = set()

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=8)
    except:
        pass

def calculate_wilders_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1.0/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0/period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

def backtest_stock(df):
    signals = []
    in_t = False
    ep, ed, eidx = 0, "", 0
    for i in range(15, len(df)):
        rsi = df['RSI'].iloc[i]
        price = df['Close'].iloc[i]
        d_str = df.index[i].strftime("%d %b %Y")
        if not in_t and rsi < 35:
            in_t = True
            ep, ed, eidx = price, d_str, i
        elif in_t:
            gain = ((price - ep) / ep) * 100
            if rsi >= 65 or gain >= 5 or (i - eidx) >= 20:
                signals.append({
                    "entryDate": ed, "entryPrice": round(ep, 2),
                    "exitDate": d_str, "exitPrice": round(price, 2),
                    "pnl": round(gain, 2), "isWin": gain > 0,
                    "days": i - eidx
                })
                in_t = False
    tot = len(signals)
    wins = len([s for s in signals if s['isWin']])
    rate = round((wins / tot) * 100, 1) if tot > 0 else 0
    last = signals[-1] if tot > 0 else None
    return tot, wins, rate, last, list(reversed(signals[-5:]))

def fetch_group(tickers, b_name):
    items = []
    try:
        data = yf.download(tickers, period="1y", interval="1d", progress=False, group_by='ticker')
        for sym in tickers:
            try:
                df = data[sym].dropna(how="all").copy() if len(tickers) > 1 else data.dropna(how="all").copy()
                if len(df) < 25:
                    continue
                df['RSI'] = calculate_wilders_rsi(df['Close'], 14)
                p = round(float(df['Close'].iloc[-1]), 2)
                r = round(float(df['RSI'].iloc[-1]), 1)
                tot, wins, rate, last, hist = backtest_stock(df)
                s_name = sym.replace(".NS", "")

                if r < 35 and s_name not in alerted:
                    msg = f"🟢 *BUY SIGNAL TRIGGERED (< 35)* 🟢\n\n" \
                          f"📌 *Stock:* {s_name} ({b_name})\n" \
                          f"💰 *LTP:* ₹{p}\n" \
                          f"📉 *RSI:* {r}\n" \
                          f"🎯 *Win Rate:* {rate}% ({wins}/{tot} Wins)\n"
                    if last:
                        msg += f"\n📜 *Last Trade:* {'✅ TARGET HIT' if last['isWin'] else '❌ STOPPED'}\n" \
                               f"• Return: {last['pnl']}%\n• Duration: {last['days']} Days"
                    send_telegram(msg)
                    alerted.add(s_name)
                elif r >= 35 and s_name in alerted:
                    alerted.discard(s_name)

                items.append({
                    "sym": s_name, "ltp": p, "rsi": r,
                    "winRate": rate, "wins": wins, "total": tot,
                    "last": last, "hist": hist
                })
            except:
                continue
    except:
        pass
    return items

def scan_loop():
    while True:
        n50 = fetch_group(NIFTY_50, "NIFTY 50")
        nxt50 = fetch_group(NIFTY_NEXT_50, "NIFTY NEXT 50")
        cached_data["nifty50"] = n50
        cached_data["next50"] = nxt50
        cached_data["updated"] = datetime.now().strftime("%I:%M %p")
        time.sleep(240)

threading.Thread(target=scan_loop, daemon=True).start()

HTML_PAGE = """<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Nifty RSI Radar</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0;font-family:sans-serif}
  body{background:#0b0e14;color:#e6edf3;padding-bottom:30px}
  .header{position:sticky;top:0;background:#161b22;padding:12px;border-bottom:1px solid #30363d;z-index:10}
  .row{display:flex;justify-content:space-between;align-items:center}
  .pulse{width:8px;height:8px;background:#3fb950;border-radius:50%;display:inline-block;box-shadow:0 0 8px #3fb950}
  .tabs{display:flex;gap:6px;background:#21262d;padding:4px;border-radius:8px;margin-top:8px}
  .tab-btn{flex:1;background:none;border:none;color:#8b949e;padding:8px;border-radius:6px;font-weight:700;font-size:13px;cursor:pointer}
  .tab-btn.active{background:#1f6feb;color:#fff}
  .filter-row{display:flex;gap:8px;margin-top:8px}
  .search-box{flex:1;background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:6px 10px;color:#fff;font-size:12px;outline:none}
  .buy-btn{background:#238636;color:#fff;border:none;border-radius:6px;padding:0 10px;font-size:11px;font-weight:700;cursor:pointer}
  .buy-btn.active{background:#2ea043;border:1px solid #fff}
  .list{padding:12px;display:flex;flex-direction:column;gap:10px}
  .card{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:12px}
  .buy-card{border-left:4px solid #3fb950;background:#0c1a14}
  .rsi-val{font-size:18px;font-weight:700}
  .pill{font-size:10px;padding:3px 6px;border-radius:4px;font-weight:700}
  .buy-pill{background:#238636;color:#fff}
  .stat-row{font-size:11px;color:#8b949e;margin-top:8px;padding-top:8px;border-top:1px solid #21262d;display:flex;justify-content:space-between}
</style>
</head>
<body>
<div class="header">
  <div class="row">
    <h3><span class="pulse"></span> NIFTY RSI RADAR</h3>
    <span id="upd" style="font-size:11px;color:#8b949e">Syncing...</span>
  </div>
  <div class="tabs">
    <button class="tab-btn active" id="b1" onclick="switchB('nifty50')">NIFTY 50</button>
    <button class="tab-btn" id="b2" onclick="switchB('next50')">NIFTY NEXT 50</button>
  </div>
  <div class="filter-row">
    <input type="text" id="srch" class="search-box" placeholder="Search stock..." oninput="render()">
    <button class="buy-btn" id="bf" onclick="toggleB()">Only BUY (<35)</button>
  </div>
</div>
<div class="list" id="box"><div style="text-align:center;padding:40px;color:#8b949e">Connecting Cloud Scanner...</div></div>
<script>
let b = 'nifty50', raw = {}, onlyBuy = false;
async function sync(){
  try{
    let r = await fetch('/api');
    raw = await r.json();
    document.getElementById('upd').innerText = "Live: " + raw.updated;
    render();
  }catch(e){}
}
function switchB(k){
  b = k;
  document.getElementById('b1').className = 'tab-btn ' + (b==='nifty50'?'active':'');
  document.getElementById('b2').className = 'tab-btn ' + (b==='next50'?'active':'');
  render();
}
function toggleB(){
  onlyBuy = !onlyBuy;
  document.getElementById('bf').className = 'buy-btn ' + (onlyBuy?'active':'');
  render();
}
function render(){
  let s = document.getElementById('srch').value.toUpperCase();
  let arr = (raw[b] || []).filter(x => x.sym.includes(s) && (onlyBuy ? x.rsi < 35 : true));
  arr.sort((x,y) => (x.rsi||99) - (y.rsi||99));
  if(!arr.length){
    document.getElementById('box').innerHTML = '<div style="text-align:center;padding:30px;color:#8b949e">Scanning or no stock matches.</div>';
    return;
  }
  document.getElementById('box').innerHTML = arr.map(i => {
    let isBuy = i.rsi < 35;
    let lastTxt = i.last ? (i.last.isWin ? '✅ Hit (+'+i.last.pnl+'%)' : '❌ Stop ('+i.last.pnl+'%)') : 'No trade';
    return `
      <div class="card ${isBuy?'buy-card':''}">
        <div class="row">
          <div><b>${i.sym}</b><div style="font-size:12px;color:#8b949e">₹${i.ltp}</div></div>
          <div style="text-align:right">
            <div class="rsi-val" style="color:${isBuy?'#3fb950':'#fff'}">${i.rsi}</div>
            <span class="pill ${isBuy?'buy-pill':''}">${isBuy?'BUY (<35)':'HOLD'}</span>
          </div>
        </div>
        <div class="stat-row">
          <div>Win Rate: <b style="color:#3fb950">${i.winRate}%</b> (${i.wins}/${i.total} W)</div>
          <div>Last: ${lastTxt}</div>
        </div>
      </div>
    `;
  }).join('');
}
setInterval(sync, 5000);
sync();
</script>
</body>
</html>"""

@app.route('/')
def home():
    return render_template_string(HTML_PAGE)

@app.route('/api')
def api():
    return jsonify(cached_data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
