import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import base64
from io import StringIO

# Streamlit app title and description
st.title("Yahoo Finance to IndexedDB (WASM) Uploader")
st.write("""
Download stock data from Yahoo Finance and store it in the browser's IndexedDB.
The data will persist in the user's browser.
""")

# User inputs
col1, col2 = st.columns(2)
with col1:
    symbol = st.text_input("Stock Symbol", value="AAPL").upper()
with col2:
    days = st.number_input("Days of History", min_value=1, max_value=365*5, value=30)

if st.button("Download and Store Data"):
    try:
        # Calculate date range
        end_date = datetime.today()
        start_date = end_date - timedelta(days=days)
        
        # Download data from Yahoo Finance
        with st.spinner(f"Downloading {symbol} data from Yahoo Finance..."):
            df = yf.download(symbol, start=start_date, end=end_date)
        
        if df.empty:
            st.error("No data found for this symbol/time period")
            st.stop()
        
        # Reset index to make Date a column
        df = df.reset_index()
        df['Date'] = df['Date'].dt.strftime('%Y-%m-%d')
        
        # Display preview
        st.subheader(f"{symbol} Data Preview ({len(df)} records)")
        st.write(df.head())
        
        # Convert DataFrame to JSON
        data_json = df.to_json(orient='records')
        
        # Create JavaScript code to store in IndexedDB
        js_code = f"""
        <script>
        // Initialize IndexedDB
        let db;
        const request = indexedDB.open("StockDatabase", 2);  // Version 2
        
        request.onerror = function(event) {{
            console.log("Database error: " + event.target.errorCode);
        }};
        
        request.onupgradeneeded = function(event) {{
            db = event.target.result;
            // Delete old object store if it exists
            if (db.objectStoreNames.contains("stockData")) {{
                db.deleteObjectStore("stockData");
            }}
            const objectStore = db.createObjectStore("stockData", {{ keyPath: "id", autoIncrement: true }});
            objectStore.createIndex("symbol", "symbol", {{ unique: false }});
            objectStore.createIndex("date", "date", {{ unique: false }});
            console.log("Database setup complete");
        }};
        
        request.onsuccess = function(event) {{
            db = event.target.result;
            console.log("Database opened successfully");
            
            // Clear existing data for this symbol
            const transaction = db.transaction(["stockData"], "readwrite");
            const objectStore = transaction.objectStore("stockData");
            const index = objectStore.index("symbol");
            const clearRequest = index.openCursor(IDBKeyRange.only("{symbol}"));
            
            let recordsToDelete = [];
            clearRequest.onsuccess = function(event) {{
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
                            console.log(`Deleted ${{recordsToDelete.length}} old records for {symbol}`);
                            addNewData();
                        }};
                    }} else {{
                        addNewData();
                    }}
                }}
            }};
            
            function addNewData() {{
                // Add new data
                const data = {data_json};
                const addTransaction = db.transaction(["stockData"], "readwrite");
                const addStore = addTransaction.objectStore("stockData");
                
                data.forEach(item => {{
                    // Add symbol to each record for filtering
                    const record = {{
                        symbol: "{symbol}",
                        date: item.Date,
                        data: item
                    }};
                    addStore.add(record);
                }});
                
                addTransaction.oncomplete = function() {{
                    console.log("All data added successfully");
                    alert(`${{data.length}} {symbol} records stored in IndexedDB successfully!`);
                }};
            }}
        }};
        </script>
        """
        
        # Display success message
        st.success(f"{symbol} data downloaded and processed successfully!")
        
        # Execute the JavaScript
        st.components.v1.html(js_code, height=0)
        
        # Download link for the data (optional)
        csv = df.to_csv(index=False)
        b64 = base64.b64encode(csv.encode()).decode()
        href = f'<a href="data:file/csv;base64,{b64}" download="{symbol}_stock_data.csv">Download {symbol} CSV</a>'
        st.markdown(href, unsafe_allow_html=True)
        
    except Exception as e:
        st.error(f"An error occurred: {str(e)}")

# Add instructions
st.markdown("""
### Instructions:
1. Enter a stock symbol (e.g., AAPL, MSFT, TSLA)
2. Select how many days of historical data you want
3. Click "Download and Store Data"
4. The data will be saved in your browser's IndexedDB

### Notes:
- Data persists in your browser until you clear site data
- You can retrieve this data later from any page on this domain
- Uses Yahoo Finance API via yfinance Python package
""")
