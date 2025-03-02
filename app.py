import os
import mysql.connector
from flask import Flask, request, render_template, redirect, url_for, session
import msal

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "default_secret_key")

# Database configuration
DB_HOST = os.getenv("DB_HOST", "moosefactorydb.mysql.database.azure.com")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER", "moose")
DB_PASS = os.getenv("DB_PASS", "Moosefactory123")
DB_NAME = os.getenv("DB_NAME", "moosefactory_sql")

# Microsoft Azure App credentials
CLIENT_ID = os.getenv("MS_CLIENT_ID", "d4c9b95e-3499-4e4c-9bdd-da2020ea0d88")
CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET", "5c7bfd46-2852-4781-83c8-d28be25ab885")
AUTHORITY = os.getenv("MS_AUTHORITY", "https://login.microsoftonline.com/170bbabd-a2f0-4c90-ad4b-0e8f0f0c4259")
REDIRECT_PATH = "https://moosefactoryusermanagment-dkbeg8ecagceahcx.centralus-01.azurewebsites.net/.auth/login/aad/callback"  # Must match the redirect URI in Azure
SCOPE = ["User.Read"]  # Permissions to request

# Initialize MSAL client
msal_client = msal.ConfidentialClientApplication(
    CLIENT_ID,
    authority=AUTHORITY,
    client_credential=CLIENT_SECRET
)

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

# Initializes database connection
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
        cursor.execute("SELECT email AS username, role_id AS access_level FROM users")
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

# Route to initiate Microsoft login
@app.route("/auth/microsoft")
def login():
    auth_url = msal_client.get_authorization_request_url(SCOPE, redirect_uri=url_for("auth_callback", _external=True))
    return redirect(auth_url)

# Route to handle Microsoft callback
@app.route("/auth/microsoft/callback")
def auth_callback():
    try:
        # Get the authorization code from the callback
        code = request.args.get("code")
        if not code:
            return "Login failed: No authorization code received.", 400

        # Acquire token using the authorization code
        result = msal_client.acquire_token_by_authorization_code(code, scopes=SCOPE, redirect_uri=url_for("auth_callback", _external=True))
        if "access_token" not in result:
            return "Login failed: No access token received.", 400

        # Use the access token to get user info
        graph_data = msal_client.acquire_token_for_user(result["access_token"])
        if "error" in graph_data:
            return f"Login failed: {graph_data['error_description']}", 400

        # Extract user info
        user_name = graph_data.get("displayName")
        user_email = graph_data.get("mail") or graph_data.get("userPrincipalName")

        # Save user to session
        if user_name and user_email:
            session["user"] = {"name": user_name, "email": user_email}
            return redirect(url_for("home"))
        else:
            return "Login failed: Unable to retrieve user information.", 400

    except Exception as e:
        return f"Login failed: {str(e)}", 500

if __name__ == "__main__":
    app.run()
