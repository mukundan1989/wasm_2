import streamlit as st
import pandas as pd
import base64
from io import StringIO

# Streamlit app title and description
st.title("CSV to IndexedDB (WASM) Uploader")
st.write("""
Upload a CSV file to store it in the browser's IndexedDB using WebAssembly.
The data will persist in the user's browser.
""")

# File upload section
uploaded_file = st.file_uploader("Choose a CSV file", type="csv")

if uploaded_file is not None:
    try:
        # Read the CSV file
        df = pd.read_csv(uploaded_file)
        
        # Display preview
        st.subheader("Data Preview")
        st.write(df.head())
        
        # Convert DataFrame to JSON
        data_json = df.to_json(orient='records')
        
        # Create JavaScript code to store in IndexedDB
        js_code = f"""
        <script>
        // Initialize IndexedDB
        let db;
        const request = indexedDB.open("CSVDatabase", 1);
        
        request.onerror = function(event) {{
            console.log("Database error: " + event.target.errorCode);
        }};
        
        request.onupgradeneeded = function(event) {{
            db = event.target.result;
            const objectStore = db.createObjectStore("csvData", {{ keyPath: "id", autoIncrement: true }});
            objectStore.createIndex("data", "data", {{ unique: false }});
            console.log("Database setup complete");
        }};
        
        request.onsuccess = function(event) {{
            db = event.target.result;
            console.log("Database opened successfully");
            
            // Clear existing data
            const transaction = db.transaction(["csvData"], "readwrite");
            const objectStore = transaction.objectStore("csvData");
            const clearRequest = objectStore.clear();
            
            clearRequest.onsuccess = function() {{
                console.log("Old data cleared");
                
                // Add new data
                const data = {data_json};
                const addTransaction = db.transaction(["csvData"], "readwrite");
                const addStore = addTransaction.objectStore("csvData");
                
                data.forEach(item => {{
                    addStore.add({{data: item}});
                }});
                
                addTransaction.oncomplete = function() {{
                    console.log("All data added successfully");
                    alert("Data stored in IndexedDB successfully! Total records: " + data.length);
                }};
            }};
        }};
        </script>
        """
        
        # Display success message
        st.success("CSV file processed successfully!")
        
        # Execute the JavaScript
        st.components.v1.html(js_code, height=0)
        
        # Download link for the data (optional)
        csv = df.to_csv(index=False)
        b64 = base64.b64encode(csv.encode()).decode()
        href = f'<a href="data:file/csv;base64,{b64}" download="processed_data.csv">Download Processed CSV</a>'
        st.markdown(href, unsafe_allow_html=True)
        
    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
