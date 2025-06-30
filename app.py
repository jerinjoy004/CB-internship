from flask import Flask, request, render_template, redirect, session, flash
from db_config import get_connection
import hashlib
import os
from datetime import date, datetime
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


@app.route('/')
def home():
    return redirect('/login')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = hash_password(request.form.get('password'))

        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO users (name, email, password) "
                           "VALUES (%s, %s, %s)",
                           (name, email, password))
            conn.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect('/login')
        except Exception as e:
            print(f"Registration error: {e}")
            flash("Error: Email might already be in use.", 'danger')
        finally:
            cursor.close()
            conn.close()
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = hash_password(request.form.get('password'))

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""SELECT * FROM users
                          WHERE email = %s AND password = %s
                          AND status = 'active'""", (email, password))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user:
            session['userID'] = user['userID']
            session['name'] = user['name']
            flash(f"Welcome back, {user['name']}!", 'success')
            return redirect('/dashboard')
        else:
            flash('Invalid email or password.', 'danger')
    return render_template('login.html')


@app.route('/dashboard')
def dashboard():
    if 'userID' not in session:
        return redirect('/login')

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session['userID']

    # Get income
    cursor.execute("""SELECT SUM(t.amount) AS total_income
                      FROM transactions t
                      JOIN categories c ON t.categoryID = c.categoryID
                      WHERE t.userID = %s AND c.type = 'income'""", (user_id,))
    income = cursor.fetchone().get('total_income') or 0

    # Get expense
    cursor.execute("""SELECT SUM(t.amount) AS total_expense
                      FROM transactions t
                      JOIN categories c ON t.categoryID = c.categoryID
                      WHERE t.userID = %s AND c.type = 'expense'""",
                   (user_id,))
    expense = cursor.fetchone().get('total_expense') or 0

    # Filters
    query = """SELECT t.*, c.name AS category, c.type
               FROM transactions t
               JOIN categories c ON t.categoryID = c.categoryID
               WHERE t.userID = %s"""
    values = [user_id]

    # Apply filters
    if (min_amount := request.args.get('min_amount')):
        query += " AND t.amount >= %s"
        values.append(float(min_amount))
    if (max_amount := request.args.get('max_amount')):
        query += " AND t.amount <= %s"
        values.append(float(max_amount))
    if (date_from := request.args.get('date_from')):
        query += " AND t.date >= %s"
        values.append(date.strptime(date_from, '%Y-%m-%d'))
    if (date_to := request.args.get('date_to')):
        query += " AND t.date <= %s"
        values.append(date.strptime(date_to, '%Y-%m-%d'))
    if (category_id := request.args.get('categoryID')):
        query += " AND t.categoryID = %s"
        values.append(int(category_id))
    if (search_text := request.args.get('search_text')):
        search = f"%{search_text}%"
        query += " AND (t.title LIKE %s OR t.notes LIKE %s)"
        values += [search, search]
    if (type_filter := request.args.get('type')):
        query += " AND c.type = %s"
        values.append(type_filter)

    query += " ORDER BY t.date DESC"
    cursor.execute(query, values)
    transactions = cursor.fetchall()

    cursor.execute("SELECT * FROM categories WHERE userID = %s "
                   "OR userID IS NULL", (user_id,))
    categories = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        'dashboard.html',
        income=income,
        expense=expense,
        balance=income - expense,
        recent_transactions=transactions,
        categories=categories
    )


@app.route('/categories', methods=['GET', 'POST'])
def manage_categories():
    if 'userID' not in session:
        return redirect('/login')

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        name = request.form.get('name')
        type_ = request.form.get('type')
        user_id = session['userID']

        cursor.execute("INSERT INTO categories (name, type, userID) "
                       "VALUES (%s, %s, %s)",
                       (name, type_, user_id))
        conn.commit()
        flash('Category added successfully!', 'success')
        return redirect('/categories')

    cursor.execute("SELECT * FROM categories WHERE userID = %s OR "
                   "userID IS NULL", (session['userID'],))
    categories = cursor.fetchall()

    cursor.close()
    conn.close()
    return render_template('categories.html', categories=categories)


@app.route('/transactions', methods=['GET', 'POST'])
def add_transactions():
    if 'userID' not in session:
        return redirect('/login')

    user_id = session['userID']
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        try:
            title = request.form.get('title')
            amount = float(request.form.get('amount'))
            txn_date = datetime.strptime(
                request.form.get('date'),
                '%Y-%m-%d'
            ).date()
            notes = request.form.get('notes')
            category_id = request.form.get('categoryID')

            cursor.execute(
                """INSERT INTO transactions
                   (title, amount, date, notes, categoryID, userID)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (title, amount, txn_date, notes, category_id, user_id)
            )
            conn.commit()
            flash('Transaction added successfully!', 'success')
        except Exception as e:
            print(f"Transaction error: {e}")
            flash('There was a problem adding the transaction.', 'danger')
        return redirect('/transactions')

    cursor.execute("SELECT * FROM categories WHERE userID = %s OR "
                   "userID IS NULL", (user_id,))
    categories = cursor.fetchall()

    cursor.close()
    conn.close()
    today = date.today().isoformat()
    return render_template('transactions.html', categories=categories,
                           current_date=today)


@app.route('/logout')
def logout():
    if 'userID' not in session:
        flash('You are not logged in.', 'warning')
    else:
        session.clear()
        flash('You have been logged out.', 'info')
    return redirect('/login')


if __name__ == '__main__':
    app.run(debug=True)
