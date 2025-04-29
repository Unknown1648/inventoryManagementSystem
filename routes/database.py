import sqlite3

DB_NAME = 'inventory.db'

def initialize_inventory_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Customers table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_number TEXT NOT NULL,
            order_date TEXT NOT NULL,
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
            item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            product_name TEXT NOT NULL,
            product_price REAL NOT NULL,
            quantity INTEGER NOT NULL,
            FOREIGN KEY(order_id) REFERENCES orders(order_id)
        )
    ''')

    # Sales table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sales (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_number TEXT NOT NULL,
            order_date TEXT NOT NULL,
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
            item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            product_name TEXT NOT NULL,
            product_price REAL NOT NULL,
            quantity INTEGER NOT NULL,
            order_date TEXT,
            cost REAL GENERATED ALWAYS AS (product_price * quantity) STORED,
            FOREIGN KEY(order_id) REFERENCES sales(order_id)
        )
    ''')

    # Notifications table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            message TEXT,
            status TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # stock table
    cursor.execute(''' 
        CREATE TABLE IF NOT EXISTS stock (
            stock_id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT NOT NULL,
            product_serial_no TEXT NOT NULL,
            stock_data TEXT NOT NULL,
            product_price REAL NOT NULL,
            entered_date TEXT,
            expiry_date TEXT,
            supplier_name TEXT
        )
    ''')
    
    # Suppliers table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_name TEXT NOT NULL,
            contact TEXT NOT NULL,
            products TEXT NOT NULL,
            initial_quantity INTEGER NOT NULL, 
            quantity INTEGER NOT NULL,
            entered_date TEXT,
            status TEXT NOT NULL,
            price_per_product REAL NOT NULL,
            delivery_price REAL NOT NULL,
            total_price REAL NOT NULL
        )
    ''')

    # table to monitor product quantity changes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS product_quantity_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT NOT NULL,
            change_type TEXT CHECK(change_type IN ('Increase', 'Decrease')),
            quantity_changed INTEGER NOT NULL,
            change_date TEXT NOT NULL
        )
    ''')
    
    # table to track Previous Quantities
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS product_quantity_snapshot (
            product_name TEXT PRIMARY KEY,
            last_quantity INTEGER NOT NULL
        )          
    ''')
    
    conn.commit()
    conn.close()
    print("All tables created successfully")
