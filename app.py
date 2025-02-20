import os
import mysql.connector
from flask import Flask, request, render_template, redirect, url_for

app = Flask(__name__)

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
    return render_template("adminpanel.html")

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
