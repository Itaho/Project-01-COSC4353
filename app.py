import os
import mysql.connector
import json
import base64
import subprocess
from flask import Flask, request, render_template, redirect, url_for, session, send_file
from werkzeug.utils import secure_filename
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "default_secret_key")

UPLOAD_FOLDER = 'static/signatures'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Create upload folder if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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
    # First, parse the Easy Auth header.
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
                    # Modified to include signature_path as NULL initially
                    cursor.execute(
                        "INSERT INTO users (email, name, signature_path) VALUES (%s, %s, NULL)", 
                        (email, name)
                    )
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
        # Query joins users and roles tables to get current access levels
        cursor.execute("""
            SELECT u.email AS username, 
                   CASE 
                       WHEN r.role_name = 'admin' THEN 'administrator'
                       ELSE 'basic'
                   END AS access_level,
                   u.status
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

@app.route("/toggle-status", methods=["POST"])
def toggle_status():
    # Checks user's role to see if they are admin
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Query the current user's role
        cursor.execute("""
            SELECT r.role_name
            FROM users u
            JOIN roles r ON u.role_id = r.role_id
            WHERE u.email = %s
        """, (current_user_email,))
        current_user = cursor.fetchone()
        
        # Deny the user request to enable or disable if they are not admin
        if not current_user or current_user["role_name"] != "admin":
            cursor.close()
            conn.close()
            return "You do not have permission to toggle user status.", 403

        # Retrieves the current status of user
        cursor.execute("""
            SELECT status 
            FROM users 
            WHERE email = %s
        """, (user_email_to_toggle,))
        row = cursor.fetchone()
        
        if not row:
            cursor.close()
            conn.close()
            return f"User with email {user_email_to_toggle} does not exist.", 404
        
        current_status = row["status"]
        new_status = "inactive" if current_status == "active" else "active"

        # 4. Update it
        cursor.execute("""
            UPDATE users 
            SET status = %s
            WHERE email = %s
        """, (new_status, user_email_to_toggle))
        conn.commit()
        
        cursor.close()
        conn.close()

    except Exception as e:
        return f"Error toggling status: {str(e)}", 500
        
    return redirect(url_for("admin_panel"))


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

@app.route('/upload-signature', methods=['POST'])
def upload_signature():
    if 'signature' not in request.files:
        return redirect(url_for('profile', error='No file selected'))
    
    file = request.files['signature']
    if file.filename == '':
        return redirect(url_for('profile', error='No selected file'))

    if file and allowed_file(file.filename):
        # Create unique filename using timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = secure_filename(f"{timestamp}_{file.filename}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        try:
            # Save the file
            file.save(filepath)
            
            # Update database with signature path
            user_info = session.get("user")
            if user_info and user_info.get("email"):
                conn = get_db_connection()
                cursor = conn.cursor()
                
                relative_path = os.path.join('signatures', filename)
                cursor.execute(
                    "UPDATE users SET signature_path = %s WHERE email = %s",
                    (relative_path, user_info["email"])
                )
                
                conn.commit()
                cursor.close()
                conn.close()
                
                # Return the success template instead of plain text
                return render_template('upload_success.html')
            else:
                return redirect(url_for('profile', error='User not authenticated'))
                
        except Exception as e:
            app.logger.error(f"Error uploading file: {e}")
            return redirect(url_for('profile', error='Error uploading file'))
            
    return redirect(url_for('profile', error='Invalid file type'))

@app.route("/profile", methods=["GET"])
def profile():
    user_info = session.get("user")
    if not user_info:
        return redirect(url_for('home'))
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT name, email, signature_path 
            FROM users 
            WHERE email = %s
        """, (user_info["email"],))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if not user:
            return "User not found", 404

        return render_template("profile.html", 
                            user=user,
                            error=request.args.get('error'),
                            success=request.args.get('success'))
    except Exception as e:
        return f"Error fetching profile: {str(e)}", 500
    
petitionTemplate = r"""
\documentclass{{article}}
\begin{{document}}
\section*{{Petition Form}}

\textbf{{Name:}} {lname}, {fname} {mname} \\
\textbf{{Contact Phone Number:}} {phone} \\
\textbf{{myUH ID:}} {myUH} \\
\textbf{{UH Email:}} {uhEmail} \\
\textbf{{Program:}} {program} \\
\textbf{{Alias:}} {alias} \\
\textbf{{Purpose of Petition:}} {purpose_of_petition} \\
\textbf{{Institution Name:}} {institution_name} \\
\textbf{{City/State/Zip:}} {city_state_zip} \\
\textbf{{Courses Approved for Transfer:}} {courses_transfer} \\
\textbf{{Hours Previously Transferred:}} {hours_transferred} \\
\textbf{{Transfer Credits on this Request:}} {transfer_credits} \\
\textbf{{Explanation of Request:}} \\
{explanation}

\end{{document}}
"""

@app.route('/PetitionSubmit', methods=['POST'])
def submit():
    # Retrieve form data
    form_data = {
        'fname': request.form.get('fname', ''),
        'mname': request.form.get('mname', ''),
        'lname': request.form.get('lname', ''),
        'phone': request.form.get('phone', ''),
        'myUH': request.form.get('myUH', ''),
        'uhEmail': request.form.get('uhEmail', ''),
        'program': request.form.get('program', ''),
        'alias': request.form.get('alias', ''),
        'purpose_of_petition': request.form.get('purpose_of_petition', ''),
        'institution_name': request.form.get('institution_name', ''),
        'city_state_zip': request.form.get('city_state_zip', ''),
        'courses_transfer': request.form.get('courses_transfer', ''),
        'hours_transferred': request.form.get('hours_transferred', ''),
        'transfer_credits': request.form.get('transfer_credits', ''),
        'explanation': request.form.get('explanation', '')
    }
    
    # Fill in the LaTeX template with the form data
    latex_content = petitionTemplate.format(**form_data)
    
    # Save the LaTeX file (e.g., in an output folder)
    output_dir = os.path.join('output')
    os.makedirs(output_dir, exist_ok=True)
    tex_filename = os.path.join(output_dir, 'petition.tex')
    with open(tex_filename, 'w') as f:
        f.write(latex_content)
    
    # Compile the LaTeX file to PDF using pdflatex
    try:
        subprocess.run(['pdflatex', '-output-directory', output_dir, tex_filename], check=True)
        pdf_filename = os.path.join(output_dir, 'petition.pdf')
        # Serve the PDF file as a download
        return send_file(pdf_filename, as_attachment=True)
    except subprocess.CalledProcessError as e:
        return f"An error occurred during PDF generation: {e}"

if __name__ == "__main__":
    app.run()

   
