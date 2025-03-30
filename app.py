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

# Initialize session state
if 'available_symbols' not in st.session_state:
    st.session_state.available_symbols = []
if 'comparison_data' not in st.session_state:
    st.session_state.comparison_data = None

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
    
    # Store downloaded symbols in session state
    downloaded_symbols = [r['symbol'] for r in results if r['status'] == 'success']
    st.session_state.available_symbols = list(set(st.session_state.available_symbols + downloaded_symbols))
    
    # Generate JavaScript code
    success_count = len(downloaded_symbols)
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
                console.log("All data processed");
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
    
    # Show summary table with error handling
    try:
        results_df = pd.DataFrame(results)
        if not results_df.empty:
            # Ensure required columns exist
            available_columns = []
            for col in ['symbol', 'status', 'message']:
                if col in results_df.columns:
                    available_columns.append(col)
            
            if available_columns:
                st.subheader("Download Summary")
                st.dataframe(results_df[available_columns])
            else:
                st.warning("No summary data available")
        else:
            st.warning("No results to display")
    except Exception as e:
        st.error(f"Error displaying results: {str(e)}")
    
    # Execute JavaScript
    st.components.v1.html(js_code, height=0)

# Get initial list of available symbols from IndexedDB
if not st.session_state.available_symbols:
    get_symbols_js = """
    <script>
    function getStoredSymbols(callback) {
        const request = indexedDB.open("StockDatabase", 3);
        
        request.onsuccess = function(event) {
            const db = event.target.result;
            const transaction = db.transaction(["stockData"], "readonly");
            const objectStore = transaction.objectStore("stockData");
            const index = objectStore.index("symbol");
            const request = index.getAllKeys();
            
            request.onsuccess = function() {
                const symbols = [...new Set(request.result)]; // Get unique symbols
                callback(symbols);
            };
        };
    }

    // Get symbols and send to Streamlit
    getStoredSymbols(function(symbols) {
        window.parent.postMessage({
            isStreamlitMessage: true,
            type: 'session',
            data: {
                key: 'available_symbols',
                value: symbols
            }
        }, '*');
    });
    </script>
    """
    st.components.v1.html(get_symbols_js, height=0)

# Comparison Section
st.subheader("Stock Comparison Tool")

# Create two columns for the dropdowns
col1, col2 = st.columns(2)

with col1:
    stock1 = st.selectbox(
        "Select First Stock",
        options=st.session_state.available_symbols,
        index=0 if st.session_state.available_symbols else None,
        key="stock1"
    )

with col2:
    stock2 = st.selectbox(
        "Select Second Stock",
        options=st.session_state.available_symbols,
        index=1 if len(st.session_state.available_symbols) > 1 else 0 if st.session_state.available_symbols else None,
        key="stock2"
    )

# JavaScript to retrieve comparison data
if stock1 and stock2 and stock1 != stock2:
    compare_js = f"""
    <script>
    function getStockData(symbol, callback) {{
        const request = indexedDB.open("StockDatabase", 3);
        
        request.onerror = function(event) {{
            console.error("Database error:", event.target.error);
            callback([]);
        }};
        
        request.onsuccess = function(event) {{
            const db = event.target.result;
            const transaction = db.transaction(["stockData"], "readonly");
            const objectStore = transaction.objectStore("stockData");
            const index = objectStore.index("symbol");
            const request = index.getAll(IDBKeyRange.only(symbol));
            
            request.onerror = function(event) {{
                console.error("Error retrieving data:", event.target.error);
                callback([]);
            }};
            
            request.onsuccess = function() {{
                const data = request.result.map(item => ({{
                    date: item.date,
                    close: item.data.Close
                }}));
                callback(data);
            }};
        }};
    }}
    
    // Get data for both stocks
    getStockData("{stock1}", function(stock1Data) {{
        console.log("Retrieved data for", "{stock1}", stock1Data);
        getStockData("{stock2}", function(stock2Data) {{
            console.log("Retrieved data for", "{stock2}", stock2Data);
            
            // Combine data by date
            const combined = [];
            
            // Create maps for quick lookup
            const stock1Map = new Map();
            stock1Data.forEach(item => {{
                stock1Map.set(item.date, item.close);
            }});
            
            const stock2Map = new Map();
            stock2Data.forEach(item => {{
                stock2Map.set(item.date, item.close);
            }});
            
            // Get all unique dates
            const allDates = [...new Set([...stock1Data.map(d => d.date), ...stock2Data.map(d => d.date)])];
            
            // Combine data for matching dates
            allDates.forEach(date => {{
                const stock1Close = stock1Map.get(date);
                const stock2Close = stock2Map.get(date);
                
                if (stock1Close !== undefined && stock2Close !== undefined) {{
                    combined.push({{
                        date: date,
                        "{stock1}": stock1Close,
                        "{stock2}": stock2Close
                    }});
                }}
            }});
            
            console.log("Combined data:", combined);
            
            // Send to Streamlit
            window.parent.postMessage({{
                isStreamlitMessage: true,
                type: 'session',
                data: {{
                    key: 'comparison_data',
                    value: {{
                        stock1: "{stock1}",
                        stock2: "{stock2}",
                        comparison: combined
                    }}
                }}
            }}, '*');
        }});
    }});
    </script>
    """
    
    st.components.v1.html(compare_js, height=0)
    
    # Display comparison results
    if st.session_state.comparison_data:
        comparison_data = st.session_state.comparison_data
        if comparison_data['stock1'] == stock1 and comparison_data['stock2'] == stock2:
            try:
                df = pd.DataFrame(comparison_data['comparison'])
                if not df.empty:
                    st.subheader(f"Comparison: {stock1} vs {stock2}")
                    
                    # Convert date strings to datetime for proper sorting
                    df['date'] = pd.to_datetime(df['date'])
                    df = df.sort_values('date')
                    
                    # Format for display
                    display_df = df.set_index('date')
                    display_df.index = display_df.index.strftime('%Y-%m-%d')
                    
                    st.dataframe(display_df)
                    
                    # Add line chart visualization
                    st.line_chart(df.set_index('date'))
                else:
                    st.warning("No matching dates found for comparison")
            except Exception as e:
                st.error(f"Error displaying comparison data: {str(e)}")
    else:
        st.info("Retrieving comparison data...")

# JavaScript message handler
message_handler_js = """
<script>
window.addEventListener('message', function(event) {
    if (event.data.isStreamlitMessage && event.data.type === 'session') {
        const data = event.data.data;
        if (data.key === 'available_symbols') {
            window.parent.postMessage({
                isStreamlitMessage: true,
                type: 'session',
                data: {
                    key: 'available_symbols',
                    value: data.value
                }
            }, '*');
        }
        else if (data.key === 'comparison_data') {
            window.parent.postMessage({
                isStreamlitMessage: true,
                type: 'session',
                data: {
                    key: 'comparison_data',
                    value: data.value
                }
            }, '*');
        }
    }
});
</script>
"""

# Add the message handler
st.components.v1.html(message_handler_js, height=0)

# Handle messages from JavaScript
if st.session_state.get('_components', {}).get('message', {}).get('data'):
    message_data = st.session_state['_components']['message']['data']
    if message_data.get('key') == 'available_symbols':
        st.session_state.available_symbols = message_data.get('value', [])
    elif message_data.get('key') == 'comparison_data':
        st.session_state.comparison_data = message_data.get('value')

# Instructions
st.sidebar.markdown("""
### Instructions:
1. Ensure `symbols.csv` exists with a "Symbol" column
2. Set the number of days of history needed
3. Click "Download All Symbols"
4. View results and select a symbol to preview
5. Use the Comparison Tool to compare two stocks

### Notes:
- Data is stored in your browser's IndexedDB
- Columns are ordered as: Date, Symbol, Open, High, Low, Close, Volume
- The preview table shows dates as row labels
- CSV downloads contain clean column headers
- Comparison tool shows side-by-side closing prices
""")
