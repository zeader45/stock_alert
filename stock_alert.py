import time
import pandas as pd
import yfinance as yf
import datetime
import io
import requests
import smtplib
from email.message import EmailMessage
import os

# === CONFIG ===
RSI_PERIOD = 14
RSI_UPPER = 85
RSI_LOWER = 15
MIN_MARKET_CAP = 5e9
MAX_TICKERS = None

# EMAIL_USER and EMAIL_PASS must be set as environment variables
# For EMAIL_PASS, use a generated App Password for security.
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
EMAIL_RECIPIENT = os.getenv("EMAIL_RECIPIENT")


# === Ticker Fetching ===
def fetch_all_tickers():
    """
    Fetches all tickers from Nasdaq, NYSE, and AMEX using reliable public CSV files.
    This method is more robust than web scraping with libraries that may get blocked.
    """
    print("Fetching all tickers from Nasdaq, NYSE, and AMEX...")

    ticker_sources = {
        "Nasdaq": "https://datahub.io/core/nasdaq-listings/_r/-/data/nasdaq-listed.csv",
        "NYSE": "https://raw.githubusercontent.com/datasets/nyse-other-listings/main/data/nyse-listed.csv"
    }

    all_tickers = []

    for exchange, url in ticker_sources.items():
        try:
            response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
            response.raise_for_status()
            csv_data = io.StringIO(response.text)
            df = pd.read_csv(csv_data)
            tickers = df['ACT Symbol'].tolist() if 'ACT Symbol' in df.columns else df['Symbol'].tolist()
            all_tickers.extend(tickers)
            print(f"Retrieved {len(tickers)} tickers from {exchange}.")
        except requests.exceptions.RequestException as e:
            print(f"Failed to fetch tickers from {exchange}: {e}")

    # Remove duplicates and sort, ensuring each element is a string before checking isalpha()
    unique_tickers = sorted(list(set(t for t in all_tickers if isinstance(t, str) and t.isalpha())))

    print(f"\nTotal unique tickers retrieved: {len(unique_tickers)}")

    return unique_tickers[:MAX_TICKERS] if MAX_TICKERS else unique_tickers


# === RSI Calculation ===
def calculate_rsi(prices, period=RSI_PERIOD):
    """
    Calculates the Relative Strength Index (RSI) for a given series of prices.
    RSI is a momentum indicator that measures the speed and change of price movements.
    """
    delta = prices.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()

    # Avoid division by zero
    rs = gain / loss.replace(0, 1e-10)

    return 100 - (100 / (1 + rs))


def send_email_with_csv(filename, sender_email, sender_password, recipient_email):
    """
    Sends an email with a CSV file attached.
    """
    if not all([sender_email, sender_password, recipient_email]):
        print("Email credentials or recipient not configured. Skipping email.")
        return

    msg = EmailMessage()
    msg['Subject'] = 'RSI Scan Results'
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg.set_content('Attached is the latest RSI scan result.')

    # Attach the file
    try:
        with open(filename, 'rb') as f:
            file_data = f.read()
            msg.add_attachment(file_data, maintype='application', subtype='octet-stream', filename=filename)

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(sender_email, sender_password)
            smtp.send_message(msg)
        print(f"Email sent to {recipient_email}")
    except Exception as e:
        print(f"Email failed: {e}")


# === Main Scanner ===
def scan_stocks(tickers):
    """
    Scans a list of stock tickers for overbought or oversold RSI conditions.
    Filters by minimum market capitalization.
    """
    print(f"\nScanning {len(tickers)} stocks at {datetime.datetime.now()}...\n")
    matched = []

    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)

            # Fetch historical data for the last 30 days
            df = stock.history(period="30d")
            if df.empty or len(df) < RSI_PERIOD + 1:
                # Need at least RSI_PERIOD + 1 data points for the calculation
                continue

            close_prices = df['Close']
            rsi = calculate_rsi(close_prices).iloc[-1]

            # Fetch market cap from stock info
            info = stock.info
            market_cap = info.get('marketCap', 0)

            # Filter stocks based on market cap and RSI conditions
            if market_cap >= MIN_MARKET_CAP and (rsi > RSI_UPPER or rsi < RSI_LOWER):
                matched.append({
                    "Ticker": ticker,
                    "RSI": round(rsi, 2),
                    "Market Cap (B)": round(market_cap / 1e9, 2)
                })

            # Add a small delay to avoid overwhelming the server
            time.sleep(.5)

        except Exception as e:
            print(f"Error with {ticker}: {e}")

    # Process and format the results
    if matched:
        df = pd.DataFrame(matched)
        df['Type'] = df['RSI'].apply(lambda x: 'Oversold' if x < RSI_LOWER else 'Overbought')

        oversold = df[df["Type"] == "Oversold"].sort_values("RSI").reset_index(drop=True)
        overbought = df[df["Type"] == "Overbought"].sort_values("RSI", ascending=False).reset_index(drop=True)

        # Pad the DataFrames to have the same length for a clean combined output
        max_len = max(len(oversold), len(overbought))
        oversold = oversold.reindex(range(max_len))
        overbought = overbought.reindex(range(max_len))

        # Combine results into a single, clean table
        final = pd.concat([
            oversold,
            pd.DataFrame({'': [''] * max_len}),
            overbought
        ], axis=1)

        output_file = "scan_results_clean.csv"
        final.to_csv(output_file, index=False)
        print(f"\nFormatted results saved to {output_file}")
        print("\n" + final.dropna(how="all").to_string(index=False))

        # Send email with the results
        send_email_with_csv(
            filename=output_file,
            sender_email=EMAIL_USER,
            sender_password=EMAIL_PASS,
            recipient_email=EMAIL_RECIPIENT
        )

    else:
        print("No matching stocks found based on the criteria.")


# === Run ===
if __name__ == "__main__":
    tickers = fetch_all_tickers()
    scan_stocks(tickers)
