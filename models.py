from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class Company(db.Model):
    __tablename__ = 'companies'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    users = db.relationship('User', backref='company', lazy=True)
    cloud_credentials = db.relationship('CloudCredential', backref='company', lazy=True)
    resources = db.relationship('CloudResource', backref='company', lazy=True)

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(120), default="Cloud Admin")
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class CloudCredential(db.Model):
    __tablename__ = 'cloud_credentials'
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    provider = db.Column(db.String(50), nullable=False)  # AWS, Azure, GCP
    account_id = db.Column(db.String(120), nullable=False) # Access Key ID or Subscription ID
    secret_key = db.Column(db.String(256), nullable=False) # Secret Key or Client Secret

class CloudResource(db.Model):
    __tablename__ = 'cloud_resources'
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    provider = db.Column(db.String(50), nullable=False)
    resource_type = db.Column(db.String(50), nullable=False) # Virtual Machines, Storage, Databases, Load Balancers, Networking
    region = db.Column(db.String(50), nullable=False)
    avg_cpu = db.Column(db.Float, default=0.0)
    monthly_cost = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(50), default="Active") # Active, Idle, Underutilized
    recommendation = db.Column(db.String(200))
    potential_savings = db.Column(db.Float, default=0.0)