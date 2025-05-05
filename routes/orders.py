from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from routes.database import get_db_connection
import datetime
import random

orders_blueprint = Blueprint('orders', __name__)

@orders_blueprint.route('/get_available_stock')
def get_available_stock():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT products, SUM(quantity) as total_quantity
        FROM suppliers
        WHERE status = 'Confirmed'
        GROUP BY products
    ''')
    stock = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()
    return jsonify(stock)

def add_order(order_number, customer_name, customer_phone, payment_method, status, total_price, items):
    order_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db_connection()
    cursor = conn.cursor()

    # Insert into the orders table and get the order_id using RETURNING
    cursor.execute(''' 
        INSERT INTO orders (order_number, order_date, customer_name, customer_phone, payment_method, status, total_price)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING order_id;
    ''', (order_number, order_date, customer_name, customer_phone, payment_method, status, total_price))

    # Fetch the generated order_id from the INSERT statement
    order_id = cursor.fetchone()[0]

    # Insert into the order_items table
    for item in items:
        cursor.execute('''
            INSERT INTO order_items (order_id, product_name, product_price, quantity)
            VALUES (%s, %s, %s, %s)
        ''', (order_id, item['product_name'], item['product_price'], item['quantity']))

    # If order is completed, save it to the sales table
    if status == 'Completed':
        save_order_to_sales(cursor, order_number, order_date, customer_name, customer_phone, payment_method, total_price, items)

    # Commit the changes to the database
    conn.commit()

def save_order_to_sales(cursor, order_number, order_date, customer_name, customer_phone, payment_method, total_price, items):
    # Insert into the sales table and get the sales_order_id using RETURNING
    cursor.execute(''' 
        INSERT INTO sales (order_number, order_date, customer_name, customer_phone, payment_method, status, total_price)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING order_id;  -- Assuming the primary key is order_id
    ''', (order_number, order_date, customer_name, customer_phone, payment_method, 'Completed', total_price))

    # Fetch the generated sales_order_id from the INSERT statement
    order_id = cursor.fetchone()[0]

    # Insert into sales_order_items table
    for item in items:
        cursor.execute(''' 
            INSERT INTO sales_order_items (order_id, product_name, product_price, quantity, order_date)
            VALUES (%s, %s, %s, %s, %s)
        ''', (order_id, item['product_name'], item['product_price'], item['quantity'], order_date))

        # Subtract product quantity from suppliers
        subtract_product_quantity(cursor, item['product_name'], item['quantity'])

def subtract_product_quantity(cursor, product_name, quantity_sold):
    # Step 1: Fetch all confirmed suppliers for this product
    cursor.execute(''' 
        SELECT id, quantity FROM suppliers
        WHERE products = %s AND status = 'Confirmed'
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
            cursor.execute('UPDATE suppliers SET quantity = %s WHERE id = %s', (new_quantity, supplier_id))
            remaining = 0
        else:
            # Not enough, zero this one out and continue
            cursor.execute('UPDATE suppliers SET quantity = 0 WHERE id = %s', (supplier_id,))
            remaining -= current_quantity

    # Step 3: Calculate total remaining quantity across all confirmed suppliers
    cursor.execute('''
        SELECT SUM(quantity) FROM suppliers
        WHERE products = %s AND status = 'Confirmed'
    ''', (product_name,))
    total_remaining = cursor.fetchone()[0] or 0

    # Step 4: Record a single, accurate quantity change
    record_quantity_change(cursor, product_name, total_remaining)

def record_quantity_change(cursor, product_name, new_quantity):
    # Fetch the current quantity from the snapshot table
    cursor.execute('SELECT last_quantity FROM product_quantity_snapshot WHERE product_name = %s', (product_name,))
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
        VALUES (%s, %s, %s, %s)
    ''', (product_name, change_type, quantity_changed, change_date))

    # Update the product's snapshot in the product_quantity_snapshot table
    cursor.execute('''
        INSERT INTO product_quantity_snapshot (product_name, last_quantity)
        VALUES (%s, %s)
        ON CONFLICT (product_name)  -- Conflict on product_name
        DO UPDATE SET last_quantity = EXCLUDED.last_quantity;  -- Update with the new quantity
    ''', (product_name, new_quantity))


@orders_blueprint.route('/order_confirmation/<order_number>')
def order_confirmation(order_number):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM orders WHERE order_number = %s', (order_number,))
        order = cursor.fetchone()

        if not order:
            return "Order not found", 404

        cursor.execute('SELECT * FROM order_items WHERE order_id = %s', (order[0],))
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
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM orders WHERE order_number = %s', (order_number,))
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

        cursor.execute('SELECT * FROM order_items WHERE order_id = %s', (order[0],))
        items = cursor.fetchall()

        for item in items:
            order_details['items'].append({
                'product_name': item[2],
                'product_price': item[3],
                'quantity': item[4]
            })

        return order_details

def delete_order(order_number):
        conn = get_db_connection()
        cursor = conn.cursor()

        # get the order_id
        cursor.execute('SELECT order_id FROM orders WHERE order_number = %s', (order_number,))
        order = cursor.fetchone()

        if not order:
            return

        order_id = order[0]

        # fetch all items from that order
        cursor.execute('SELECT product_name, quantity FROM order_items WHERE order_id = %s', (order_id,))
        items = cursor.fetchall()

        # restore quantities to suppliers
        for product_name, quantity in items:
            restore_product_quantity(cursor, product_name, quantity)

        # delete order and items
        cursor.execute('DELETE FROM order_items WHERE order_id = %s', (order_id,))
        cursor.execute('DELETE FROM orders WHERE order_number = %s', (order_number,))

def restore_product_quantity(cursor, product_name, quantity_to_restore):
    # Get all confirmed suppliers for this product, in reverse order of deduction (newest last)
    cursor.execute('''
        SELECT id, quantity FROM suppliers
        WHERE products = %s AND status = 'Confirmed'
        ORDER BY id DESC
    ''', (product_name,))
    rows = cursor.fetchall()

    remaining = quantity_to_restore

    for supplier_id, current_quantity in rows:
        if remaining <= 0:
            break

        # restore to suppliers
        new_quantity = current_quantity + remaining
        cursor.execute('UPDATE suppliers SET quantity = %s WHERE id = %s', (new_quantity, supplier_id))
        remaining = 0

    # After restoring, recalculate total stock and record change
    cursor.execute('''
        SELECT SUM(quantity) FROM suppliers
        WHERE products = %s AND status = 'Confirmed'
    ''', (product_name,))
    total_quantity = cursor.fetchone()[0] or 0

    record_quantity_change(cursor, product_name, total_quantity)

def update_order_status(order_number, new_status):
        conn = get_db_connection()
        cursor = conn.cursor()

        if new_status == 'Completed':
            # Fetch order_id and items
            cursor.execute('SELECT order_id FROM orders WHERE order_number = %s', (order_number,))
            order = cursor.fetchone()
            if not order:
                return "Order not found"
            order_id = order[0]

            cursor.execute('SELECT product_name, quantity FROM order_items WHERE order_id = %s', (order_id,))
            items = cursor.fetchall()

            # Check stock availability
            for product_name, quantity in items:
                cursor.execute('''
                    SELECT SUM(quantity) FROM suppliers
                    WHERE products = %s AND status = 'Confirmed'
                ''', (product_name,))
                total_stock = cursor.fetchone()[0] or 0
                if quantity > total_stock:
                    return f"Insufficient stock for {product_name}"

            # Deduct stock and record quantity change
            for product_name, quantity in items:
                subtract_product_quantity(cursor, product_name, quantity)

        # update status
        cursor.execute('UPDATE orders SET status = %s WHERE order_number = %s', (new_status, order_number))
        conn.commit()

def get_all_orders():
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM orders')
        orders = cursor.fetchall()

        columns = ['order_id', 'order_number', 'order_date', 'customer_name', 'customer_phone', 'payment_method', 'status', 'total_price']
        return [dict(zip(columns, row)) for row in orders]

@orders_blueprint.route('/view_orders')
def view_orders():
    search_query = request.args.get('search', '').strip()
    conn = get_db_connection()
    cursor = conn.cursor()
    if search_query:
        cursor.execute('''
                SELECT * FROM orders
                WHERE order_number LIKE %s OR customer_name LIKE %s
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
        conn = get_db_connection()
        cursor = conn.cursor()
        while True:
            code = ''.join(random.choices('ABCDEFGHIJKLMNOP0123456789', k=8))
            order_number = f"ORDER-{code}"
            cursor.execute("SELECT 1 FROM orders WHERE order_number = %s", (order_number,))
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

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name, contact FROM customers")
    customers = [{'name': row[0], 'contact': row[1]} for row in cursor.fetchall()]
    conn.close()

    orders = get_all_orders()
    return render_template('create_order.html', orders=orders, customers=customers)

