import sqlite3
def get_user(username):
    # This is a SQL Injection vulnerability
    query = "SELECT * FROM users WHERE name = '" + username + "'"
    cursor.execute(query)
