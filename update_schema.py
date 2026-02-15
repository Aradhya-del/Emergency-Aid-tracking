from app import app, db
from sqlalchemy import text

# Add delivery_status column to transaction table
with app.app_context():
    with db.engine.connect() as conn:
        # Add missing columns
        try:
            conn.execute(text('ALTER TABLE "transaction" ADD COLUMN current_lat FLOAT'))
            conn.execute(text('ALTER TABLE "transaction" ADD COLUMN current_lon FLOAT'))
            conn.execute(text('ALTER TABLE "transaction" ADD COLUMN last_updated DATETIME'))
            conn.commit()
            print("Database schema updated successfully!")
        except Exception as e:
            print(f"Error updating schema: {e}")
            conn.rollback()