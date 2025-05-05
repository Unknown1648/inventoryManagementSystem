from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from routes.stocks import *
from routes.sales import *
from routes.customers import *
from routes.suppliers import *
from routes.orders import *
from routes.database import *
from routes.cloud import start_backup_scheduler
from datetime import datetime, timedelta
import os, atexit
from apscheduler.schedulers.background import BackgroundScheduler
from routes.ai_forecast import get_combined_sales_data, check_and_notify_all
import psycopg2
from psycopg2 import sql

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Initialize PostgreSQL database
initialize_inventory_db()

# Logins
admin_username = "admin"
admin_password = "helloMe"

@app.route('/', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if username == admin_username and password == admin_password:
            session['logged_in'] = True
            return redirect(url_for('dashboard'))
        else:
            error = "Invalid username or password. Please try again."
    
    return render_template('login.html', error=error)

@app.route('/dashboard')
def dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('login'))  # Redirect to login if user is not logged in

    # Fetch the count of urgents from PostgreSQL
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM notifications WHERE status = %s', ('Urgent',))
    urgent_count = cursor.fetchone()[0]
    conn.close()

    return render_template('dashboard.html', urgent_count=urgent_count)


@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

# Blueprints
app.register_blueprint(manage_stocks, url_prefix='/stocks')  
app.register_blueprint(sales_blueprint, url_prefix='/sales')
app.register_blueprint(customers_blueprint, url_prefix='/customers')
app.register_blueprint(suppliers_blueprint, url_prefix='/suppliers')
app.register_blueprint(orders_blueprint, url_prefix='/orders')

@app.route('/notifications')
def notifications_page():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE notifications SET status = %s WHERE status = %s', ("read", "unread"))
    conn.commit()
    cursor.execute('SELECT id, title, message, status, created_at FROM notifications ORDER BY created_at DESC')
    notifications = cursor.fetchall()
    conn.close()
    return render_template('notification.html', notifications=notifications)

@app.route('/sales-history', methods=['GET'])
def sales_history():
    df = get_combined_sales_data()
    grouped = df.groupby(['order_date', 'product_name'])['quantity'].sum().reset_index()

    # Convert datetime to string for JSON serialization
    grouped['order_date'] = grouped['order_date'].astype(str)

    return grouped.to_dict(orient='records')

def combined_job():
    check_and_notify_all()
    generate_weekly_notifications()

if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    # Scheduler to check notifications and forecasts.
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=combined_job, trigger="interval", minutes=1)
    scheduler.start()

    # Start cloud backup scheduler (1 week)
    backup_scheduler = start_backup_scheduler(604800)
    backup_scheduler.start()

    # Shut down properly
    atexit.register(lambda: scheduler.shutdown())
    atexit.register(lambda: backup_scheduler.shutdown())
    
@app.route('/product_quantity_over_time', methods=['GET'])
def product_quantity_over_time():
    product_filter = request.args.get('product_name')
    offset = int(request.args.get('offset', 0))

    end_time = datetime.now() - timedelta(hours=24 * offset)
    start_time = end_time - timedelta(hours=24)

    times = [(start_time + timedelta(hours=i)).strftime('%Y-%m-%d %H:00') for i in range(25)]

    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch all distinct product names from the product_quantity_changes table
    cursor.execute(''' 
        SELECT DISTINCT product_name
        FROM product_quantity_changes
    ''')
    all_products = [row[0] for row in cursor.fetchall()]

    if product_filter:
        cursor.execute(''' 
            SELECT product_name, change_type, quantity_changed, change_date
            FROM product_quantity_changes
            WHERE change_date BETWEEN %s AND %s AND product_name = %s
            ORDER BY change_date
        ''', (start_time, end_time, product_filter))
    else:
        cursor.execute(''' 
            SELECT product_name, change_type, quantity_changed, change_date
            FROM product_quantity_changes
            WHERE change_date BETWEEN %s AND %s
            ORDER BY product_name, change_date
        ''', (start_time, end_time))

    changes = cursor.fetchall()
    conn.close()

    if not changes:
        print("No data found for the specified time range.")
        changes = [(product, 'Increase', 0, start_time) for product in all_products]

    product_hourly_changes = {}
    for product, change_type, qty_changed, change_date in changes:
        hour_str = change_date.strftime('%Y-%m-%d %H:00')
        product_hourly_changes.setdefault(product, {}).setdefault(hour_str, 0)
        if change_type == 'Increase':
            product_hourly_changes[product][hour_str] += qty_changed
        else:
            product_hourly_changes[product][hour_str] -= qty_changed

    result = {}

    for product in product_hourly_changes:
        hourly_quantities = []
        current_qty = 0

        for hour in times:
            hourly_change = product_hourly_changes[product].get(hour, 0)
            current_qty += hourly_change
            current_qty = max(current_qty, 0)
            hourly_quantities.append(current_qty)

        result[product] = {
            'dates': times,
            'quantities': hourly_quantities
        }

    return jsonify(result)

if __name__ == '__main__':
    app.run(debug=True)
