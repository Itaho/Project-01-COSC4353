import os
import mysql.connector
from flask import Flask

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

@app.route("/")
def home():
    return "Moose Factory Project"

if __name__ == "__main__":
    app.run()
