from flask import Blueprint, render_template, request, redirect, url_for, flash
from routes.database import get_db_connection
import datetime

suppliers_blueprint = Blueprint('suppliers', __name__)

def execute_db_query(query, params=(), fetch=False):
    """Utility function to execute a database query and handle connection and cursor management."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(query, params)
    if fetch:
        result = cursor.fetchall()
    else:
        conn.commit()
        result = None
    conn.close()
    return result

# Record quantity change in product_quantity_changes and update snapshot
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
    ON CONFLICT (product_name)
    DO UPDATE SET last_quantity = EXCLUDED.last_quantity
''', (product_name, new_quantity))


# Add supplier
def add_supplier(supplier_name, contact, products, initial_quantity, status, price_per_product, delivery_price, total_price):
    # insert the new supplier into the suppliers table
    insert_query = '''
        INSERT INTO suppliers (
            supplier_name, contact, products, initial_quantity, quantity, entered_date, status,
            price_per_product, delivery_price, total_price
        ) VALUES (%s, %s, %s, %s, %s, NOW(), %s, %s, %s, %s)
    '''
    params = (supplier_name, contact, products, initial_quantity, initial_quantity, status, price_per_product, delivery_price, total_price)
    execute_db_query(insert_query, params)

    #calculate total quantity for product from all confirmed suppliers
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT SUM(quantity) FROM suppliers
        WHERE products = %s AND status = 'Confirmed'
    ''', (products,))
    total_quantity = cursor.fetchone()[0] or 0

    # record change in product quantity based on total confirmed quantity
    record_quantity_change(cursor, products, total_quantity)
    
    conn.commit()
    conn.close()

def get_all_suppliers():
    query = 'SELECT * FROM suppliers'
    suppliers = execute_db_query(query, fetch=True)

    columns = [
        'id', 'supplier_name', 'contact', 'products',
        'initial_quantity', 'quantity', 'entered_date', 'status',
        'price_per_product', 'delivery_price', 'total_price'
    ]

    supplier_dicts = [dict(zip(columns, row)) for row in suppliers]

    return supplier_dicts

# Delete supplier
@suppliers_blueprint.route('/delete_supplier/<int:supplier_id>', methods=['POST'])
def delete_supplier(supplier_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    # fetch supplier's product and quantity
    cursor.execute('SELECT products, quantity FROM suppliers WHERE id = %s', (supplier_id,))
    supplier = cursor.fetchone()

    if not supplier:
        return redirect(url_for('suppliers.suppliers_management_page'))

    product_name, supplier_quantity = supplier

    # delete that supplier
    cursor.execute('DELETE FROM suppliers WHERE id = %s', (supplier_id,))

    # recalculate total quantity for the product
    cursor.execute('''
        SELECT SUM(quantity) FROM suppliers
        WHERE products = %s AND status = 'Confirmed'
    ''', (product_name,))
    total_remaining = cursor.fetchone()[0] or 0

    # record inventory change
    record_quantity_change(cursor, product_name, total_remaining)

    conn.commit()
    conn.close()

    return redirect(url_for('suppliers.suppliers_management_page'))

# editing status
@suppliers_blueprint.route('/edit_status/<int:supplier_id>', methods=['POST'])
def edit_status(supplier_id):
    new_status = request.form.get('new_status')
    if new_status:
        conn = get_db_connection()
        cursor = conn.cursor()

        # get current status, quantity, and product
        cursor.execute('SELECT status, quantity, products FROM suppliers WHERE id = %s', (supplier_id,))
        supplier_data = cursor.fetchone()

        if supplier_data:
            current_status, supplier_quantity, product_name = supplier_data

            # if status change is Pending - Confirmed, check upcoming quantity
            if current_status == "Pending" and new_status == "Confirmed":
                cursor.execute('SELECT SUM(quantity) FROM suppliers WHERE status = "Confirmed"')
                total_confirmed_quantity = cursor.fetchone()[0] or 0
                projected_total = total_confirmed_quantity + supplier_quantity

                if projected_total > 10000:
                    flash("⚠️ Cannot confirm supplier. Total quantity would exceed 10,000 units.", "error")
                    conn.close()
                    return redirect(url_for('suppliers.suppliers_management_page'))

            # update status
            cursor.execute('UPDATE suppliers SET status = %s WHERE id = %s', (new_status, supplier_id))

            # recalculate and update product quantity
            cursor.execute('''
                SELECT SUM(quantity) FROM suppliers
                WHERE products = %s AND status = 'Confirmed'
            ''', (product_name,))
            total_quantity = cursor.fetchone()[0] or 0

            record_quantity_change(cursor, product_name, total_quantity)

            cursor.execute('''
                INSERT INTO product_quantity_snapshot (product_name, last_quantity)
                VALUES (%s, %s)
                ON CONFLICT (product_name) DO UPDATE SET last_quantity = %s
            ''', (product_name, total_quantity, total_quantity))

        conn.commit()
        conn.close()

    return redirect(url_for('suppliers.suppliers_management_page'))

# Suppliers management page route
@suppliers_blueprint.route('/manage_suppliers')
def suppliers_management_page():
    suppliers = get_all_suppliers()
    return render_template('manage_suppliers.html', suppliers=suppliers)

# Manage suppliers route
@suppliers_blueprint.route('/', methods=['GET', 'POST'])
def manage_suppliers():
    if request.method == 'POST':
        supplier_name = request.form['supplier_name']
        contact = request.form['contact']
        products = request.form['products']
        initial_quantity = int(request.form['initial_quantity'])
        status = request.form['status']
        price_per_product = float(request.form['price_per_product'])
        delivery_price = float(request.form['delivery_price'])

        total_price = (initial_quantity * price_per_product) + delivery_price
        add_supplier(supplier_name, contact, products, initial_quantity, status, price_per_product, delivery_price, total_price)

        return redirect(url_for('suppliers.manage_suppliers'))

    suppliers = get_all_suppliers()

    # calculate total confirmed quantity
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT SUM(quantity) FROM suppliers WHERE status = \'Confirmed\'')
    total_confirmed_quantity = cursor.fetchone()[0] or 0
    conn.close()

    return render_template('suppliers.html', suppliers=suppliers, total_confirmed_quantity=total_confirmed_quantity)
