from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Enum
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os
import csv
from enums import Source, InterestLevel, Status

load_dotenv()

app = Flask(__name__)
CORS(app)
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
db = SQLAlchemy(app)

# Association Table for Many-to-Many Relationship between Salesperson and Leads
salesperson_leads = db.Table(
    "salesperson_leads",
    db.Column(
        "salesperson_id", db.Integer, db.ForeignKey("salespersons.id"), primary_key=True
    ),
    db.Column("lead_id", db.Integer, db.ForeignKey("leads.id"), primary_key=True),
)


# Lead Model to Store Sales Leads
class Lead(db.Model):
    __tablename__ = "leads"
    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, nullable=False)
    lead_name = db.Column(db.String(200), nullable=False)
    contact_info = db.Column(db.String(200), nullable=False)
    source = db.Column(Enum(Source), nullable=False)
    interest_level = db.Column(Enum(InterestLevel), nullable=False)
    status = db.Column(Enum(Status), nullable=False)
    salespersons = db.relationship(
        "Salesperson", secondary=salesperson_leads, back_populates="leads"
    )


# Salesperson Model with Authentication Attributes
class Salesperson(db.Model):
    __tablename__ = "salespersons"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(300), nullable=False)
    leads = db.relationship(
        "Lead", secondary=salesperson_leads, back_populates="salespersons"
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


# Initialize Database
with app.app_context():
    db.drop_all()
    db.create_all()
    # Pre-populate Salesperson table
    salespersons = [
        Salesperson(username="Alice"),
        Salesperson(username="Diane"),
        Salesperson(username="Charlie"),
        Salesperson(username="Bob"),
    ]
    for salesperson in salespersons:
        salesperson.set_password("pass123")  # Default password for demo purposes
    db.session.bulk_save_objects(salespersons)
    db.session.commit()


# Authentication Decorator
def basic_auth_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth = request.authorization
        if not auth or not auth.username or not auth.password:
            return jsonify({"error": "Authentication required"}), 401
        salesperson = Salesperson.query.filter_by(username=auth.username).first()
        if salesperson is None or not salesperson.check_password(auth.password):
            return jsonify({"error": "Invalid credentials"}), 401
        return f(salesperson, *args, **kwargs)

    return decorated_function


# Endpoint to Ingest CSV Leads Data
@app.route("/ingest_leads", methods=["POST"])
def ingest_leads():
    try:
        csvfile = request.files["file"]
        csvreader = csv.DictReader(
            csvfile.read().decode("utf-8").splitlines(), delimiter=","
        )
        # csvreader = csv.DictReader(open("leads.csv"), delimiter=",")
        for row in csvreader:
            salesperson = Salesperson.query.filter_by(
                username=row["Assigned Salesperson"]
            ).first()
            if not salesperson:
                return (
                    jsonify(
                        {
                            "error": f"Salesperson '{row['Assigned Salesperson']}' not found"
                        }
                    ),
                    400,
                )

            source = Source[row["Source"].replace(" ", "_").upper()]
            interest_level = InterestLevel[row["Interest Level"].upper()]
            status = Status[row["Status"].upper()]

            lead = Lead(
                lead_id=row["Lead ID"],
                lead_name=row["Lead Name"],
                contact_info=row["Contact Information"],
                source=source,
                interest_level=interest_level,
                status=status,
            )

            lead.salespersons.append(salesperson)
            db.session.add(lead)

        db.session.commit()
        return jsonify({"message": "Leads ingested successfully!"}), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Failed to ingest leads", "details": str(e)}), 400


# Helper function to map string to Enum
def get_enum_value(enum, value):
    try:
        return enum[value.replace(" ", "_").upper()]
    except KeyError:
        raise ValueError(f"Invalid value for {enum.__name__}: {value}")


@app.route("/leads", methods=["POST"])
@basic_auth_required
def get_salesperson_leads(salesperson):
    try:
        data = request.get_json()
        sources = data.get("source", [])
        interest_levels = data.get("interest_level", [])
        statuses = data.get("status", [])
        page = data.get("page", 1)
        per_page = data.get("per_page", 10)

        query = Lead.query.join(salesperson_leads).filter(
            salesperson_leads.c.salesperson_id == salesperson.id
        )

        if sources:
            query = query.filter(
                Lead.source.in_([get_enum_value(Source, source) for source in sources])
            )
        if interest_levels:
            query = query.filter(
                Lead.interest_level.in_(
                    [get_enum_value(InterestLevel, level) for level in interest_levels]
                )
            )
        if statuses:
            query = query.filter(
                Lead.status.in_([get_enum_value(Status, status) for status in statuses])
            )

        paginated_leads = query.paginate(page=page, per_page=per_page)

        return jsonify(
            {
                "leads": [
                    {
                        "lead_id": lead.lead_id,
                        "lead_name": lead.lead_name,
                        "contact_info": lead.contact_info,
                        "source": lead.source.value,
                        "interest_level": lead.interest_level.value,
                        "status": lead.status.value,
                    }
                    for lead in paginated_leads.items
                ],
                "total_pages": paginated_leads.pages,
                "total_leads": paginated_leads.total,
            }
        )
    except Exception as e:
        return jsonify({"error": "Failed to retrieve leads", "details": str(e)}), 400


# Endpoint to Basic Login Salesperson
@app.route("/login", methods=["POST"])
def login():
    try:
        data = request.get_json()
        username = data.get("username")
        password = data.get("password")
        salesperson = Salesperson.query.filter_by(username=username).first()
        if salesperson is None or not salesperson.check_password(password):
            return jsonify({"error": "Invalid credentials"}), 401
        return jsonify({"message": "Login successful"}), 200
    except Exception as e:
        return jsonify({"error": "Failed to login", "details": str(e)}), 400


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8000)
