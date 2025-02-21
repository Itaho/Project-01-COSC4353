import os
import mysql.connector
import requests
import msal
from flask import Flask, request, render_template, redirect, url_for, session

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "supersecretkey")  # Required for session management

# Database configuration
DB_HOST = os.getenv("DB_HOST", "moosefactorydb.mysql.database.azure.com")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER", "moose")
DB_PASS = os.getenv("DB_PASS", "Moosefactory123")
DB_NAME = os.getenv("DB_NAME", "moosefactory_sql")

# Azure AD configuration
CLIENT_ID = os.getenv("AZURE_CLIENT_ID")  # Your Azure AD App Client ID
CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET")  # Your Azure AD App Client Secret
AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID")  # Your Azure AD Tenant ID
AUTHORITY = f"https://login.microsoftonline.com/{AZURE_TENANT_ID}"
REDIRECT_PATH = "/login/callback"  # Must match the redirect URI in Azure AD
SCOPE = ["User.Read"]  # Permissions to request

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
        statement = statement.strip()
        if statement:
            cursor.execute(statement)
            if statement.lower().startswith("select"):
                cursor.fetchall()

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

# Home route
@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")

# Admin panel route
@app.route("/adminpanel.html", methods=["GET"])
def admin_panel():
    # Check if user is authenticated and has the correct role
    if "user" not in session or session["user"].get("role_id") != 1:  # role_id=1 for administrator
        return "Unauthorized", 403
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT name AS username, role_id AS access_level FROM users")
        users = cursor.fetchall()
        cursor.close()
        conn.close()
    except Exception as e:
        return f"Error fetching users: {str(e)}", 500
    return render_template("adminpanel.html", users=users)

# Update user route
@app.route("/update-user", methods=["POST"])
def update_user():
    if "user" not in session or session["user"].get("role_id") != 1:  # role_id=1 for administrator
        return "Unauthorized", 403
    username = request.form.get("username")
    new_access_level = request.form.get("access_level")
    role_map = {
        "basic": 2,  # basicuser
        "administrator": 1  # administrator
    }
    new_role_id = role_map.get(new_access_level, 2)
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        update_query = "UPDATE users SET role_id = %s WHERE email = %s"
        cursor.execute(update_query, (new_role_id, username))
        conn.commit()
        cursor.close()
        conn.close()
        return "User changed successfully"
    except Exception as e:
        return f"Error updating user: {str(e)}", 500

# Apply route
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
        return render_template("thankyou.html")
    except mysql.connector.Error as err:
        return f"Database Error: {err}", 500

# Login route
@app.route("/login")
def login():
    msal_app = msal.ConfidentialClientApplication(
        CLIENT_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET
    )
    auth_url = msal_app.get_authorization_request_url(SCOPE, redirect_uri=url_for("callback", _external=True))
    return redirect(auth_url)

# Callback route
@app.route("/login/callback")
def callback():
    msal_app = msal.ConfidentialClientApplication(
        CLIENT_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET
    )
    result = msal_app.acquire_token_by_authorization_code(
        request.args["code"], scopes=SCOPE, redirect_uri=url_for("callback", _external=True)
    )
    if "access_token" in result:
        graph_data = requests.get(
            "https://graph.microsoft.com/v1.0/me",
            headers={"Authorization": f"Bearer {result['access_token']}"},
        ).json()
        email = graph_data.get("mail") or graph_data.get("userPrincipalName")
        name = graph_data.get("displayName")
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT user_id, role_id FROM users WHERE email = %s", (email,))
            user = cursor.fetchone()
            if not user:
                cursor.execute(
                    "INSERT INTO users (name, email, role_id, status) VALUES (%s, %s, %s, %s)",
                    (name, email, 2, "active"),  # Default role_id=2 (basicuser), status=active
                )
                conn.commit()
                cursor.execute("SELECT user_id, role_id FROM users WHERE email = %s", (email,))
                user = cursor.fetchone()
            cursor.close()
            conn.close()
            # Store user details in session
            session["user"] = {
                "user_id": user[0],
                "email": email,
                "name": name,
                "role_id": user[1],
            }
            return redirect(url_for("home"))
        except Exception as e:
            return f"Error adding user to database: {str(e)}", 500
    else:
        return "Login failed", 401

# Logout route
@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("home"))

if __name__ == "__main__":
    app.run(debug=True)
