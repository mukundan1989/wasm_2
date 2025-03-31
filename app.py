import streamlit as st
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
                    df = yf.download(symbol, start=start_date, end=end_date, progress=False)
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
            // Convert to format Streamlit can display
            const tableData = data.map(item => item.data);
            
            // Send to Streamlit
            window.parent.postMessage({
                isStreamlitMessage: true,
                type: 'previewData',
                symbol: symbol,
                data: tableData
            }, '*');
        } else {
            window.parent.postMessage({
                isStreamlitMessage: true,
                type: 'previewData',
                symbol: symbol,
                data: null
            }, '*');
        }
    });
}

// Listen for symbol selection changes
const selectBox = document.querySelector('select[aria-label="Select symbol to preview"]');
if (selectBox) {
    selectBox.addEventListener('change', (event) => {
        updatePreview(event.target.value);
    });
}
</script>
"""

# Display component for preview
preview_placeholder = st.empty()
st.components.v1.html(preview_js, height=0)

# Handle the preview data
if 'preview_data' not in st.session_state:
    st.session_state.preview_data = None

# Custom component to receive data from JS
html("""
<script>
window.addEventListener('message', (event) => {
    if (event.data.isStreamlitMessage && event.data.type === 'previewData') {
        // This would need a proper Streamlit component to handle
        console.log('Received preview data for:', event.data.symbol);
    }
});
</script>
""", height=0)

# Fallback display using selectbox + button
selected_symbol = st.selectbox("Select symbol to preview", symbols)
if st.button("Show Preview"):
    display_js = f"""
    <script>
    updatePreview('{selected_symbol}');
    </script>
    """
    st.components.v1.html(display_js, height=0)
    
    # Simulate what we would do with proper JS-Python communication
    st.info("In a full implementation, this would show the actual data from IndexedDB")
    
    # For demo purposes, show a sample
    sample_data = {
        'Date': pd.date_range(end=datetime.today(), periods=5).strftime('%Y-%m-%d').tolist(),
        'Open': [150.0, 151.5, 152.3, 153.1, 154.2],
        'High': [151.2, 152.8, 153.5, 154.3, 155.0],
        'Low': [149.8, 150.5, 151.8, 152.5, 153.8],
        'Close': [151.0, 152.3, 153.0, 153.8, 154.5],
        'Volume': [1000000, 1200000, 950000, 1100000, 1050000]
    }
    st.dataframe(pd.DataFrame(sample_data))

# Instructions
st.sidebar.markdown("""
### How to Use:
1. Set days of history
2. Click "Download All Symbols"
3. Select symbol from dropdown
4. Click "Show Preview"

### Implementation Notes:
- Data stored in browser's IndexedDB
- Full implementation requires custom Streamlit component
- Currently shows sample data for demonstration
""")
