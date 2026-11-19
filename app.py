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

    return render_template(
        "rentals.html",
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
