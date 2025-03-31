import streamlit as st
import pandas as pd
import base64

# Streamlit app title and description
st.title("IndexedDB Stock Data Reader")
st.write("""
This app reads stock data previously stored in your browser's IndexedDB
and displays it for analysis.
""")

# User input for symbol
symbol = st.text_input("Stock Symbol", value="AAPL").upper()

# Create a button to trigger the data retrieval
if st.button("Retrieve Data"):
    # JavaScript to read from IndexedDB and display the data
    js_code = f"""
    <script>
    // Function to read data from IndexedDB
    async function readFromIndexedDB() {{
        return new Promise((resolve, reject) => {{
            const request = indexedDB.open("StockDatabase", 2);
            
            request.onerror = function(event) {{
                reject("Database error: " + event.target.errorCode);
            }};
            
            request.onsuccess = function(event) {{
                const db = event.target.result;
                
                if (!db.objectStoreNames.contains("stockData")) {{
                    reject("No stock data store found");
                    return;
                }}
                
                const transaction = db.transaction(["stockData"], "readonly");
                const objectStore = transaction.objectStore("stockData");
                const index = objectStore.index("symbol");
                const request = index.getAll(IDBKeyRange.only("{symbol}"));
                
                request.onsuccess = function(event) {{
                    const records = event.target.result;
                    if (records.length > 0) {{
                        // Extract the data from each record
                        const stockData = records.map(record => record.data);
                        resolve(stockData);
                    }} else {{
                        reject(`No data found for symbol {symbol}`);
                    }}
                }};
                
                request.onerror = function(event) {{
                    reject("Error reading data: " + event.target.errorCode);
                }};
            }};
        }});
    }}

    // Function to convert data to CSV
    function convertToCSV(objArray) {{
        const array = typeof objArray != 'object' ? JSON.parse(objArray) : objArray;
        let str = '';
        
        // Add headers
        const headers = Object.keys(array[0]);
        str += headers.join(',') + '\\r\\n';
        
        // Add rows
        for (let i = 0; i < array.length; i++) {{
            let line = '';
            for (let index in headers) {{
                if (line != '') line += ',';
                let value = array[i][headers[index]];
                if (typeof value === 'string') {{
                    // Escape quotes and wrap in quotes
                    value = '"' + value.replace(/"/g, '""') + '"';
                }}
                line += value;
            }}
            str += line + '\\r\\n';
        }}
        return str;
    }}

    // Function to create a download link
    function createDownloadLink(data, filename) {{
        const csvData = convertToCSV(data);
        const blob = new Blob([csvData], {{ type: 'text/csv;charset=utf-8;' }});
        const url = URL.createObjectURL(blob);
        
        const link = document.createElement('a');
        link.href = url;
        link.setAttribute('download', filename);
        link.innerHTML = 'Download Data as CSV';
        link.className = 'download-link';
        link.style.display = 'block';
        link.style.margin = '10px 0';
        link.style.padding = '10px';
        link.style.backgroundColor = '#4CAF50';
        link.style.color = 'white';
        link.style.textAlign = 'center';
        link.style.textDecoration = 'none';
        link.style.borderRadius = '4px';
        
        return link;
    }}

    // Function to create a table from the data
    function createTable(data) {{
        if (!data || data.length === 0) return null;
        
        const table = document.createElement('table');
        table.className = 'data-table';
        table.style.width = '100%';
        table.style.borderCollapse = 'collapse';
        table.style.marginTop = '20px';
        table.style.marginBottom = '20px';
        
        // Create header row
        const thead = document.createElement('thead');
        const headerRow = document.createElement('tr');
        
        const headers = Object.keys(data[0]);
        headers.forEach(header => {{
            const th = document.createElement('th');
            th.textContent = header;
            th.style.padding = '8px';
            th.style.backgroundColor = '#f2f2f2';
            th.style.borderBottom = '1px solid #ddd';
            th.style.textAlign = 'left';
            headerRow.appendChild(th);
        }});
        
        thead.appendChild(headerRow);
        table.appendChild(thead);
        
        // Create table body
        const tbody = document.createElement('tbody');
        
        // Sort data by Date if available (newest first)
        if (data[0].Date) {{
            data.sort((a, b) => {{
                return new Date(b.Date) - new Date(a.Date);
            }});
        }}
        
        // Add data rows
        data.forEach((row, index) => {{
            const tr = document.createElement('tr');
            tr.style.backgroundColor = index % 2 === 0 ? '#f9f9f9' : 'white';
            
            headers.forEach(header => {{
                const td = document.createElement('td');
                td.textContent = row[header];
                td.style.padding = '8px';
                td.style.borderBottom = '1px solid #ddd';
                tr.appendChild(td);
            }});
            
            tbody.appendChild(tr);
        }});
        
        table.appendChild(tbody);
        return table;
    }}

    // Function to create a simple chart
    function createChart(data) {{
        if (!data || data.length === 0 || !data[0].Date || !data[0].Close) return null;
        
        // Sort data by date (oldest first for charting)
        const sortedData = [...data].sort((a, b) => new Date(a.Date) - new Date(b.Date));
        
        const chartContainer = document.createElement('div');
        chartContainer.style.width = '100%';
        chartContainer.style.height = '400px';
        chartContainer.style.marginTop = '20px';
        chartContainer.style.marginBottom = '20px';
        
        // Create canvas for chart
        const canvas = document.createElement('canvas');
        canvas.id = 'priceChart';
        canvas.style.width = '100%';
        canvas.style.height = '100%';
        
        chartContainer.appendChild(canvas);
        
        // Add Chart.js script if not already loaded
        if (!window.Chart) {{
            const script = document.createElement('script');
            script.src = 'https://cdn.jsdelivr.net/npm/chart.js';
            script.onload = () => drawChart(sortedData, canvas);
            document.head.appendChild(script);
        }} else {{
            drawChart(sortedData, canvas);
        }}
        
        return chartContainer;
    }}

    function drawChart(data, canvas) {{
        const ctx = canvas.getContext('2d');
        
        // Extract dates and closing prices
        const dates = data.map(item => item.Date);
        const prices = data.map(item => item.Close);
        
        new Chart(ctx, {{
            type: 'line',
            data: {{
                labels: dates,
                datasets: [{{
                    label: '{symbol} Closing Price',
                    data: prices,
                    borderColor: 'rgb(75, 192, 192)',
                    tension: 0.1,
                    fill: false
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    x: {{
                        title: {{
                            display: true,
                            text: 'Date'
                        }}
                    }},
                    y: {{
                        title: {{
                            display: true,
                            text: 'Price'
                        }}
                    }}
                }}
            }}
        }});
    }}

    // Function to create summary statistics
    function createSummaryStats(data) {{
        if (!data || data.length === 0) return null;
        
        const stats = document.createElement('div');
        stats.className = 'summary-stats';
        stats.style.marginTop = '20px';
        stats.style.marginBottom = '20px';
        stats.style.padding = '15px';
        stats.style.backgroundColor = '#f9f9f9';
        stats.style.borderRadius = '4px';
        
        const heading = document.createElement('h3');
        heading.textContent = 'Summary Statistics';
        heading.style.marginTop = '0';
        stats.appendChild(heading);
        
        // Calculate statistics for numeric columns
        const numericColumns = ['Open', 'High', 'Low', 'Close', 'Volume'];
        
        numericColumns.forEach(column => {{
            if (data[0][column] !== undefined) {{
                const values = data.map(row => parseFloat(row[column]));
                const min = Math.min(...values).toFixed(2);
                const max = Math.max(...values).toFixed(2);
                const avg = (values.reduce((a, b) => a + b, 0) / values.length).toFixed(2);
                
                const statRow = document.createElement('p');
                statRow.innerHTML = `<strong>${{column}}:</strong> Min: ${{min}} | Max: ${{max}} | Avg: ${{avg}}`;
                stats.appendChild(statRow);
            }}
        }});
        
        return stats;
    }}

    // Main function to display data
    async function displayData() {{
        const resultDiv = document.getElementById('indexeddb-result');
        resultDiv.innerHTML = '<p>Loading data from IndexedDB...</p>';
        
        try {{
            const data = await readFromIndexedDB();
            
            // Clear previous content
            resultDiv.innerHTML = '';
            
            // Add success message
            const successMsg = document.createElement('div');
            successMsg.style.padding = '10px';
            successMsg.style.backgroundColor = '#dff0d8';
            successMsg.style.color = '#3c763d';
            successMsg.style.borderRadius = '4px';
            successMsg.style.marginBottom = '20px';
            successMsg.innerHTML = `<strong>Success!</strong> Found ${{data.length}} records for ${{'{symbol}'}}.`;
            resultDiv.appendChild(successMsg);
            
            // Add summary statistics
            const statsElement = createSummaryStats(data);
            if (statsElement) resultDiv.appendChild(statsElement);
            
            // Add chart
            const chartElement = createChart(data);
            if (chartElement) resultDiv.appendChild(chartElement);
            
            // Add download link
            const downloadLink = createDownloadLink(data, `${{'{symbol}'}}_stock_data.csv`);
            resultDiv.appendChild(downloadLink);
            
            // Add table
            const tableElement = createTable(data);
            if (tableElement) resultDiv.appendChild(tableElement);
            
        }} catch (error) {{
            resultDiv.innerHTML = `<div style="padding: 10px; background-color: #f2dede; color: #a94442; border-radius: 4px;"><strong>Error:</strong> ${{error}}</div>`;
        }}
    }}

    // Execute the display function
    displayData();
    </script>

    <div id="indexeddb-result" style="margin-top: 20px;"></div>
    """
    
    # Display the JavaScript
    st.components.v1.html(js_code, height=800)
    
    # Add instructions for using the downloaded CSV
    st.markdown("""
    ### Using the Downloaded Data in Python
    
    Once you've downloaded the CSV file, you can load it in Python with:
    
    \`\`\`python
    import pandas as pd
    
    # Replace with your downloaded file path
    df = pd.read_csv('downloaded_stock_data.csv')
    
    # Now you can analyze the data with pandas
    print(df.describe())
    \`\`\`
    """)

# Add instructions
st.markdown("""
### Instructions:
1. Enter the stock symbol you previously stored in IndexedDB
2. Click "Retrieve Data" to fetch and display the data
3. The app will show statistics, a chart, and a table of your data
4. You can download the data as CSV for further analysis in Python

### Notes:
- This app reads from your browser's IndexedDB
- It can only access data that was previously stored by the uploader app
- The data remains in your browser until you clear site data
""")