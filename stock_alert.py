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
MAX_TICKERS = 1000

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


def send_email_with_csv(filename, sender_email, sender_password, recipient_email):
    msg = EmailMessage()
    msg['Subject'] = '📈 RSI Scan Results'
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg.set_content('Attached is the latest RSI scan result.')

    # Attach the file
    with open(filename, 'rb') as f:
        file_data = f.read()
        msg.add_attachment(file_data, maintype='application', subtype='octet-stream', filename=filename)

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(sender_email, sender_password)
            smtp.send_message(msg)
        print(f"📧 Email sent to {recipient_email}")
    except Exception as e:
        print(f"⚠️ Email failed: {e}")


# === Main Scanner ===
def scan_stocks_individual(tickers):
    print(f"\n🔍 Scanning {len(tickers)} stocks at {datetime.datetime.now()}...\n")
    matched = []

    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)

            # Fetch historical data
            df = stock.history(period="30d")
            if df.empty or len(df) < RSI_PERIOD:
                continue

            close_prices = df['Close']
            rsi = calculate_rsi(close_prices).iloc[-1]

            # Fetch market cap
            info = stock.info
            market_cap = info.get('marketCap', 0)

            # Filter matches
            if market_cap >= MIN_MARKET_CAP and (rsi > RSI_UPPER or rsi < RSI_LOWER):
                matched.append({
                    "Ticker": ticker,
                    "RSI": round(rsi, 2),
                    "Market Cap (B)": round(market_cap / 1e9, 2)
                })
            time.sleep(1.5)

        except Exception as e:
            print(f"⚠️ Error with {ticker}: {e}")

    # Output results
    df = pd.DataFrame(matched)
    if not df.empty:
        output_file = "scan_results.csv"
        df.to_csv(output_file, index=False)
        print(f"\n✅ Matching stocks saved to {output_file}")

        # Send email
        send_email_with_csv(
            filename=output_file,
            sender_email="zeader2012@gmail.com",
            sender_password="mdej uriw yhiv huhc",
            recipient_email="zeader2012@gmail.com"
        )
        # df.to_csv("scan_results_individual.csv", index=False)
        # print("\n✅ Matching stocks saved to scan_results_individual.csv")
        # print(df.to_string(index=False))
    else:
        print("No matching stocks found.")

# === Run ===
if __name__ == "__main__":
    tickers = fetch_all_tickers()
    scan_stocks_individual(tickers)



