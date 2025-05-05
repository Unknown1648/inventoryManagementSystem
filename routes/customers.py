from flask import Blueprint, render_template, request, redirect, url_for
from routes.database import get_db_connection

customers_blueprint = Blueprint('customers', __name__)

# fetch all customers
@customers_blueprint.route('/get_all_customers')
def get_customers():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM customers')
    customers = cursor.fetchall()
    conn.close()
    return customers

# Add new customer
def add_customer(name, contact, email, address, payment_method):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO customers (name, contact, email, address, payment_method)
        VALUES (%s, %s, %s, %s, %s)
    ''', (name, contact, email, address, payment_method))
    conn.commit()
    conn.close()

# fetch customr data by ID
def get_customer_by_id(customer_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM customers WHERE customer_id = %s', (customer_id,))
    customer = cursor.fetchone()
    conn.close()

    if customer:
        return {
            'customer_id': customer[0],
            'name': customer[1],
            'contact': customer[2],
            'email': customer[3],
            'address': customer[4],
            'payment_method': customer[5]
        }
    return None

# Update customer details
def update_customer(customer_id, name, contact, email, address, payment_method):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE customers
        SET name = %s, contact = %s, email = %s, address = %s, payment_method = %s
        WHERE customer_id = %s
    ''', (name, contact, email, address, payment_method, customer_id))
    conn.commit()
    conn.close()

@customers_blueprint.route('/edit_customer/<int:customer_id>', methods=['GET', 'POST'])
def edit_customer(customer_id):
    customer = get_customer_by_id(customer_id)

    if request.method == 'POST':
        name = request.form['name']
        contact = request.form['contact']
        email = request.form['email']
        address = request.form['address']
        payment_method = request.form['payment_method']
        update_customer(customer_id, name, contact, email, address, payment_method)

        return redirect(url_for('customers.customers_page'))

    return render_template('edit_customer.html', customer=customer)

# Delete customer
def delete_customer(customer_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM customers WHERE customer_id = %s', (customer_id,))
    conn.commit()
    conn.close()

# Router for managing customers
@customers_blueprint.route('/', methods=['GET', 'POST'])
def customers_page():
    if request.method == 'POST':
        name = request.form['name']
        contact = request.form['contact']
        email = request.form['email']
        address = request.form['address']
        payment_method = request.form['payment_method']
        add_customer(name, contact, email, address, payment_method)

        return redirect(url_for('customers.customers_page'))

    customers = get_customers()
    return render_template('customers.html', customers=customers)

# Route to delete a customer
@customers_blueprint.route('/delete_customer/<int:customer_id>', methods=['GET'])
def delete_customer_route(customer_id):
    delete_customer(customer_id)
    return redirect(url_for('customers.customers_page'))
