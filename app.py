from datetime import date, timedelta, datetime
from flask import Flask, request, render_template, redirect, session, flash
from db_config import get_connection
import hashlib
import os
from dotenv import load_dotenv
from collections import defaultdict
from weasyprint import HTML  # type: ignore
from flask import make_response
import calendar


load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


app.jinja_env.globals['timedelta'] = timedelta


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


@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'userID' not in session:
        return redirect('/login')

    user_id = session['userID']
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Handle Add Category and Add Transaction forms
    if request.method == 'POST':
        form_type = request.form.get('form_type')
        if form_type == 'add_category':
            name = request.form.get('name')
            type_ = request.form.get('type')
            if name and type_:
                cursor.execute(
                    "INSERT INTO categories (name, type, userID)"
                    " VALUES (%s, %s, %s)",
                    (name, type_, user_id)
                )
                conn.commit()
                flash('Category added successfully!', 'success')
            else:
                flash('Please provide all category details.', 'danger')
        elif form_type == 'add_transaction':
            title = request.form.get('title')
            amount = request.form.get('amount')
            date_ = request.form.get('date')
            categoryID = request.form.get('categoryID')
            notes = request.form.get('notes')
            if title and amount and date_ and categoryID:
                cursor.execute(
                    "INSERT INTO transactions "
                    "(userID, categoryID, title, amount, date, notes)"
                    " VALUES (%s, %s, %s, %s, %s, %s)",
                    (user_id, categoryID, title, amount, date_, notes)
                )
                conn.commit()
                flash('Transaction added successfully!', 'success')
            else:
                flash('Please provide all transaction details.', 'danger')
        return redirect('/dashboard')

    # Fetch categories for forms and filters
    cursor.execute(
        "SELECT * FROM categories WHERE userID = %s OR userID IS NULL",
        (user_id,))
    categories = cursor.fetchall()

    # Fetch all transactions for global stats
    cursor.execute(
        """SELECT t.amount, c.type
           FROM transactions t
           JOIN categories c ON t.categoryID = c.categoryID
           WHERE t.userID = %s""",
        (user_id,)
    )
    all_transactions = cursor.fetchall()
    global_credit = sum(t['amount'] for t in all_transactions
                        if t['type'] == 'credit')
    global_debit = sum(t['amount'] for t in all_transactions
                       if t['type'] == 'debit')
    global_balance = global_credit - global_debit

    # Report filters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    tx_type = request.args.get('type')
    category_id = request.args.get('categoryID')

    query = """SELECT t.*, c.name AS category, c.type
               FROM transactions t
               JOIN categories c ON t.categoryID = c.categoryID
               WHERE t.userID = %s"""
    values = [user_id]

    # Month logic
    today = date.today()
    default_month = today.replace(day=1)
    # if today.day < 9:
    #   if default_month.month == 1:
    #      default_month = default_month.replace(year=default_month.year - 1,
    #                                           month=12)
    # else:
    #   default_month = default_month.replace(month=default_month.month - 1)

    month_param = request.args.get('month')
    if month_param:
        try:
            selected_month = datetime.strptime(month_param, "%Y-%m").date()
        except ValueError:
            selected_month = default_month
    else:
        selected_month = default_month

    selected_month_str = selected_month.strftime("%Y-%m")

    # Apply filter conditions
    filters_applied = start_date or end_date or tx_type or category_id

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

    # If no filters, apply month filter
    if not filters_applied:
        year = selected_month.year
        month = selected_month.month
        start = date(year, month, 1)
        last_day = calendar.monthrange(year, month)[1]
        end = date(year, month, last_day)
        query += " AND t.date >= %s AND t.date <= %s"
        values.extend([start.isoformat(), end.isoformat()])

    query += " ORDER BY t.date DESC"
    cursor.execute(query, values)
    transactions = cursor.fetchall()

    # Stats for filtered transactions
    total_credit = sum(t['amount'] for t in transactions
                       if t['type'] == 'credit')
    total_debit = sum(t['amount'] for t in transactions
                      if t['type'] == 'debit')
    total_balance = total_credit - total_debit

    category_spend = defaultdict(float)
    monthly_income = defaultdict(float)
    monthly_expense = defaultdict(float)

    for tx in transactions:
        if tx['type'] == 'debit':
            category_spend[tx['category']] += float(tx['amount'])
            monthly_expense[tx['date'].
                            strftime('%Y-%m')] += float(tx['amount'])
        if tx['type'] == 'credit':
            monthly_income[tx['date'].strftime('%Y-%m')] += float(tx['amount'])

    category_labels = list(category_spend.keys())
    category_values = list(category_spend.values())
    monthly_income_labels = list(monthly_income.keys())
    monthly_income_values = list(monthly_income.values())
    monthly_expense_labels = list(monthly_expense.keys())
    monthly_expense_values = list(monthly_expense.values())

    # Add running balance to transactions
    sorted_tx = sorted(transactions, key=lambda x: x['date'])
    running_balance = 0
    tx_with_balance = []
    for tx in sorted_tx:
        if tx['type'] == 'credit':
            running_balance += tx['amount']
            tx_with_balance.append({
                'date': tx['date'],
                'title': tx['title'],
                'category': tx['category'],
                'notes': tx['notes'],
                'credit': tx['amount'],
                'debit': 0,
                'running_balance': running_balance
            })
        else:
            running_balance -= tx['amount']
            tx_with_balance.append({
                'date': tx['date'],
                'title': tx['title'],
                'category': tx['category'],
                'notes': tx['notes'],
                'credit': 0,
                'debit': tx['amount'],
                'running_balance': running_balance
            })
    tx_with_balance.reverse()

    current_date = date.today().isoformat()
    cursor.close()
    conn.close()

    return render_template(
        'dashboard.html',
        credit=global_credit,
        debit=global_debit,
        balance=global_balance,
        total_credit=total_credit,
        total_debit=total_debit,
        total_balance=total_balance,
        categories=categories,
        category_labels=category_labels,
        category_values=category_values,
        monthly_income_labels=monthly_income_labels,
        monthly_income_values=monthly_income_values,
        monthly_expense_labels=monthly_expense_labels,
        monthly_expense_values=monthly_expense_values,
        current_date=current_date,
        transactions=tx_with_balance,
        selected_month=selected_month_str
    )


@app.route('/export_pdf', methods=['POST'])
def export_pdf():
    if 'userID' not in session:
        return redirect('/login')

    user_id = session['userID']
    username = session['name']

    # Get filter params from hidden inputs
    filters = {
        'start_date': request.form.get('start_date'),
        'end_date': request.form.get('end_date'),
        'type': request.form.get('type'),
        'categoryID': request.form.get('categoryID')
    }

    # Fetch filtered transactions and summary
    transactions, summary_data = get_filtered_data(user_id, filters)

    # Get base64 chart images
    chart_images = {
        'typeChart_img': request.form.get('typeChart_img'),
        'categoryChart_img': request.form.get('categoryChart_img'),
        'monthlyChart_img': request.form.get('monthlyChart_img')
    }

    # Render HTML
    rendered = render_template('report_pdf.html',
                               username=username,
                               current_date=date.today().strftime("%B %d, %Y"),
                               transactions=transactions,
                               from_date=filters['start_date'],
                               to_date=filters['end_date'],
                               **summary_data,
                               **chart_images)

    # Generate PDF
    pdf = HTML(string=rendered).write_pdf()
    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment;' \
        'filename=financial_report.pdf'
    return response


def get_filtered_data(user_id, filters):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    query = """SELECT t.*, c.name AS category, c.type
               FROM transactions t
               JOIN categories c ON t.categoryID = c.categoryID
               WHERE t.userID = %s"""
    values = [user_id]

    if filters['start_date']:
        query += " AND t.date >= %s"
        values.append(filters['start_date'])
    if filters['end_date']:
        query += " AND t.date <= %s"
        values.append(filters['end_date'])
    if filters['type']:
        query += " AND c.type = %s"
        values.append(filters['type'])
    if filters['categoryID']:
        query += " AND t.categoryID = %s"
        values.append(int(filters['categoryID']))

    query += " ORDER BY t.date DESC"
    cursor.execute(query, values)
    transactions = cursor.fetchall()

    # Summary
    total_credit = sum(t['amount'] for t in transactions
                       if t['type'] == 'credit')
    total_debit = sum(t['amount'] for t in transactions
                      if t['type'] == 'debit')
    total_balance = total_credit - total_debit

    cursor.close()
    conn.close()

    return transactions, {
        'total_credit': total_credit,
        'total_debit': total_debit,
        'total_balance': total_balance
    }


@app.template_filter('to_datetime')
def to_datetime_filter(s, fmt='%Y-%m'):
    return datetime.strptime(s, fmt)


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
