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

# Load symbols from CSV with robust error handling
@st.cache_data
def load_symbols():
    try:
        symbols_df = pd.read_csv("symbols.csv")
        valid_symbols = [str(s).strip().upper() for s in symbols_df['Symbol'].unique() if pd.notna(s)]
        return valid_symbols
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
    
    # Download each symbol with comprehensive error handling
    for i, symbol in enumerate(symbols):
        try:
            status_text.text(f"Downloading {symbol} ({i+1}/{len(symbols)})...")
            
            # Try downloading with retries
            df = None
            last_error = None
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
                    last_error = str(e)
                    if attempt == max_retries - 1:
                        raise
                    time.sleep(1)  # Wait before retrying
            
            if df is None or df.empty:
                results.append({
                    "symbol": symbol, 
                    "status": "failed", 
                    "message": last_error if last_error else "No data found after retries"
                })
                continue
            
            # Prepare data with validation
            try:
                df = df.reset_index()
                df['Date'] = df['Date'].dt.strftime('%Y-%m-%d')
                df['Symbol'] = symbol  # Add symbol column to dataframe
                
                # Validate we have required columns
                required_columns = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
                missing_cols = [col for col in required_columns if col not in df.columns]
                if missing_cols:
                    raise ValueError(f"Missing required columns: {missing_cols}")
                
                # Store results with all necessary metadata
                results.append({
                    "symbol": symbol,
                    "status": "success",
                    "records": len(df),
                    "start_date": df['Date'].min(),
                    "end_date": df['Date'].max(),
                    "columns": list(df.columns)
                })
                
            except Exception as e:
                results.append({
                    "symbol": symbol, 
                    "status": "failed", 
                    "message": f"Data processing error: {str(e)}"
                })
            
        except Exception as e:
            results.append({
                "symbol": symbol, 
                "status": "failed", 
                "message": str(e)
            })
        
        # Update progress
        progress_bar.progress((i + 1) / len(symbols))
    
    # Generate JavaScript code for storage
    success_count = sum(1 for r in results if r['status'] == 'success')
    
    # Prepare results display with guaranteed columns
    display_cols = ['symbol', 'status']
    results_df = pd.DataFrame(results)
    
    # Ensure 'message' column exists
    if 'message' not in results_df.columns:
        results_df['message'] = ''
    
    # Select only columns that exist
    available_cols = [col for col in display_cols + ['message'] if col in results_df.columns]
    
    # Display results
    st.success(f"Downloaded {success_count}/{len(symbols)} symbols successfully!")
    st.subheader("Download Summary")
    st.dataframe(results_df[available_cols])
    
    # Generate and execute JavaScript only for successful downloads
    success_symbols = [r['symbol'] for r in results if r['status'] == 'success']
    if success_symbols:
        js_code = f"""
        <script>
        // Initialize IndexedDB
        let db;
        const request = indexedDB.open("StockDatabase", 5);  // Version 5
        
        request.onerror = function(event) {{
            console.log("Database error: " + event.target.errorCode);
        }};
        
        request.onupgradeneeded = function(event) {{
            db = event.target.result;
            if (!db.objectStoreNames.contains("stockData")) {{
                const objectStore = db.createObjectStore("stockData", {{ 
                    keyPath: ["symbol", "date"] 
                }});
                objectStore.createIndex("by_symbol", "symbol");
                objectStore.createIndex("by_date", "date");
                objectStore.createIndex("by_symbol_date", ["symbol", "date"]);
                console.log("Database setup complete");
            }}
        }};
        
        request.onsuccess = function(event) {{
            db = event.target.result;
            console.log("Database opened successfully");
            
            // Process successful symbols
            const symbols = {json.dumps(success_symbols)};
            let processedCount = 0;
            
            function processNext(index) {{
                if (index >= symbols.length) {{
                    // All done
                    alert(`Processed ${{symbols.length}} symbols successfully!`);
                    return;
                }}
                
                const symbol = symbols[index];
                fetchAndStoreData(symbol, index);
            }}
            
            function fetchAndStoreData(symbol, index) {{
                const url = `https://query1.finance.yahoo.com/v7/finance/download/${{symbol}}?period1=${{Math.floor((new Date('{start_date.strftime('%Y-%m-%d')}')).getTime()/1000)}}&period2=${{Math.floor((new Date('{end_date.strftime('%Y-%m-%d')}')).getTime()/1000)}}&interval=1d&events=history`;
                
                fetch(url)
                    .then(response => {{
                        if (!response.ok) throw new Error(`HTTP error! status: ${{response.status}}`);
                        return response.text();
                    }})
                    .then(csvData => {{
                        // Parse CSV data
                        const lines = csvData.split('\\n');
                        if (lines.length < 2) throw new Error("No data in CSV");
                        
                        const headers = lines[0].split(',');
                        const records = [];
                        
                        for (let i = 1; i < lines.length; i++) {{
                            if (lines[i].trim() === '') continue;
                            const values = lines[i].split(',');
                            if (values.length !== headers.length) continue;
                            
                            const record = {{}};
                            for (let j = 0; j < headers.length; j++) {{
                                record[headers[j]] = values[j];
                            }}
                            record['Symbol'] = symbol;
                            records.push(record);
                        }}
                        
                        if (records.length === 0) throw new Error("No valid records found");
                        
                        // Store in IndexedDB
                        const tx = db.transaction(["stockData"], "readwrite");
                        const store = tx.objectStore("stockData");
                        
                        records.forEach(record => {{
                            store.put({{
                                symbol: symbol,
                                date: record.Date,
                                data: record
                            }});
                        }});
                        
                        tx.oncomplete = () => {{
                            processedCount++;
                            console.log(`Stored ${{records.length}} records for ${{symbol}}`);
                            processNext(index + 1);
                        }};
                        
                        tx.onerror = (event) => {{
                            console.error("Transaction error:", event.target.error);
                            processNext(index + 1);
                        }};
                    }})
                    .catch(error => {{
                        console.error(`Error processing ${{symbol}}:`, error);
                        processNext(index + 1);
                    }});
            }}
            
            // Start processing
            processNext(0);
        }};
        </script>
        """
        
        st.components.v1.html(js_code, height=0)

# JavaScript code to fetch data from IndexedDB for preview
query_js = """
<script>
function getSymbolData(symbol, callback) {
    const request = indexedDB.open("StockDatabase", 5);
    
    request.onerror = function(event) {
        console.log("Database error:", event.target.error);
        callback([]);
    };
    
    request.onsuccess = function(event) {
        const db = event.target.result;
        const tx = db.transaction(["stockData"], "readonly");
        const store = tx.objectStore("stockData");
        const index = store.index("by_symbol_date");
        const range = IDBKeyRange.bound(
            [symbol, ""],
            [symbol, "\uffff"]
        );
        
        const request = index.getAll(range);
        
        request.onerror = function(event) {
            console.log("Query error:", event.target.error);
            callback([]);
        };
        
        request.onsuccess = function(event) {
            const data = event.target.result.map(item => item.data);
            callback(data);
        };
    };
}
</script>
"""

# Display the query JavaScript
st.components.v1.html(query_js, height=0)

# Symbol selection and preview
if 'results' in locals():
    success_symbols = [r['symbol'] for r in results if r['status'] == 'success']
else:
    # Fallback to all symbols if no recent download
    success_symbols = symbols

if success_symbols:
    selected_symbol = st.selectbox("Select Symbol to Preview", success_symbols)
    
    # JavaScript to fetch and display data
    display_js = f"""
    <script>
    getSymbolData("{selected_symbol}", function(data) {{
        if (data && data.length > 0) {{
            // Create a preview table
            const table = document.createElement('table');
            table.style.width = '100%';
            table.style.borderCollapse = 'collapse';
            
            // Add header
            const thead = document.createElement('thead');
            const headerRow = document.createElement('tr');
            Object.keys(data[0]).forEach(key => {{
                const th = document.createElement('th');
                th.textContent = key;
                th.style.border = '1px solid #ddd';
                th.style.padding = '8px';
                headerRow.appendChild(th);
            }});
            thead.appendChild(headerRow);
            table.appendChild(thead);
            
            // Add data rows (limit to 10 for preview)
            const tbody = document.createElement('tbody');
            data.slice(0, 10).forEach(item => {{
                const row = document.createElement('tr');
                Object.values(item).forEach(val => {{
                    const td = document.createElement('td');
                    td.textContent = val;
                    td.style.border = '1px solid #ddd';
                    td.style.padding = '8px';
                    row.appendChild(td);
                }});
                tbody.appendChild(row);
            }});
            table.appendChild(tbody);
            
            // Display in Streamlit
            const container = document.createElement('div');
            container.appendChild(table);
            document.body.appendChild(container);
        }} else {{
            console.log("No data found for {selected_symbol}");
        }}
    }});
    </script>
    """
    
    st.components.v1.html(display_js, height=300)

# Instructions
st.sidebar.markdown("""
### Instructions:
1. Ensure `symbols.csv` exists with a "Symbol" column
2. Set the number of days of history needed
3. Click "Download All Symbols"
4. Select a symbol to preview data from IndexedDB

### Error Handling:
- Automatic retries for failed downloads
- Comprehensive error logging
- Graceful handling of missing data
""")
