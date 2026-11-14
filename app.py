
import os
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, session
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, or_


# ---------------- APP CONFIG ----------------

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", "change-this-secret-key"
)

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "pg")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "pg134")

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
    db_path = os.path.join(
        app.instance_path, "patel_generator.db"
    )
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + db_path

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# ---------------- DATABASE MODEL ----------------

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

    entry_date = db.Column(
        db.DateTime, default=datetime.now
    )

    exit_date = db.Column(db.DateTime)
    delivered_to = db.Column(db.String(120))

    status = db.Column(
        db.String(20), default="IN SHOP"
    )


# ---------------- LOGIN SYSTEM ----------------

def login_required(route):
    @wraps(route)
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))

        return route(*args, **kwargs)

    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():

    if session.get("logged_in"):
        return redirect(url_for("index"))

    if request.method == "POST":

        username = request.form.get("username", "")
        password = request.form.get("password", "")

        if (
            username == ADMIN_USERNAME
            and password == ADMIN_PASSWORD
        ):
            session.clear()
            session["logged_in"] = True

            return redirect(url_for("index"))

        flash("Wrong username or password!")

    return render_template("login.html")


@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("login"))


# ---------------- DASHBOARD ----------------

@app.route("/")
@login_required
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

    latest = Genset.query.order_by(
        Genset.entry_date.desc()
    ).limit(5).all()

    return render_template(
        "index.html",
        total=total,
        inside=inside,
        delivered=delivered,
        revenue=revenue,
        latest=latest
    )


# ---------------- NEW ENTRY ----------------

@app.route("/entry", methods=["GET", "POST"])
@login_required
def entry():

    if request.method == "POST":

        customer = request.form.get("customer", "").strip()

        if not customer:
            flash("Customer name is required!")
            return redirect(url_for("entry"))

        try:
            amount = float(request.form.get("amount") or 0)
        except ValueError:
            flash("Enter a valid amount!")
            return redirect(url_for("entry"))

        record = Genset(
            customer=customer,
            mobile=request.form.get("mobile"),
            address=request.form.get("address"),
            company=request.form.get("company"),
            model=request.form.get("model"),
            serial=request.form.get("serial"),
            kva=request.form.get("kva"),
            complaint=request.form.get("complaint"),
            work=request.form.get("work"),
            amount=amount,
            status="IN SHOP"
        )

        db.session.add(record)
        db.session.commit()

        flash("Generator entry saved successfully!")

        return redirect(url_for("records"))

    return render_template("entry.html")


# ---------------- RECORDS AND SEARCH ----------------

@app.route("/records")
@login_required
def records():

    search = request.args.get("search", "").strip()
    status = request.args.get("status", "").strip()

    query = Genset.query

    if search:
        query = query.filter(
            or_(
                Genset.customer.ilike(f"%{search}%"),
                Genset.mobile.ilike(f"%{search}%"),
                Genset.serial.ilike(f"%{search}%"),
                Genset.model.ilike(f"%{search}%"),
                Genset.company.ilike(f"%{search}%")
            )
        )

    if status in ["IN SHOP", "DELIVERED"]:
        query = query.filter_by(status=status)

    all_records = query.order_by(
        Genset.entry_date.desc()
    ).all()

    return render_template(
        "records.html",
        records=all_records,
        search=search,
        status=status
    )


# ---------------- DELIVER GENERATOR ----------------

@app.route("/deliver/<int:id>", methods=["POST"])
@login_required
def deliver(id):

    record = Genset.query.get_or_404(id)

    if record.status == "IN SHOP":

        record.status = "DELIVERED"
        record.exit_date = datetime.now()

        record.delivered_to = request.form.get(
            "delivered_to"
        )

        db.session.commit()

        flash("Generator marked as delivered!")

    else:
        flash("This generator is already delivered!")

    return redirect(url_for("records"))


# ---------------- DELETE DELIVERED RECORD ----------------

@app.route("/delete/<int:id>", methods=["POST"])
@login_required
def delete_record(id):

    record = Genset.query.get_or_404(id)

    if record.status != "DELIVERED":
        flash("Only delivered generators can be deleted!")
        return redirect(url_for("records"))

    db.session.delete(record)
    db.session.commit()

    flash("Delivered generator deleted successfully!")

    return redirect(url_for("records"))


# ---------------- GENERATOR DETAILS ----------------

@app.route("/details/<int:id>")
@login_required
def details(id):

    record = Genset.query.get_or_404(id)

    return render_template(
        "details.html",
        record=record,
        r=record
    )


# ---------------- CUSTOMERS ----------------

@app.route("/customers")
@login_required
def customers():

    search = request.args.get("search", "").strip()

    query = db.session.query(
        func.min(Genset.id).label("id"),
        Genset.customer.label("customer"),
        Genset.mobile.label("mobile"),
        func.count(Genset.id).label("total"),
        func.max(Genset.entry_date).label("last_visit")
    )

    if search:
        query = query.filter(
            or_(
                Genset.customer.ilike(f"%{search}%"),
                Genset.mobile.ilike(f"%{search}%")
            )
        )

    customer_rows = query.group_by(
        Genset.customer,
        Genset.mobile
    ).order_by(
        func.max(Genset.entry_date).desc()
    ).all()

    return render_template(
        "customers.html",
        customers=customer_rows,
        search=search
    )


# ---------------- CUSTOMER HISTORY ----------------

@app.route("/customer-history/<int:id>")
@login_required
def customer_history(id):

    customer_record = Genset.query.get_or_404(id)

    query = Genset.query.filter(
        Genset.customer == customer_record.customer
    )

    if customer_record.mobile:
        query = query.filter(
            Genset.mobile == customer_record.mobile
        )

    history = query.order_by(
        Genset.entry_date.desc()
    ).all()

    return render_template(
        "customer_history.html",
        customer=customer_record,
        records=history
    )


# ---------------- DATABASE INITIALIZATION ----------------

with app.app_context():
    db.create_all()


# ---------------- RUN APP ----------------

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
