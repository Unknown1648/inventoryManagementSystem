from flask import Blueprint, render_template
from routes.database import *
import sqlite3

sales_blueprint = Blueprint('sales', __name__)

# Fetch pending orders
def get_pending_orders():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT order_id, order_number, order_date, customer_name, customer_phone, payment_method, status
            FROM orders
            WHERE status = "Pending"
        ''')
        orders = cursor.fetchall()

    columns = ['order_id', 'order_number', 'order_date', 'customer_name', 'customer_phone', 'payment_method', 'status']
    return [dict(zip(columns, row)) for row in orders]

# Fetch completed orders
def get_completed_orders():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT order_id, order_number, order_date, customer_name, customer_phone, payment_method, status
            FROM orders
            WHERE status = "Completed"
        ''')
        orders = cursor.fetchall()

    columns = ['order_id', 'order_number', 'order_date', 'customer_name', 'customer_phone', 'payment_method', 'status']
    return [dict(zip(columns, row)) for row in orders]

# Fetch items for a specific order
def get_order_items(order_id):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT product_name, product_price, quantity
            FROM order_items
            WHERE order_id = ?
        ''', (order_id,))
        rows = cursor.fetchall()

    return [{'name': row[0], 'price': row[1], 'quantity': row[2], 'serial': None} for row in rows]

# Route to sales page
@sales_blueprint.route('/sales', methods=['GET'])
def sales_page():
    pending_orders = get_pending_orders()
    completed_orders = get_completed_orders()

    # Include items to each order
    for order in pending_orders:
        order['items'] = get_order_items(order['order_id'])

    for order in completed_orders:
        order['items'] = get_order_items(order['order_id'])

    return render_template('sales.html', pending_orders=pending_orders, completed_orders=completed_orders)
