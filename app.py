
import os
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, or_, desc

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "patel-generator-secret-key")

# Database setup
os.makedirs("instance", exist_ok=True)

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
else:
    database_url = "sqlite:///../instance/patel_generator.db"

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# Generator database model
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


with app.app_context():
    db.create_all()


def parse_datetime(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def get_kva_stats():
    rows = db.session.query(
        Genset.kva,
        func.count(Genset.id).label("total"),
        func.sum(
            db.case((Genset.status == "IN SHOP", 1), else_=0)
        ).label("in_shop"),
        func.sum(
            db.case((Genset.status == "DELIVERED", 1), else_=0)
        ).label("delivered")
    ).group_by(Genset.kva).order_by(Genset.kva).all()

    stats = []

    for row in rows:
        stats.append({
            "kva": row.kva or "Not Set",
            "total": row.total or 0,
            "in_shop": row.in_shop or 0,
            "delivered": row.delivered or 0
        })

    return stats


def apply_record_search(query, search):
    if search:
        like = f"%{search}%"

        query = query.filter(
            or_(
                Genset.customer.ilike(like),
                Genset.mobile.ilike(like),
                Genset.company.ilike(like),
                Genset.model.ilike(like),
                Genset.serial.ilike(like),
                Genset.kva.ilike(like),
                Genset.work.ilike(like),
                Genset.status.ilike(like)
            )
        )

    return query


# Dashboard
@app.route("/")
def index():
    total = Genset.query.count()

    in_shop = Genset.query.filter_by(
        status="IN SHOP"
    ).count()

    delivered = Genset.query.filter_by(
        status="DELIVERED"
    ).count()

    delivered_amount = db.session.query(
        func.coalesce(func.sum(Genset.amount), 0)
    ).filter(
        Genset.status == "DELIVERED"
    ).scalar()

    latest = Genset.query.order_by(
        desc(Genset.entry_date),
        desc(Genset.id)
    ).limit(5).all()

    return render_template(
        "index.html",
        total=total,
        in_shop=in_shop,
        delivered=delivered,
        delivered_amount=delivered_amount,
        latest=latest,
        kva_stats=get_kva_stats()
    )


# Add new generator entries
@app.route("/entry", methods=["GET", "POST"])
def entry():
    if request.method == "POST":
        try:
            quantity = int(request.form.get("quantity", 1))
            quantity = max(1, min(quantity, 100))

            serials = request.form.getlist("serials[]")
            common_serial = request.form.get("serial", "").strip()

            new_records = []

            for i in range(quantity):
                serial = (
                    serials[i].strip()
                    if i < len(serials) and serials[i].strip()
                    else common_serial
                )

                record = Genset(
                    customer=request.form.get("customer", "").strip(),
                    mobile=request.form.get("mobile", "").strip(),
                    address=request.form.get("address", "").strip(),
                    company=request.form.get("company", "").strip(),
                    model=request.form.get("model", "").strip(),
                    serial=serial,
                    kva=request.form.get("kva", "").strip(),
                    complaint=request.form.get("complaint", "").strip(),
                    work=request.form.get("work", "").strip(),
                    amount=float(request.form.get("amount") or 0),
                    entry_date=parse_datetime(
                        request.form.get("entry_date")
                    ) or datetime.now(),
                    status="IN SHOP"
                )

                new_records.append(record)

            db.session.add_all(new_records)
            db.session.commit()

            flash(
                f"{quantity} generator record(s) added successfully!",
                "success"
            )
            return redirect(url_for("records"))

        except (ValueError, TypeError):
            db.session.rollback()
            flash("Please enter valid details.", "error")

    return render_template("entry.html", record=None)


# Records page: independent IN SHOP and DELIVERED sections
@app.route("/records")
def records():
    in_search = request.args.get("in_search", "").strip()
    del_search = request.args.get("del_search", "").strip()

    in_query = Genset.query.filter_by(status="IN SHOP")
    del_query = Genset.query.filter_by(status="DELIVERED")

    in_query = apply_record_search(in_query, in_search)
    del_query = apply_record_search(del_query, del_search)

    in_records = in_query.order_by(
        desc(Genset.entry_date),
        desc(Genset.id)
    ).all()

    del_records = del_query.order_by(
        desc(Genset.exit_date),
        desc(Genset.id)
    ).all()

    # Overall counts are not affected by either search box
    in_count = Genset.query.filter_by(status="IN SHOP").count()
    del_count = Genset.query.filter_by(status="DELIVERED").count()
    total_count = Genset.query.count()

    return render_template(
        "records.html",
        in_records=in_records,
        del_records=del_records,
        in_search=in_search,
        del_search=del_search,
        in_count=in_count,
        del_count=del_count,
        total_count=total_count
    )


# Edit generator
@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit(id):
    record = Genset.query.get_or_404(id)

    if request.method == "POST":
        try:
            record.customer = request.form.get("customer", "").strip()
            record.mobile = request.form.get("mobile", "").strip()
            record.address = request.form.get("address", "").strip()
            record.company = request.form.get("company", "").strip()
            record.model = request.form.get("model", "").strip()
            record.serial = request.form.get("serial", "").strip()
            record.kva = request.form.get("kva", "").strip()
            record.complaint = request.form.get("complaint", "").strip()
            record.work = request.form.get("work", "").strip()
            record.amount = float(request.form.get("amount") or 0)

            new_entry_date = parse_datetime(
                request.form.get("entry_date")
            )
            if new_entry_date:
                record.entry_date = new_entry_date

            new_exit_date = parse_datetime(
                request.form.get("exit_date")
            )
            record.exit_date = new_exit_date

            record.delivered_to = request.form.get(
                "delivered_to", ""
            ).strip()

            new_status = request.form.get("status", record.status)
            if new_status in ["IN SHOP", "DELIVERED"]:
                record.status = new_status

            if record.status == "IN SHOP":
                record.exit_date = None
                record.delivered_to = ""

            elif record.status == "DELIVERED" and not record.exit_date:
                record.exit_date = datetime.now()

            db.session.commit()
            flash("Generator updated successfully!", "success")
            return redirect(url_for("records"))

        except (ValueError, TypeError):
            db.session.rollback()
            flash("Please enter valid details.", "error")

    return render_template("entry.html", record=record)


# Generator details
@app.route("/details/<int:id>")
def details(id):
    record = Genset.query.get_or_404(id)
    return render_template("details.html", record=record)


# Mark generator as delivered
@app.route("/deliver/<int:id>", methods=["POST"])
def deliver(id):
    record = Genset.query.get_or_404(id)

    if record.status != "DELIVERED":
        record.status = "DELIVERED"
        record.exit_date = datetime.now()
        record.delivered_to = request.form.get(
            "delivered_to", ""
        ).strip() or record.customer

        db.session.commit()
        flash("Generator marked as delivered!", "success")

    return redirect(url_for("records"))


# Delete delivered generator only
@app.route("/delete/<int:id>", methods=["POST"])
def delete(id):
    record = Genset.query.get_or_404(id)

    if record.status == "DELIVERED":
        db.session.delete(record)
        db.session.commit()
        flash("Delivered generator deleted successfully!", "success")
    else:
        flash("Only delivered generators can be deleted.", "error")

    return redirect(url_for("records"))


# KVA-wise records
@app.route("/kva/<path:kva>")
def kva_records(kva):
    records = Genset.query.filter_by(kva=kva).order_by(
        desc(Genset.entry_date)
    ).all()

    return render_template(
        "kva_records.html",
        records=records,
        kva=kva
    )


# Customer list
@app.route("/customers")
def customers():
    customer_list = db.session.query(
        Genset.customer,
        Genset.mobile,
        func.count(Genset.id).label("total")
    ).group_by(
        Genset.customer,
        Genset.mobile
    ).order_by(Genset.customer).all()

    return render_template(
        "customers.html",
        customers=customer_list
    )


# Customer history
@app.route("/customer-history/<int:id>")
def customer_history(id):
    record = Genset.query.get_or_404(id)

    history = Genset.query.filter_by(
        customer=record.customer
    ).order_by(desc(Genset.entry_date)).all()

    return render_template(
        "customer_history.html",
        customer=record.customer,
        history=history
    )


if __name__ == "__main__":
    app.run(debug=True)
