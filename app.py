
import os
from datetime import datetime
from types import SimpleNamespace

from flask import (
    Flask, render_template, request,
    redirect, url_for, flash
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_, func, desc


# ================= APP CONFIG =================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "patel-generator-secret-key"
)

database_url = os.environ.get("DATABASE_URL")

if database_url:
    if database_url.startswith("postgres://"):
        database_url = database_url.replace(
            "postgres://",
            "postgresql+psycopg://",
            1
        )
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace(
            "postgresql://",
            "postgresql+psycopg://",
            1
        )
else:
    os.makedirs(app.instance_path, exist_ok=True)
    db_path = os.path.join(
        app.instance_path,
        "patel_generator.db"
    )
    database_url = "sqlite:///" + db_path.replace("\\", "/")

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# ================= DATABASE MODEL =================

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

    entry_date = db.Column(
        db.DateTime,
        default=datetime.now
    )

    exit_date = db.Column(db.DateTime, nullable=True)

    delivered_to = db.Column(db.String(120))

    status = db.Column(
        db.String(20),
        default="IN SHOP"
    )


# ================= HELPER FUNCTIONS =================

def parse_datetime(value):
    if not value:
        return None

    try:
        return datetime.strptime(
            value,
            "%Y-%m-%dT%H:%M"
        )
    except (ValueError, TypeError):
        return None


def parse_amount(value):
    try:
        return float(value or 0)
    except (ValueError, TypeError):
        return None


def get_kva_stats():
    all_records = Genset.query.all()
    grouped = {}

    for record in all_records:
        kva_name = (record.kva or "Not Specified").strip()

        if kva_name not in grouped:
            grouped[kva_name] = {
                "kva": kva_name,
                "total": 0,
                "inside": 0,
                "delivered": 0
            }

        grouped[kva_name]["total"] += 1

        if record.status == "IN SHOP":
            grouped[kva_name]["inside"] += 1

        elif record.status == "DELIVERED":
            grouped[kva_name]["delivered"] += 1

    def sort_key(item):
        try:
            number = float(
                item["kva"].upper().replace("KVA", "").strip()
            )
            return (0, number)
        except (ValueError, AttributeError):
            return (1, item["kva"].lower())

    return [
        SimpleNamespace(**item)
        for item in sorted(
            grouped.values(),
            key=sort_key
        )
    ]


# ================= DASHBOARD =================

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
        func.coalesce(
            func.sum(Genset.amount),
            0
        )
    ).filter(
        Genset.status == "DELIVERED"
    ).scalar()

    latest = Genset.query.order_by(
        desc(Genset.entry_date)
    ).limit(5).all()

    kva_stats = get_kva_stats()

    return render_template(
        "index.html",
        total=total,
        in_shop=in_shop,
        delivered=delivered,
        delivered_amount=delivered_amount,
        latest=latest,
        kva_stats=kva_stats
    )


# ================= NEW ENTRY =================

@app.route("/entry", methods=["GET", "POST"])
def entry():

    if request.method == "POST":

        customer = request.form.get(
            "customer", ""
        ).strip()

        if not customer:
            flash("Customer name is required!")
            return redirect(url_for("entry"))

        amount = parse_amount(
            request.form.get("amount")
        )

        if amount is None:
            flash("Please enter a valid amount!")
            return redirect(url_for("entry"))

        record = Genset(
            customer=customer,
            mobile=request.form.get("mobile", "").strip(),
            address=request.form.get("address", "").strip(),

            company=request.form.get("company", "").strip(),
            model=request.form.get("model", "").strip(),
            serial=request.form.get("serial", "").strip(),

            kva=request.form.get("kva", "").strip(),
            complaint=request.form.get("complaint", "").strip(),
            work=request.form.get("work", "").strip(),

            amount=amount,
            entry_date=datetime.now(),
            status="IN SHOP"
        )

        db.session.add(record)
        db.session.commit()

        flash("Generator entry added successfully!")

        return redirect(url_for("records"))

    return render_template(
        "entry.html",
        record=None
    )


# ================= EDIT ENTRY =================

@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit_entry(id):

    record = Genset.query.get_or_404(id)

    if request.method == "POST":

        customer = request.form.get(
            "customer", ""
        ).strip()

        if not customer:
            flash("Customer name is required!")
            return redirect(
                url_for("edit_entry", id=id)
            )

        amount = parse_amount(
            request.form.get("amount")
        )

        entry_date = parse_datetime(
            request.form.get("entry_date")
        )

        exit_value = request.form.get(
            "exit_date", ""
        ).strip()

        exit_date = (
            parse_datetime(exit_value)
            if exit_value else None
        )

        if amount is None or entry_date is None:
            flash("Enter a valid amount and entry date!")
            return redirect(
                url_for("edit_entry", id=id)
            )

        if exit_value and exit_date is None:
            flash("Enter a valid delivery date!")
            return redirect(
                url_for("edit_entry", id=id)
            )

        new_status = request.form.get("status")

        if new_status not in ["IN SHOP", "DELIVERED"]:
            flash("Invalid status!")
            return redirect(
                url_for("edit_entry", id=id)
            )

        record.customer = customer
        record.mobile = request.form.get("mobile", "").strip()
        record.address = request.form.get("address", "").strip()

        record.company = request.form.get("company", "").strip()
        record.model = request.form.get("model", "").strip()
        record.serial = request.form.get("serial", "").strip()

        record.kva = request.form.get("kva", "").strip()
        record.complaint = request.form.get("complaint", "").strip()
        record.work = request.form.get("work", "").strip()

        record.amount = amount
        record.entry_date = entry_date
        record.exit_date = exit_date

        record.delivered_to = request.form.get(
            "delivered_to", ""
        ).strip()

        record.status = new_status

        db.session.commit()

        flash("Generator details updated successfully!")

        return redirect(url_for("records"))

    return render_template(
        "entry.html",
        record=record
    )


# ================= ALL RECORDS / SEARCH =================

@app.route("/records")
def records():

    search = request.args.get(
        "search", ""
    ).strip()

    status_filter = request.args.get(
        "status", ""
    ).strip()

    query = Genset.query

    if search:
        like = f"%{search}%"

        query = query.filter(
            or_(
                Genset.customer.ilike(like),
                Genset.mobile.ilike(like),
                Genset.serial.ilike(like),
                Genset.model.ilike(like),
                Genset.company.ilike(like),
                Genset.kva.ilike(like)
            )
        )

    if status_filter in ["IN SHOP", "DELIVERED"]:
        query = query.filter(
            Genset.status == status_filter
        )

    all_records = query.order_by(
        desc(Genset.entry_date)
    ).all()

    return render_template(
        "records.html",
        records=all_records,
        search=search,
        status_filter=status_filter
    )


# ================= KVA-WISE RECORDS =================

@app.route("/kva/<path:kva>")
def kva_records(kva):

    all_records = Genset.query.filter_by(
        kva=kva
    ).order_by(
        desc(Genset.entry_date)
    ).all()

    # Reuse records.html. No separate kva.html required.
    return render_template(
        "records.html",
        records=all_records,
        search="",
        status_filter=""
    )


# ================= MARK DELIVERED =================

@app.route("/deliver/<int:id>", methods=["POST"])
def deliver(id):

    record = Genset.query.get_or_404(id)

    if record.status != "IN SHOP":
        flash("This generator is already delivered!")
        return redirect(url_for("records"))

    delivered_to = request.form.get(
        "delivered_to", ""
    ).strip()

    record.status = "DELIVERED"
    record.exit_date = datetime.now()
    record.delivered_to = delivered_to or record.customer

    db.session.commit()

    flash("Generator marked as delivered!")

    return redirect(url_for("records"))


# ================= DELETE DELIVERED RECORD =================

@app.route("/delete/<int:id>", methods=["POST"])
def delete_record(id):

    record = Genset.query.get_or_404(id)

    if record.status != "DELIVERED":
        flash("Only delivered generators can be deleted!")
        return redirect(url_for("records"))

    db.session.delete(record)
    db.session.commit()

    flash("Delivered generator deleted successfully!")

    return redirect(url_for("records"))


# ================= VIEW DETAILS =================

@app.route("/details/<int:id>")
def details(id):

    record = Genset.query.get_or_404(id)

    return render_template(
        "details.html",
        record=record
    )


# ================= CUSTOMERS =================

@app.route("/customers")
def customers():

    customer_list = db.session.query(
        Genset.customer,
        Genset.mobile,
        func.count(Genset.id).label("total")
    ).group_by(
        Genset.customer,
        Genset.mobile
    ).order_by(
        Genset.customer
    ).all()

    return render_template(
        "customers.html",
        customers=customer_list
    )


# ================= CUSTOMER HISTORY =================

@app.route("/customer-history/<int:id>")
def customer_history(id):

    selected = Genset.query.get_or_404(id)

    history = Genset.query.filter_by(
        customer=selected.customer
    ).order_by(
        desc(Genset.entry_date)
    ).all()

    return render_template(
        "customer_history.html",
        customer=selected.customer,
        records=history
    )


# ================= DATABASE INIT =================

with app.app_context():
    db.create_all()


# ================= RUN =================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=True
    )
