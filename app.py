from flask import Flask, render_template, jsonify
from models import db, CloudResource
import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///optimizer.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

with app.app_context():
    db.create_all()
    if CloudResource.query.count() == 0:
        samples = [
            CloudResource(name="web-app-frontend", provider="AWS", resource_type="EC2", avg_cpu=78.0, monthly_cost=120.0, status="Active", recommendation="Optimal", potential_savings=0.0),
            CloudResource(name="VM-Development-01", provider="AWS", resource_type="EC2", avg_cpu=0.5, monthly_cost=95.0, status="Idle", recommendation="Stop instance", potential_savings=95.0),
            CloudResource(name="analytics-cluster", provider="AWS", resource_type="EKS", avg_cpu=8.0, monthly_cost=120.0, status="Underutilized", recommendation="Resize to t3.small", potential_savings=48.0),
            CloudResource(name="blob-backup-old", provider="Azure", resource_type="Blob Storage", avg_cpu=0.0, monthly_cost=84.0, status="Idle", recommendation="Move to cold tier", potential_savings=84.0),
            CloudResource(name="sql-db-prod", provider="Azure", resource_type="Azure SQL", avg_cpu=65.0, monthly_cost=340.0, status="Active", recommendation="Optimal", potential_savings=0.0),
            CloudResource(name="bq-dataset-logs", provider="Google Cloud", resource_type="BigQuery", avg_cpu=6.0, monthly_cost=210.0, status="Underutilized", recommendation="Downsize tier", potential_savings=50.0)
        ]
        db.session.bulk_save_objects(samples)
        db.session.commit()

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/summary")
def get_summary():
    resources = CloudResource.query.all()
    total_spend = sum(r.monthly_cost for r in resources)
    total_savings = sum(r.potential_savings for r in resources)
    idle_count = sum(1 for r in resources if r.status == "Idle")
    
    return jsonify({
        "total_resources": len(resources),
        "idle_resources": idle_count,
        "monthly_cost": round(total_spend, 2),
        "potential_savings": round(total_savings, 2)
    })

@app.route("/api/resources")
def get_resources():
    resources = CloudResource.query.all()
    return jsonify([{
        "id": r.id,
        "name": r.name,
        "provider": r.provider,
        "type": r.resource_type,
        "avg_cpu": r.avg_cpu,
        "cost": r.monthly_cost,
        "status": r.status,
        "recommendation": r.recommendation,
        "savings": r.potential_savings
    } for r in resources])

if __name__ == "__main__":
    app.run(debug=True, port=5000)