import os
import mysql.connector
import json
import base64
from flask import Flask, request, render_template, redirect, url_for, session

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "default_secret_key")

@app.before_request
def parse_easy_auth_headers():
    principal_header = request.headers.get('X-MS-CLIENT-PRINCIPAL')
    if principal_header:
        # Decode from Base64
        decoded = base64.b64decode(principal_header).decode('utf-8')
        # Parse the JSON
        principal_data = json.loads(decoded)

        # Find email in claims
        claims = principal_data.get("claims", [])
        email = None
        name = None

        for c in claims:
            if c.get("typ") == "preferred_username":
                email = c.get("val")
            elif c.get("typ") == "name":
                name = c.get("val")
        
        # Store in session so we can use it anywhere else in the app
        session["user"] = {"email": email, "name": name}
    else:
        # If header isn't present, clear user info
        session.pop("user", None)

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
    # First, parse the Easy Auth header (the function above).
    parse_easy_auth_headers()

    # Now see if session["user"] is set.
    user_info = session.get("user")
    if user_info:
        email = user_info.get("email")
        name = user_info.get("name")

        if email and name:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT email FROM users WHERE email = %s", (email,))
                existing_user = cursor.fetchone()

                if not existing_user:
                    cursor.execute("INSERT INTO users (email, name) VALUES (%s, %s)", (email, name))
                    conn.commit()
            except mysql.connector.Error as err:
                app.logger.error(f"Database error: {err}")
                conn.rollback()
            finally:
                cursor.close()
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
@app.route("/adminpanel.html", methods=["GET"])
def admin_panel():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT u.email AS username, 
                   CASE 
                       WHEN r.role_name = 'admin' THEN 'administrator'
                       ELSE 'basic'
                   END AS access_level
            FROM users u
            JOIN roles r ON u.role_id = r.role_id
        """)
        users = cursor.fetchall()
        cursor.close()
        conn.close()
    except Exception as e:
        # This will display the error message to help you debug
        return f"Error fetching users: {str(e)}", 500
    return render_template("adminpanel.html", users=users)

@app.route("/update-user", methods=["POST"])
def update_user():
    # Get form data
    username = request.form.get("username")
    new_access_level = request.form.get("access_level")

    # Map access level strings to integer role IDs
    role_map = {
        "basic": 2,        # matches 'basicuser' role_id
        "administrator": 1  # matches 'admin' role_id
    }
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)  # Changed to dictionary cursor
        
        # Update the user's role
        update_query = "UPDATE users SET role_id = %s WHERE email = %s"
        cursor.execute(update_query, (role_map[new_access_level], username))
        conn.commit()
        
        # Re-fetch all users with role information
        cursor.execute("""
            SELECT u.email AS username, 
                   CASE 
                       WHEN r.role_name = 'admin' THEN 'administrator'
                       ELSE 'basic'
                   END AS access_level
            FROM users u
            JOIN roles r ON u.role_id = r.role_id
        """)
        users = cursor.fetchall()
        cursor.close()
        conn.close()

        # Redirect back to admin panel with updated data
        return redirect(url_for('admin_panel'))
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

if __name__ == "__main__":
    app.run()
