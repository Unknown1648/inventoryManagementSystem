from flask import Flask, render_template, request, redirect, url_for, session, jsonify, request
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

app = Flask(__name__)
app.secret_key = 'your_secret_key'

initialize_inventory_db()

# logins
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
        return redirect(url_for('login'))  # Redirect to login if user != logged in

    # Fetch the count of urgents
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM notifications WHERE status = "Urgent"')
    urgent_count = cursor.fetchone()[0]
    conn.close()

    return render_template('dashboard.html', urgent_count=urgent_count)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

#blueprints
app.register_blueprint(manage_stocks, url_prefix='/stocks')  
app.register_blueprint(sales_blueprint, url_prefix='/sales')
app.register_blueprint(customers_blueprint, url_prefix='/customers')
app.register_blueprint(suppliers_blueprint, url_prefix='/suppliers')
app.register_blueprint(orders_blueprint, url_prefix='/orders')

@app.route('/notifications')
def notifications_page():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('UPDATE notifications SET status = "read" WHERE status = "unread"')
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
    # Scheduler for checking notifications, forecasts, etc.
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=combined_job, trigger="interval", minutes=1)
    scheduler.start()

    # start cloud backup scheduler (1 week)
    backup_scheduler = start_backup_scheduler(604800)
    backup_scheduler.start()

    # shut down properly
    atexit.register(lambda: scheduler.shutdown())
    atexit.register(lambda: backup_scheduler.shutdown())

@app.route('/product_quantity_over_time', methods=['GET'])
def product_quantity_over_time():
    product_filter = request.args.get('product_name')

    end_date = datetime.today().date()
    start_date = end_date - timedelta(days=6)
    dates = [(start_date + timedelta(days=i)).isoformat() for i in range(7)]

    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()

        # fetch all changes for the product in the last 7 days
        if product_filter:
            cursor.execute(''' 
                SELECT product_name, change_type, quantity_changed, DATE(change_date)
                FROM product_quantity_changes
                WHERE DATE(change_date) BETWEEN ? AND ? AND product_name = ?
                ORDER BY change_date
            ''', (start_date.isoformat(), end_date.isoformat(), product_filter))
        else:
            cursor.execute('''
                SELECT product_name, change_type, quantity_changed, DATE(change_date)
                FROM product_quantity_changes
                WHERE DATE(change_date) BETWEEN ? AND ?
                ORDER BY product_name, change_date
            ''', (start_date.isoformat(), end_date.isoformat()))
        
        changes = cursor.fetchall()

    # organize changes
    product_daily_changes = {}
    for product, change_type, qty_changed, change_date in changes:
        product_daily_changes.setdefault(product, {}).setdefault(change_date, 0)
        if change_type == 'Increase':
            product_daily_changes[product][change_date] += qty_changed
        else:
            product_daily_changes[product][change_date] -= qty_changed

    result = {}

    for product in product_daily_changes:
        daily_quantities = []
        current_qty = 0

        # initialize starting quantity on the first day of the timeframe
        for day in dates:
            daily_change = product_daily_changes[product].get(day, 0)
            current_qty += daily_change
            current_qty = max(current_qty, 0)
            daily_quantities.append(current_qty)

        result[product] = {
            "dates": dates,
            "quantities": daily_quantities
        }

    return jsonify(result)

if __name__ == '__main__':
    app.run(debug=True)