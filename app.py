from flask import Flask, request, render_template, redirect, session, flash
from db_config import get_connection
import hashlib
import os
from datetime import date, datetime
from dotenv import load_dotenv
from collections import defaultdict

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

    # Get total credit
    cursor.execute("""
        SELECT SUM(t.amount) AS total_credit
        FROM transactions t
        JOIN categories c ON t.categoryID = c.categoryID
        WHERE t.userID = %s AND c.type = 'credit'
    """, (user_id,))
    credit = cursor.fetchone().get('total_credit') or 0

    # Get total debit
    cursor.execute("""
        SELECT SUM(t.amount) AS total_debit
        FROM transactions t
        JOIN categories c ON t.categoryID = c.categoryID
        WHERE t.userID = %s AND c.type = 'debit'
    """, (user_id,))
    debit = cursor.fetchone().get('total_debit') or 0

    # Base query
    query = """
        SELECT t.*, c.name AS category, c.type
        FROM transactions t
        JOIN categories c ON t.categoryID = c.categoryID
        WHERE t.userID = %s
    """
    values = [user_id]

    # Filtering logic
    if (min_amount := request.args.get('min_amount')):
        query += " AND t.amount >= %s"
        values.append(float(min_amount))

    if (max_amount := request.args.get('max_amount')):
        query += " AND t.amount <= %s"
        values.append(float(max_amount))

    if (date_from := request.args.get('date_from')):
        query += " AND t.date >= %s"
        values.append(date_from)

    if (date_to := request.args.get('date_to')):
        query += " AND t.date <= %s"
        values.append(date_to)

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
    # Sort transactions by date ascending for running balance
    transactions.sort(key=lambda x: x['date'])

    running_balance = 0
    for tx in transactions:
        if tx['type'] == 'credit':
            running_balance += float(tx['amount'])
        else:
            running_balance -= float(tx['amount'])
        tx['balance'] = round(running_balance, 2)

# Reverse back if needed for display (latest first)
    transactions.reverse()

    # Load categories
    cursor.execute("""
        SELECT * FROM categories
        WHERE userID = %s OR userID IS NULL
    """, (user_id,))
    categories = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        'dashboard.html',
        credit=credit,
        debit=debit,
        balance=credit - debit,
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


@app.route('/edit_category/<int:category_id>', methods=['GET', 'POST'])
def edit_category(category_id):
    if 'userID' not in session:
        return redirect('/login')

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM categories WHERE categoryID = %s "
        "AND (userID = %s OR userID IS NULL)",
        (category_id, session['userID'])
    )
    category = cursor.fetchone()

    if not category:
        flash('Category not found or unauthorized.', 'danger')
        return redirect('/categories')

    if request.method == 'POST':
        new_name = request.form.get('name')
        new_type = request.form.get('type')
        cursor.execute("""
            UPDATE categories
            SET name = %s, type = %s
            WHERE categoryID = %s""", (new_name, new_type, category_id))
        conn.commit()
        flash('Category updated successfully!', 'success')
        return redirect('/categories')
    return render_template('edit_category.html', category=category)


@app.route('/delete_category/<int:category_id>', methods=['POST'])
def delete_category(category_id):
    if 'userID' not in session:
        return redirect('/login')

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)  # Use dictionary cursor

    cursor.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE categoryID = %s",
        (category_id,))
    result = cursor.fetchone()
    count = result['count'] if result else 0
    if count > 0:
        flash('Cannot delete category with existing transactions.', 'danger')
        cursor.close()
        conn.close()
        return redirect('/categories')
    cursor.execute(
        "DELETE FROM categories WHERE categoryID = %s AND "
        "(userID = %s OR userID IS NULL)",
        (category_id, session['userID']))
    conn.commit()
    cursor.close()
    conn.close()
    flash('Category deleted successfully!', 'success')
    return redirect('/categories')


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


@app.route('/report', methods=['GET', 'POST'])
def report():
    if 'userID' not in session:
        return redirect('/login')

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session['userID']

    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    tx_type = request.args.get('type')
    category_id = request.args.get('categoryID')

    query = """SELECT t.*, c.name AS category, c.type
               FROM transactions t
               JOIN categories c ON t.categoryID = c.categoryID
               WHERE t.userID = %s"""
    values = [user_id]

    if start_date:
        query += " AND t.date >= %s"
        values.append(start_date)
    if end_date:
        query += " AND t.date <= %s"
        values.append(end_date)
    if tx_type:
        query += " AND c.type = %s"
        values.append(tx_type)
    if category_id:
        query += " AND t.categoryID = %s"
        values.append(int(category_id))

    query += " ORDER BY t.date DESC"
    cursor.execute(query, values)
    transactions = cursor.fetchall()

    total_credit = sum(t['amount'] for t in transactions
                       if t['type'] == 'credit')
    total_debit = sum(t['amount'] for t in transactions
                      if t['type'] == 'debit')
    balance = total_credit - total_debit

    category_spend = defaultdict(float)
    category_count = defaultdict(int)
    monthly_income = defaultdict(float)
    monthly_expense = defaultdict(float)
    transactions_amount = []

    for tx in transactions:
        if tx['type'] == 'debit':
            category_spend[tx['category']] += float(tx['amount'])
            category_count[tx['category']] += 1

        if tx['type'] == 'credit':
            monthly_income[tx['date'].strftime('%Y-%m')] += float(tx['amount'])

        if tx['type'] == 'debit':
            monthly_expense[tx['date'].strftime('%Y%m')] += float(tx['amount'])

        transactions_amount.append(tx['amount'])

    top_spend_category = max(category_spend, key=category_spend.get,
                             default=None)
    most_frequent_category = max(category_count, key=category_count.get,
                                 default=None)
    peak_income_month = max(monthly_income, key=monthly_income.get,
                            default=None)
    average_transaction = round(
        sum(transactions_amount) / len(transactions_amount), 2
    ) if transactions_amount else None

    # Fetch all categories (for filter UI)
    cursor.execute("SELECT * FROM categories WHERE userID = %s "
                   "OR userID IS NULL", (user_id,))
    categories = cursor.fetchall()

    category_labels = list(category_spend.keys())
    category_values = list(category_spend.values())
    monthly_income_labels = list(monthly_income.keys())
    monthly_income_values = list(monthly_income.values())
    monthly_expense_labels = list(monthly_expense.keys())
    monthly_expense_values = list(monthly_expense.values())

    cursor.close()
    conn.close()

    return render_template('report.html',
                           transactions=transactions,
                           total_credit=total_credit,
                           total_debit=total_debit,
                           balance=balance,
                           top_spend_category=top_spend_category,
                           most_frequent_category=most_frequent_category,
                           peak_income_month=peak_income_month,
                           average_transaction=average_transaction,
                           categories=categories,
                           category_labels=category_labels,
                           category_values=category_values,
                           monthly_income_labels=monthly_income_labels,
                           monthly_income_values=monthly_income_values,
                           monthly_expense_values=monthly_expense_values,
                           monthly_expense_labels=monthly_expense_labels
                           )


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
