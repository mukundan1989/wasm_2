import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import base64
from io import StringIO
import time

# Streamlit app configuration
st.set_page_config(layout="wide")
st.title("Batch Stock Data Download to IndexedDB")
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
            
            # Convert to JSON safely
            try:
                data_json = df.to_json(orient='records', date_format='iso')
            except Exception as e:
                results.append({"symbol": symbol, "status": "failed", "message": f"JSON conversion error: {str(e)}"})
                continue
            
            # Store results for JavaScript
            results.append({
                "symbol": symbol,
                "status": "success",
                "data": data_json,
                "records": len(df),
                "columns": list(df.columns)
            })
            
        except Exception as e:
            results.append({"symbol": symbol, "status": "failed", "message": str(e)})
        
        # Update progress
        progress_bar.progress((i + 1) / len(symbols))
    
    # Generate JavaScript code
    success_count = sum(1 for r in results if r['status'] == 'success')
    js_code = f"""
    <script>
    // Initialize IndexedDB
    let db;
    const request = indexedDB.open("StockDatabase", 3);  // Version 3
    
    request.onerror = function(event) {{
        console.log("Database error: " + event.target.errorCode);
    }};
    
    request.onupgradeneeded = function(event) {{
        db = event.target.result;
        if (!db.objectStoreNames.contains("stockData")) {{
            const objectStore = db.createObjectStore("stockData", {{ keyPath: "id", autoIncrement: true }});
            objectStore.createIndex("symbol", "symbol", {{ unique: false }});
            objectStore.createIndex("date", "date", {{ unique: false }});
            console.log("Database setup complete");
        }}
    }};
    
    request.onsuccess = function(event) {{
        db = event.target.result;
        console.log("Database opened successfully");
        
        // Process results
        const results = {results};
        let totalAdded = 0;
        
        function processNext(index) {{
            if (index >= results.length) {{
                // All done
                alert(`Processed ${{results.length}} symbols. Success: ${{success_count}}, Failed: ${{results.length - success_count}}`);
                return;
            }}
            
            const result = results[index];
            if (result.status !== 'success') {{
                console.log(`Skipping ${{result.symbol}}: ${{result.message}}`);
                processNext(index + 1);
                return;
            }}
            
            // Clear existing data for this symbol
            const transaction = db.transaction(["stockData"], "readwrite");
            const objectStore = transaction.objectStore("stockData");
            const indexReq = objectStore.index("symbol").openCursor(IDBKeyRange.only(result.symbol));
            
            let recordsToDelete = [];
            indexReq.onsuccess = function(event) {{
                const cursor = event.target.result;
                if (cursor) {{
                    recordsToDelete.push(cursor.value.id);
                    cursor.continue();
                }} else {{
                    // Delete all matching records
                    if (recordsToDelete.length > 0) {{
                        const deleteTransaction = db.transaction(["stockData"], "readwrite");
                        const deleteStore = deleteTransaction.objectStore("stockData");
                        
                        recordsToDelete.forEach(id => {{
                            deleteStore.delete(id);
                        }});
                        
                        deleteTransaction.oncomplete = function() {{
                            console.log(`Deleted ${{recordsToDelete.length}} old records for ${{result.symbol}}`);
                            addNewData(result, index);
                        }};
                    }} else {{
                        addNewData(result, index);
                    }}
                }}
            }};
        }}
        
        function addNewData(result, index) {{
            // Add new data
            try {{
                const data = JSON.parse(result.data);
                const addTransaction = db.transaction(["stockData"], "readwrite");
                const addStore = addTransaction.objectStore("stockData");
                
                data.forEach(item => {{
                    const record = {{
                        symbol: result.symbol,
                        date: item.Date,
                        data: item
                    }};
                    addStore.add(record);
                }});
                
                addTransaction.oncomplete = function() {{
                    console.log(`Added ${{data.length}} records for ${{result.symbol}}`);
                    totalAdded += data.length;
                    processNext(index + 1);
                }};
            }} catch(e) {{
                console.error(`Error processing ${{result.symbol}}:`, e);
                processNext(index + 1);
            }}
        }}
        
        // Start processing
        processNext(0);
    }};
    </script>
    """
    
    # Display results
    st.success(f"Downloaded {success_count}/{len(symbols)} symbols successfully!")
    
    # Show summary table
    results_df = pd.DataFrame(results)
    st.subheader("Download Summary")
    st.dataframe(results_df[['symbol', 'status', 'message']])
    
    # Execute JavaScript
    st.components.v1.html(js_code, height=0)

    # Symbol selection dropdown (after download)
    success_symbols = [r['symbol'] for r in results if r['status'] == 'success']
    if success_symbols:
        selected_symbol = st.selectbox("Select Symbol to Preview", success_symbols)
        
        # Display preview for selected symbol
        selected_data = next(r for r in results if r['symbol'] == selected_symbol and r['status'] == 'success')
        try:
            df = pd.read_json(StringIO(selected_data['data']))
            
            # Set clean column names
            clean_columns = ['Date', 'Symbol', 'Open', 'High', 'Low', 'Close', 'Volume']
            df.columns = clean_columns
            
            # Display without index column
            st.subheader(f"{selected_symbol} Data Preview")
            st.dataframe(df.set_index('Date'))  # Using Date as index to remove the numbered index column
            
            # Download button with clean CSV (no index)
            csv = df.to_csv(index=False)
            b64 = base64.b64encode(csv.encode()).decode()
            href = f'<a href="data:file/csv;base64,{b64}" download="{selected_symbol}_data.csv">Download {selected_symbol} CSV</a>'
            st.markdown(href, unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Could not display data for {selected_symbol}: {str(e)}")

# Instructions
st.sidebar.markdown("""
### Instructions:
1. Ensure `symbols.csv` exists with a "Symbol" column
2. Set the number of days of history needed
3. Click "Download All Symbols"
4. View results and select a symbol to preview

### Notes:
- Data is stored in your browser's IndexedDB
- Columns are ordered as: Date, Symbol, Open, High, Low, Close, Volume
- The preview table shows dates as row labels (no numbered index column)
- CSV downloads contain clean column headers without index
""")
