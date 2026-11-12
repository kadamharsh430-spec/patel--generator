
import sqlite3
import os

db_path = os.path.join(
    os.path.dirname(__file__),
    "instance",
    "patel_generator.db"
)

con = sqlite3.connect(db_path)
cur = con.cursor()

cur.execute("PRAGMA table_info(genset)")
columns = [row[1] for row in cur.fetchall()]

new_columns = {
    "exit_date": "DATETIME",
    "delivered_to": "VARCHAR(120)"
}

for column, data_type in new_columns.items():
    if column not in columns:
        cur.execute(
            f"ALTER TABLE genset ADD COLUMN {column} {data_type}"
        )
        print(f"Added column: {column}")
    else:
        print(f"Already exists: {column}")

con.commit()
con.close()

print("Database migration completed!")
