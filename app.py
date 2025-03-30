import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import base64
from io import StringIO
import time
import matplotlib.pyplot as plt

def data_download_page():
    st.title("Stock Data Download to IndexedDB")
    st.write("""
    Download historical stock data for multiple symbols and store in browser's IndexedDB.
    """)

    # Load symbols from CSV
    @st.cache_data
    def load_symbols():
        try:
            symbols_df = pd.read_csv("symbols.csv")
            return [s.strip().upper() for s in symbols_df['Symbol'].unique() if pd.notna(s)]
        except Exception as e:
            st.error(f"Could not load symbols.csv: {str(e)}")
            return []

    symbols = load_symbols()

    # Only proceed if we have symbols
    if not symbols:
        st.stop()

    # UI Elements
    days = st.number_input("Days of History", min_value=1, max_value=365*5, value=30)
    max_retries = 3  # Number of retry attempts for failed downloads

    if st.button("Download All Symbols"):
        if not symbols:
            st.error("No symbols found in symbols.csv")
            st.stop()
        
        # Calculate date range
        end_date = datetime.today()
        start_date = end_date - timedelta(days=days)
        
        # Initialize progress
        progress_bar = st.progress(0)
        status_text = st.empty()
        results = []
        
        # Download each symbol
        for i, symbol in enumerate(symbols):
            try:
                status_text.text(f"Downloading {symbol} ({i+1}/{len(symbols)})...")
                
                # Try downloading with retries
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
                        time.sleep(1)  # Wait before retrying
                
                if df is None or df.empty:
                    results.append({"symbol": symbol, "status": "failed", "message": "No data found after retries"})
                    continue
                
                # Prepare data with correct column order
                df = df.reset_index()
                df['Date'] = df['Date'].dt.strftime('%Y-%m-%d')
                df['Symbol'] = symbol  # Add symbol column
                
                # Reorder columns as: Date, Symbol, Open, High, Low, Close, Volume
                column_order = ['Date', 'Symbol', 'Open', 'High', 'Low', 'Close', 'Volume']
                df = df[column_order]
                
                # Store results (we'll use session state instead of IndexedDB for simplicity)
                results.append({
                    "symbol": symbol,
                    "status": "success",
                    "data": df.to_dict('records'),
                    "records": len(df),
                    "columns": list(df.columns)
                })
                
            except Exception as e:
                results.append({"symbol": symbol, "status": "failed", "message": str(e)})
            
            # Update progress
            progress_bar.progress((i + 1) / len(symbols))
        
        # Store results in session state
        st.session_state.stock_data = results
        st.success(f"Downloaded {sum(1 for r in results if r['status'] == 'success')}/{len(symbols)} symbols successfully!")
        
        # Show summary table
        results_df = pd.DataFrame(results)
        st.subheader("Download Summary")
        st.dataframe(results_df[['symbol', 'status', 'message']])

        # Symbol selection dropdown (after download)
        success_symbols = [r['symbol'] for r in results if r['status'] == 'success']
        if success_symbols:
            selected_symbol = st.selectbox("Select Symbol to Preview", success_symbols)
            
            # Display preview for selected symbol
            selected_data = next(r for r in results if r['symbol'] == selected_symbol and r['status'] == 'success')
            try:
                df = pd.DataFrame(selected_data['data'])
                
                # Set clean column names
                clean_columns = ['Date', 'Symbol', 'Open', 'High', 'Low', 'Close', 'Volume']
                df.columns = clean_columns
                
                # Display without index column
                st.subheader(f"{selected_symbol} Data Preview")
                st.dataframe(df.set_index('Date'))
                
                # Download button with clean CSV (no index)
                csv = df.to_csv(index=False)
                b64 = base64.b64encode(csv.encode()).decode()
                href = f'<a href="data:file/csv;base64,{b64}" download="{selected_symbol}_data.csv">Download {selected_symbol} CSV</a>'
                st.markdown(href, unsafe_allow_html=True)
            except Exception as e:
                st.error(f"Could not display data for {selected_symbol}: {str(e)}")

def backtesting_page():
    st.title("Pair Trading Backtesting")
    
    # Check if we have data
    if 'stock_data' not in st.session_state:
        st.warning("Please download stock data first from the Data Download page")
        return
    
    # Input Section
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
        # Get data from session state
        stock_data = st.session_state.stock_data
        
        # Find the requested stocks
        stock1_data = next((item for item in stock_data if item['symbol'] == stock1 and item['status'] == 'success'), None)
        stock2_data = next((item for item in stock_data if item['symbol'] == stock2 and item['status'] == 'success'), None)
        
        if not stock1_data or not stock2_data:
            st.error("One or both symbols not found in downloaded data")
            return
        
        # Convert to DataFrames
        df1 = pd.DataFrame(stock1_data['data'])
        df2 = pd.DataFrame(stock2_data['data'])
        
        # Convert date strings to datetime and set as index
        df1['Date'] = pd.to_datetime(df1['Date'])
        df2['Date'] = pd.to_datetime(df2['Date'])
        
        df1.set_index('Date', inplace=True)
        df2.set_index('Date', inplace=True)
        
        # Combine into single dataframe
        pairs = pd.DataFrame({
            stock1: df1['Close'],
            stock2: df2['Close']
        }).dropna()
        
        if len(pairs) == 0:
            st.error("No overlapping data found for these symbols")
            return
        
        # Filter by selected date range
        pairs = pairs.loc[start_date:end_date]
        
        if len(pairs) == 0:
            st.error("No data found for selected date range")
            return
        
        # Calculate ratio and z-score
        pairs['Ratio'] = pairs[stock1] / pairs[stock2]
        pairs['Z-Score'] = (pairs['Ratio'] - pairs['Ratio'].rolling(window=lookback).mean()) / pairs['Ratio'].rolling(window=lookback).std()
        
        # Generate signals
        pairs['Position'] = 0
        pairs['Trade'] = None
        current_position = 0
        entry_z = None
        entry_date = None
        
        trade_history = []
        
        for i in range(len(pairs)):
            date = pairs.index[i]
            z_score = pairs.loc[date, 'Z-Score']
            
            # No position - look for entry
            if current_position == 0:
                if z_score > entry_threshold:
                    # Short ratio (sell stock1, buy stock2)
                    pairs.loc[date, 'Position'] = -1
                    current_position = -1
                    entry_z = z_score
                    entry_date = date
                    pairs.loc[date, 'Trade'] = 'Short Ratio'
                    trade_history.append({
                        'Entry Date': date,
                        'Type': 'Short Ratio',
                        'Entry Z-Score': z_score,
                        'Exit Date': None,
                        'Exit Z-Score': None,
                        'Holding Period': None,
                        'PnL': None
                    })
                elif z_score < -entry_threshold:
                    # Long ratio (buy stock1, sell stock2)
                    pairs.loc[date, 'Position'] = 1
                    current_position = 1
                    entry_z = z_score
                    entry_date = date
                    pairs.loc[date, 'Trade'] = 'Long Ratio'
                    trade_history.append({
                        'Entry Date': date,
                        'Type': 'Long Ratio',
                        'Entry Z-Score': z_score,
                        'Exit Date': None,
                        'Exit Z-Score': None,
                        'Holding Period': None,
                        'PnL': None
                    })
            # Existing position - look for exit
            else:
                pairs.loc[date, 'Position'] = current_position
                
                # Check exit conditions
                if (current_position == 1 and z_score >= -exit_threshold) or \
                   (current_position == -1 and z_score <= exit_threshold):
                    
                    # Close position
                    exit_pnl = (entry_z - z_score) * current_position
                    holding_days = (date - entry_date).days
                    
                    # Update trade history
                    for trade in reversed(trade_history):
                        if trade['Exit Date'] is None:
                            trade['Exit Date'] = date
                            trade['Exit Z-Score'] = z_score
                            trade['Holding Period'] = holding_days
                            trade['PnL'] = exit_pnl
                            break
                    
                    current_position = 0
                    entry_z = None
                    entry_date = None
                    pairs.loc[date, 'Trade'] = 'Exit'
        
        # Calculate daily PnL
        pairs['Daily PnL'] = pairs['Position'] * pairs['Z-Score'].diff().shift(-1)
        pairs['Cumulative PnL'] = pairs['Daily PnL'].cumsum().fillna(0)
        
        # Process trade history
        trades_df = pd.DataFrame(trade_history)
        trades_df = trades_df.dropna()
        
        if not trades_df.empty:
            trades_df['PnL %'] = trades_df['PnL'] * 10  # Simplified PnL calculation
            trades_df['Holding Period'] = trades_df['Exit Date'] - trades_df['Entry Date']
            trades_df['Holding Period'] = trades_df['Holding Period'].dt.days
        
        # Display results
        st.header("Ratio and Z-Score Data")
        st.dataframe(pairs[[stock1, stock2, 'Ratio', 'Z-Score']].tail(20))
        
        if not trades_df.empty:
            st.header("Trade History")
            st.dataframe(trades_df)
            
            # Calculate metrics
            total_pnl = trades_df['PnL %'].sum()
            num_trades = len(trades_df)
            win_rate = len(trades_df[trades_df['PnL %'] > 0]) / num_trades
            sharpe_ratio = trades_df['PnL %'].mean() / trades_df['PnL %'].std() * np.sqrt(252)
            
            long_trades = trades_df[trades_df['Type'] == 'Long Ratio']
            short_trades = trades_df[trades_df['Type'] == 'Short Ratio']
            
            long_win_rate = len(long_trades[long_trades['PnL %'] > 0]) / len(long_trades) if len(long_trades) > 0 else 0
            short_win_rate = len(short_trades[short_trades['PnL %'] > 0]) / len(short_trades) if len(short_trades) > 0 else 0
            avg_holding = trades_df['Holding Period'].mean()
            
            # Display metrics
            st.header("Performance Metrics")
            metrics = {
                'Total PnL %': f"{total_pnl:.2f}%",
                'Number of Trades': num_trades,
                'Win Rate': f"{win_rate*100:.1f}%",
                'Sharpe Ratio': f"{sharpe_ratio:.2f}",
                'Long Ratio Win Rate': f"{long_win_rate*100:.1f}%" if len(long_trades) > 0 else "N/A",
                'Short Ratio Win Rate': f"{short_win_rate*100:.1f}%" if len(short_trades) > 0 else "N/A",
                'Average Holding Period': f"{avg_holding:.1f} days"
            }
            st.table(pd.DataFrame.from_dict(metrics, orient='index', columns=['Value']))
            
            # Plot equity curve
            st.header("Equity Curve")
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.plot(pairs.index, pairs['Cumulative PnL'], label='Cumulative PnL')
            ax.set_title("Pair Trading Equity Curve")
            ax.set_xlabel("Date")
            ax.set_ylabel("Cumulative PnL (Z-Score Units)")
            ax.grid(True)
            st.pyplot(fig)
            
            # Plot ratio and z-score
            st.header("Ratio and Z-Score")
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
            
            # Plot ratio
            ax1.plot(pairs.index, pairs['Ratio'], label='Price Ratio', color='blue')
            ax1.set_ylabel("Price Ratio")
            ax1.grid(True)
            
            # Plot z-score with thresholds
            ax2.plot(pairs.index, pairs['Z-Score'], label='Z-Score', color='green')
            ax2.axhline(entry_threshold, color='red', linestyle='--', label='Entry Threshold')
            ax2.axhline(-entry_threshold, color='red', linestyle='--')
            ax2.axhline(exit_threshold, color='orange', linestyle='--', label='Exit Threshold')
            ax2.axhline(-exit_threshold, color='orange', linestyle='--')
            ax2.set_ylabel("Z-Score")
            ax2.set_xlabel("Date")
            ax2.grid(True)
            
            plt.tight_layout()
            st.pyplot(fig)
        else:
            st.warning("No trades were executed with the current parameters")

def main():
    st.sidebar.title("Navigation")
    page = st.sidebar.radio("Go to", ["Data Download", "Backtesting"])
    
    if page == "Data Download":
        data_download_page()
    elif page == "Backtesting":
        backtesting_page()

if __name__ == "__main__":
    main()
