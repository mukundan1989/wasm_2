import streamlit as st
import pandas as pd
import streamlit.components.v1 as components
import os

# Load symbols from symbols.csv
def load_symbols():
    if os.path.exists("symbols.csv"):
        df = pd.read_csv("symbols.csv")
        return df["Symbol"].tolist()
    return []

# UI Title
st.title("Stock Data Storage & Retrieval using IndexedDB")

# Load symbols
symbols = load_symbols()

# Select symbol to store data
symbol = st.selectbox("Select a stock symbol to store data", [""] + symbols)

# Text area for pasting CSV data
data = st.text_area("Paste CSV Data (Date,Open,High,Low,Close,Volume):")

# Store Data Button
if st.button("Store Data in IndexedDB"):
    if symbol and data:
        # Convert CSV text to JavaScript format
        data_list = [
            {"date": row.split(",")[0], "data": {
                "Open": row.split(",")[1],
                "High": row.split(",")[2],
                "Low": row.split(",")[3],
                "Close": row.split(",")[4],
                "Volume": row.split(",")[5]
            }} for row in data.split("\n") if row
        ]

        # JavaScript to Store in IndexedDB
        js_code = f"""
        <script>
        function storeInIndexedDB(symbol, data) {{
            let request = indexedDB.open("StockDatabase", 1);
            request.onupgradeneeded = function(event) {{
                let db = event.target.result;
                if (!db.objectStoreNames.contains("stockData")) {{
                    let store = db.createObjectStore("stockData", {{ keyPath: "date" }});
                    store.createIndex("symbol", "symbol", {{ unique: false }});
                }}
            }};
            request.onsuccess = function(event) {{
                let db = event.target.result;
                let transaction = db.transaction(["stockData"], "readwrite");
                let store = transaction.objectStore("stockData");

                // Delete existing data for this symbol
                let index = store.index("symbol");
                let range = IDBKeyRange.only(symbol);
                let cursorRequest = index.openCursor(range);
                cursorRequest.onsuccess = function(event) {{
                    let cursor = event.target.result;
                    if (cursor) {{
                        store.delete(cursor.primaryKey);
                        cursor.continue();
                    }}
                }};

                // Insert new data
                data.forEach(row => {{
                    store.put({{ date: row.date, symbol: symbol, data: row.data }});
                }});

                alert("Data successfully stored for " + symbol);
            }};
        }}
        storeInIndexedDB("{symbol}", {data_list});
        </script>
        """
        components.html(js_code, height=0)
        st.success(f"Data stored in IndexedDB for {symbol}")

# Select symbol to retrieve data
selected_symbol = st.selectbox("Select a stock symbol to retrieve data", [""] + symbols)

# JavaScript to Retrieve Data from IndexedDB
js_fetch_code = f"""
<script>
function fetchFromIndexedDB(symbol) {{
    let request = indexedDB.open("StockDatabase", 1);
    request.onsuccess = function(event) {{
        let db = event.target.result;
        let transaction = db.transaction(["stockData"], "readonly");
        let objectStore = transaction.objectStore("stockData");
        let index = objectStore.index("symbol");
        let range = IDBKeyRange.only(symbol);
        let cursorRequest = index.openCursor(range);

        let data = [];
        cursorRequest.onsuccess = function(event) {{
            let cursor = event.target.result;
            if (cursor) {{
                data.push(cursor.value);
                cursor.continue();
            }} else {{
                window.parent.postMessage({{ type: "indexeddb_data", symbol: symbol, data: data }}, "*");
            }}
        }};
    }};
}}

window.addEventListener("message", function(event) {{
    if (event.data.type === "request_data") {{
        fetchFromIndexedDB(event.data.symbol);
    }}
}});

if ("{selected_symbol}") {{
    window.parent.postMessage({{ type: "request_data", symbol: "{selected_symbol}" }}, "*");
}}

window.addEventListener("message", function(event) {{
    if (event.data.type === "indexeddb_data" && event.data.symbol === "{selected_symbol}") {{
        let data = event.data.data;
        console.log("Received data:", data);

        let csvContent = "data:text/csv;charset=utf-8," + "Date,Open,High,Low,Close,Volume\\n";
        data.forEach(row => {{
            csvContent += `${{row.date}},${{row.data.Open}},${{row.data.High}},${{row.data.Low}},${{row.data.Close}},${{row.data.Volume}}\\n`;
        }});

        let encodedUri = encodeURI(csvContent);
        let downloadLink = document.getElementById("download_link");
        downloadLink.href = encodedUri;
        downloadLink.style.display = "block";
    }}
}});
</script>

<a id="download_link" style="display: none;" download="{selected_symbol}_data.csv">Download CSV</a>
"""

components.html(js_fetch_code, height=0)
