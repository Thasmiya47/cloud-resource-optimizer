import os
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from models import db, Company, User, CloudCredential, CloudResource

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "super-secret-optimizer-key-2026")
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///optimizer.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

with app.app_context():
    db.create_all()

def seed_sample_resources(company_id):
    """Seed data matching prototype numbers if newly registered"""
    samples = [
        CloudResource(company_id=company_id, name="prod-k8s-node-01", provider="AWS", resource_type="Virtual Machines", region="us-east-1", avg_cpu=82.0, monthly_cost=420.0, status="Active", recommendation="Optimal operation", potential_savings=0.0),
        CloudResource(company_id=company_id, name="dev-staging-vm", provider="AWS", resource_type="Virtual Machines", region="us-east-1", avg_cpu=0.4, monthly_cost=180.0, status="Idle", recommendation="Stop instance immediately", potential_savings=180.0),
        CloudResource(company_id=company_id, name="analytics-warehouse", provider="Google Cloud", resource_type="Databases", region="us-central1", avg_cpu=6.2, monthly_cost=650.0, status="Underutilized", recommendation="Downgrade compute tier", potential_savings=220.0),
        CloudResource(company_id=company_id, name="legacy-backup-disk", provider="Azure", resource_type="Storage", region="East US", avg_cpu=0.0, monthly_cost=140.0, status="Idle", recommendation="Unattached disk - Delete volume", potential_savings=140.0),
        CloudResource(company_id=company_id, name="ingress-lb-dev", provider="AWS", resource_type="Load Balancers", region="us-west-2", avg_cpu=2.1, monthly_cost=95.0, status="Underutilized", recommendation="Migrate to shared Gateway", potential_savings=45.0),
        CloudResource(company_id=company_id, name="vpc-nat-gateway-spare", provider="Google Cloud", resource_type="Networking", region="us-east1", avg_cpu=0.0, monthly_cost=120.0, status="Idle", recommendation="Release unused static IP & NAT", potential_savings=120.0)
    ]
    db.session.bulk_save_objects(samples)
    db.session.commit()

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
        if user and user.check_password(password):
            session["user_id"] = user.id
            session["user_name"] = user.full_name
            session["company_id"] = user.company_id
            session["company_name"] = user.company.name
            
            # Check if company has credentials added
            has_creds = CloudCredential.query.filter_by(company_id=user.company_id).first()
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
        if not company:
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

        seed_sample_resources(company.id)
        return redirect(url_for("connect_cloud"))
    return render_template("signup.html")

@app.route("/connect-cloud", methods=["GET", "POST"])
def connect_cloud():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if request.method == "POST":
        company_id = session["company_id"]
        provider = request.form.get("provider")
        account_id = request.form.get("account_id")
        secret_key = request.form.get("secret_key")

        cred = CloudCredential(company_id=company_id, provider=provider, account_id=account_id, secret_key=secret_key)
        db.session.add(cred)
        db.session.commit()
        return redirect(url_for("dashboard"))
    return render_template("connect_cloud.html")

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("dashboard.html", user_name=session.get("user_name"), company_name=session.get("company_name"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/api/data")
def api_data():
    if "company_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    cid = session["company_id"]
    resources = CloudResource.query.filter_by(company_id=cid).all()
    
    total_spend = sum(r.monthly_cost for r in resources)
    total_savings = sum(r.potential_savings for r in resources)
    idle_count = sum(1 for r in resources if r.status == "Idle")

    # Resource type breakdown
    type_counts = {"Virtual Machines": 0, "Storage": 0, "Databases": 0, "Load Balancers": 0, "Networking": 0}
    for r in resources:
        type_counts[r.resource_type] = type_counts.get(r.resource_type, 0) + 1

    return jsonify({
        "summary": {
            "total_resources": len(resources),
            "idle_resources": idle_count,
            "monthly_cost": round(total_spend, 2),
            "potential_savings": round(total_savings, 2),
            "optimization_score": 86
        },
        "distribution": type_counts,
        "resources": [{
            "id": r.id,
            "name": r.name,
            "provider": r.provider,
            "type": r.resource_type,
            "region": r.region,
            "avg_cpu": r.avg_cpu,
            "cost": r.monthly_cost,
            "status": r.status,
            "recommendation": r.recommendation,
            "savings": r.potential_savings
        } for r in resources]
    })

if __name__ == "__main__":
    app.run(debug=True, port=5000)