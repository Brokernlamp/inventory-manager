from db import get_connection

from dotenv import load_dotenv
load_dotenv()
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, session
import os
from datetime import datetime
import urllib.parse
import hashlib
import secrets
from db_config import PostgreSQLDB

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

# Main database for users
MAIN_DB = PostgreSQLDB('inventory_main')

def init_main_db():
    """Initialize main database with users table"""
    MAIN_DB.create_database()
    conn = MAIN_DB.get_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(255) UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                database_name VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"Error initializing main database: {e}")
        return False

def hash_password(password, salt):
    """Hash password with salt"""
    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)

def verify_password(password, salt, password_hash):
    """Verify password against hash"""
    return hash_password(password, salt) == password_hash

def get_user_db():
    """Get current user's database instance"""
    if 'user_id' not in session:
        return None

    conn = MAIN_DB.get_connection()
    if not conn:
        return None
    
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT database_name FROM users WHERE id=%s', (session['user_id'],))
        result = cursor.fetchone()
        cursor.close()
        conn.close()

        if result:
            return PostgreSQLDB(result['database_name'])
        return None
    except Exception as e:
        print(f"Error getting user database: {e}")
        return None

# WhatsApp message template
WHATSAPP_TEMPLATE = """
🚨 LOW STOCK ALERT 🚨

Dear {supplier_name},

We need to restock the following item:

📦 Product: {product_name}
📊 Current Stock: {current_quantity}
⚠️ Threshold: {threshold}
💰 Unit Price: ${price}

Please arrange for restocking at your earliest convenience.

Thank you for your partnership!

Best regards,
Inventory Management System
"""

def generate_whatsapp_link(phone_number, message):
    """Generate WhatsApp Web link with pre-filled message"""
    try:
        clean_phone = ''.join(c for c in phone_number if c.isdigit() or c == '+')
        encoded_message = urllib.parse.quote(message)
        whatsapp_url = f"https://wa.me/{clean_phone.replace('+', '')}?text={encoded_message}"
        return whatsapp_url
    except Exception as e:
        print(f"Error generating WhatsApp link: {str(e)}")
        return None

def check_low_stock():
    """Check for low stock items and return alerts data"""
    user_db = get_user_db()
    if not user_db:
        return []

    conn = user_db.get_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT p.id, p.name, p.quantity, p.threshold, p.price,
                   s.name, s.phone
            FROM products p
            JOIN suppliers s ON p.supplier_id = s.id
            WHERE p.quantity <= p.threshold
        ''')

        low_stock_items = cursor.fetchall()
        cursor.close()
        conn.close()

        alerts = []
        for item in low_stock_items:
            message = WHATSAPP_TEMPLATE.format(
                supplier_name=item['name'],
                product_name=item['name'],
                current_quantity=item['quantity'],
                threshold=item['threshold'],
                price=item['price']
            )

            whatsapp_link = generate_whatsapp_link(item['phone'], message)
            alerts.append({
                'product_name': item['name'],
                'supplier_name': item['name'],
                'supplier_phone': item['phone'],
                'whatsapp_link': whatsapp_link,
                'message': message
            })
        
        return alerts
    except Exception as e:
        print(f"Error checking low stock: {e}")
        return []

# Authentication routes
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = MAIN_DB.get_connection()
        if not conn:
            flash('Database connection error!', 'error')
            return render_template('login.html')

        try:
            cursor = conn.cursor()
            cursor.execute('SELECT id, password_hash, salt FROM users WHERE username=%s', (username,))
            user = cursor.fetchone()
            cursor.close()
            conn.close()

            if user and verify_password(password, user['salt'], user['password_hash']):
                session['user_id'] = user['id']
                session['username'] = username
                flash('Login successful!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid username or password!', 'error')
        except Exception as e:
            flash(f'Login error: {str(e)}', 'error')

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        if password != confirm_password:
            flash('Passwords do not match!', 'error')
            return render_template('register.html')

        salt = secrets.token_hex(16)
        password_hash = hash_password(password, salt)
        db_name = f"inventory_{username}_{secrets.token_hex(8)}"

        conn = MAIN_DB.get_connection()
        if not conn:
            flash('Database connection error!', 'error')
            return render_template('register.html')

        try:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO users (username, password_hash, salt, database_name)
                VALUES (%s, %s, %s, %s)
            ''', (username, password_hash, salt, db_name))
            conn.commit()
            cursor.close()
            conn.close()

            # Initialize user's inventory database
            user_db = PostgreSQLDB(db_name)
            user_db.create_database()
            user_db.init_tables()

            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash(f'Registration error: {str(e)}', 'error')

    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

def login_required(f):
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

# Product CRUD operations
@app.route('/products')
@login_required
def products():
    user_db = get_user_db()
    if not user_db:
        flash('Database error!', 'error')
        return redirect(url_for('dashboard'))

    conn = user_db.get_connection()
    if not conn:
        flash('Database connection error!', 'error')
        return redirect(url_for('dashboard'))

    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT p.id, p.name, p.description, p.quantity, p.threshold, 
                   p.price, s.name as supplier_name, p.created_at
            FROM products p
            LEFT JOIN suppliers s ON p.supplier_id = s.id
            ORDER BY p.created_at DESC
        ''')
        products = cursor.fetchall()
        cursor.close()
        conn.close()
        return render_template('products.html', products=products)
    except Exception as e:
        flash(f'Error loading products: {str(e)}', 'error')
        return redirect(url_for('dashboard'))

@app.route('/products/add', methods=['GET', 'POST'])
@login_required
def add_product():
    user_db = get_user_db()
    if not user_db:
        flash('Database error!', 'error')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        quantity = int(request.form['quantity'])
        threshold = int(request.form['threshold'])
        price = float(request.form['price'])
        supplier_id = request.form['supplier_id'] if request.form['supplier_id'] else None

        conn = user_db.get_connection()
        if not conn:
            flash('Database connection error!', 'error')
            return redirect(url_for('products'))

        try:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO products (name, description, quantity, threshold, price, supplier_id)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (name, description, quantity, threshold, price, supplier_id))
            conn.commit()
            cursor.close()
            conn.close()

            flash('Product added successfully!', 'success')
            return redirect(url_for('products'))
        except Exception as e:
            flash(f'Error adding product: {str(e)}', 'error')

    # Get suppliers for the dropdown
    conn = user_db.get_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute('SELECT id, name FROM suppliers ORDER BY name')
            suppliers = cursor.fetchall()
            cursor.close()
            conn.close()
        except Exception as e:
            suppliers = []
            flash(f'Error loading suppliers: {str(e)}', 'warning')
    else:
        suppliers = []

    return render_template('add_product.html', suppliers=suppliers)

@app.route('/products/edit/<int:product_id>', methods=['GET', 'POST'])
@login_required
def edit_product(product_id):
    user_db = get_user_db()
    if not user_db:
        flash('Database error!', 'error')
        return redirect(url_for('dashboard'))

    conn = user_db.get_connection()
    if not conn:
        flash('Database connection error!', 'error')
        return redirect(url_for('products'))

    try:
        cursor = conn.cursor()

        if request.method == 'POST':
            name = request.form['name']
            description = request.form['description']
            quantity = int(request.form['quantity'])
            threshold = int(request.form['threshold'])
            price = float(request.form['price'])
            supplier_id = request.form['supplier_id'] if request.form['supplier_id'] else None

            cursor.execute('''
                UPDATE products 
                SET name=%s, description=%s, quantity=%s, threshold=%s, price=%s, supplier_id=%s, updated_at=CURRENT_TIMESTAMP
                WHERE id=%s
            ''', (name, description, quantity, threshold, price, supplier_id, product_id))
            conn.commit()
            cursor.close()
            conn.close()

            flash('Product updated successfully!', 'success')
            return redirect(url_for('products'))

        cursor.execute('SELECT * FROM products WHERE id=%s', (product_id,))
        product = cursor.fetchone()

        cursor.execute('SELECT id, name FROM suppliers ORDER BY name')
        suppliers = cursor.fetchall()
        cursor.close()
        conn.close()

        return render_template('edit_product.html', product=product, suppliers=suppliers)
    except Exception as e:
        flash(f'Error editing product: {str(e)}', 'error')
        return redirect(url_for('products'))

@app.route('/products/delete/<int:product_id>')
@login_required
def delete_product(product_id):
    user_db = get_user_db()
    if not user_db:
        flash('Database error!', 'error')
        return redirect(url_for('dashboard'))

    conn = user_db.get_connection()
    if not conn:
        flash('Database connection error!', 'error')
        return redirect(url_for('products'))

    try:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM products WHERE id=%s', (product_id,))
        conn.commit()
        cursor.close()
        conn.close()

        flash('Product deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting product: {str(e)}', 'error')

    return redirect(url_for('products'))

# Supplier CRUD operations
@app.route('/suppliers')
@login_required
def suppliers():
    user_db = get_user_db()
    if not user_db:
        flash('Database error!', 'error')
        return redirect(url_for('dashboard'))

    conn = user_db.get_connection()
    if not conn:
        flash('Database connection error!', 'error')
        return redirect(url_for('dashboard'))

    try:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM suppliers ORDER BY created_at DESC')
        suppliers = cursor.fetchall()
        cursor.close()
        conn.close()
        return render_template('suppliers.html', suppliers=suppliers)
    except Exception as e:
        flash(f'Error loading suppliers: {str(e)}', 'error')
        return redirect(url_for('dashboard'))

@app.route('/suppliers/add', methods=['GET', 'POST'])
@login_required
def add_supplier():
    user_db = get_user_db()
    if not user_db:
        flash('Database error!', 'error')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        name = request.form['name']
        phone = request.form['phone']
        email = request.form['email']
        address = request.form['address']

        conn = user_db.get_connection()
        if not conn:
            flash('Database connection error!', 'error')
            return redirect(url_for('suppliers'))

        try:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO suppliers (name, phone, email, address)
                VALUES (%s, %s, %s, %s)
            ''', (name, phone, email, address))
            conn.commit()
            cursor.close()
            conn.close()

            flash('Supplier added successfully!', 'success')
            return redirect(url_for('suppliers'))
        except Exception as e:
            flash(f'Error adding supplier: {str(e)}', 'error')

    return render_template('add_supplier.html')

@app.route('/suppliers/edit/<int:supplier_id>', methods=['GET', 'POST'])
@login_required
def edit_supplier(supplier_id):
    user_db = get_user_db()
    if not user_db:
        flash('Database error!', 'error')
        return redirect(url_for('dashboard'))

    conn = user_db.get_connection()
    if not conn:
        flash('Database connection error!', 'error')
        return redirect(url_for('suppliers'))

    try:
        cursor = conn.cursor()

        if request.method == 'POST':
            name = request.form['name']
            phone = request.form['phone']
            email = request.form['email']
            address = request.form['address']

            cursor.execute('''
                UPDATE suppliers 
                SET name=%s, phone=%s, email=%s, address=%s
                WHERE id=%s
            ''', (name, phone, email, address, supplier_id))
            conn.commit()
            cursor.close()
            conn.close()

            flash('Supplier updated successfully!', 'success')
            return redirect(url_for('suppliers'))

        cursor.execute('SELECT * FROM suppliers WHERE id=%s', (supplier_id,))
        supplier = cursor.fetchone()
        cursor.close()
        conn.close()

        return render_template('edit_supplier.html', supplier=supplier)
    except Exception as e:
        flash(f'Error editing supplier: {str(e)}', 'error')
        return redirect(url_for('suppliers'))

@app.route('/suppliers/delete/<int:supplier_id>')
@login_required
def delete_supplier(supplier_id):
    user_db = get_user_db()
    if not user_db:
        flash('Database error!', 'error')
        return redirect(url_for('dashboard'))

    conn = user_db.get_connection()
    if not conn:
        flash('Database connection error!', 'error')
        return redirect(url_for('suppliers'))

    try:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM suppliers WHERE id=%s', (supplier_id,))
        conn.commit()
        cursor.close()
        conn.close()

        flash('Supplier deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting supplier: {str(e)}', 'error')

    return redirect(url_for('suppliers'))

@app.route('/check-stock')
@login_required
def check_stock_alerts():
    alerts = check_low_stock()
    if alerts:
        flash(f'Found {len(alerts)} low stock items. Check alerts page for WhatsApp links.', 'warning')
    else:
        flash('All items are well stocked!', 'success')
    return redirect(url_for('alerts'))

@app.route('/dashboard')
@login_required
def dashboard():
    user_db = get_user_db()
    if not user_db:
        flash('Database error!', 'error')
        return redirect(url_for('login'))

    conn = user_db.get_connection()
    if not conn:
        flash('Database connection error!', 'error')
        return redirect(url_for('login'))

    try:
        cursor = conn.cursor()

        # Get total products
        cursor.execute('SELECT COUNT(*) as count FROM products')
        total_products = cursor.fetchone()['count']

        # Get total suppliers
        cursor.execute('SELECT COUNT(*) as count FROM suppliers')
        total_suppliers = cursor.fetchone()['count']

        # Get low stock items
        cursor.execute('SELECT COUNT(*) as count FROM products WHERE quantity <= threshold')
        low_stock_count = cursor.fetchone()['count']

        # Get total inventory value
        cursor.execute('SELECT COALESCE(SUM(quantity * price), 0) as total FROM products')
        total_value = cursor.fetchone()['total']

        # Get recent products for quick management
        cursor.execute('''
            SELECT id, name, description, quantity, threshold, price
            FROM products 
            ORDER BY updated_at DESC 
            LIMIT 10
        ''')
        recent_products = cursor.fetchall()

        cursor.close()
        conn.close()

        return render_template('dashboard.html', 
                             total_products=total_products,
                             total_suppliers=total_suppliers,
                             low_stock_count=low_stock_count,
                             total_value=total_value,
                             recent_products=recent_products)
    except Exception as e:
        flash(f'Error loading dashboard: {str(e)}', 'error')
        return redirect(url_for('login'))

@app.route('/adjust-stock', methods=['POST'])
@login_required
def adjust_stock():
    """Adjust product stock quantity"""
    try:
        data = request.get_json()
        product_id = data.get('product_id')
        change = data.get('change')
        
        if not product_id or change is None:
            return jsonify({'success': False, 'message': 'Invalid data provided'})
        
        user_db = get_user_db()
        if not user_db:
            return jsonify({'success': False, 'message': 'Database error'})

        conn = user_db.get_connection()
        if not conn:
            return jsonify({'success': False, 'message': 'Database connection error'})
        
        cursor = conn.cursor()
        
        # Get current product data
        cursor.execute('SELECT quantity, threshold FROM products WHERE id=%s', (product_id,))
        product = cursor.fetchone()
        
        if not product:
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'message': 'Product not found'})
        
        current_quantity = product['quantity']
        threshold = product['threshold']
        new_quantity = current_quantity + change
        
        # Prevent negative stock
        if new_quantity < 0:
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'message': 'Cannot reduce stock below 0'})
        
        # Update the quantity
        cursor.execute('UPDATE products SET quantity=%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s', 
                     (new_quantity, product_id))
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True, 
            'newStock': new_quantity,
            'threshold': threshold,
            'message': f'Stock updated to {new_quantity}'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/alerts')
@login_required
def alerts():
    """Show low stock alerts"""
    user_db = get_user_db()
    if not user_db:
        flash('Database error!', 'error')
        return redirect(url_for('dashboard'))

    conn = user_db.get_connection()
    if not conn:
        flash('Database connection error!', 'error')
        return redirect(url_for('dashboard'))

    try:
        cursor = conn.cursor()

        # Get low stock items with supplier info
        cursor.execute('''
            SELECT p.id as product_id, p.name as product_name, p.quantity as current_stock, 
                   p.threshold, p.price, s.id as supplier_id, s.name as supplier_name, s.phone as supplier_phone
            FROM products p
            LEFT JOIN suppliers s ON p.supplier_id = s.id
            WHERE p.quantity <= p.threshold
            ORDER BY p.quantity ASC
        ''')
        
        low_stock_items = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return render_template('alerts.html', low_stock_items=low_stock_items)
    except Exception as e:
        flash(f'Error loading alerts: {str(e)}', 'error')
        return redirect(url_for('dashboard'))

@app.route('/send-restock-order', methods=['POST'])
@login_required
def send_restock_order():
    """Generate WhatsApp link for restock order"""
    try:
        data = request.get_json()
        product_id = data.get('product_id')
        supplier_id = data.get('supplier_id')
        quantity = data.get('quantity')
        message = data.get('message')
        
        if not all([product_id, supplier_id, quantity, message]):
            return jsonify({'success': False, 'message': 'Missing required data'})
        
        user_db = get_user_db()
        if not user_db:
            return jsonify({'success': False, 'message': 'Database error'})

        conn = user_db.get_connection()
        if not conn:
            return jsonify({'success': False, 'message': 'Database connection error'})
        
        cursor = conn.cursor()
        
        # Get supplier phone number
        cursor.execute('SELECT phone FROM suppliers WHERE id=%s', (supplier_id,))
        supplier = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not supplier:
            return jsonify({'success': False, 'message': 'Supplier not found'})
        
        # Generate WhatsApp link
        whatsapp_link = generate_whatsapp_link(supplier['phone'], message)
        
        if whatsapp_link:
            return jsonify({
                'success': True, 
                'message': 'WhatsApp link generated successfully',
                'whatsapp_link': whatsapp_link
            })
        else:
            return jsonify({'success': False, 'message': 'Failed to generate WhatsApp link'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/generate-order/<int:supplier_id>')
@login_required
def generate_order(supplier_id):
    """Generate order for supplier based on low stock items"""
    user_db = get_user_db()
    if not user_db:
        flash('Database error!', 'error')
        return redirect(url_for('suppliers'))

    conn = user_db.get_connection()
    if not conn:
        flash('Database connection error!', 'error')
        return redirect(url_for('suppliers'))

    try:
        cursor = conn.cursor()

        # Get supplier info
        cursor.execute('SELECT name, phone FROM suppliers WHERE id=%s', (supplier_id,))
        supplier = cursor.fetchone()

        if not supplier:
            flash('Supplier not found!', 'error')
            return redirect(url_for('suppliers'))

        # Get low stock products from this supplier
        cursor.execute('''
            SELECT name, quantity, threshold, price, (threshold - quantity + 10) as suggested_order
            FROM products 
            WHERE supplier_id=%s AND quantity <= threshold
            ORDER BY name
        ''', (supplier_id,))
        low_stock_products = cursor.fetchall()
        cursor.close()
        conn.close()

        if not low_stock_products:
            flash(f'No low stock items found for {supplier["name"]}', 'info')
            return redirect(url_for('suppliers'))

        # Generate order message
        order_message = f"""
📋 STOCK ORDER REQUEST

Dear {supplier['name']},

Please prepare the following items for delivery:

"""

        total_value = 0
        for product in low_stock_products:
            item_total = product['suggested_order'] * product['price']
            total_value += item_total

            order_message += f"""
📦 {product['name']}
   Current Stock: {product['quantity']}
   Threshold: {product['threshold']}
   Suggested Order: {product['suggested_order']} units
   Unit Price: ₹{product['price']:.2f}
   Total: ₹{item_total:.2f}
"""

        order_message += f"""
💰 TOTAL ORDER VALUE: ₹{total_value:.2f}

Please confirm availability and delivery schedule.

Thank you for your partnership!

Best regards,
Inventory Management System
"""

        # Generate WhatsApp link
        whatsapp_link = generate_whatsapp_link(supplier['phone'], order_message)
        if whatsapp_link:
            flash(f'WhatsApp link generated for {supplier["name"]}. Click the link in the alerts to open WhatsApp Web.', 'success')
            session['whatsapp_link'] = whatsapp_link
            session['order_message'] = order_message
        else:
            flash(f'Order generated but link generation failed. Please contact {supplier["name"]} manually.', 'warning')

        return redirect(url_for('suppliers'))
    except Exception as e:
        flash(f'Error generating order: {str(e)}', 'error')
        return redirect(url_for('suppliers'))

if __name__ == '__main__':
    init_main_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
