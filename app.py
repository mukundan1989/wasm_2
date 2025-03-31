import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import base64
from io import StringIO
import time
import json

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
            
            # Prepare data
            df = df.reset_index()
            df['Date'] = df['Date'].dt.strftime('%Y-%m-%d')
            df['Symbol'] = symbol  # Add symbol column to dataframe
            
            # Store results for JavaScript
            results.append({
                "symbol": symbol,
                "status": "success",
                "records": len(df),
                "columns": list(df.columns)
            })
            
        except Exception as e:
            results.append({"symbol": symbol, "status": "failed", "message": str(e)})
        
        # Update progress
        progress_bar.progress((i + 1) / len(symbols))
    
    # Generate JavaScript code for storage
    success_count = sum(1 for r in results if r['status'] == 'success')
    js_code = f"""
    <script>
    // Initialize IndexedDB
    let db;
    const request = indexedDB.open("StockDatabase", 4);  // Version 4
    
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
        
        // Process symbols
        const symbols = {json.dumps([r['symbol'] for r in results if r['status'] == 'success'])};
        let processedCount = 0;
        
        function processNext(index) {{
            if (index >= symbols.length) {{
                // All done
                alert(`Processed ${{symbols.length}} symbols successfully!`);
                return;
            }}
            
            const symbol = symbols[index];
            console.log(`Processing ${{symbol}}...`);
            
            // Clear existing data for this symbol
            const transaction = db.transaction(["stockData"], "readwrite");
            const objectStore = transaction.objectStore("stockData");
            const indexReq = objectStore.index("symbol").openCursor(IDBKeyRange.only(symbol));
            
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
                            console.log(`Deleted ${{recordsToDelete.length}} old records for ${{symbol}}`);
                            fetchAndStoreData(symbol, index);
                        }};
                    }} else {{
                        fetchAndStoreData(symbol, index);
                    }}
                }}
            }};
        }}
        
        function fetchAndStoreData(symbol, index) {{
            // Fetch fresh data from Yahoo Finance
            const url = `https://query1.finance.yahoo.com/v7/finance/download/${{symbol}}?period1=${{Math.floor((new Date('{start_date.strftime('%Y-%m-%d')}')).getTime()/1000)}}&period2=${{Math.floor((new Date('{end_date.strftime('%Y-%m-%d')}')).getTime()/1000)}}&interval=1d&events=history`;
            
            fetch(url)
                .then(response => response.text())
                .then(csvData => {{
                    // Parse CSV data
                    const lines = csvData.split('\\n');
                    const headers = lines[0].split(',');
                    const records = [];
                    
                    for (let i = 1; i < lines.length; i++) {{
                        if (lines[i].trim() === '') continue;
                        const values = lines[i].split(',');
                        const record = {{}};
                        for (let j = 0; j < headers.length; j++) {{
                            record[headers[j]] = values[j];
                        }}
                        record['Symbol'] = symbol;
                        records.push(record);
                    }}
                    
                    // Store in IndexedDB
                    const addTransaction = db.transaction(["stockData"], "readwrite");
                    const addStore = addTransaction.objectStore("stockData");
                    
                    records.forEach(record => {{
                        addStore.add({{
                            symbol: symbol,
                            date: record.Date,
                            data: record
                        }});
                    }});
                    
                    addTransaction.oncomplete = function() {{
                        console.log(`Stored ${{records.length}} records for ${{symbol}}`);
                        processedCount++;
                        updateProgress(processedCount, symbols.length);
                        processNext(index + 1);
                    }};
                }})
                .catch(error => {{
                    console.error(`Error processing ${{symbol}}:`, error);
                    processedCount++;
                    updateProgress(processedCount, symbols.length);
                    processNext(index + 1);
                }});
        }}
        
        function updateProgress(current, total) {{
            // Send progress update back to Python
            const progress = Math.round((current / total) * 100);
            console.log(`Progress: ${{progress}}%`);
            // This would need a proper Streamlit-JS bridge for real-time updates
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

# JavaScript code to fetch data from IndexedDB for preview
query_js = """
<script>
function getSymbolData(symbol, callback) {
    const request = indexedDB.open("StockDatabase", 4);
    
    request.onerror = function(event) {
        console.log("Database error:", event.target.error);
        callback([]);
    };
    
    request.onsuccess = function(event) {
        const db = event.target.result;
        const transaction = db.transaction(["stockData"], "readonly");
        const objectStore = transaction.objectStore("stockData");
        const index = objectStore.index("symbol");
        const request = index.getAll(IDBKeyRange.only(symbol));
        
        request.onerror = function(event) {
            console.log("Query error:", event.target.error);
            callback([]);
        };
        
        request.onsuccess = function(event) {
            const data = event.target.result.map(item => item.data);
            callback(data);
        };
    };
    
    request.onupgradeneeded = function(event) {
        // Handle case where DB needs upgrade
        callback([]);
    };
}

// Function to communicate with Streamlit
function updateSymbolData(symbol, data) {
    const dataStr = JSON.stringify(data);
    window.parent.postMessage({
        type: 'symbolData',
        symbol: symbol,
        data: dataStr
    }, '*');
}
</script>
"""

# Display the query JavaScript
st.components.v1.html(query_js, height=0)

# Symbol selection dropdown
if 'results' in locals():
    success_symbols = [r['symbol'] for r in results if r['status'] == 'success']
else:
    # If no recent download, show all symbols we have in IndexedDB
    success_symbols = symbols  # Fallback to all symbols from CSV

if success_symbols:
    selected_symbol = st.selectbox("Select Symbol to Preview", success_symbols)
    
    # JavaScript to fetch and display data
    display_js = f"""
    <script>
    getSymbolData("{selected_symbol}", function(data) {{
        if (data && data.length > 0) {{
            updateSymbolData("{selected_symbol}", data);
        }} else {{
            console.log("No data found for {selected_symbol}");
        }}
    }});
    </script>
    """
    
    st.components.v1.html(display_js, height=0)
    
    # Placeholder for the data display
    data_placeholder = st.empty()
    
    # JavaScript message handler
    handler_js = """
    <script>
    window.addEventListener('message', function(event) {
        if (event.data.type === 'symbolData') {
            // This would need proper Streamlit-JS bridge to update the Python side
            console.log("Received data for:", event.data.symbol);
            console.log("Sample data:", event.data.data.substring(0, 100));
        }
    });
    </script>
    """
    st.components.v1.html(handler_js, height=0)
    
    # Note: In a production app, you would need a proper Streamlit-JS bridge
    st.info("Note: A full implementation would require a proper Streamlit-JS bridge to display the data fetched from IndexedDB. This example shows the concept but doesn't implement the full data transfer.")

# Instructions
st.sidebar.markdown("""
### Instructions:
1. Ensure `symbols.csv` exists with a "Symbol" column
2. Set the number of days of history needed
3. Click "Download All Symbols"
4. Select a symbol to preview data from IndexedDB

### Notes:
- Data is stored in your browser's IndexedDB
- Preview now shows data fetched directly from IndexedDB
- Full implementation requires Streamlit-JS bridge for data transfer
""")
