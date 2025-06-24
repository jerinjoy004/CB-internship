from flask import (
    Flask, request, render_template, redirect, session, flash
)

from db_config import get_connection
import hashlib
import os

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
        name = request.form['name']
        email = request.form['email']
        password = hash_password(request.form['password'])

        conn = get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                (
                    "INSERT INTO users (name, email, password) "
                    "VALUES (%s, %s, %s)"
                ),
                (name, email, password)
            )
            conn.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect('/login')
        except Exception:
            flash("Error: Email already exists.", 'danger')
        finally:
            cursor.close()
            conn.close()

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = hash_password(request.form['password'])
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM users WHERE email = %s AND password = %s "
            "AND status = 'active'",
            (email, password)
        )
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        if user:
            session['userID'] = user['userID']
            session['name'] = user['name']
            flash(f'Welcome back, {user["name"]}!', 'success')
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

    cursor.execute(
        "SELECT SUM(t.amount) AS total_income "
        "FROM transactions t "
        "JOIN categories c ON t.categoryID = c.categoryID "
        "WHERE t.userID = %s AND c.type = 'income'",
        (user_id,)
    )
    income = cursor.fetchone()['total_income'] or 0

    cursor.execute(
        "SELECT SUM(t.amount) AS total_expense "
        "FROM transactions t "
        "JOIN categories c ON t.categoryID = c.categoryID "
        "WHERE t.userID = %s AND c.type = 'expense'",
        (user_id,)
    )
    expense = cursor.fetchone()['total_expense'] or 0

    cursor.execute("""
        SELECT t.title, t.amount, t.date, c.name AS category, c.type, t.notes
        FROM transactions t
        JOIN categories c ON t.categoryID = c.categoryID
        WHERE t.userID = %s
        ORDER BY t.date DESC
        LIMIT 10
    """, (user_id,))
    recent = cursor.fetchall()

    cursor.close()
    conn.close()

    balance = income - expense
    return render_template(
        'dashboard.html',
        income=income,
        expense=expense,
        balance=balance,
        recent_transactions=recent
    )


@app.route('/categories', methods=['GET', 'POST'])
def manage_categories():
    if 'userID' not in session:
        return redirect('/login')

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        name = request.form['name']
        type_ = request.form['type']
        user_id = session['userID']

        cursor.execute(
            "INSERT INTO categories (name, type, userID) "
            "VALUES (%s, %s, %s)",
            (name, type_, user_id)
        )
        conn.commit()
        flash('Category added successfully!', 'success')
        return redirect('/categories')

    cursor.execute(
        "SELECT * FROM categories WHERE userID = %s OR userID IS NULL",
        (session['userID'],)
    )
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
        title = request.form['title']
        amount = float(request.form['amount'])
        date = request.form['date']
        notes = request.form['notes']
        category_id = request.form['categoryID']

        cursor.execute(
            "INSERT INTO transactions (title, amount, date, notes,"
            " categoryID, userID) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (title, amount, date, notes, category_id, user_id)
        )
        conn.commit()
        flash('Transaction added successfully!', 'success')
        return redirect('/transactions')

    cursor.execute(
        "SELECT * FROM categories WHERE userID = %s OR userID IS NULL",
        (user_id,)
    )
    categories = cursor.fetchall()

    cursor.close()
    conn.close()
    return render_template('transactions.html', categories=categories)


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect('/login')


if __name__ == '__main__':
    app.run(debug=True)
