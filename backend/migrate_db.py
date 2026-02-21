import sqlite3
import os

DB_PATH = "vagent.db"

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"Database {DB_PATH} not found. Skipping migration.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check if column exists
        cursor.execute("PRAGMA table_info(heats)")
        columns = [info[1] for info in cursor.fetchall()]
        
        if "equilibrium_final_temp" not in columns:
            print("Adding column 'equilibrium_final_temp' to 'heats' table...")
            cursor.execute("ALTER TABLE heats ADD COLUMN equilibrium_final_temp FLOAT")
            conn.commit()
            print("Migration successful.")
        else:
            print("Column 'equilibrium_final_temp' already exists.")
            
    except Exception as e:
        print(f"Migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
