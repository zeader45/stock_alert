import time
import pandas as pd
import yfinance as yf
import datetime
from yahoo_fin import stock_info as si
import smtplib
from email.message import EmailMessage
import os

# === CONFIG ===
RSI_PERIOD = 14
RSI_UPPER = 80
RSI_LOWER = 20
MIN_MARKET_CAP = 1e9
MAX_TICKERS = None

EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
EMAIL_RECIPIENT = os.getenv("EMAIL_RECIPIENT")

# === Ticker Fetching ===
def fetch_all_tickers():
    print("Fetching tickers...")
    tickers = si.tickers_nasdaq() + si.tickers_other() + si.tickers_dow()
    tickers = list(set(t for t in tickers if t.isalpha()))
    print(f"✅ Retrieved {len(tickers)} tickers.")
    return tickers[:MAX_TICKERS] if MAX_TICKERS else tickers

# === RSI Calculation ===
def calculate_rsi(prices, period=RSI_PERIOD):
    delta = prices.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# === IV Estimate ===
def fetch_iv_estimate(ticker):
    try:
        stock = yf.Ticker(ticker)
        options_dates = stock.options
        if not options_dates:
            return None
        chain = stock.option_chain(options_dates[0])
        calls_iv = chain.calls['impliedVolatility'].mean()
        puts_iv = chain.puts['impliedVolatility'].mean()
        return round((calls_iv + puts_iv) / 2, 4)
    except:
        return None

# === Email Dispatch ===
def send_email_with_csv(filename):
    msg = EmailMessage()
    msg['Subject'] = '📈 RSI Scan Results with Trend & IV'
    msg['From'] = EMAIL_USER
    msg['To'] = EMAIL_RECIPIENT
    msg.set_content('Attached is the latest RSI scan result.')

    with open(filename, 'rb') as f:
        msg.add_attachment(f.read(), maintype='application', subtype='octet-stream', filename=filename)

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(EMAIL_USER, EMAIL_PASS)
            smtp.send_message(msg)
        print(f"📧 Email sent to {EMAIL_RECIPIENT}")
    except Exception as e:
        print(f"⚠️ Email failed: {e}")

# === Main Scanner ===
def scan_stocks_individual(tickers):
    print(f"\n🔍 Scanning {len(tickers)} stocks at {datetime.datetime.now()}...\n")
    matched = []

    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period="200d")
            if df.empty or len(df) < 200:
                continue

            close_prices = df['Close']
            rsi = calculate_rsi(close_prices).iloc[-1]
            price = close_prices.iloc[-1]
            ma50 = close_prices.rolling(50).mean().iloc[-1]
            ma200 = close_prices.rolling(200).mean().iloc[-1]
            trend_pass = False
            signal = None

            # Determine signal with trend confirmation
            if rsi < RSI_LOWER and price > ma200 and price > ma50:
                signal = "Sell Put"
                trend_pass = True
            elif rsi > RSI_UPPER and price < ma200 and price < ma50:
                signal = "Sell Call"
                trend_pass = True
            else:
                signal = "Trend Conflict"

            if not trend_pass:
                continue  # skip mismatches

            market_cap = stock.info.get('marketCap', 0)
            if market_cap < MIN_MARKET_CAP:
                continue

            iv_estimate = fetch_iv_estimate(ticker)

            matched.append({
                "Ticker": ticker,
                "RSI": round(rsi, 2),
                "MA50": round(ma50, 2),
                "MA200": round(ma200, 2),
                "IV Estimate": iv_estimate if iv_estimate else "N/A",
                "Market Cap (B)": round(market_cap / 1e9, 2),
                "Signal": signal
            })

            time.sleep(1)

        except Exception as e:
            print(f"⚠️ Error with {ticker}: {e}")

    if matched:
        df = pd.DataFrame(matched)
        sell_puts = df[df["Signal"] == "Sell Put"].sort_values("RSI").reset_index(drop=True)
        sell_calls = df[df["Signal"] == "Sell Call"].sort_values("RSI", ascending=False).reset_index(drop=True)

        max_len = max(len(sell_puts), len(sell_calls))
        sell_puts = sell_puts.reindex(range(max_len))
        sell_calls = sell_calls.reindex(range(max_len))

        sell_puts = sell_puts[["Ticker", "RSI", "Market Cap (B)", "Signal"]].rename(columns=lambda x: x + " (Put)")
        sell_calls = sell_calls[["Ticker", "RSI", "Market Cap (B)", "Signal"]].rename(columns=lambda x: x + " (Call)")

        spacer = pd.DataFrame({'': [''] * max_len})

        final = pd.concat([sell_puts, spacer, sell_calls], axis=1)

        # Save with consistent header
        output_file = "scan_results_with_iv.csv"
        final.to_csv(output_file, index=False)
        print(f"\n✅ Formatted results saved to {output_file}")
        print(final.dropna(how="all").to_string(index=False))
        send_email_with_csv(output_file)
    else:
        print("No matching stocks found.")

# === Run ===
if __name__ == "__main__":
    tickers = fetch_all_tickers()
    scan_stocks_individual(tickers)
