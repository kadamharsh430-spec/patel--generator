
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)

app.config["SECRET_KEY"] = "patel-generator-secret-key-change-later"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///patel_generator.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# ==================================
# DATABASE MODEL
# ==================================

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


# ==================================
# CREATE DATABASE
# ==================================

with app.app_context():
    db.create_all()


# ==================================
# DASHBOARD
# ==================================

@app.route("/")
def dashboard():

    total = Genset.query.count()

    inside = Genset.query.filter_by(
        status="IN SHOP"
    ).count()

    delivered = Genset.query.filter_by(
        status="DELIVERED"
    ).count()

    revenue = db.session.query(
        db.func.sum(Genset.amount)
    ).filter_by(status="DELIVERED").scalar() or 0

    recent = Genset.query.order_by(
        Genset.entry_date.desc()
    ).limit(5).all()

    return render_template(
        "index.html",
        total=total,
        inside=inside,
        delivered=delivered,
        revenue=revenue,
        recent=recent
    )


# ==================================
# NEW GENSET ENTRY
# ==================================

@app.route("/entry", methods=["GET", "POST"])
def entry():

    if request.method == "POST":

        try:
            amount = float(request.form.get("amount") or 0)

            if amount < 0:
                raise ValueError("Amount cannot be negative")

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

                amount=amount
            )

            if not record.customer:
                flash("Customer name is required!", "error")
                return redirect(url_for("entry"))

            db.session.add(record)
            db.session.commit()

            flash("Genset entry saved successfully!", "success")

            return redirect(url_for("records"))

        except ValueError:
            flash("Please enter a valid amount.", "error")
            return redirect(url_for("entry"))

        except Exception:
            db.session.rollback()
            flash("Could not save entry. Please try again.", "error")
            return redirect(url_for("entry"))

    return render_template("entry.html")


# ==================================
# ALL RECORDS + SEARCH
# ==================================

@app.route("/records")
def records():

    search = request.args.get("search", "").strip()
    status = request.args.get("status", "").strip()

    query = Genset.query

    if search:
        term = f"%{search}%"

        query = query.filter(
            db.or_(
                Genset.customer.ilike(term),
                Genset.mobile.ilike(term),
                Genset.serial.ilike(term),
                Genset.model.ilike(term),
                Genset.company.ilike(term)
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


# ==================================
# GENSET EXIT / DELIVERY
# ==================================

@app.route("/deliver/<int:id>", methods=["POST"])
def deliver(id):

    record = db.session.get(Genset, id)

    if not record:
        flash("Genset record not found!", "error")
        return redirect(url_for("records"))

    if record.status == "DELIVERED":
        flash("This genset is already delivered.", "error")
        return redirect(url_for("records"))

    record.status = "DELIVERED"
    record.exit_date = datetime.now()
    record.delivered_to = request.form.get(
        "delivered_to", ""
    ).strip()

    db.session.commit()

    flash("Genset marked as delivered!", "success")

    return redirect(url_for("records"))


# ==================================
# VIEW SINGLE RECORD
# ==================================

@app.route("/details/<int:id>")
def details(id):

    record = db.session.get(Genset, id)

    if not record:
        flash("Record not found!", "error")
        return redirect(url_for("records"))

    return render_template(
        "details.html",
        record=record
    )


# ==================================
# RUN APPLICATION
# ==================================

if __name__ == "__main__":
    app.run(debug=True)

# ==================================
# CUSTOMER MANAGEMENT
# ==================================

@app.route("/customers")
def customers():

    customer_list = db.session.query(
        Genset.customer,
        Genset.mobile,
        db.func.count(Genset.id).label("total"),
        db.func.max(Genset.entry_date).label("last_visit")
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


# ==================================
# CUSTOMER HISTORY
# ==================================

@app.route("/customers")
def customers():

    customer_list = db.session.query(
        db.func.min(Genset.id).label("id"),
        Genset.customer,
        Genset.mobile,
        db.func.count(Genset.id).label("total"),
        db.func.max(Genset.entry_date).label("last_visit")
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


@app.route("/customer-history/<int:id>")
def customer_history(id):

    selected = db.session.get(Genset, id)

    if not selected:
        flash("Customer not found!", "error")
        return redirect(url_for("customers"))

    query = Genset.query.filter(
        Genset.customer == selected.customer
    )

    if selected.mobile:
        query = query.filter(Genset.mobile == selected.mobile)
    else:
        query = query.filter(
            db.or_(Genset.mobile == None, Genset.mobile == "")
        )

    history = query.order_by(
        Genset.entry_date.desc()
    ).all()

    return render_template(
        "customer_history.html",
        customer=selected,
        history=history
    )

