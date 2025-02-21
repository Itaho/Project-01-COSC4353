import os
import mysql.connector
from flask import Flask, request, render_template, redirect, url_for, session

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
    # Check if user info is in session (adjust keys based on your auth setup)
    if 'user' in session:
        email = session['user'].get('email')  # Adjust to match your session keys
        name = session['user'].get('name')
        
        if not email or not name:
            return  # Skip if data is missing
        
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            # Check if user exists
            cursor.execute("SELECT email FROM users WHERE email = %s", (email,))
            if not cursor.fetchone():
                # Insert new user with default role_id (basicuser)
                cursor.execute("INSERT INTO users (name, email) VALUES (%s, %s)", (name, email))
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
@app.route("/adminpanel.html", methods=["GET"])
def admin_panel():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT name AS username, role_id AS access_level FROM users")
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
'''
@app.route("/login/callback")
def callback():
    # Handle the callback from Azure AD
    msal_app = msal.ConfidentialClientApplication(
        CLIENT_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET
    )
    result = msal_app.acquire_token_by_authorization_code(
        request.args["code"], scopes=SCOPE, redirect_uri=url_for("callback", _external=True)
    )

    if "access_token" in result:
        # Fetch user details from Microsoft Graph
        graph_data = requests.get(
            "https://graph.microsoft.com/v1.0/me",
            headers={"Authorization": f"Bearer {result['access_token']}"},
        ).json()

        # Extract user details
        email = graph_data.get("mail") or graph_data.get("userPrincipalName")
        name = graph_data.get("displayName")

        # Add user to the database if they don't already exist
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # Check if the user already exists
            cursor.execute("SELECT user_id FROM users WHERE email = %s", (email,))
            user = cursor.fetchone()

            if not user:
                # Insert new user into the database
                cursor.execute(
                    """
                    INSERT INTO users (name, email, role_id, status)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (name, email, 2, "active"),  # Default role_id=2 (basicuser), status=active
                )
                conn.commit()

            cursor.close()
            conn.close()
        except Exception as e:
            return f"Error adding user to database: {str(e)}", 500

        # Redirect to home or admin panel
        return redirect(url_for("home"))
    else:
        return "Login failed", 401
'''
if __name__ == "__main__":
    app.run()
