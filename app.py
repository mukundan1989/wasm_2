import streamlit as st
from streamlit.components.v1 import html  # This was missing
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import json
import time

# Streamlit app configuration
st.set_page_config(layout="wide")
st.title("Stock Data Manager with IndexedDB")
st.write("Download, store, and preview stock data in your browser's IndexedDB")

# Load symbols from CSV
@st.cache_data
def load_symbols():
    try:
        symbols_df = pd.read_csv("symbols.csv")
        return [str(s).strip().upper() for s in symbols_df['Symbol'].unique() if pd.notna(s)]
    except Exception as e:
        st.error(f"Error loading symbols.csv: {str(e)}")
        return []

symbols = load_symbols()

if not symbols:
    st.stop()

# Main UI
days = st.number_input("Days of History", min_value=1, max_value=365*5, value=30)

if st.button("Download All Symbols"):
    if not symbols:
        st.error("No symbols found")
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
            for attempt in range(3):
                try:
                    df = yf.download(
                        symbol, 
                        start=start_date, 
                        end=end_date, 
                        progress=False,
                        auto_adjust=True  # Explicitly set to handle yfinance changes
                    )
                    if df is not None and not df.empty:
                        break
                except Exception as e:
                    if attempt == 2:
                        raise
                    time.sleep(1)
            
            if df is None or df.empty:
                results.append({"symbol": symbol, "status": "failed", "message": "No data"})
                continue
            
            df = df.reset_index()
            df['Date'] = df['Date'].dt.strftime('%Y-%m-%d')
            df['Symbol'] = symbol
            
            results.append({
                "symbol": symbol,
                "status": "success",
                "records": len(df),
                "start_date": df['Date'].min(),
                "end_date": df['Date'].max()
            })
            
            # JavaScript to store data
            js_store = f"""
            <script>
            async function store{symbol}Data() {{
                const db = await new Promise((resolve, reject) => {{
                    const request = indexedDB.open("StockDB", 1);
                    request.onerror = () => reject(request.error);
                    request.onsuccess = () => resolve(request.result);
                    request.onupgradeneeded = (event) => {{
                        const db = event.target.result;
                        if (!db.objectStoreNames.contains('stocks')) {{
                            const store = db.createObjectStore('stocks', {{ keyPath: ['symbol', 'date'] }});
                            store.createIndex('by_symbol', 'symbol');
                            store.createIndex('by_date', 'date');
                        }}
                    }};
                }});
                
                const tx = db.transaction('stocks', 'readwrite');
                const store = tx.objectStore('stocks');
                
                const data = {df.to_dict('records')};
                
                // Clear old data first
                const clearReq = store.index('by_symbol').openCursor(IDBKeyRange.only('{symbol}'));
                clearReq.onsuccess = (event) => {{
                    const cursor = event.target.result;
                    if (cursor) {{
                        store.delete(cursor.primaryKey);
                        cursor.continue();
                    }} else {{
                        // Add new data
                        data.forEach(item => {{
                            store.put({{
                                symbol: '{symbol}',
                                date: item.Date,
                                data: item
                            }});
                        }});
                    }}
                }};
                
                await new Promise((resolve) => {{
                    tx.oncomplete = resolve;
                    tx.onerror = (event) => {{
                        console.error('Transaction error:', event.target.error);
                        resolve();
                    }};
                }});
            }}
            
            store{symbol}Data();
            </script>
            """
            st.components.v1.html(js_store, height=0)
            
        except Exception as e:
            results.append({"symbol": symbol, "status": "failed", "message": str(e)})
        
        progress_bar.progress((i + 1) / len(symbols))
    
    st.success(f"Processed {len(symbols)} symbols")
    st.dataframe(pd.DataFrame(results))

# Preview Section
st.header("Data Preview")

# JavaScript to fetch and display data
preview_js = """
<script>
async function getSymbolData(symbol) {
    try {
        const db = await new Promise((resolve, reject) => {
            const request = indexedDB.open("StockDB", 1);
            request.onerror = () => reject(request.error);
            request.onsuccess = () => resolve(request.result);
        });
        
        const tx = db.transaction('stocks', 'readonly');
        const store = tx.objectStore('stocks');
        const index = store.index('by_symbol');
        
        return new Promise((resolve) => {
            const request = index.getAll(IDBKeyRange.only(symbol));
            request.onsuccess = () => resolve(request.result);
            request.onerror = (event) => {
                console.error("Query error:", event.target.error);
                resolve([]);
            };
        });
    } catch (error) {
        console.error("Database error:", error);
        return [];
    }
}

function updatePreview(symbol) {
    getSymbolData(symbol).then(data => {
        if (data && data.length > 0) {
            // Create HTML table for preview
            const table = document.createElement('table');
            table.style.width = '100%';
            table.style.borderCollapse = 'collapse';
            table.style.margin = '10px 0';
            
            // Add header
            const thead = document.createElement('thead');
            const headerRow = document.createElement('tr');
            Object.keys(data[0].data).forEach(key => {
                const th = document.createElement('th');
                th.textContent = key;
                th.style.border = '1px solid #ddd';
                th.style.padding = '8px';
                th.style.textAlign = 'left';
                headerRow.appendChild(th);
            });
            thead.appendChild(headerRow);
            table.appendChild(thead);
            
            // Add data rows (limit to 10)
            const tbody = document.createElement('tbody');
            data.slice(0, 10).forEach(item => {
                const row = document.createElement('tr');
                Object.values(item.data).forEach(val => {
                    const td = document.createElement('td');
                    td.textContent = val;
                    td.style.border = '1px solid #ddd';
                    td.style.padding = '8px';
                    row.appendChild(td);
                });
                tbody.appendChild(row);
            });
            table.appendChild(tbody);
            
            // Display in Streamlit
            const container = document.getElementById('preview-container');
            if (container) {
                container.innerHTML = '';
                container.appendChild(table);
            }
        } else {
            const container = document.getElementById('preview-container');
            if (container) {
                container.innerHTML = '<p>No data found for this symbol</p>';
            }
        }
    });
}

// Initialize on load
document.addEventListener('DOMContentLoaded', () => {
    const selectBox = document.querySelector('select[aria-label="Select symbol to preview"]');
    if (selectBox) {
        selectBox.addEventListener('change', (event) => {
            updatePreview(event.target.value);
        });
        
        // Trigger initial update
        updatePreview(selectBox.value);
    }
});
</script>
"""

# Create container for preview
html("<div id='preview-container'></div>")
st.components.v1.html(preview_js, height=0)

# Fallback display using selectbox
selected_symbol = st.selectbox("Select symbol to preview", symbols, key='symbol_preview')

# Instructions
st.sidebar.markdown("""
### How to Use:
1. Set days of history
2. Click "Download All Symbols"
3. Select symbol from dropdown
4. View data in preview section

### Key Features:
- Data stored in browser's IndexedDB
- Persistent storage between sessions
- Fast client-side processing
""")
