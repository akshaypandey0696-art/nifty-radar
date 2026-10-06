from flask import Flask, jsonify, render_template_string
import urllib.request
import json
import threading
import time
import os
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

market_store = {"nifty50": [], "next50": [], "updated": "Syncing..."}
alerted = set()

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = json.dumps({"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}).encode('utf-8')
        req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(req, timeout=10)
    except:
        pass

def calculate_rsi_series(prices, period=14):
    if len(prices) <= period:
        return [50.0] * len(prices)
    gains, losses = [], []
    for i in range(1, len(prices)):
        d = prices[i] - prices[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))

    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    rsis = [None] * period
    rs = 100 if avg_l == 0 else avg_g / avg_l
    rsis.append(round(100 - (100 / (1 + rs)), 1))

    for i in range(period, len(gains)):
        avg_g = (avg_g * 13 + gains[i]) / 14
        avg_l = (avg_l * 13 + losses[i]) / 14
        rs = 100 if avg_l == 0 else avg_g / avg_l
        rsis.append(round(100 - (100 / (1 + rs)), 1))
    return rsis

def backtest(prices, rsis, dates):
    trades = []
    in_t = False
    ep, ed, eidx = 0, "", 0
    for i in range(15, len(prices)):
        r = rsis[i]
        p = prices[i]
        d = dates[i]
        if not in_t and r and r < 35:
            in_t = True
            ep, ed, eidx = p, d, i
        elif in_t:
            gain = ((p - ep) / ep) * 100
            if (r and r >= 65) or gain >= 5 or (i - eidx) >= 20:
                trades.append({
                    "entryDate": ed, "entryPrice": round(ep, 2),
                    "exitDate": d, "exitPrice": round(p, 2),
                    "pnl": round(gain, 2), "isWin": gain > 0,
                    "days": i - eidx
                })
                in_t = False
    tot = len(trades)
    wins = len([t for t in trades if t['isWin']])
    rate = round((wins / tot) * 100, 1) if tot > 0 else 0
    last = trades[-1] if tot > 0 else None
    return tot, wins, rate, last

def fetch_single(symbol, b_name):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1y&interval=1d"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as res:
            d = json.loads(res.read().decode('utf-8'))['chart']['result'][0]
            ts = d['timestamp']
            quotes = d['indicators']['quote'][0]['close']
            
            clean_p, clean_d = [], []
            for t, p in zip(ts, quotes):
                if p is not None:
                    clean_p.append(p)
                    clean_d.append(datetime.fromtimestamp(t).strftime('%d %b %Y'))
            
            if len(clean_p) < 25:
                return None
            
            rsis = calculate_rsi_series(clean_p)
            ltp = round(clean_p[-1], 2)
            curr_rsi = rsis[-1]
            tot, wins, wr, last = backtest(clean_p, rsis, clean_d)
            sym_clean = symbol.replace(".NS", "")

            # Duplicate Check: Sirf fresh signal trigger par alert
            if curr_rsi and curr_rsi < 35 and sym_clean not in alerted:
                msg = f"🟢 *BUY SIGNAL TRIGGERED (< 35)* 🟢\n\n" \
                      f"📌 *Stock:* {sym_clean} ({b_name})\n" \
                      f"💰 *LTP:* ₹{ltp}\n" \
                      f"📉 *RSI:* {curr_rsi}\n" \
                      f"🎯 *Win Rate:* {wr}% ({wins}/{tot} Wins)\n"
                if last:
                    msg += f"\n📜 *Last Trade:* {'✅ TARGET HIT' if last['isWin'] else '❌ STOPPED'}\n" \
                           f"• Return: {last['pnl']}%\n• Duration: {last['days']} Days"
                send_telegram(msg)
                alerted.add(sym_clean)
            elif curr_rsi and curr_rsi >= 35 and sym_clean in alerted:
                alerted.discard(sym_clean)

            return {
                "sym": sym_clean, "ltp": ltp, "rsi": curr_rsi,
                "winRate": wr, "wins": wins, "total": tot,
                "last": last
            }
    except:
        return None

def background_loop():
    while True:
        for b_name, b_list, b_key in [("NIFTY 50", NIFTY_50, "nifty50"), ("NIFTY NEXT 50", NIFTY_NEXT_50, "next50")]:
            temp = []
            for s in b_list:
                item = fetch_single(s, b_name)
                if item:
                    temp.append(item)
                time.sleep(0.3)
            market_store[b_key] = temp
        market_store["updated"] = datetime.now().strftime("%I:%M %p")
        time.sleep(180)

threading.Thread(target=background_loop, daemon=True).start()

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
    <button class="buy-btn" id="bf" onclick="toggleB()">Only BUY (&lt;35)</button>
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
setInterval(sync, 4000);
sync();
</script>
</body>
</html>"""

@app.route('/')
def home():
    return render_template_string(HTML_PAGE)

@app.route('/api')
def api():
    return jsonify(market_store)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
