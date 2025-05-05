import os
import psycopg2
from sqlalchemy import create_engine
from urllib.parse import urlparse

def get_db_connection():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is missing.")
    
    url = urlparse(database_url)
    return psycopg2.connect(
        dbname=url.path[1:],
        user=url.username,
        password=url.password,
        host=url.hostname,
        port=url.port
    )

def get_db_engine():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is missing.")
    
    return create_engine(database_url, pool_pre_ping=True)

def initialize_inventory_db():
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Customers table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS customers (
                customer_id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                contact TEXT NOT NULL,
                email TEXT NOT NULL,
                address TEXT NOT NULL,
                payment_method TEXT NOT NULL
            )
        ''')

        # Orders table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                order_id SERIAL PRIMARY KEY,
                order_number TEXT NOT NULL,
                order_date TIMESTAMP NOT NULL,
                customer_name TEXT NOT NULL,
                customer_phone TEXT NOT NULL,
                payment_method TEXT NOT NULL,
                status TEXT NOT NULL,
                total_price REAL NOT NULL
            )
        ''')

        # Order items table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS order_items (
                item_id SERIAL PRIMARY KEY,
                order_id INTEGER REFERENCES orders(order_id),
                product_name TEXT NOT NULL,
                product_price REAL NOT NULL,
                quantity INTEGER NOT NULL
            )
        ''')

        # Sales table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sales (
                order_id SERIAL PRIMARY KEY,
                order_number TEXT NOT NULL,
                order_date TIMESTAMP NOT NULL,
                customer_name TEXT NOT NULL,
                customer_phone TEXT NOT NULL,
                payment_method TEXT NOT NULL,
                status TEXT NOT NULL,
                total_price REAL NOT NULL
            )
        ''')

        # Sales order items table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sales_order_items (
                item_id SERIAL PRIMARY KEY,
                order_id INTEGER REFERENCES sales(order_id),
                product_name TEXT NOT NULL,
                product_price REAL NOT NULL,
                quantity INTEGER NOT NULL,
                order_date TIMESTAMP,
                cost REAL GENERATED ALWAYS AS (product_price * quantity) STORED
            )
        ''')

        # Notifications table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                id SERIAL PRIMARY KEY,
                title TEXT,
                message TEXT,
                status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Stock table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stock (
                stock_id SERIAL PRIMARY KEY,
                product_name TEXT NOT NULL,
                product_serial_no TEXT NOT NULL,
                stock_data TEXT NOT NULL,
                product_price REAL NOT NULL,
                entered_date TIMESTAMP,
                expiry_date TIMESTAMP,
                supplier_name TEXT
            )
        ''')

        # Suppliers table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS suppliers (
                id SERIAL PRIMARY KEY,
                supplier_name TEXT NOT NULL,
                contact TEXT NOT NULL,
                products TEXT NOT NULL,
                initial_quantity INTEGER NOT NULL, 
                quantity INTEGER NOT NULL,
                entered_date TIMESTAMP,
                status TEXT NOT NULL,
                price_per_product REAL NOT NULL,
                delivery_price REAL NOT NULL,
                total_price REAL NOT NULL
            )
        ''')

        # Table to monitor product quantity changes
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS product_quantity_changes (
                id SERIAL PRIMARY KEY,
                product_name TEXT NOT NULL,
                change_type TEXT CHECK(change_type IN ('Increase', 'Decrease')),
                quantity_changed INTEGER NOT NULL,
                change_date TIMESTAMP NOT NULL
            )
        ''')

        # Table to track Previous Quantities
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS product_quantity_snapshot (
                product_name TEXT PRIMARY KEY,
                last_quantity INTEGER NOT NULL
            )
        ''')

        conn.commit()
        print("All tables created successfully")

    except Exception as e:
        print("Error initializing database:", e)

    finally:
        if conn:
            cursor.close()
            conn.close()
