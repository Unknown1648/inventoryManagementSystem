from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from routes.database import *
import datetime
import random

orders_blueprint = Blueprint('orders', __name__)


@orders_blueprint.route('/get_available_stock')
def get_available_stock():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT products, SUM(quantity) as total_quantity
            FROM suppliers
            WHERE status = "Confirmed"
            GROUP BY products
        ''')
        stock = {row[0]: row[1] for row in cursor.fetchall()}
    return jsonify(stock)

def add_order(order_number, customer_name, customer_phone, payment_method, status, total_price, items):
    order_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()

        # Insert into the orders table
        cursor.execute(''' 
            INSERT INTO orders (order_number, order_date, customer_name, customer_phone, payment_method, status, total_price)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (order_number, order_date, customer_name, customer_phone, payment_method, status, total_price))

        order_id = cursor.lastrowid

        # Insert into the order_items table
        for item in items:
            cursor.execute('''
                INSERT INTO order_items (order_id, product_name, product_price, quantity)
                VALUES (?, ?, ?, ?)
            ''', (order_id, item['product_name'], item['product_price'], item['quantity']))

        # If order is completed, save it to the sales table
        if status == 'Completed':
            save_order_to_sales(cursor, order_number, order_date, customer_name, customer_phone, payment_method, total_price, items)

        # Commit the changes to the database
        conn.commit()

def save_order_to_sales(cursor, order_number, order_date, customer_name, customer_phone, payment_method, total_price, items):
    cursor.execute('''
        INSERT INTO sales (order_number, order_date, customer_name, customer_phone, payment_method, status, total_price)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (order_number, order_date, customer_name, customer_phone, payment_method, 'Completed', total_price))

    sales_order_id = cursor.lastrowid

    # Insert into sales_order_items and subtract product quantity
    for item in items:
        cursor.execute('''
            INSERT INTO sales_order_items (order_id, product_name, product_price, quantity, order_date)
            VALUES (?, ?, ?, ?, ?)
        ''', (sales_order_id, item['product_name'], item['product_price'], item['quantity'], order_date))

        # Subtract product quantity from suppliers
        subtract_product_quantity(cursor, item['product_name'], item['quantity'])

def subtract_product_quantity(cursor, product_name, quantity_sold):
    # Step 1: Fetch all confirmed suppliers for this product
    cursor.execute(''' 
        SELECT id, quantity FROM suppliers
        WHERE products = ? AND status = "Confirmed"
        ORDER BY id ASC
    ''', (product_name,))
    rows = cursor.fetchall()

    remaining = quantity_sold

    # Step 2: Loop through suppliers and deduct quantity as needed
    for supplier_id, current_quantity in rows:
        if remaining <= 0:
            break  # Done deducting

        if current_quantity >= remaining:
            # Supplier has enough to cover the rest
            new_quantity = current_quantity - remaining
            cursor.execute('UPDATE suppliers SET quantity = ? WHERE id = ?', (new_quantity, supplier_id))
            remaining = 0
        else:
            # Not enough, zero this one out and continue
            cursor.execute('UPDATE suppliers SET quantity = 0 WHERE id = ?', (supplier_id,))
            remaining -= current_quantity

    # Step 3: Calculate total remaining quantity across all confirmed suppliers
    cursor.execute('''
        SELECT SUM(quantity) FROM suppliers
        WHERE products = ? AND status = "Confirmed"
    ''', (product_name,))
    total_remaining = cursor.fetchone()[0] or 0

    # Step 4: Record a single, accurate quantity change
    record_quantity_change(cursor, product_name, total_remaining)

# Record the quantity change in product_quantity_changes and update snapshot
def record_quantity_change(cursor, product_name, new_quantity):
    # Fetch the current quantity from the snapshot table
    cursor.execute('SELECT last_quantity FROM product_quantity_snapshot WHERE product_name = ?', (product_name,))
    result = cursor.fetchone()

    if result is None:
        old_quantity = 0
    else:
        old_quantity = result[0]

    # Determine the change type and quantity changed
    if new_quantity > old_quantity:
        change_type = 'Increase'
        quantity_changed = new_quantity - old_quantity
    elif new_quantity < old_quantity:
        change_type = 'Decrease'
        quantity_changed = old_quantity - new_quantity
    else:
        # No change in quantity
        return

    # Get the current timestamp for the change date
    change_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Insert the change into the product_quantity_changes table
    cursor.execute('''
        INSERT INTO product_quantity_changes (product_name, change_type, quantity_changed, change_date)
        VALUES (?, ?, ?, ?)
    ''', (product_name, change_type, quantity_changed, change_date))

    # Update the product's snapshot in the product_quantity_snapshot table
    cursor.execute('''
        INSERT OR REPLACE INTO product_quantity_snapshot (product_name, last_quantity)
        VALUES (?, ?)
    ''', (product_name, new_quantity))

@orders_blueprint.route('/order_confirmation/<order_number>')
def order_confirmation(order_number):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM orders WHERE order_number = ?', (order_number,))
        order = cursor.fetchone()

        if not order:
            return "Order not found", 404

        cursor.execute('SELECT * FROM order_items WHERE order_id = ?', (order[0],))
        items = cursor.fetchall()

    order_dict = {
        'order_id': order[0],
        'order_number': order[1],
        'order_date': order[2],
        'customer_name': order[3],
        'customer_phone': order[4],
        'payment_method': order[5],
        'status': order[6],
        'total_price': order[7],
        'items': [{
            'product_name': item[2],
            'product_price': item[3],
            'quantity': item[4]
        } for item in items]
    }

    return render_template('order_confirmation.html', order=order_dict)

def get_order_details(order_number):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM orders WHERE order_number = ?', (order_number,))
        order = cursor.fetchone()

        if not order:
            return None

        order_details = {
            'order_number': order[1],
            'order_date': order[2],
            'customer_name': order[3],
            'customer_phone': order[4],
            'payment_method': order[5],
            'status': order[6],
            'total_price': order[7],
            'items': []
        }

        cursor.execute('SELECT * FROM order_items WHERE order_id = ?', (order[0],))
        items = cursor.fetchall()

        for item in items:
            order_details['items'].append({
                'product_name': item[2],
                'product_price': item[3],
                'quantity': item[4]
            })

    return order_details

def delete_order(order_number):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()

        # Step 1: Get the order_id
        cursor.execute('SELECT order_id FROM orders WHERE order_number = ?', (order_number,))
        order = cursor.fetchone()

        if not order:
            return

        order_id = order[0]

        # Step 2: Fetch all items from the order
        cursor.execute('SELECT product_name, quantity FROM order_items WHERE order_id = ?', (order_id,))
        items = cursor.fetchall()

        # Step 3: Restore quantities to suppliers
        for product_name, quantity in items:
            restore_product_quantity(cursor, product_name, quantity)

        # Step 4: Delete order and items
        cursor.execute('DELETE FROM order_items WHERE order_id = ?', (order_id,))
        cursor.execute('DELETE FROM orders WHERE order_number = ?', (order_number,))

def restore_product_quantity(cursor, product_name, quantity_to_restore):
    # Get all confirmed suppliers for this product, in reverse order of deduction (newest last)
    cursor.execute('''
        SELECT id, quantity FROM suppliers
        WHERE products = ? AND status = "Confirmed"
        ORDER BY id DESC
    ''', (product_name,))
    rows = cursor.fetchall()

    remaining = quantity_to_restore

    for supplier_id, current_quantity in rows:
        if remaining <= 0:
            break

        # Let's restore to suppliers, you can also add a cap if there's a max limit per supplier
        new_quantity = current_quantity + remaining
        cursor.execute('UPDATE suppliers SET quantity = ? WHERE id = ?', (new_quantity, supplier_id))
        remaining = 0

    # After restoring, recalculate the total stock and record the change
    cursor.execute('''
        SELECT SUM(quantity) FROM suppliers
        WHERE products = ? AND status = "Confirmed"
    ''', (product_name,))
    total_quantity = cursor.fetchone()[0] or 0

    record_quantity_change(cursor, product_name, total_quantity)

def update_order_status(order_number, new_status):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()

        if new_status == "Completed":
            # Fetch order_id and items
            cursor.execute('SELECT order_id FROM orders WHERE order_number = ?', (order_number,))
            order = cursor.fetchone()
            if not order:
                return "Order not found"
            order_id = order[0]

            cursor.execute('SELECT product_name, quantity FROM order_items WHERE order_id = ?', (order_id,))
            items = cursor.fetchall()

            # Check stock availability
            for product_name, quantity in items:
                cursor.execute('''
                    SELECT SUM(quantity) FROM suppliers
                    WHERE products = ? AND status = "Confirmed"
                ''', (product_name,))
                total_stock = cursor.fetchone()[0] or 0
                if quantity > total_stock:
                    return f"Insufficient stock for {product_name}"

            # Deduct stock and record quantity change
            for product_name, quantity in items:
                subtract_product_quantity(cursor, product_name, quantity)

        # Finally update status
        cursor.execute('UPDATE orders SET status = ? WHERE order_number = ?', (new_status, order_number))
        conn.commit()

def get_all_orders():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM orders')
        orders = cursor.fetchall()

    columns = ['order_id', 'order_number', 'order_date', 'customer_name', 'customer_phone', 'payment_method', 'status', 'total_price']
    return [dict(zip(columns, row)) for row in orders]

@orders_blueprint.route('/view_orders')
def view_orders():
    search_query = request.args.get('search', '').strip()
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        if search_query:
            cursor.execute('''
                SELECT * FROM orders
                WHERE order_number LIKE ? OR customer_name LIKE ?
                ORDER BY order_date DESC
            ''', (f'%{search_query}%', f'%{search_query}%'))
        else:
            cursor.execute('SELECT * FROM orders ORDER BY order_date DESC')
        orders = cursor.fetchall()

    columns = ['order_id', 'order_number', 'order_date', 'customer_name', 'customer_phone', 'payment_method', 'status', 'total_price']
    return render_template('view_orders.html', orders=[dict(zip(columns, row)) for row in orders])

@orders_blueprint.route('/order_details/<order_number>', methods=['GET', 'POST'])
def order_details_route(order_number):
    order = get_order_details(order_number)
    if not order:
        return "Order not found!", 404

    if request.method == 'POST':
        new_status = request.form['status']
        result = update_order_status(order_number, new_status)
        if result and isinstance(result, str): 
            return render_template('order_details.html', order=order, error=result)
        return redirect(url_for('orders.order_details_route', order_number=order_number))

    return render_template('order_details.html', order=order)

@orders_blueprint.route('/delete_order/<order_number>')
def delete_order_route(order_number):
    delete_order(order_number)
    return redirect(url_for('orders.view_orders'))

def generate_unique_order_number():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        while True:
            code = ''.join(random.choices('ABCDEFGHIJ0123456789', k=8))
            order_number = f"ORDER-{code}"
            cursor.execute("SELECT 1 FROM orders WHERE order_number = ?", (order_number,))
            if not cursor.fetchone():
                return order_number

@orders_blueprint.route('/manage_orders', methods=['GET', 'POST'])
def manage_orders():
    if request.method == 'POST':
        order_number = generate_unique_order_number()
        customer_name = request.form['customer_name']
        customer_phone = request.form['customer_phone']
        payment_method = request.form['payment_method']
        payment_status = request.form.get('payment_status', 'Unpaid')
        discount = float(request.form.get('discount', 0))
        status = 'Completed' if payment_status == 'Paid' else 'Pending'

        items = []
        total_price = 0
        i = 1
        while f'items[{i}][name]' in request.form:
            name = request.form[f'items[{i}][name]']
            price = float(request.form[f'items[{i}][price]'])
            quantity = int(request.form[f'items[{i}][quantity]'])
            items.append({
                'product_name': name,
                'product_price': price,
                'quantity': quantity
            })
            total_price += price * quantity
            i += 1

        total_price -= discount
        add_order(order_number, customer_name, customer_phone, payment_method, status, total_price, items)

        return redirect(url_for('orders.order_confirmation', order_number=order_number))

    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name, contact FROM customers")
        customers = [{'name': row[0], 'contact': row[1]} for row in cursor.fetchall()]

    orders = get_all_orders()
    return render_template('create_order.html', orders=orders, customers=customers)
