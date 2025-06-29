# utils/database_setup.py

import sys
import os
import mysql.connector
from mysql.connector import errorcode

# --- الحل لمشكلة ModuleNotFoundError: No module named 'config' ---
# هذا الكود يضيف المجلد الرئيسي للمشروع إلى مسار بايثون
# حتى يتمكن هذا السكربت من إيجاد ملف config.py
# os.path.abspath(__file__) -> /home/hussam/information-retrieval-system/utils/database_setup.py
# os.path.dirname(...) -> /home/hussam/information-retrieval-system/utils
# os.path.dirname(...) -> /home/hussam/information-retrieval-system
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# الآن يمكننا استيراد DB_CONFIG بنجاح
from config import DB_CONFIG

def create_database_and_tables():
    db_name = DB_CONFIG['database']
    try:
        temp_config = DB_CONFIG.copy()
        temp_config.pop('database', None)
        cnx = mysql.connector.connect(**temp_config)
        cursor = cnx.cursor()
        
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name} DEFAULT CHARACTER SET utf8mb4")
        print(f"Database '{db_name}' is ready.")
        cnx.database = db_name

        table_desc = (
            "CREATE TABLE IF NOT EXISTS `documents` ("
            "  `doc_id` varchar(255) NOT NULL,"
            "  `dataset` varchar(100) NOT NULL,"
            "  `original_text` LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,"
            "  `processed_text` LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,"
            "  PRIMARY KEY (`doc_id`, `dataset`)"
            ") ENGINE=InnoDB"
        )
        print("Creating table `documents`...", end=' ')
        cursor.execute(table_desc)
        print("Done.")
        print("\nDatabase setup is complete.")

    except mysql.connector.Error as err:
        print(f"\nDatabase setup failed: {err}")
        print("Please check your MySQL credentials and server status in 'config.py'.")
        exit(1)
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'cnx' in locals() and cnx.is_connected():
            cnx.close()

if __name__ == "__main__":
    create_database_and_tables()


