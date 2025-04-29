from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from routes.database import *
from datetime import datetime, timedelta
from routes.ai_forecast import check_and_notify_all
import sqlite3

manage_stocks = Blueprint('manage_stocks', __name__)

def create_notification(title, message, status="Info"):
    """Create a notification with a given severity status."""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO notifications (title, message, status, created_at)
            VALUES (?, ?, ?, ?)
        ''', (title, message, status, datetime.now()))
        conn.commit()

@manage_stocks.route('/notifications/archive/<int:notification_id>', methods=['POST'])
def archive_notification(notification_id):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE notifications SET status = "archived" WHERE id = ?', (notification_id,))
        conn.commit()
    return jsonify({'success': True})

@manage_stocks.route('/notifications/delete/<int:notification_id>', methods=['POST'])
def delete_notification(notification_id):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM notifications WHERE id = ?', (notification_id,))
        conn.commit()
    return jsonify({'success': True, 'message': 'Notification deleted.'})

# Add stock to db
def add_stock(product_name, product_serial_no, stock_data, product_price, expiry_date, supplier_name):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute(''' 
            INSERT INTO stock (
                product_name, product_serial_no, stock_data, 
                product_price, entered_date, expiry_date, supplier_name
            ) 
            VALUES (?, ?, ?, ?, datetime('now'), ?, ?)
        ''', (product_name, product_serial_no, stock_data, product_price, expiry_date, supplier_name))
        conn.commit()

# Fetch all stock records
def get_all_stock():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM stock')
        stocks = cursor.fetchall()

    columns = [
        'stock_id', 'product_name', 'product_serial_no', 
        'stock_data', 'product_price', 'entered_date', 
        'expiry_date', 'supplier_name'
    ]
    return [dict(zip(columns, row)) for row in stocks]

# Fetch unique products (names and prices) from stocks table
def get_unique_products():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT DISTINCT product_name, product_price FROM stock')
        products = cursor.fetchall()
    return products

# Update price of a product
def update_product_price(stock_id, new_price):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE stock SET product_price = ? WHERE stock_id = ?', (new_price, stock_id))
        conn.commit()

# Fetching all suppliers
def get_all_suppliers():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT supplier_name FROM suppliers')
        suppliers = [row[0] for row in cursor.fetchall()]
    return suppliers

# Route to view and manage stocks
@manage_stocks.route('/', methods=['GET', 'POST'])
def manage_stocks_page():
    if request.method == 'POST':
        product_name = request.form['product_name']
        product_serial_no = request.form['product_serial_no']
        stock_data = request.form['stock_data']
        product_price = float(request.form['product_price'])
        expiry_date = request.form['expiry_date']
        supplier_name = request.form['supplier']

        add_stock(product_name, product_serial_no, stock_data, product_price, expiry_date, supplier_name)
        return redirect(url_for('manage_stocks.manage_stocks_page'))

    stocks = get_all_stock()
    suppliers = get_all_suppliers()
    return render_template('stocks.html', stocks=stocks, suppliers=suppliers)

# Fetch unique products (name and price)
@manage_stocks.route('/get_products', methods=['GET'])
def get_products():
    products = get_unique_products()
    return jsonify(products)

@manage_stocks.route('/edit_prices', methods=['POST', 'GET'])
def edit_prices():
    if request.method == 'POST':
        stock_id = request.form.get('stock_id')
        action = request.form.get('action')

        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            if action == 'update':
                # Price update
                price_field = f'price_{stock_id}'
                new_price = request.form.get(price_field)
                if new_price:
                    cursor.execute("UPDATE stock SET product_price = ? WHERE stock_id = ?", (new_price, stock_id))
                    conn.commit()

            elif action == 'delete':
                # Product delete
                cursor.execute("DELETE FROM stock WHERE stock_id = ?", (stock_id,))
                conn.commit()

        return redirect(url_for('manage_stocks.edit_prices'))

    # Search and display
    search = request.args.get('search', '')
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        if search:
            cursor.execute("SELECT * FROM stock WHERE product_name LIKE ?", ('%' + search + '%',))
        else:
            cursor.execute("SELECT * FROM stock")
        stocks = cursor.fetchall()

    return render_template('edit_prices.html', stocks=stocks, search=search)

@manage_stocks.route('/count_product_quantity_page', methods=['GET'])
def count_product_quantity_page():
    return render_template('count_product_quantity.html')

def count_all_product_quantities_confirmed():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT products, SUM(initial_quantity), SUM(quantity)
            FROM suppliers
            WHERE status = "Confirmed"
            GROUP BY products
        ''')
        data = cursor.fetchall()

    result = [
        {
            "product_name": row[0],
            "initial_quantity": row[1],
            "quantity": row[2]
        }
        for row in data
    ]

    return result

# Fetch all products and their quantities from confirmed supplies
@manage_stocks.route('/count_all_product_quantities', methods=['GET'])
def count_all_product_quantities():
    # Fetch list of products and quantities
    products = count_all_product_quantities_confirmed()
    return jsonify(products)

def notification_exists(title, message, status):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM notifications 
            WHERE title = ? AND message = ? AND status = ?
        ''', (title, message, status))
        exists = cursor.fetchone()[0] > 0
    return exists

def generate_weekly_notifications():
    # Get total quantity per product from confirmed suppliers
    with sqlite3.connect(DB_NAME) as conn_suppliers:
        cursor_suppliers = conn_suppliers.cursor()
        cursor_suppliers.execute('''
            SELECT products, SUM(quantity)
            FROM suppliers
            WHERE status = "Confirmed"
            GROUP BY products
        ''')
        supplier_data = cursor_suppliers.fetchall()

    # Get total quantity sold per product
    with sqlite3.connect(DB_NAME) as conn_sales:
        cursor_sales = conn_sales.cursor()
        cursor_sales.execute('''
            SELECT product_name, SUM(quantity)
            FROM sales_order_items
            GROUP BY product_name
        ''')
        sales_data = cursor_sales.fetchall()

    sold_quantities = {row[0]: row[1] if row[1] else 0 for row in sales_data}

    # Check for low stock and generate restock notifications
    for product, total_supplied in supplier_data:
        total_sold = sold_quantities.get(product, 0)
        current_quantity = total_supplied

        if current_quantity < 100:
            title = f"⚠️ Restock Alert: {product}"
            message = f"The stock for '{product}' is low. Current quantity: {current_quantity}. Please restock."
            status = "Urgent"

            if not notification_exists(title, message, status):
                create_notification(title=title, message=message, status=status)

    # Sales notifications(week)
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()

        one_week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('''
            SELECT product_name, SUM(quantity) AS total_sales
            FROM sales_order_items
            WHERE order_date >= ?
            GROUP BY product_name
            ORDER BY total_sales DESC
        ''', (one_week_ago,))
        sales_data = cursor.fetchall()

    if sales_data:
        most_sold = sales_data[0]
        least_sold = sales_data[-1]

        most_title = "Most Sold Product At The Moment"
        most_msg = f"{most_sold[0]} with {most_sold[1]} units sold in the past 7 days."
        least_title = "Least Sold Product"
        least_msg = f"{least_sold[0]} with {least_sold[1]} units sold in the past 7 days."

        if not notification_exists(most_title, most_msg, "Info"):
            create_notification(title=most_title, message=most_msg, status="Info")

        if not notification_exists(least_title, least_msg, "Info"):
            create_notification(title=least_title, message=least_msg, status="Info")
            
    # Forecast-based notifications
    check_and_notify_all()

@manage_stocks.route('/revenue')
def revenue():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()

        # fetch unique combinations of product_name + supplier_name + entered_date
        cursor.execute('''
            SELECT product_name, supplier_name, entered_date, product_price
            FROM stock
            GROUP BY product_name, supplier_name, entered_date;
        ''')
        stocks = cursor.fetchall()

    revenue_data = []
    for stock in stocks:
        product_name, supplier_name, entered_date , product_price = stock

        # fetch price_per_product from suppliers
        with sqlite3.connect(DB_NAME) as conn_suppliers:
            cursor_suppliers = conn_suppliers.cursor()
            cursor_suppliers.execute('''
                SELECT price_per_product, total_price
                FROM suppliers
                WHERE supplier_name = ? AND products = ?;
            ''', (supplier_name, product_name))
            price = cursor_suppliers.fetchone()

        if price:
            revenue_data.append({
                'product_name': product_name,
                'supplier_name': supplier_name,
                'entered_date': entered_date,
                'price': price[0],
                'product_price': product_price,
            })

    return render_template('revenue.html', revenue_data=revenue_data)

@manage_stocks.route('/revenue_detail/<product_name>/<supplier_name>/<entered_date>', methods=['GET', 'POST'])
def revenue_detail(product_name, supplier_name, entered_date):
    # Connecting to stocks, suppliers, and sales
    with sqlite3.connect(DB_NAME) as stock_conn:
        stock_cur = stock_conn.cursor()
        stock_cur.execute('''SELECT COUNT(*) FROM stock WHERE product_name = ? AND supplier_name = ? AND entered_date = ?''', (product_name, supplier_name, entered_date))
        total_entries = stock_cur.fetchone()[0]

    with sqlite3.connect(DB_NAME) as supplier_conn:
        supplier_cur = supplier_conn.cursor()
        supplier_cur.execute('''SELECT price_per_product, total_price FROM suppliers WHERE supplier_name = ? AND products = ? LIMIT 1''', (supplier_name, product_name))
        price_data = supplier_cur.fetchone()

    with sqlite3.connect(DB_NAME) as sales_conn:
        sales_cur = sales_conn.cursor()
        sales_cur.execute('''SELECT SUM(cost) FROM sales_order_items WHERE product_name = ?''', (product_name,))
        total_sales = sales_cur.fetchone()[0] or 0

    # Fetch operational cost and debts if provided by the user (default to 0)
    operational_cost = request.form.get('operational_cost', 0)
    debts = request.form.get('debts', 0)

    price = price_data[0] if price_data else 0
    purchasing_cost = price_data[1] if price_data else 0  # This is the purchasing cost
    total_revenue = total_sales - float(debts) - float(operational_cost) - purchasing_cost

    # Data to be passed to revenue details
    detail = {
        'product_name': product_name,
        'supplier_name': supplier_name,
        'entered_date': entered_date,
        'price': round(price, 2),
        'purchasing_cost': round(purchasing_cost, 2),
        'total_sales': round(total_sales, 2),
        'operational_cost': round(float(operational_cost), 2),
        'debts': round(float(debts), 2),
        'total_revenue': round(total_revenue, 2),
    }

    return render_template('revenue_details.html', detail=detail)