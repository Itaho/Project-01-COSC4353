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
                else:
                    # checks for current cougar id
                    cursor.execute("SELECT cougar_id FROM users WHERE email = %s", (email,))
                    result = cursor.fetchone()
                    if result and not result[0] and request.endpoint not in ("set_cougar_id", "static"):
                        return redirect(url_for("set_cougar_id"))

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

        # Load users with access level info (now includes moderator)
        cursor.execute("""
            SELECT 
                u.email AS username, 
                CASE 
                    WHEN r.role_name = 'admin' THEN 'administrator'
                    WHEN r.role_name = 'moderator' THEN 'moderator'
                    ELSE 'basic'
                END AS access_level,
                u.status,
                u.signature_path
            FROM users u
            JOIN roles r ON u.role_id = r.role_id
            ORDER BY u.email
        """)
        users = cursor.fetchall()

        # Load petitions
        cursor.execute("""
            SELECT
                req.request_id,
                req.status AS req_status,
                req.form_type,
                req.submitted_at,
                u.email,
                u.user_id,
                d.document_path
            FROM requests req
            JOIN users u ON req.user_id = u.user_id
            LEFT JOIN documents d ON req.request_id = d.request_id
            WHERE req.form_type = 'petition'
            ORDER BY req.submitted_at DESC
        """)
        petitions = cursor.fetchall()

        # Load reports
        cursor.execute("""
            SELECT r.report_id,
                   reporter.email  AS reporter_email,
                   reported.email  AS reported_email,
                   rc.category_name,
                   r.description,
                   r.status,
                   r.created_at,
                   r.moderator_comments,
                   r.admin_comments
            FROM   reports           r
            JOIN   users   reporter  ON reporter.user_id = r.reporter_id
            JOIN   users   reported  ON reported.user_id = r.reported_user_id
            JOIN   report_categories rc ON rc.category_id = r.category_id
            ORDER  BY r.created_at DESC
        """)
        reports = cursor.fetchall()

        cursor.close()
        conn.close()

        return render_template("adminpanel.html", users=users, petitions=petitions, reports=reports)

    except Exception as e:
        return f"Error fetching users: {str(e)}", 500

@app.route("/update-report", methods=["POST"])
def update_report():
    if "user" not in session:
        return "Not logged in", 403

    admin_email = session["user"].get("email")

    action    = request.form.get("action")      # 'resolved' or 'dismissed'
    report_id = request.form.get("report_id")

    if action not in ("resolved", "dismissed"):
        return "Invalid action", 400
    if not report_id:
        return "No report_id provided", 400

    try:
        conn   = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # checks if user is admin
        cursor.execute("""
            SELECT r.role_name
            FROM   users u
            JOIN   roles r ON u.role_id = r.role_id
            WHERE  u.email = %s
        """, (admin_email,))
        role_row = cursor.fetchone()
        if not role_row or role_row["role_name"] != "admin":
            return "You must be admin to update reports.", 403

        # update report
        cursor.execute("""
            UPDATE reports
            SET    status      = %s,
                   resolved_by = (SELECT user_id FROM users WHERE email = %s)
            WHERE  report_id   = %s
        """, (action, admin_email, report_id))

        conn.commit()

    except Exception as e:
        app.logger.exception(e)
        return "Database error", 500

    finally:
        try:
            cursor.close(); conn.close()
        except Exception:
            pass

    return redirect(url_for("admin_panel"))

@app.route("/toggle-status", methods=["POST"])
def toggle_status():
    # Checks if user is logged in
    if "user" not in session:
        return "You must be logged in to toggle status.", 403

    # Checks email in session
    current_user_email = session["user"].get("email")
    if not current_user_email:
        return "No valid email in session.", 403

    # Get target user email & the action ("enable" or "disable")
    user_email_to_toggle = request.form.get("email")
    action = request.form.get("action")  # <-- new

    if not user_email_to_toggle:
        return "User email missing.", 400
    if not action:
        return "Action (enable/disable) missing.", 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Checks if current user is admin
        cursor.execute("""
            SELECT r.role_name
            FROM users u
            JOIN roles r ON u.role_id = r.role_id
            WHERE u.email = %s
        """, (current_user_email,))
        current_user = cursor.fetchone()

        if not current_user or current_user["role_name"] != "admin":
            cursor.close()
            conn.close()
            return "You do not have permission to toggle user status.", 403

        cursor.execute("SELECT status FROM users WHERE email = %s", (user_email_to_toggle,))
        row = cursor.fetchone()
        if not row:
            cursor.close()
            conn.close()
            return f"User with email {user_email_to_toggle} does not exist.", 404

        # Decide new status
        if action == "enable":
            new_status = "active"
        else:
            new_status = "inactive"

        # Update in DB
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

@app.before_request
def check_user_status():
    # Makes it so if a user is detected as disabled they see a different page
    # skips endpoints to avoid infinite loop
    if request.endpoint in ("disabled_access", "static", "some_logout_route"):
        return
        
    # Checks if user is logged in
    user_info = session.get("user")
    if not user_info:
        return
        
    # Get status of user in database
    email = user_info.get("email")
    if not email:
        return

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT status FROM users WHERE email = %s", (email,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()

        # If status is inactive show them the disabled page lol
        if row and row["status"] == "inactive":
            return redirect(url_for('disabled_access'))
    except Exception:
        pass

@app.route("/disabled")
def disabled_access():
    return render_template("disabled.html")

@app.route("/update-user", methods=["POST"])
def update_user():
    # Get form data
    username = request.form.get("username")
    new_access_level = request.form.get("access_level")

    # Map access level strings to integer role IDs
    role_map = {
        "basic": 2,          # matches 'basicuser'
        "moderator": 3,      # new role
        "administrator": 1   # matches 'admin'
    }

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Update the user's role
        update_query = "UPDATE users SET role_id = %s WHERE email = %s"
        cursor.execute(update_query, (role_map[new_access_level], username))
        conn.commit()

        # Re-fetch all users with role information
        cursor.execute("""
            SELECT u.email AS username, 
                   CASE 
                       WHEN r.role_name = 'admin' THEN 'administrator'
                       WHEN r.role_name = 'moderator' THEN 'moderator'
                       ELSE 'basic'
                   END AS access_level
            FROM users u
            JOIN roles r ON u.role_id = r.role_id
        """)
        users = cursor.fetchall()
        cursor.close()
        conn.close()

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

@app.route("/report-user", methods=["POST"])
def report_user():
    # Get form data
    reporter_email = session.get("user", {}).get("email")
    reported_email = request.form.get("reported_email")
    category_id = request.form.get("category_id")
    description = request.form.get("description")
    
    # Validate required fields
    if not all([reporter_email, reported_email, category_id, description]):
        return "All fields are required!", 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Verififcation
        cursor.execute("SELECT user_id FROM users WHERE email = %s", (reported_email,))
        reported_user = cursor.fetchone()
        if not reported_user:
            return "Reported user not found", 404
        cursor.execute("SELECT category_id FROM report_categories WHERE category_id = %s", (category_id,))
        if not cursor.fetchone():
            return "Invalid report category", 400
        if reporter_email == reported_email:
            return "You cannot report yourself", 400
               
        cursor.execute("SELECT user_id FROM users WHERE email = %s", (reporter_email,))
        reporter = cursor.fetchone()
        if not reporter:
            return "Reporter not found", 404

        # Get Cougar ID
        cursor.execute("SELECT cougar_id FROM users WHERE email = %s", (reporter_email,))
        cougar_id_row = cursor.fetchone()
        cougar_id = cougar_id_row["cougar_id"] if cougar_id_row else None

        # Insert report
        cursor.execute("""
            INSERT INTO reports (
                reporter_id,
                reporter_cougar_id,
                reported_user_id,
                category_id,
                description,
                status
            ) VALUES (%s, %s, %s, %s, %s, 'submitted')
        """, (
            reporter['user_id'],
            cougar_id,
            reported_user['user_id'],
            category_id,
            description
        ))

        # Get the reporter's name for confirmation message
        cursor.execute("SELECT name FROM users WHERE email = %s", (reporter_email,))
        reporter_name = cursor.fetchone()['name']
        
        conn.commit()
        cursor.close()
        conn.close()
        
        # Send to confirmation page (Currently using thankyou.html)
        return render_template("thankyou.html", 
                            reporter_name=reporter_name,
                            reported_email=reported_email)
        
    except mysql.connector.Error as err:
        return f"Database Error: {err}", 500
    except Exception as e:
        return f"Unexpected error: {str(e)}", 500
    
@app.route("/report")
def report_form():
    conn   = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Get active categories
    cursor.execute("SELECT category_id, category_name FROM report_categories WHERE is_active")
    categories = cursor.fetchall()

    # Get active users
    cursor.execute("SELECT user_id, name, email FROM users WHERE status = 'active'")
    users = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("report.html", categories=categories, users=users)


@app.route('/upload-signature', methods=['POST'])
def upload_signature():
    if 'signature' not in request.files:
        return redirect(url_for('profile', error='No file selected'))
    
    file = request.files['signature']
    if file.filename == '':
        return redirect(url_for('profile', error='No selected file'))

    if file and allowed_file(file.filename):
        try:
            # Create unique filename using timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = secure_filename(f"{timestamp}_{file.filename}")
            
            # Ensure the signatures directory exists in static folder
            signatures_dir = os.path.join('static', 'signatures')
            os.makedirs(signatures_dir, exist_ok=True)
            
            # Save file in static/signatures
            filepath = os.path.join(signatures_dir, filename)
            file.save(filepath)
            
            # Log the file save
            app.logger.info(f"Saved signature file to: {filepath}")
            
            # Update database with signature path
            user_info = session.get("user")
            if user_info and user_info.get("email"):
                conn = get_db_connection()
                cursor = conn.cursor()
                
                # Store path relative to static directory
                relative_path = f"signatures/{filename}"  # Use forward slash for web paths
                cursor.execute(
                    "UPDATE users SET signature_path = %s WHERE email = %s",
                    (relative_path, user_info["email"])
                )
                
                conn.commit()
                cursor.close()
                conn.close()
                
                app.logger.info(f"Updated database with signature path: {relative_path}")
                return render_template('upload_success.html')
            else:
                return redirect(url_for('profile', error='User not authenticated'))
                
        except Exception as e:
            app.logger.error(f"Error uploading file: {str(e)}")
            return redirect(url_for('profile', error=f'Error uploading file: {str(e)}'))
            
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
    
@app.route("/set-cougar-id", methods=["GET", "POST"])
def set_cougar_id():
    if "user" not in session:
        return redirect(url_for("home"))

    email = session["user"]["email"]

    if request.method == "POST":
        id1 = request.form.get("cougar_id")
        id2 = request.form.get("confirm_id")

        if id1 != id2:
            return render_template("set_cougar_id.html", error="IDs don't match.")

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET cougar_id = %s WHERE email = %s", (id1, email))
            conn.commit()
            cursor.close()
            conn.close()
            return redirect(url_for("verify_cougar_id"))
        except Exception as e:
            return f"Error saving Cougar ID: {str(e)}", 500

    return render_template("set_cougar_id.html")

@app.route("/verify-cougar-id", methods=["GET", "POST"])
def verify_cougar_id():
    if "user" not in session:
        return redirect(url_for("home"))

    email = session["user"]["email"]

    if request.method == "POST":
        entered_id = request.form.get("cougar_id")
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT cougar_id FROM users WHERE email = %s", (email,))
            result = cursor.fetchone()
            cursor.close()
            conn.close()

            if result and result["cougar_id"] == entered_id:
                session["cougar_verified"] = True
                return redirect(url_for("home"))  # or dashboard, etc.
            else:
                return render_template("verify_cougar_id.html", error="Invalid Cougar ID")
        except Exception as e:
            return f"Error verifying Cougar ID: {str(e)}", 500

    return render_template("verify_cougar_id.html")
   
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
@app.route('/petition')
def petition():
    return render_template('petition.html')

@app.route('/PetitionSubmit', methods=['POST'])
def submit():
    user_info = session.get("user")
    if not user_info:
        return "You must be logged in", 403

    # Gather form data
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

    latex_content = petitionTemplate.format(**form_data)

    # Generate a unique ID for the file
    unique_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    # Use a persistent folder in /home (which Azure preserves)
    output_dir = os.path.join(os.environ.get("HOME", "/home"), "output")
    os.makedirs(output_dir, exist_ok=True)
    
    tex_filename = os.path.join(output_dir, f"petition_{unique_id}.tex")
    pdf_filename = os.path.join(output_dir, f"petition_{unique_id}.pdf")

    with open(tex_filename, 'w') as f:
        f.write(latex_content)

    try:
        subprocess.run(['pdflatex', '-output-directory', output_dir, tex_filename], check=True)
    except subprocess.CalledProcessError as e:
        return f"An error occurred during PDF generation: {e}"

    # Verify PDF was created
    if not os.path.exists(pdf_filename):
        return f"PDF generation failed: {pdf_filename} not found", 500

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT user_id FROM users WHERE email=%s", (user_info["email"],))
    user_row = cursor.fetchone()
    if not user_row:
        cursor.close()
        conn.close()
        return "User not found in DB", 404

    user_id = user_row["user_id"]

    cursor.execute("""
        INSERT INTO requests (user_id, form_type, status)
        VALUES (%s, %s, %s)
    """, (user_id, 'petition', 'submitted'))
    request_id = cursor.lastrowid

    cursor.execute("""
        INSERT INTO documents (request_id, document_path)
        VALUES (%s, %s)
    """, (request_id, pdf_filename))

    conn.commit()
    cursor.close()
    conn.close()

    return send_file(pdf_filename, as_attachment=True)

@app.route("/download_pdf/<int:request_id>")
def download_pdf(request_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT document_path
            FROM documents
            WHERE request_id = %s
        """, (request_id,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if not row:
            return f"No PDF found for request_id={request_id}", 404

        pdf_path = row["document_path"]
        if not os.path.exists(pdf_path):
            return f"PDF file not found on disk: {pdf_path}", 404

        return send_file(pdf_path, as_attachment=False)

    except Exception as e:
        return f"Error retrieving PDF: {str(e)}", 500

@app.route("/approve_request", methods=["POST"])
def approve_request():
    if "user" not in session:
        return "Not logged in", 403

    admin_email = session["user"].get("email")

    # checks for admin
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT r.role_name
        FROM users u
        JOIN roles r ON u.role_id = r.role_id
        WHERE u.email = %s
    """, (admin_email,))
    role_check = cursor.fetchone()

    if not role_check or role_check["role_name"] != "admin":
        cursor.close()
        conn.close()
        return "You must be admin to approve requests.", 403

    request_id = request.form.get("request_id")
    if not request_id:
        cursor.close()
        conn.close()
        return "No request ID provided", 400

    # approves request
    cursor.execute("UPDATE requests SET status='approved' WHERE request_id=%s", (request_id,))
    
    conn.commit()
    cursor.close()
    conn.close()

    return redirect(url_for("admin_panel"))
@app.route("/InterInstitutional")
def inter_institutional():
    return render_template("InterInstitutional.html")

@app.route("/UndergradForm")
def undergrad_form():
    return render_template("UndergradForm.html")

@app.route("/withdraw", methods=["GET"])
def withdraw():
    return render_template("withdrawForm.html")

# 3. Route to process withdrawal form submission and generate LaTeX PDF
@app.route("/WithdrawSubmit", methods=["POST"])
def submit_withdraw():
    user_info = session.get("user")
    if not user_info:
        return "You must be logged in", 403

    # Form data
    data = {
        'student_name': request.form.get('student_name', ''),
        'myuh_id': request.form.get('myuh_id', ''),
        'phone': request.form.get('phone', ''),
        'email': request.form.get('email', ''),
        'program': request.form.get('program', ''),
        'career': request.form.get('career', ''),
        'term': request.form.get('term', ''),
        'year': request.form.get('year', ''),
        'aid': 'Yes' if request.form.get('aid') else 'No',
        'intl': 'Yes' if request.form.get('intl') else 'No',
        'athlete': 'Yes' if request.form.get('athlete') else 'No',
        'veteran': 'Yes' if request.form.get('veteran') else 'No',
        'grad': 'Yes' if request.form.get('grad') else 'No',
        'doctoral': 'Yes' if request.form.get('doctoral') else 'No',
        'housing': 'Yes' if request.form.get('housing') else 'No',
        'dining': 'Yes' if request.form.get('dining') else 'No',
        'parking': 'Yes' if request.form.get('parking') else 'No',
        'agree': 'Yes' if request.form.get('agree') else 'No',
        'date': request.form.get('date', '')
    }

    # Load LaTeX template
    with open("templates/withdraw_template.tex", "r") as f:
        template = Template(f.read())

    rendered_tex = template.render(**data)

    # Generate filenames
    unique_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    
    # Create static/pdfs directory if it doesn't exist
    pdf_dir = os.path.join(app.root_path, "static", "pdfs")
    os.makedirs(pdf_dir, exist_ok=True)
    
    # Define paths
    relative_path = os.path.join("static", "pdfs", f"withdraw_{unique_id}.pdf")
    full_path = os.path.join(app.root_path, relative_path)
    tex_filename = os.path.join(pdf_dir, f"withdraw_{unique_id}.tex")

    # Write LaTeX file
    with open(tex_filename, 'w') as f:
        f.write(rendered_tex)

    try:
        # Run pdflatex in the same directory as the tex file
        subprocess.run(['pdflatex', '-output-directory', pdf_dir, tex_filename], check=True)
    except subprocess.CalledProcessError as e:
        return f"LaTeX generation failed: {e}"

    if not os.path.exists(full_path):
        return "PDF generation failed.", 500

    # Store in database
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get user_id
        cursor.execute("SELECT user_id FROM users WHERE email=%s", (user_info["email"],))
        user_row = cursor.fetchone()
        if not user_row:
            cursor.close()
            conn.close()
            return "User not found in DB", 404
            
        user_id = user_row["user_id"]
        
        # Create request
        cursor.execute("""
            INSERT INTO requests (user_id, form_type, status)
            VALUES (%s, %s, %s)
        """, (user_id, 'withdrawal', 'submitted'))
        
        request_id = cursor.lastrowid
        
        # Store document path
        cursor.execute("""
            INSERT INTO documents (request_id, document_path)
            VALUES (%s, %s)
        """, (request_id, relative_path))
        
        conn.commit()
        cursor.close()
        conn.close()
        
    except Exception as e:
        return f"Database error: {str(e)}", 500

    return send_file(full_path, as_attachment=True)

@app.route('/InterInstitutionalSubmit', methods=['POST'])
def submit_inter_institutional():
    user_info = session.get("user")
    if not user_info:
        return "You must be logged in", 403

    # Gather form data dynamically
    form_data = {key: request.form.get(key, '') for key in request.form}

    # Load the LaTeX template file from disk
    template_path = os.path.join("templates", "LatexTemplates", "Inter_Institutional.tex")
    try:
        with open(template_path, 'r') as f:
            latex_template = f.read()
    except FileNotFoundError:
        return f"LaTeX template not found at {template_path}", 500

    # Render LaTeX content using Jinja2
    from jinja2 import Template
    latex_content = Template(latex_template).render(**form_data)

    # Create filenames using user email prefix
    user_prefix = user_info["email"].split('@')[0]
    unique_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output_dir = os.path.join(os.environ.get("HOME", "/home"), "output")
    os.makedirs(output_dir, exist_ok=True)

    tex_filename = os.path.join(output_dir, f"{user_prefix}_interinstitutional_{unique_id}.tex")
    pdf_filename = os.path.join(output_dir, f"{user_prefix}_interinstitutional_{unique_id}.pdf")

    with open(tex_filename, 'w') as f:
        f.write(latex_content)

    # Generate PDF with pdflatex
    try:
        subprocess.run(['pdflatex', '-output-directory', output_dir, tex_filename], check=True)
    except subprocess.CalledProcessError as e:
        return f"An error occurred during PDF generation: {e}"

    if not os.path.exists(pdf_filename):
        return f"PDF generation failed: {pdf_filename} not found", 500

    # Save metadata to DB
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT user_id FROM users WHERE email=%s", (user_info["email"],))
    user_row = cursor.fetchone()
    if not user_row:
        cursor.close()
        conn.close()
        return "User not found in DB", 404

    user_id = user_row["user_id"]

    cursor.execute("""
        INSERT INTO requests (user_id, form_type, status)
        VALUES (%s, %s, %s)
    """, (user_id, 'interinstitutional', 'submitted'))
    request_id = cursor.lastrowid

    cursor.execute("""
        INSERT INTO documents (request_id, document_path)
        VALUES (%s, %s)
    """, (request_id, pdf_filename))

    conn.commit()
    cursor.close()
    conn.close()

    return send_file(pdf_filename, as_attachment=True)

@app.route('/UndergraduatePetitionSubmit', methods=['POST'])
def submit_undergrad_petition():
    user_info = session.get("user")
    if not user_info:
        return "You must be logged in", 403

    # Collect all form fields dynamically
    form_data = {key: request.form.get(key, '') for key in request.form}

    # Load LaTeX template
    template_path = os.path.join("templates", "LatexTemplates", "UndergradForm.tex")
    try:
        with open(template_path, 'r') as f:
            latex_template = f.read()
    except FileNotFoundError:
        return f"LaTeX template not found at {template_path}", 500

    # Render LaTeX with form data
    from jinja2 import Template
    latex_content = Template(latex_template).render(**form_data)

    # Define output filenames
    user_prefix = user_info["email"].split('@')[0]
    unique_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output_dir = os.path.join(os.environ.get("HOME", "/home"), "output")
    os.makedirs(output_dir, exist_ok=True)

    tex_filename = os.path.join(output_dir, f"{user_prefix}_undergradpetition_{unique_id}.tex")
    pdf_filename = os.path.join(output_dir, f"{user_prefix}_undergradpetition_{unique_id}.pdf")

    # Write .tex file
    with open(tex_filename, 'w') as f:
        f.write(latex_content)

    # Compile LaTeX to PDF
    try:
        subprocess.run(['pdflatex', '-output-directory', output_dir, tex_filename], check=True)
    except subprocess.CalledProcessError as e:
        return f"An error occurred during PDF generation: {e}", 500

    if not os.path.exists(pdf_filename):
        return f"PDF generation failed: {pdf_filename} not found", 500

    # Store in database
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT user_id FROM users WHERE email=%s", (user_info["email"],))
    user_row = cursor.fetchone()
    if not user_row:
        cursor.close()
        conn.close()
        return "User not found in DB", 404

    user_id = user_row["user_id"]

    cursor.execute("""
        INSERT INTO requests (user_id, form_type, status)
        VALUES (%s, %s, %s)
    """, (user_id, 'undergrad_petition', 'submitted'))
    request_id = cursor.lastrowid

    cursor.execute("""
        INSERT INTO documents (request_id, document_path)
        VALUES (%s, %s)
    """, (request_id, pdf_filename))

    conn.commit()
    cursor.close()
    conn.close()

    return send_file(pdf_filename, as_attachment=True)

@app.route("/get-user-role")
def get_user_role():
    user_info = session.get("user")
    if not user_info:
        return {"role": "none"}
    
    email = user_info.get("email")
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT r.role_name 
            FROM users u 
            JOIN roles r ON u.role_id = r.role_id 
            WHERE u.email = %s
        """, (email,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()

        if not result:
            return {"role": "none"}

        return {"role": result["role_name"]}
    except Exception:
        return {"role": "none"}

@app.route("/IdLookup", methods=["GET"])
def id_lookup_page():
    return render_template("IdLookup.html", searched=False)

@app.route("/lookup-reports", methods=["POST"])
def lookup_reports():
    cougar_id = request.form.get("cougar_id")
    if not cougar_id:
        return render_template("IdLookup.html", reports=[], searched=True)

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT r.report_id,
                   reporter.email  AS reporter_email,
                   reported.email  AS reported_email,
                   rc.category_name,
                   r.description,
                   r.status,
                   r.created_at
            FROM reports r
            JOIN users reporter ON r.reporter_id = reporter.user_id
            JOIN users reported ON r.reported_user_id = reported.user_id
            JOIN report_categories rc ON rc.category_id = r.category_id
            WHERE r.reporter_cougar_id = %s
            ORDER BY r.created_at DESC
        """, (cougar_id,))
        
        reports = cursor.fetchall()
        cursor.close()
        conn.close()

        return render_template("IdLookup.html", reports=reports, searched=True)
    except Exception as e:
        return f"Error fetching reports: {str(e)}", 500
    
@app.route("/moderator/handle_report", methods=["POST"])
def handle_report():
    report_id = request.form.get("report_id")
    action = request.form.get("action")  # 'resolved' or 'dismissed'
    reason_or_punishment = request.form.get("reason_or_punishment")

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        update_query = """
            UPDATE reports
            SET status = %s,
                moderator_comments = %s,
                resolved_by = %s,
                updated_at = NOW()
            WHERE report_id = %s
        """

        cursor.execute(update_query, (
            action,
            reason_or_punishment,
            session["user_id"],  # Assuming the moderator is logged in
            report_id
        ))

        conn.commit()
        cursor.close()
        conn.close()

        flash("Report updated successfully.")
        return redirect("/ModPanel.html")  # Adjust route if needed

    except Exception as e:
        return f"Error handling report: {str(e)}", 500

@app.route("/ModPanel.html", methods=["GET"])
def mod_panel():
    return render_template("ModPanel.html")

# --- for local testing ---
@app.route("/dev-login")
def dev_login():
    session["user"] = {"email": "admin@example.com", "name": "Local Admin"}
    return "Dev user logged in! Go back to /adminpanel.html", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
