from credential_security import encrypt_secret, decrypt_secret
from azure_connector import discover_azure_resources
from azure.core.exceptions import AzureError
from cryptography.fernet import InvalidToken
from sqlalchemy.exc import SQLAlchemyError
from uuid import UUID
import secrets
import csv
import io
from flask import Response
from assessment import demo_resources
from azure_assessment import assess_azure, payload
import os
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from models import db, Company, User, CloudCredential, CloudResource, AzureConnection
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"]
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///optimizer.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

with app.app_context():
    db.create_all()

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        user = User.query.filter_by(email=email).first()
        if user and password and user.check_password(password):
            session.clear()
            session["user_id"] = user.id
            session["user_name"] = user.full_name
            session["company_id"] = user.company_id
            session["company_name"] = user.company.name
            
            # Check if company has credentials added
            has_creds = AzureConnection.query.filter_by(company_id=user.company_id).first()
            if not has_creds:
                return redirect(url_for("connect_cloud"))
            return redirect(url_for("dashboard"))
        flash("Invalid email or password", "danger")
    return render_template("login.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        full_name = request.form.get("full_name")
        email = request.form.get("email")
        password = request.form.get("password")
        company_name = request.form.get("company_name")

        if User.query.filter_by(email=email).first():
            flash("Email already registered", "danger")
            return redirect(url_for("signup"))

        company = Company.query.filter_by(name=company_name).first()

        if company:
            flash(
                "This company already exists. Contact its administrator for access.",
                "danger"
            )
            return redirect(url_for("signup"))

        company = Company(name=company_name)
        db.session.add(company)
        db.session.commit()

        user = User(email=email, full_name=full_name, company_id=company.id)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        session["user_id"] = user.id
        session["user_name"] = user.full_name
        session["company_id"] = company.id
        session["company_name"] = company.name

        return redirect(url_for("connect_cloud"))
    return render_template("signup.html")

@app.route("/connect-cloud", methods=["GET", "POST"])
def connect_cloud():
    user = db.session.get(User, session.get("user_id")) if session.get("user_id") else None
    if user is None:
        return redirect(url_for("login"))
    if "cloud_csrf" not in session:
        session["cloud_csrf"] = secrets.token_urlsafe(32)
    if request.method == "POST":
        token = request.form.get("csrf_token", "")
        if not secrets.compare_digest(token, session["cloud_csrf"]):
            return "Form expired. Reload this page and try again.", 400
        try:
            tenant_id = str(UUID(request.form.get("tenant_id", "").strip()))
            client_id = str(UUID(request.form.get("client_id", "").strip()))
            subscription_id = str(UUID(request.form.get("subscription_id", "").strip()))
        except ValueError:
            flash("Tenant, client and subscription IDs must be valid UUIDs.", "danger")
            return redirect(url_for("connect_cloud"))
        client_secret = request.form.get("client_secret", "").strip()
        if not client_secret:
            flash("Client secret Value is required.", "danger")
            return redirect(url_for("connect_cloud"))
        try:
            resources = discover_azure_resources(
                tenant_id, client_id, client_secret, subscription_id
            )
        except (AzureError, ValueError):
            flash("Azure connection failed. Check your IDs, secret Value, network and Reader access.", "danger")
            return redirect(url_for("connect_cloud"))
        try:
            connection = AzureConnection.query.filter_by(company_id=user.company_id).first()
            if connection is None:
                connection = AzureConnection(company_id=user.company_id)
                db.session.add(connection)
            connection.tenant_id = tenant_id
            connection.client_id = client_id
            connection.subscription_id = subscription_id
            connection.encrypted_client_secret = "fernet:v1:" + encrypt_secret(client_secret)
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            flash("Could not save the connection. Please try again.", "danger")
            return redirect(url_for("connect_cloud"))
        flash(f"Azure connected. Discovered {len(resources)} resources.", "success")
        return redirect(url_for("dashboard"))
    return render_template("connect_cloud.html", csrf_token=session["cloud_csrf"])

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("dashboard.html", user_name=session.get("user_name"), company_name=session.get("company_name"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

def current_assessment():
    user = db.session.get(User, session.get("user_id")) if session.get("user_id") else None
    if user is None:
        return {"error": "Please sign in again."}, 401
    mode = request.args.get("mode", "live")
    if mode not in ("live", "demo"):
        return {"error": "Unknown mode."}, 400
    if mode == "demo":
        return payload(demo_resources(), "demo"), 200
    connection = AzureConnection.query.filter_by(company_id=user.company_id).first()
    if connection is None:
        return {"error": "Connect an Azure account to load live resources."}, 409
    try:
        secret = decrypt_secret(connection.encrypted_client_secret.removeprefix("fernet:v1:"))
        return assess_azure(connection.tenant_id, connection.client_id, secret, connection.subscription_id), 200
    except InvalidToken:
        return {"error": "Stored credentials cannot be decrypted. Reconnect Azure."}, 503
    except (AzureError, ValueError):
        return {"error": "Azure request failed. Check network, credentials and Reader access. Demo mode is available separately."}, 502


@app.route("/api/data")
def api_data():
    data, status = current_assessment()
    response = jsonify(data)
    response.status_code = status
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/api/report.csv")
def report_csv():
    data, status = current_assessment()
    if status != 200:
        return jsonify(data), status
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["Source", "Generated UTC", "Name", "Type", "Region", "Status", "Average CPU %", "CPU coverage %", "Monthly cost USD (demo only)", "Potential saving USD (demo only)", "Recommendation"])
    def safe(value):
        text = "" if value is None else str(value)
        return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")) else text
    for r in data["resources"]:
        writer.writerow([safe(v) for v in [data["source"], data["generated_at"], r["name"], r["type"], r["region"], r["status"], r.get("avg_cpu"), r.get("cpu_coverage"), r.get("cost"), r.get("savings"), r.get("recommendation")]])
    response = Response(output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = f'attachment; filename="optimizer-{data["mode"]}-report.csv"'
    response.headers["Cache-Control"] = "no-store"
    return response

if __name__ == "__main__":
    app.run(debug=True, port=5000)