import sqlite3
import pandas as pd
from prophet import Prophet
from datetime import datetime
from routes.database import DB_NAME

def get_combined_sales_data():
    # Combine data from both sales_order_items and order_items tables
    conn = sqlite3.connect(DB_NAME)

    # Get sales data from the sales_order_items table
    sales_order_items_query = '''
        SELECT order_date, product_name, quantity
        FROM sales_order_items
    '''
    sales_order_items_df = pd.read_sql_query(sales_order_items_query, conn)

    # Get sales data from the order_items table
    order_items_query = '''
        SELECT product_name, quantity
        FROM order_items
    '''
    order_items_df = pd.read_sql_query(order_items_query, conn)

    conn.close()

    # Combine both sales dataframes
    df = pd.concat([sales_order_items_df, order_items_df], ignore_index=True)

    # Format and aggregate data
    df['order_date'] = pd.to_datetime(df['order_date'])
    df = df.groupby(['order_date', 'product_name'])['quantity'].sum().reset_index()

    return df

def forecast_sales(product_name, periods=7):
    # Use the combined sales data instead of just the sales_order_items
    df = get_combined_sales_data()
    df = df[df['product_name'] == product_name]

    if df.empty or df.shape[0] < 2:
        print(f"[WARNING] Not enough sales data for '{product_name}'")
        return []

    df = df.rename(columns={'order_date': 'ds', 'quantity': 'y'})
    df = df.dropna(subset=['ds', 'y'])

    model = Prophet(daily_seasonality=True)
    model.fit(df)

    future = model.make_future_dataframe(periods=periods)
    forecast = model.predict(future)

    return forecast[['ds', 'yhat']].tail(periods).round(0).to_dict(orient='records')


def get_combined_inventory_data():
    # Combine data from both the suppliers table and the product_quantity_changes table
    conn = sqlite3.connect(DB_NAME)

    # Get supplier-related inventory changes
    supplier_query = '''
        SELECT entered_date AS change_date, products , quantity, 'Increase' AS change_type
        FROM suppliers
    '''
    supplier_df = pd.read_sql_query(supplier_query, conn)

    # Get quantity change data from the product_quantity_changes table
    quantity_changes_query = '''
        SELECT change_date, product_name, quantity_changed, change_type
        FROM product_quantity_changes
    '''
    quantity_changes_df = pd.read_sql_query(quantity_changes_query, conn)

    conn.close()

    # Combine both dataframes
    df = pd.concat([supplier_df, quantity_changes_df], ignore_index=True)

    # Process the data (add net_change column, aggregate, etc.)
    df['change_date'] = pd.to_datetime(df['change_date'])
    df['net_change'] = df.apply(
        lambda row: row['quantity'] if row['change_type'] == 'Increase' else row['quantity_changed'] if row['change_type'] == 'Increase' else -row['quantity_changed'],
        axis=1
    )
    df = df.groupby(['change_date', 'product_name'])['net_change'].sum().reset_index()
    return df

def forecast_inventory(product_name, periods=7):
    # Use the combined inventory data instead of just the product_quantity_changes
    df = get_combined_inventory_data()
    df = df[df['product_name'] == product_name]

    if df.empty or df.shape[0] < 2:
        print(f"[WARNING] Not enough inventory data for '{product_name}'")
        return []

    df = df.rename(columns={'change_date': 'ds', 'net_change': 'y'})
    df = df.dropna(subset=['ds', 'y'])

    model = Prophet(daily_seasonality=True)
    model.fit(df)

    future = model.make_future_dataframe(periods=periods)
    forecast = model.predict(future)

    return forecast[['ds', 'yhat']].tail(periods).round(0).to_dict(orient='records')


def notification_exists(title, message, status):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM notifications 
            WHERE title = ? AND message = ? AND status = ?
        ''', (title, message, status))
        return cursor.fetchone()[0] > 0

def insert_notification(title, message, status):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO notifications (title, message, status)
            VALUES (?, ?, ?)
        ''', (title, message, status))
        conn.commit()
        
def check_and_notify_all(sales_threshold=100, inventory_threshold=100):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Get all unique product names from both sales and inventory tables
    cursor.execute("""
        SELECT DISTINCT product_name FROM sales_order_items
        UNION
        SELECT DISTINCT product_name FROM order_items
        UNION
        SELECT DISTINCT product_name FROM product_quantity_changes
        UNION
        SELECT DISTINCT products AS product_name FROM suppliers
    """)
    products = [row[0] for row in cursor.fetchall()]
    conn.close()

    for product in products:
        # === Sales Forecast Check ===
        forecasted_sales = forecast_sales(product)
        if forecasted_sales:
            min_sales = min([day['yhat'] for day in forecasted_sales])
            if min_sales < sales_threshold:
                title = "Low Sales Forecast Alert"
                message = f"Sales for '{product}' may drop below {sales_threshold} units."
                status = "Urgent"
                if not notification_exists(title, message, status):
                    insert_notification(title, message, status)

        # === Inventory Forecast Check ===
        forecasted_inventory = forecast_inventory(product)
        if forecasted_inventory:
            min_inventory = min([day['yhat'] for day in forecasted_inventory])
            if min_inventory < inventory_threshold:
                title = "Low Inventory Forecast Alert"
                message = f"Inventory for '{product}' may drop below {inventory_threshold} units."
                status = "Warning"
                if not notification_exists(title, message, status):
                    insert_notification(title, message, status)
