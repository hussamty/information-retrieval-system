# utils/database_setup.py

# Import standard Python libraries
import sys
import os
# Import the MySQL connector library to interact with a MySQL database
import mysql.connector
from mysql.connector import errorcode # For specific error codes from the connector

# --- Solution for the "ModuleNotFoundError: No module named 'config'" problem ---
# This code adds the main project directory to Python's path.
# This allows the script, which is in a subdirectory (utils), to find and import 'config.py' from the root directory.
# os.path.abspath(__file__) -> gets the full path of the current script.
# os.path.dirname(...) -> gets the directory containing the file.
# Using dirname twice goes up one level from 'utils' to the project root.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Now that the path is set up, we can successfully import the database configuration.
from config import DB_CONFIG

# This function handles the creation of the database and its tables.
def create_database_and_tables():
    # Get the database name from the imported configuration.
    db_name = DB_CONFIG['database']
    # Use a try...except...finally block to handle potential connection errors gracefully.
    try:
        # Create a temporary copy of the config dictionary.
        temp_config = DB_CONFIG.copy()
        # Remove the 'database' key because we need to connect to the MySQL server first before selecting a specific database.
        temp_config.pop('database', None)
        # Establish a connection to the MySQL server.
        cnx = mysql.connector.connect(**temp_config)
        # Create a cursor object, which is used to execute SQL commands.
        cursor = cnx.cursor()
        
        # Execute the SQL command to create the database if it doesn't already exist.
        # It sets the default character set to utf8mb4 to support a wide range of characters, including emojis.
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name} DEFAULT CHARACTER SET utf8mb4")
        print(f"Database '{db_name}' is ready.")
        # Switch the connection to use the newly created (or already existing) database.
        cnx.database = db_name

        # Define the SQL statement for creating the 'documents' table.
        table_desc = (
            "CREATE TABLE IF NOT EXISTS `documents` ("
            "  `doc_id` varchar(255) NOT NULL,"  # The unique ID for the document.
            "  `dataset` varchar(100) NOT NULL," # The name of the dataset the document belongs to.
            "  `original_text` LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL," # The full, original text.
            "  `processed_text` LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci," # The cleaned and processed text.
            "  PRIMARY KEY (`doc_id`, `dataset`)" # A composite primary key to uniquely identify a document within a dataset.
            ") ENGINE=InnoDB" # Use the InnoDB storage engine, which supports transactions.
        )
        print("Creating table `documents`...", end=' ')
        # Execute the table creation command.
        cursor.execute(table_desc)
        print("Done.")
        print("\nDatabase setup is complete.")

    # Catch any errors that occur during the database connection or setup.
    except mysql.connector.Error as err:
        print(f"\nDatabase setup failed: {err}")
        print("Please check your MySQL credentials and server status in 'config.py'.")
        # Exit the script with an error code if setup fails.
        exit(1)
    # The 'finally' block will execute whether an error occurred or not.
    finally:
        # Check if the cursor was created and close it.
        if 'cursor' in locals() and cursor:
            cursor.close()
        # Check if the connection was established and close it.
        if 'cnx' in locals() and cnx.is_connected():
            cnx.close()

# This standard Python construct checks if the script is being run directly.
# If it is, it calls the main function to set up the database.
# This prevents the code from running if the script is imported as a module into another file.
if __name__ == "__main__":
    create_database_and_tables()

