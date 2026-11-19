import os
import math
from datetime import datetime, date

from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, or_, desc, case

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "patel-generator-secret-key")

# ---------------- DATABASE ----------------

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


# ---------------- GENERATOR MODEL ----------------

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


# ---------------- RENTAL MODEL ----------------
# A separate table keeps all previous rental history.
# Existing genset rows and IDs are not duplicated or reset.

class Rental(db.Model):
    __tablename__ = "rental"

    id = db.Column(db.Integer, primary_key=True)
    genset_id = db.Column(
        db.Integer, db.ForeignKey("genset.id"), nullable=False, index=True
    )

    renter_name = db.Column(db.String(120), nullable=False)
    renter_mobile = db.Column(db.String(20))
    renter_address = db.Column(db.Text)

    rate_type = db.Column(db.String(20), nullable=False)  # DAILY/MONTHLY/YEARLY
    rate = db.Column(db.Float, nullable=False, default=0)

    start_date = db.Column(db.Date, nullable=False, default=date.today)
    expected_return_date = db.Column(db.Date)
    actual_return_date = db.Column(db.Date)

    advance = db.Column(db.Float, default=0)
    paid_amount = db.Column(db.Float, default=0)
    total_rent = db.Column(db.Float, default=0)
    balance = db.Column(db.Float, default=0)

    notes = db.Column(db.Text)
    status = db.Column(db.String(20), default="ON RENT")
    created_at = db.Column(db.DateTime, default=datetime.now)

    generator = db.relationship(
        "Genset", backref=db.backref("rental_records", lazy=True)
    )


with app.app_context():
    # Creates only missing tables. It does not drop or reset existing records.
    db.create_all()


# ---------------- COMMON HELPERS ----------------

def parse_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def safe_float(value, default=0):
    try:
        number = float(value or 0)
        return number if math.isfinite(number) else default
    except (ValueError, TypeError):
        return default


def rent_units(start, end, rate_type):
    """Charge at least one unit; partial days/months/years round up."""
    days = max(1, (end - start).days)

    if rate_type == "DAILY":
        return days
    if rate_type == "MONTHLY":
        return max(1, math.ceil(days / 30))
    if rate_type == "YEARLY":
        return max(1, math.ceil(days / 365))
    return 0


def calculate_rent(rental, end_date):
    units = rent_units(rental.start_date, end_date, rental.rate_type)
    total = round(units * (rental.rate or 0), 2)
    rental.total_rent = total
    rental.balance = round(total - (rental.paid_amount or 0), 2)
    return total


def get_kva_stats():
    rows = db.session.query(
        Genset.kva,
        func.count(Genset.id).label("total"),
        func.sum(
            case((Genset.status == "IN SHOP", 1), else_=0)
        ).label("in_shop"),
        func.sum(
            case((Genset.status == "DELIVERED", 1), else_=0)
        ).label("delivered"),
        func.sum(
            case((Genset.status == "ON RENT", 1), else_=0)
        ).label("on_rent")
    ).group_by(Genset.kva).order_by(Genset.kva).all()

    return [{
        "kva": row.kva or "Not Set",
        "total": row.total or 0,
        "in_shop": row.in_shop or 0,
        "delivered": row.delivered or 0,
        "on_rent": row.on_rent or 0
    } for row in rows]


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


# ---------------- DASHBOARD ----------------

@app.route("/")
def index():
    total = Genset.query.count()
    in_shop = Genset.query.filter_by(status="IN SHOP").count()
    delivered = Genset.query.filter_by(status="DELIVERED").count()
    on_rent = Genset.query.filter_by(status="ON RENT").count()

    delivered_amount = db.session.query(
        func.coalesce(func.sum(Genset.amount), 0)
    ).filter(Genset.status == "DELIVERED").scalar()

    active_rental_balance = db.session.query(
        func.coalesce(func.sum(Rental.balance), 0)
    ).filter(Rental.status == "ON RENT").scalar()

    latest = Genset.query.order_by(
        desc(Genset.entry_date), desc(Genset.id)
    ).limit(5).all()

    return render_template(
        "index.html",
        total=total,
        in_shop=in_shop,
        delivered=delivered,
        on_rent=on_rent,
        delivered_amount=delivered_amount,
        active_rental_balance=active_rental_balance,
        latest=latest,
        kva_stats=get_kva_stats()
    )


# ---------------- ADD GENERATORS ----------------

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

                new_records.append(Genset(
                    customer=request.form.get("customer", "").strip(),
                    mobile=request.form.get("mobile", "").strip(),
                    address=request.form.get("address", "").strip(),
                    company=request.form.get("company", "").strip(),
                    model=request.form.get("model", "").strip(),
                    serial=serial,
                    kva=request.form.get("kva", "").strip(),
                    complaint=request.form.get("complaint", "").strip(),
                    work=request.form.get("work", "").strip(),
                    amount=safe_float(request.form.get("amount")),
                    entry_date=parse_datetime(
                        request.form.get("entry_date")
                    ) or datetime.now(),
                    status="IN SHOP"
                ))

            db.session.add_all(new_records)
            db.session.commit()
            flash(f"{quantity} generator record(s) added successfully!", "success")
            return redirect(url_for("records"))

        except (ValueError, TypeError):
            db.session.rollback()
            flash("Please enter valid details.", "error")

    return render_template("entry.html", record=None)


# ---------------- RECORDS: IN SHOP / ON RENT / DELIVERED ----------------

@app.route("/records")
def records():
    in_search = request.args.get("in_search", "").strip()
    del_search = request.args.get("del_search", "").strip()
    rent_search = request.args.get("rent_search", "").strip()

    in_query = apply_record_search(
        Genset.query.filter_by(status="IN SHOP"), in_search
    )
    del_query = apply_record_search(
        Genset.query.filter_by(status="DELIVERED"), del_search
    )
    rent_query = apply_record_search(
        Genset.query.filter_by(status="ON RENT"), rent_search
    )

    in_records = in_query.order_by(
        desc(Genset.entry_date), desc(Genset.id)
    ).all()

    del_records = del_query.order_by(
        desc(Genset.exit_date), desc(Genset.id)
    ).all()

    rent_records = rent_query.order_by(
        desc(Genset.entry_date), desc(Genset.id)
    ).all()

    in_count = Genset.query.filter_by(status="IN SHOP").count()
    del_count = Genset.query.filter_by(status="DELIVERED").count()
    on_rent_count = Genset.query.filter_by(status="ON RENT").count()
    total_count = Genset.query.count()

    active_rentals = {
        r.genset_id: r
        for r in Rental.query.filter_by(status="ON RENT").all()
    }

    return render_template(
        "records.html",
        in_records=in_records,
        del_records=del_records,
        rent_records=rent_records,
        active_rentals=active_rentals,
        in_search=in_search,
        del_search=del_search,
        rent_search=rent_search,
        in_count=in_count,
        del_count=del_count,
        on_rent_count=on_rent_count,
        total_count=total_count
    )


# ---------------- EDIT GENERATOR ----------------

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
            record.amount = safe_float(request.form.get("amount"))

            new_entry_date = parse_datetime(request.form.get("entry_date"))
            if new_entry_date:
                record.entry_date = new_entry_date

            # Delivered records can have their delivery details edited.
            if record.status == "DELIVERED":
                record.exit_date = parse_datetime(
                    request.form.get("exit_date")
                ) or record.exit_date
                record.delivered_to = request.form.get(
                    "delivered_to", ""
                ).strip()

            # Keep rental status controlled by the Rent/Return workflow.
            if record.status != "ON RENT":
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

    return render_template("edit.html", record=record)


# Backward-compatible endpoint for older templates that still use edit_entry.
app.add_url_rule(
    "/edit/<int:id>", endpoint="edit_entry", view_func=edit, methods=["GET", "POST"]
)


# ---------------- GENERATOR DETAILS ----------------

@app.route("/details/<int:id>")
def details(id):
    record = Genset.query.get_or_404(id)
    return render_template("details.html", record=record)


# ---------------- DELIVER GENERATOR ----------------

@app.route("/deliver/<int:id>", methods=["POST"])
def deliver(id):
    record = Genset.query.get_or_404(id)

    if record.status == "IN SHOP":
        record.status = "DELIVERED"
        record.exit_date = parse_datetime(
            request.form.get("exit_date")
        ) or datetime.now()
        record.delivered_to = request.form.get(
            "delivered_to", ""
        ).strip() or record.customer

        db.session.commit()
        flash("Generator marked as delivered!", "success")
    else:
        flash("Only IN SHOP generators can be delivered.", "error")

    return redirect(url_for("records"))


# ---------------- RENT GENERATOR ----------------

@app.route("/rent/<int:genset_id>", methods=["GET", "POST"])
def rent_generator(genset_id):
    generator = Genset.query.get_or_404(genset_id)

    if generator.status != "IN SHOP":
        flash("Only IN SHOP generators can be rented.", "error")
        return redirect(url_for("records"))

    if request.method == "POST":
        try:
            renter_name = request.form.get("renter_name", "").strip()
            rate_type = request.form.get("rate_type", "").upper()
            rate = safe_float(request.form.get("rate"), -1)
            start_date = parse_date(request.form.get("start_date"))
            expected_date = parse_date(
                request.form.get("expected_return_date")
            )
            advance = safe_float(request.form.get("advance"), -1)
            extra_paid = safe_float(request.form.get("paid_amount"), -1)
            notes = request.form.get("notes", "").strip()

            if not renter_name:
                raise ValueError("Customer name is required.")
            if rate_type not in ["DAILY", "MONTHLY", "YEARLY"]:
                raise ValueError("Choose a valid rent type.")
            if rate <= 0:
                raise ValueError("Rent rate must be greater than zero.")
            if not start_date:
                raise ValueError("Please enter rental start date.")
            if expected_date and expected_date < start_date:
                raise ValueError("Return date cannot be before start date.")
            if advance < 0 or extra_paid < 0:
                raise ValueError("Payment amounts cannot be negative.")

            rental = Rental(
                genset_id=generator.id,
                renter_name=renter_name,
                renter_mobile=request.form.get("renter_mobile", "").strip(),
                renter_address=request.form.get("renter_address", "").strip(),
                rate_type=rate_type,
                rate=rate,
                start_date=start_date,
                expected_return_date=expected_date,
                advance=advance,
                paid_amount=round(advance + extra_paid, 2),
                notes=notes,
                status="ON RENT"
            )

            # If no expected date is entered, show rent accrued up to today.
            estimate_end = expected_date or date.today()
            calculate_rent(rental, estimate_end)

            generator.status = "ON RENT"
            db.session.add(rental)
            db.session.commit()

            flash("Generator successfully marked ON RENT!", "success")
            return redirect(url_for("records"))

        except ValueError as error:
            db.session.rollback()
            flash(str(error), "error")

    return render_template(
        "rent.html",
        generator=generator,
        genset=generator,
        rental=None,
        today=date.today().isoformat()
    )


# ---------------- EDIT RENTAL DETAILS ----------------

@app.route("/rental/edit/<int:rental_id>", methods=["GET", "POST"])
def edit_rental(rental_id):
    rental = Rental.query.get_or_404(rental_id)

    if request.method == "POST":
        try:
            renter_name = request.form.get("renter_name", "").strip()
            rate_type = request.form.get("rate_type", "").upper()
            rate = safe_float(request.form.get("rate"), -1)
            start_date = parse_date(request.form.get("start_date"))
            expected_date = parse_date(
                request.form.get("expected_return_date")
            )
            advance = safe_float(request.form.get("advance"))
            paid_amount = safe_float(request.form.get("paid_amount"))

            if not renter_name:
                raise ValueError("Customer name is required.")
            if rate_type not in ["DAILY", "MONTHLY", "YEARLY"]:
                raise ValueError("Choose a valid rent type.")
            if rate <= 0 or not start_date:
                raise ValueError("Enter a valid rent rate and start date.")
            if expected_date and expected_date < start_date:
                raise ValueError("Return date cannot be before start date.")
            if advance < 0 or paid_amount < 0:
                raise ValueError("Payments cannot be negative.")

            rental.renter_name = renter_name
            rental.renter_mobile = request.form.get(
                "renter_mobile", ""
            ).strip()
            rental.renter_address = request.form.get(
                "renter_address", ""
            ).strip()
            rental.rate_type = rate_type
            rental.rate = rate
            rental.start_date = start_date
            rental.expected_return_date = expected_date
            rental.advance = advance
            rental.paid_amount = max(advance, paid_amount)
            rental.notes = request.form.get("notes", "").strip()

            end_date = (
                rental.actual_return_date
                if rental.status == "RETURNED" and rental.actual_return_date
                else expected_date
            )
            calculate_rent(rental, end_date or date.today())

            db.session.commit()
            flash("Rental details updated!", "success")
            return redirect(url_for("rental_history", genset_id=rental.genset_id))

        except ValueError as error:
            db.session.rollback()
            flash(str(error), "error")

    return render_template(
        "rent.html",
        generator=rental.generator,
        genset=rental.generator,
        rental=rental,
        today=date.today().isoformat()
    )


# ---------------- ADD RENTAL PAYMENT ----------------

@app.route("/rental/payment/<int:rental_id>", methods=["POST"])
def rental_payment(rental_id):
    rental = Rental.query.get_or_404(rental_id)

    try:
        payment = safe_float(request.form.get("payment"), -1)
        if payment <= 0:
            raise ValueError("Payment must be greater than zero.")

        rental.paid_amount = round((rental.paid_amount or 0) + payment, 2)

        end_date = (
            rental.actual_return_date
            if rental.status == "RETURNED" and rental.actual_return_date
            else (rental.expected_return_date or date.today())
        )
        calculate_rent(rental, end_date)

        db.session.commit()
        flash("Rental payment added!", "success")

    except ValueError as error:
        db.session.rollback()
        flash(str(error), "error")

    return redirect(url_for("rental_history", genset_id=rental.genset_id))


# ---------------- RETURN RENTED GENERATOR ----------------

@app.route("/return-rental/<int:rental_id>", methods=["POST"])
def return_rental(rental_id):
    rental = Rental.query.get_or_404(rental_id)

    if rental.status != "ON RENT":
        flash("This rental is already returned.", "error")
        return redirect(url_for("records"))

    return_date = parse_date(request.form.get("actual_return_date")) or date.today()

    if return_date < rental.start_date:
        flash("Return date cannot be before rental start date.", "error")
        return redirect(url_for("records"))

    rental.actual_return_date = return_date
    rental.status = "RETURNED"
    calculate_rent(rental, return_date)

    generator = rental.generator
    if generator:
        generator.status = "IN SHOP"

    db.session.commit()
    flash(
        f"Generator returned. Final rent: Rs. {rental.total_rent:.2f}; "
        f"balance: Rs. {rental.balance:.2f}",
        "success"
    )
    return redirect(url_for("records"))


# ---------------- RENTAL HISTORY ----------------

@app.route("/rental-history/<int:genset_id>")
def rental_history(genset_id):
    generator = Genset.query.get_or_404(genset_id)
    rentals = Rental.query.filter_by(
        genset_id=genset_id
    ).order_by(desc(Rental.created_at), desc(Rental.id)).all()

    return render_template(
        "rental_history.html",
        generator=generator,
        rentals=rentals
    )


# ---------------- ALL RENTALS ----------------

@app.route("/rentals")
def rentals():
    active = Rental.query.filter_by(status="ON RENT").order_by(
        desc(Rental.start_date)
    ).all()
    returned = Rental.query.filter_by(status="RETURNED").order_by(
        desc(Rental.actual_return_date)
    ).all()

    all_rentals = active + returned
    return render_template(
        "rentals.html",
        rentals=all_rentals,
        active=active,
        returned=returned
    )


# ---------------- DELETE DELIVERED GENERATOR ONLY ----------------

@app.route("/delete/<int:id>", methods=["POST"])
def delete(id):
    record = Genset.query.get_or_404(id)

    if record.status == "DELIVERED":
        # Keep rental history intact: do not delete a generator linked to rentals.
        past_rentals = Rental.query.filter_by(genset_id=record.id).count()
        if past_rentals:
            flash(
                "This generator has rental history, so it cannot be deleted. "
                "Its history is being preserved.",
                "error"
            )
        else:
            db.session.delete(record)
            db.session.commit()
            flash("Delivered generator deleted successfully!", "success")
    else:
        flash("Only delivered generators can be deleted.", "error")

    return redirect(url_for("records"))


# ---------------- KVA RECORDS ----------------

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


# ---------------- CUSTOMERS ----------------

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


# ---------------- CUSTOMER HISTORY ----------------

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
