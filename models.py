from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class CloudResource(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    provider = db.Column(db.String(50), nullable=False)  # AWS, Azure, GCP
    resource_type = db.Column(db.String(50), nullable=False)  # EC2, EBS, RDS, Load Balancer
    region = db.Column(db.String(50), default="us-east-1")
    avg_cpu = db.Column(db.Float, default=0.0)
    monthly_cost = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default="Active")  # Active, Underutilized, Idle
    recommendation = db.Column(db.String(200))
    potential_savings = db.Column(db.Float, default=0.0)