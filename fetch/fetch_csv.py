import yfinance as yf
import pandas as pd
import yaml
import os

def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def fetch_and_save(symbol):
    df = yf.download(symbol, period="2y")
    df = df.reset_index()[["Date", "Close"]]
    
    os.makedirs("../data/processed", exist_ok=True)
    df.to_csv(f"../data/processed/{symbol}.csv", index=False)

def main():
    config = load_config("../config/tickers.yaml")
    
    for t in config["tickers"]:
        fetch_and_save(t["symbol"])

if __name__ == "__main__":
    main()