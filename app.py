
import os
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", "patel-generator-secret-key"
)

# Local SQLite / Cloud PostgreSQL
database_url = os.environ.get("DATABASE_URL")

if database_url:
    if database_url.startswith("postgres://"):
        database_url = database_url.replace(
            "postgres://", "postgresql+psycopg://", 1
        )
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace(
            "postgresql://", "postgresql+psycopg://", 1
        )
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
else:
    os.makedirs(app.instance_path, exist_ok=True)
    db_path = os.path.join(app.instance_path, "patel_generator.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + db_path

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# DATABASE MODEL
class Genset(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    customer = db.Column(db.String(120), nullable=False)
    mobile = db.Column(db.String(20))
    address = db.Column(db.Text)

    company = db.Column(db.String(100))
    model = db.Column(db.String(100))
    serial = db.Column(db.String(100))
    kva = db.Column(db.String(30))

    complaint = db.Column(db.Text)
    work = db.Column(db.String(100))
    amount = db.Column(db.Float, default=0)

    entry_date = db.Column(db.DateTime, default=datetime.now)
    exit_date = db.Column(db.DateTime)

    delivered_to = db.Column(db.String(120))
    status = db.Column(db.String(20), default="IN SHOP")


# DASHBOARD
@app.route("/")
def index():
    total = Genset.query.count()

    inside = Genset.query.filter_by(
        status="IN SHOP"
    ).count()

    delivered = Genset.query.filter_by(
        status="DELIVERED"
    ).count()

    revenue = db.session.query(
        func.coalesce(func.sum(Genset.amount), 0)
    ).filter_by(status="DELIVERED").scalar()

    recent = Genset.query.order_by(
        Genset.id.desc()
    ).limit(5).all()

    return render_template(
        "index.html",
        total=total,
        inside=inside,
        delivered=delivered,
        revenue=revenue,
        recent=recent
    )


# NEW ENTRY
@app.route("/entry", methods=["GET", "POST"])
def entry():
    if request.method == "POST":
        try:
            record = Genset(
                customer=request.form.get("customer", "").strip(),
                mobile=request.form.get("mobile", "").strip(),
                address=request.form.get("address", "").strip(),
                company=request.form.get("company", "").strip(),
                model=request.form.get("model", "").strip(),
                serial=request.form.get("serial", "").strip(),
                kva=request.form.get("kva", "").strip(),
                complaint=request.form.get("complaint", "").strip(),
                work=request.form.get("work", "").strip(),
                amount=float(request.form.get("amount") or 0),
                status="IN SHOP"
            )

            if not record.customer:
                flash("Customer name is required.")
                return redirect(url_for("entry"))

            db.session.add(record)
            db.session.commit()

            flash("Generator entry saved successfully!")
            return redirect(url_for("records"))

        except ValueError:
            db.session.rollback()
            flash("Please enter a valid amount.")
            return redirect(url_for("entry"))

        except Exception:
            db.session.rollback()
            flash("Entry could not be saved.")
            raise

    return render_template("entry.html")


# ALL RECORDS + SEARCH
@app.route("/records")
def records():
    search = request.args.get("search", "").strip()
    status = request.args.get("status", "").strip()

    query = Genset.query

    if search:
        query = query.filter(
            db.or_(
                Genset.customer.ilike(f"%{search}%"),
                Genset.mobile.ilike(f"%{search}%"),
                Genset.serial.ilike(f"%{search}%"),
                Genset.model.ilike(f"%{search}%"),
                Genset.company.ilike(f"%{search}%")
            )
        )

    if status in ["IN SHOP", "DELIVERED"]:
        query = query.filter_by(status=status)

    all_records = query.order_by(Genset.id.desc()).all()

    return render_template(
        "records.html",
        records=all_records,
        search=search,
        status=status
    )


# MARK AS DELIVERED
@app.route("/deliver/<int:id>", methods=["POST"])
def deliver(id):
    record = Genset.query.get_or_404(id)

    if record.status != "DELIVERED":
        record.status = "DELIVERED"
        record.exit_date = datetime.now()
        record.delivered_to = request.form.get(
            "delivered_to", ""
        ).strip()

        db.session.commit()
        flash("Generator marked as delivered!")

    return redirect(request.referrer or url_for("records"))


# GENERATOR DETAILS
@app.route("/details/<int:id>")
def details(id):
    record = Genset.query.get_or_404(id)
    return render_template("details.html", record=record)


# CUSTOMERS
@app.route("/customers")
def customers():
    search = request.args.get("search", "").strip()

    query = db.session.query(
        func.min(Genset.id).label("id"),
        Genset.customer.label("customer"),
        Genset.mobile.label("mobile"),
        func.count(Genset.id).label("count"),
        func.max(Genset.entry_date).label("last_visit")
    ).group_by(Genset.customer, Genset.mobile)

    if search:
        query = query.having(
            db.or_(
                Genset.customer.ilike(f"%{search}%"),
                Genset.mobile.ilike(f"%{search}%")
            )
        )

    customer_list = query.order_by(
        func.max(Genset.entry_date).desc()
    ).all()

    return render_template(
        "customers.html",
        customers=customer_list,
        search=search
    )


# CUSTOMER HISTORY
@app.route("/customer-history/<int:id>")
def customer_history(id):
    selected = Genset.query.get_or_404(id)

    query = Genset.query.filter(
        Genset.customer == selected.customer
    )

    if selected.mobile:
        query = query.filter(Genset.mobile == selected.mobile)
    else:
        query = query.filter(
            db.or_(Genset.mobile == None, Genset.mobile == "")
        )

    history = query.order_by(Genset.id.desc()).all()

    return render_template(
        "customer_history.html",
        customer=selected,
        records=history
    )


# CREATE TABLES
with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
