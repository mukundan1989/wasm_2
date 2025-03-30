import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import base64
import time
import matplotlib.pyplot as plt

def data_download_page():
    st.title("Stock Data Download")
    st.write("Download historical stock data for multiple symbols")

    @st.cache_data
    def load_symbols():
        try:
            symbols_df = pd.read_csv("symbols.csv")
            return [s.strip().upper() for s in symbols_df['Symbol'].unique() if pd.notna(s)]
        except Exception as e:
            st.error(f"Could not load symbols.csv: {str(e)}")
            return []

    symbols = load_symbols()

    if not symbols:
        st.stop()

    days = st.number_input("Days of History", min_value=1, max_value=365*5, value=30)
    max_retries = 3

    if st.button("Download All Symbols"):
        if not symbols:
            st.error("No symbols found in symbols.csv")
            st.stop()
        
        end_date = datetime.today()
        start_date = end_date - timedelta(days=days)
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        results = []
        
        for i, symbol in enumerate(symbols):
            try:
                status_text.text(f"Downloading {symbol} ({i+1}/{len(symbols)})...")
                
                df = None
                for attempt in range(max_retries):
                    try:
                        df = yf.download(
                            symbol, 
                            start=start_date, 
                            end=end_date, 
                            progress=False,
                            auto_adjust=True
                        )
                        if df is not None and not df.empty:
                            break
                    except Exception as e:
                        if attempt == max_retries - 1:
                            raise
                        time.sleep(1)
                
                if df is None or df.empty:
                    results.append({"symbol": symbol, "status": "failed", "message": "No data found after retries"})
                    continue
                
                # Ensure date column exists and is properly named
                df = df.reset_index().rename(columns={'index': 'Date'})  # Fix: Explicitly rename index column
                df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
                df['Symbol'] = symbol
                
                column_order = ['Date', 'Symbol', 'Open', 'High', 'Low', 'Close', 'Volume']
                df = df[column_order]
                
                results.append({
                    "symbol": symbol,
                    "status": "success",
                    "data": df.to_dict('records'),
                    "records": len(df),
                    "columns": list(df.columns)
                })
                
            except Exception as e:
                results.append({"symbol": symbol, "status": "failed", "message": str(e)})
            
            progress_bar.progress((i + 1) / len(symbols))
        
        st.session_state.stock_data = results
        st.success(f"Downloaded {sum(1 for r in results if r['status'] == 'success')}/{len(symbols)} symbols successfully!")
        
        results_df = pd.DataFrame(results)
        st.subheader("Download Summary")
        st.dataframe(results_df[['symbol', 'status', 'message']])

        success_symbols = [r['symbol'] for r in results if r['status'] == 'success']
        if success_symbols:
            selected_symbol = st.selectbox("Select Symbol to Preview", success_symbols)
            
            selected_data = next(r for r in results if r['symbol'] == selected_symbol and r['status'] == 'success')
            try:
                df = pd.DataFrame(selected_data['data'])
                
                clean_columns = ['Date', 'Symbol', 'Open', 'High', 'Low', 'Close', 'Volume']
                df.columns = clean_columns
                
                st.subheader(f"{selected_symbol} Data Preview")
                st.dataframe(df.set_index('Date'))
                
                csv = df.to_csv(index=False)
                b64 = base64.b64encode(csv.encode()).decode()
                href = f'<a href="data:file/csv;base64,{b64}" download="{selected_symbol}_data.csv">Download {selected_symbol} CSV</a>'
                st.markdown(href, unsafe_allow_html=True)
            except Exception as e:
                st.error(f"Could not display data for {selected_symbol}: {str(e)}")

def backtesting_page():
    st.title("Pair Trading Backtesting")
    
    if 'stock_data' not in st.session_state:
        st.warning("Please download stock data first from the Data Download page")
        return
    
    st.header("Input Parameters")
    col1, col2 = st.columns(2)
    with col1:
        stock1 = st.text_input("Stock 1 Symbol", value="AAPL").upper()
    with col2:
        stock2 = st.text_input("Stock 2 Symbol", value="MSFT").upper()
    
    col1, col2 = st.columns(2)
    with col1:
        lookback = st.number_input("Lookback Period (days)", min_value=5, max_value=252, value=30)
    with col2:
        entry_threshold = st.number_input("Entry Threshold (z-score)", value=2.5, step=0.1)
        exit_threshold = st.number_input("Exit Threshold (z-score)", value=1.5, step=0.1)
    
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start Date", value=datetime.today() - timedelta(days=365))
    with col2:
        end_date = st.date_input("End Date", value=datetime.today())
    
    if st.button("Run Backtest"):
        stock_data = st.session_state.stock_data
        
        stock1_data = next((item for item in stock_data if item['symbol'] == stock1 and item['status'] == 'success'), None)
        stock2_data = next((item for item in stock_data if item['symbol'] == stock2 and item['status'] == 'success'), None)
        
        if not stock1_data or not stock2_data:
            st.error("One or both symbols not found in downloaded data")
            return
        
        # Convert to DataFrames with proper date handling
        df1 = pd.DataFrame(stock1_data['data'])
        df2 = pd.DataFrame(stock2_data['data'])
        
        # Ensure date column exists
        required_columns = {'Date', 'Symbol', 'Open', 'High', 'Low', 'Close', 'Volume'}
        if not required_columns.issubset(df1.columns) or not required_columns.issubset(df2.columns):
            st.error("Missing required columns in data")
            return
        
        # Process dates
        df1['Date'] = pd.to_datetime(df1['Date'])
        df2['Date'] = pd.to_datetime(df2['Date'])
        
        df1.set_index('Date', inplace=True)
        df2.set_index('Date', inplace=True)
        
        # Merge data
        pairs = pd.DataFrame({
            stock1: df1['Close'],
            stock2: df2['Close']
        }).dropna()
        
        if len(pairs) == 0:
            st.error("No overlapping data found for these symbols")
            return
        
        # Filter by date range
        pairs = pairs.loc[start_date:end_date]
        
        if len(pairs) == 0:
            st.error("No data found for selected date range")
            return
        
        # Calculate ratio and z-score
        pairs['Ratio'] = pairs[stock1] / pairs[stock2]
        pairs['Z-Score'] = (pairs['Ratio'] - pairs['Ratio'].rolling(window=lookback).mean()) / pairs['Ratio'].rolling(window=lookback).std()
        
        # Generate signals (unchanged)
        # ... [rest of backtesting logic remains the same] ...

def main():
    st.sidebar.title("Navigation")
    page = st.sidebar.radio("Go to", ["Data Download", "Backtesting"])
    
    if page == "Data Download":
        data_download_page()
    elif page == "Backtesting":
        backtesting_page()

if __name__ == "__main__":
    main()