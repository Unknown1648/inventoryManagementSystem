import pandas as pd
from prophet import Prophet
from datetime import datetime, timedelta
from routes.database import get_db_engine
from sqlalchemy import text

def get_combined_sales_data():
    engine = get_db_engine()

    # Get sales data from sales_order_items
    sales_order_items_query = '''
        SELECT order_date, product_name, quantity
        FROM sales_order_items
    '''
    sales_order_items_df = pd.read_sql_query(sales_order_items_query, engine)

    # Get sales data from order_items
    order_items_query = '''
        SELECT CURRENT_DATE AS order_date, product_name, quantity
        FROM order_items
    '''
    order_items_df = pd.read_sql_query(order_items_query, engine)

    # Combine
    df = pd.concat([sales_order_items_df, order_items_df], ignore_index=True)

    df['order_date'] = pd.to_datetime(df['order_date'])
    df = df.groupby(['order_date', 'product_name'])['quantity'].sum().reset_index()

    return df

def forecast_sales(product_name, periods=7):
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
    engine = get_db_engine()

    # Supplier inventory increases
    supplier_query = '''
        SELECT entered_date AS change_date, products AS product_name, quantity, 'Increase' AS change_type
        FROM suppliers
    '''
    supplier_df = pd.read_sql_query(supplier_query, engine)

    # Quantity changes
    quantity_changes_query = '''
        SELECT change_date, product_name, quantity_changed, change_type
        FROM product_quantity_changes
    '''
    quantity_changes_df = pd.read_sql_query(quantity_changes_query, engine)

    supplier_df = supplier_df.rename(columns={'quantity': 'net_change'})
    supplier_df['net_change'] = supplier_df['net_change'].fillna(0)

    quantity_changes_df['net_change'] = quantity_changes_df.apply(
        lambda row: row['quantity_changed'] if row['change_type'] == 'Increase' else -row['quantity_changed'],
        axis=1
    )

    quantity_changes_df = quantity_changes_df[['change_date', 'product_name', 'net_change']]

    supplier_df = supplier_df[['change_date', 'product_name', 'net_change']]

    # Combine
    df = pd.concat([supplier_df, quantity_changes_df], ignore_index=True)
    df['change_date'] = pd.to_datetime(df['change_date'])

    df = df.groupby(['change_date', 'product_name'])['net_change'].sum().reset_index()

    return df

def forecast_inventory(product_name, periods=7):
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
    engine = get_db_engine()
    with engine.connect() as conn:
        query = text("""
            SELECT COUNT(*) FROM notifications 
            WHERE title = :title AND message = :message AND status = :status
        """)
        result = conn.execute(query, {
            "title": title,
            "message": message,
            "status": status
        }).fetchone()
        return result[0] > 0

def insert_notification(title, message, status):
    engine = get_db_engine()
    with engine.connect() as conn:
        query = text("""
            INSERT INTO notifications (title, message, status)
            VALUES (:title, :message, :status)
        """)
        conn.execute(query, {
            "title": title,
            "message": message,
            "status": status
        })

def check_and_notify_all(sales_threshold=100, inventory_threshold=100):
    engine = get_db_engine()
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT DISTINCT product_name FROM sales_order_items
            UNION
            SELECT DISTINCT product_name FROM order_items
            UNION
            SELECT DISTINCT product_name FROM product_quantity_changes
            UNION
            SELECT DISTINCT products AS product_name FROM suppliers
        """))
        products = [row[0] for row in result.fetchall()]

    for product in products:
        # sales forecast
        forecasted_sales = forecast_sales(product)
        if forecasted_sales:
            min_sales = min([day['yhat'] for day in forecasted_sales])
            if min_sales < sales_threshold:
                title = "Low Sales Forecast Alert"
                message = f"Sales for '{product}' may drop below {sales_threshold} units."
                status = "Urgent"
                if not notification_exists(title, message, status):
                    insert_notification(title, message, status)

        # inventory
        forecasted_inventory = forecast_inventory(product)
        if forecasted_inventory:
            min_inventory = min([day['yhat'] for day in forecasted_inventory])
            if min_inventory < inventory_threshold:
                title = "Low Inventory Forecast Alert"
                message = f"Inventory for '{product}' may drop below {inventory_threshold} units."
                status = "Warning"
                if not notification_exists(title, message, status):
                    insert_notification(title, message, status)
