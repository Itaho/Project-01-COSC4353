import os
import mysql.connector
from flask import Flask, request, render_template, redirect, url_for, session, flash
from werkzeug.security import check_password_hash  # For password verification

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "default_secret_key")

DB_HOST = os.getenv("DB_HOST", "moosefactorydb.mysql.database.azure.com")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER", "moose")
DB_PASS = os.getenv("DB_PASS", "Moosefactory123")
DB_NAME = os.getenv("DB_NAME", "moosefactory_sql")

def get_db_connection():
    return mysql.connector.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME
    )

def execute_sql_file(cursor, filename):
    with open(filename, "r") as f:
        sql_script = f.read()
    
    statements = sql_script.split(";")

    for statement in statements:
        statement = statement.strip()  # Remove unnecessary spaces
        if statement:  # Only execute non-empty statements
            cursor.execute(statement)
            if statement.lower().startswith("select"):
                cursor.fetchall()

@app.before_request
def add_user_to_db():
    # First check if 'user' exists in session
    if 'user' not in session:
        return
    
    # Then verify the user data is valid
    user_data = session.get('user')
    if not user_data or not isinstance(user_data, dict):
        return
        
    # Ensure required fields exist
    required_fields = ['email', 'name']  # adjust based on your user data structure
    if not all(field in user_data for field in required_fields):
        return
    
    # Proceed with adding user to database
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Check if user exists
        cursor.execute("SELECT email FROM users WHERE email = %s", (user_data['email'],))
        if not cursor.fetchone():
            # Insert new user with default role_id (basicuser)
            cursor.execute("INSERT INTO users (name, email) VALUES (%s, %s)", (user_data['name'], user_data['email']))
            conn.commit()
    except mysql.connector.Error as err:
        app.logger.error(f"Database error: {err}")
        if conn:
            conn.rollback()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()               

#Initializes database connection
@app.route("/init-db")
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor(buffered=True)

    try:
        execute_sql_file(cursor, "database_template.sql")
        execute_sql_file(cursor, "default_dataset.sql")
        execute_sql_file(cursor, "test_case.sql")

        conn.commit()
        cursor.close()
        conn.close()
        return "Database initialized successfully!"
    except mysql.connector.Error as err:
        return f"SQL Execution Error: {err}", 500

@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")
@app.route('/admin')
def admin_panel():
    # Fetch all users from the database
    all_users = users.find({})  # If using MongoDB
    # If using MySQL:
    # cursor = mysql.connection.cursor()
    # cursor.execute("SELECT name, email, role_id FROM users")
    # all_users = cursor.fetchall()
    
    return render_template('adminpanel.html', users=all_users)

@app.route("/update-user", methods=["POST"])
def update_user():
    # Get form data
    username = request.form.get("username")      # The user's email from the form
    new_access_level = request.form.get("access_level")  # "basic" or "administrator"

    # Map access level strings to integer role IDs (adjust as needed)
    role_map = {
        "basic": 0,
        "administrator": 1
    }
    new_role_id = role_map.get(new_access_level, 0)

    try:
        # 1. Update the user's role
        conn = get_db_connection()
        cursor = conn.cursor()
        update_query = "UPDATE users SET role_id = %s WHERE email = %s"
        cursor.execute(update_query, (new_role_id, username))
        conn.commit()
        cursor.close()
        conn.close()

        # 2. Re-fetch all users so the updated data is shown
        conn2 = get_db_connection()
        cursor2 = conn2.cursor(dictionary=True)
        cursor2.execute("SELECT email AS username, role_id AS access_level FROM users")
        users = cursor2.fetchall()
        cursor2.close()
        conn2.close()

        # 3. Re-render the admin panel with a success message
        return render_template("adminpanel.html", users=users, success_msg="User changed successfully!")
    except Exception as e:
        return f"Error updating user: {str(e)}", 500

# Processes the form submission from the landing page
@app.route("/apply", methods=["POST"])
def apply():
    email = request.form.get("email")
    message = request.form.get("message")
    
    if not email or not message:
        return "Email and message are required!", 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = "INSERT INTO applications (email, message) VALUES (%s, %s)"
        cursor.execute(sql, (email, message))
        conn.commit()
        cursor.close()
        conn.close()
        # Redirect to thank you
        return render_template("thankyou.html")
    except mysql.connector.Error as err:
        return f"Database Error: {err}", 500

# Basic email/password login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user_data = {
            'email': request.form.get('email'),
            'name': request.form.get('name')
        }
        
        # Store user data in session
        session['user'] = user_data
        
        # Redirect to homepage or dashboard
        return redirect(url_for('index'))  # or whatever your home route is
        
    return render_template('login.html')

# Google OAuth callback route
@app.route('/oauth/callback')
def oauth_callback():
    # Get the authorization code from Google
    code = request.args.get('code')
    
    try:
        # Exchange code for tokens (implementation depends on your OAuth library)
        token_response = get_google_tokens(code)  # You'll need to implement this
        
        # Get user info from Google
        user_info = get_google_user_info(token_response)  # You'll need to implement this
        
        # Set session variables
        session['user'] = {
            'email': user_info['email'],
            'name': user_info['name'],
            'id': user_info.get('sub')  # Google's unique user ID
        }
        
        return redirect(url_for('dashboard'))
        
    except Exception as e:
        flash('Failed to log in with Google')
        return redirect(url_for('login_page'))

if __name__ == "__main__":
    app.run()
