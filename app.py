
import os
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, or_


app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", "patel-generator-secret"
)

# DATABASE
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


# GENERATOR MODEL
class Genset(db.Model):
    __tablename__ = "genset"

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
    inside = Genset.query.filter_by(status="IN SHOP").count()
    delivered = Genset.query.filter_by(status="DELIVERED").count()

    revenue = db.session.query(
        func.coalesce(func.sum(Genset.amount), 0)
    ).filter_by(status="DELIVERED").scalar()

    latest = Genset.query.order_by(
        Genset.entry_date.desc()
    ).limit(5).all()

    kva_values = db.session.query(
        Genset.kva
    ).filter(
        Genset.kva.isnot(None),
        Genset.kva != ""
    ).distinct().all()

    kva_stats = []

    for row in kva_values:
        kva = row[0]

        kva_stats.append({
            "kva": kva,
            "total": Genset.query.filter_by(kva=kva).count(),
            "inside": Genset.query.filter_by(
                kva=kva, status="IN SHOP"
            ).count(),
            "delivered": Genset.query.filter_by(
                kva=kva, status="DELIVERED"
            ).count()
        })

    def kva_sort(item):
        try:
            return (0, float(
                item["kva"].lower().replace("kva", "").strip()
            ))
        except (ValueError, AttributeError):
            return (1, item["kva"].lower())

    kva_stats.sort(key=kva_sort)

    return render_template(
        "index.html",
        total=total,
        inside=inside,
        delivered=delivered,
        revenue=revenue,
        latest=latest,
        kva_stats=kva_stats
    )


# NEW ENTRY
@app.route("/entry", methods=["GET", "POST"])
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

    return render_template("entry.html", record=None)


# EDIT EXISTING ENTRY
@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit_entry(id):
    record = Genset.query.get_or_404(id)

    if request.method == "POST":
        customer = request.form.get("customer", "").strip()

        if not customer:
            flash("Customer name is required!")
            return redirect(url_for("edit_entry", id=id))

        try:
            amount = float(request.form.get("amount") or 0)
        except ValueError:
            flash("Enter a valid amount!")
            return redirect(url_for("edit_entry", id=id))

        record.customer = customer
        record.mobile = request.form.get("mobile")
        record.address = request.form.get("address")
        record.company = request.form.get("company")
        record.model = request.form.get("model")
        record.serial = request.form.get("serial")
        record.kva = request.form.get("kva")
        record.complaint = request.form.get("complaint")
        record.work = request.form.get("work")
        record.amount = amount

        db.session.commit()

        flash("Generator entry updated successfully!")
        return redirect(url_for("details", id=record.id))

    return render_template("entry.html", record=record)


# ALL RECORDS + SEARCH
@app.route("/records")
def records():
    search = request.args.get("search", "").strip()
    status = request.args.get("status", "").strip()

    query = Genset.query

    if search:
        query = query.filter(or_(
            Genset.customer.ilike(f"%{search}%"),
            Genset.mobile.ilike(f"%{search}%"),
            Genset.serial.ilike(f"%{search}%"),
            Genset.model.ilike(f"%{search}%"),
            Genset.company.ilike(f"%{search}%"),
            Genset.kva.ilike(f"%{search}%")
        ))

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


# KVA RECORDS
@app.route("/kva/<path:kva>")
def kva_records(kva):
    records = Genset.query.filter_by(kva=kva).order_by(
        Genset.entry_date.desc()
    ).all()

    total = len(records)
    inside = sum(1 for r in records if r.status == "IN SHOP")
    delivered = sum(1 for r in records if r.status == "DELIVERED")

    return render_template(
        "kva_records.html",
        records=records,
        kva=kva,
        total=total,
        inside=inside,
        delivered=delivered
    )


# DELIVER GENERATOR
@app.route("/deliver/<int:id>", methods=["POST"])
def deliver(id):
    record = Genset.query.get_or_404(id)

    if record.status == "IN SHOP":
        record.status = "DELIVERED"
        record.exit_date = datetime.now()
        record.delivered_to = request.form.get("delivered_to")
        db.session.commit()
        flash("Generator delivered successfully!")
    else:
        flash("Generator is already delivered!")

    return redirect(url_for("records"))


# DELETE DELIVERED GENERATOR
@app.route("/delete/<int:id>", methods=["POST"])
def delete_record(id):
    record = Genset.query.get_or_404(id)

    if record.status != "DELIVERED":
        flash("Only delivered generators can be deleted!")
        return redirect(url_for("records"))

    db.session.delete(record)
    db.session.commit()

    flash("Generator record deleted!")
    return redirect(url_for("records"))


# DETAILS
@app.route("/details/<int:id>")
def details(id):
    record = Genset.query.get_or_404(id)
    return render_template("details.html", record=record, r=record)


# CUSTOMERS
@app.route("/customers")
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
        query = query.filter(or_(
            Genset.customer.ilike(f"%{search}%"),
            Genset.mobile.ilike(f"%{search}%")
        ))

    customer_rows = query.group_by(
        Genset.customer, Genset.mobile
    ).order_by(
        func.max(Genset.entry_date).desc()
    ).all()

    return render_template(
        "customers.html",
        customers=customer_rows,
        search=search
    )


# CUSTOMER HISTORY
@app.route("/customer-history/<int:id>")
def customer_history(id):
    customer_record = Genset.query.get_or_404(id)

    query = Genset.query.filter_by(
        customer=customer_record.customer
    )

    if customer_record.mobile:
        query = query.filter_by(mobile=customer_record.mobile)
    else:
        query = query.filter(Genset.mobile.is_(None))

    history = query.order_by(
        Genset.entry_date.desc()
    ).all()

    return render_template(
        "customer_history.html",
        customer=customer_record,
        records=history
    )


# DATABASE INITIALIZATION
with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
