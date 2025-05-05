from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from routes.database import *
from datetime import datetime, timedelta
from routes.ai_forecast import check_and_notify_all

manage_stocks = Blueprint('manage_stocks', __name__)

def create_notification(title, message, status="Info"):
    """Create a notification with a given severity status."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
            INSERT INTO notifications (title, message, status, created_at)
            VALUES (%s, %s, %s, %s)
        ''', (title, message, status, datetime.now()))
    conn.commit()

@manage_stocks.route('/notifications/archive/<int:notification_id>', methods=['POST'])
def archive_notification(notification_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE notifications SET status = %s WHERE id = %s', ('archived', notification_id))    
    conn.commit()
    return jsonify({'success': True})

@manage_stocks.route('/notifications/delete/<int:notification_id>', methods=['POST'])
def delete_notification(notification_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM notifications WHERE id = %s', (notification_id,))
    conn.commit()
    return jsonify({'success': True, 'message': 'Notification deleted.'})

def add_stock(product_name, product_serial_no, stock_data, product_price, expiry_date, supplier_name):
    if not expiry_date:
        expiry_date = None
    else:
        try:
            expiry_date = datetime.strptime(expiry_date, '%Y-%m-%d').date()
        except ValueError:
            print("Invalid expiry date format provided.")
            expiry_date = None

    # Database connection and insertion
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO stock (
            product_name, product_serial_no, stock_data, 
            product_price, entered_date, expiry_date, supplier_name
        ) 
        VALUES (%s, %s, %s, %s, NOW(), %s, %s)
    ''', (product_name, product_serial_no, stock_data, product_price, expiry_date, supplier_name))
    conn.commit()
    conn.close()

# Fetch all stock records
def get_all_stock():
    conn = get_db_connection()
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
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT product_name, product_price FROM stock')
    products = cursor.fetchall()
    return products

# Fetching all suppliers
def get_all_suppliers():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT supplier_name FROM suppliers')
    suppliers = [row[0] for row in cursor.fetchall()]
    return suppliers

# Route to view and manage stocks
@manage_stocks.route('/', methods=['GET', 'POST'])
def manage_stocks_page():
    if request.method == 'POST':
        product_name = request.form['product_name']
        product_serial_no = request.form.get('product_serial_no') or "N/A"
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

        conn = get_db_connection()
        cursor = conn.cursor()
        if action == 'update':
                # Price update
            price_field = f'price_{stock_id}'
            new_price = request.form.get(price_field)
            if new_price:
                cursor.execute("UPDATE stock SET product_price = %s WHERE stock_id = %s", (new_price, stock_id))
                conn.commit()

        elif action == 'delete':
                cursor.execute("SELECT product_name FROM stock WHERE stock_id = %s", (stock_id,))
                result = cursor.fetchone()
                if result:
                    product_name = result[0]

                    cursor.execute("DELETE FROM product_quantity_changes WHERE product_name = %s", (product_name,))
                    cursor.execute("DELETE FROM product_quantity_snapshot WHERE product_name = %s", (product_name,))

                    cursor.execute("DELETE FROM stock WHERE stock_id = %s", (stock_id,))
                    conn.commit()

        return redirect(url_for('manage_stocks.edit_prices'))

    # Search and display
    search = request.args.get('search', '')
    conn = get_db_connection()
    cursor = conn.cursor()
    if search:
        cursor.execute("SELECT * FROM stock WHERE product_name LIKE %s", ('%' + search + '%',))
    else:
        cursor.execute("SELECT * FROM stock")
    stocks = cursor.fetchall()

    return render_template('edit_prices.html', stocks=stocks, search=search)

@manage_stocks.route('/count_product_quantity_page', methods=['GET'])
def count_product_quantity_page():
    return render_template('count_product_quantity.html')

def count_all_product_quantities_confirmed():
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT products, SUM(initial_quantity), SUM(quantity)
            FROM suppliers
            WHERE status = 'Confirmed'
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
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
            SELECT COUNT(*) FROM notifications 
            WHERE title = %s AND message = %s AND status = %s
        ''', (title, message, status))
    exists = cursor.fetchone()[0] > 0
    return exists

def generate_weekly_notifications():
    try:
        # check total quantity per product from confirmed suppliers ---
        conn_suppliers = get_db_connection()
        cursor_suppliers = conn_suppliers.cursor()
        cursor_suppliers.execute('''
            SELECT products, SUM(quantity)
            FROM suppliers
            WHERE status = 'Confirmed'
            GROUP BY products
        ''')
        supplier_data = cursor_suppliers.fetchall()
        
        if not supplier_data:
            print("No supplier data found.")
            return

        # get total quantity sold per product ---
        conn_sales = get_db_connection()
        cursor_sales = conn_sales.cursor()
        cursor_sales.execute('''
            SELECT product_name, SUM(quantity)
            FROM sales_order_items
            GROUP BY product_name
        ''')
        sales_data = cursor_sales.fetchall()
        sold_quantities = {row[0]: row[1] if row[1] else 0 for row in sales_data}
        
        # generate restock alerts ---
        for row in supplier_data:
            if len(row) != 2:
                print(f"Unexpected row structure: {row}")
                continue

            product, total_supplied = row
            total_sold = sold_quantities.get(product, 0)
            current_quantity = total_supplied - total_sold

            if current_quantity < 100:
                title = f"⚠️ Restock Alert: {product}"
                message = f"The stock for '{product}' is low. Current quantity: {current_quantity}. Please restock."
                status = "Urgent"

                if not notification_exists(title, message, status):
                    create_notification(title=title, message=message, status=status)

        # weekly sales insights (most & least sold)
        conn = get_db_connection()
        cursor = conn.cursor()
        one_week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('''
            SELECT product_name, SUM(quantity) AS total_sales
            FROM sales_order_items
            WHERE order_date >= %s
            GROUP BY product_name
            ORDER BY total_sales DESC
        ''', (one_week_ago,))
        weekly_sales_data = cursor.fetchall()
        
        if weekly_sales_data and all(len(row) == 2 for row in weekly_sales_data):
            if len(weekly_sales_data) >= 2:
                most_sold = weekly_sales_data[0]
                least_sold = weekly_sales_data[-1]
            else:
                most_sold = least_sold = weekly_sales_data[0]

            most_title = "Most Sold Product At The Moment"
            most_msg = f"{most_sold[0]} with {most_sold[1] or 0} units sold in the past 7 days."

            least_title = "Least Sold Product"
            least_msg = f"{least_sold[0]} with {least_sold[1] or 0} units sold in the past 7 days."

            if not notification_exists(most_title, most_msg, "Info"):
                create_notification(title=most_title, message=most_msg, status="Info")

            if not notification_exists(least_title, least_msg, "Info"):
                create_notification(title=least_title, message=least_msg, status="Info")

        check_and_notify_all()

    except Exception as e:
        print(f"Error in generate_weekly_notifications: {e}")
    
@manage_stocks.route('/revenue')
def revenue():
    query = request.args.get('query', '').lower()

    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch unique combinations
    cursor.execute('''
        SELECT product_name, supplier_name, entered_date, product_price
        FROM stock
        GROUP BY product_name, supplier_name, entered_date, product_price;
    ''')
    stocks = cursor.fetchall()

    revenue_data = []

    for stock in stocks:
        product_name, supplier_name, entered_date, product_price = stock

        conn_suppliers = get_db_connection()
        cursor_suppliers = conn_suppliers.cursor()

        cursor_suppliers.execute('''
            SELECT price_per_product, total_price
            FROM suppliers
            WHERE supplier_name = %s AND products = %s;
        ''', (supplier_name, product_name))

        price = cursor_suppliers.fetchone()
        conn_suppliers.close()

        if price:
            price_per_product = price[0]
            item = {
                'product_name': product_name,
                'supplier_name': supplier_name,
                'entered_date': entered_date,
                'price': price_per_product,
                'product_price': product_price
            }

            if query:
                if (
                    query in product_name.lower() or
                    query in supplier_name.lower() or
                    query in str(entered_date).lower() or
                    query in str(price_per_product).lower() or
                    query in str(product_price).lower()
                ):
                    revenue_data.append(item)
            else:
                revenue_data.append(item)

    # Global total revenue
    cur = conn.cursor()
    cur.execute('SELECT SUM(cost) FROM sales_order_items')
    total_sales_sum = cur.fetchone()[0] or 0

    cur.execute('SELECT SUM(total_price) FROM suppliers')
    total_purchasing_sum = cur.fetchone()[0] or 0

    conn.close()

    summed_revenue = round(total_sales_sum - total_purchasing_sum, 2)

    return render_template('revenue.html', revenue_data=revenue_data, summed_revenue=summed_revenue)    

@manage_stocks.route('/revenue_detail/<product_name>/<supplier_name>/<entered_date>', methods=['GET', 'POST'])
def revenue_detail(product_name, supplier_name, entered_date):
    # Connecting to stocks, suppliers, and sales
    stock_conn = get_db_connection()
    stock_cur = stock_conn.cursor()
    
    stock_cur.execute('''SELECT COUNT(*) FROM stock WHERE product_name = %s AND supplier_name = %s AND entered_date = %s''', (product_name, supplier_name, entered_date))
    total_entries = stock_cur.fetchone()[0]

    supplier_conn = get_db_connection()
    supplier_cur = supplier_conn.cursor()
    
    supplier_cur.execute('''SELECT price_per_product, total_price FROM suppliers WHERE supplier_name = %s AND products = %s LIMIT 1''', (supplier_name, product_name))
    price_data = supplier_cur.fetchone()

    sales_conn = get_db_connection()
    sales_cur = sales_conn.cursor()

    sales_cur.execute('''SELECT SUM(cost) FROM sales_order_items WHERE product_name = %s''', (product_name,))
    total_sales = sales_cur.fetchone()[0] or 0

    # Fetch operational cost and debts if provided by the user (else = 0)
    operational_cost = request.form.get('operational_cost', 0)
    debts = request.form.get('debts', 0)

    price = price_data[0] if price_data else 0
    purchasing_cost = price_data[1] if price_data else 0
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
