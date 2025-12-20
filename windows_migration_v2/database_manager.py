import sqlite3
import bcrypt
from datetime import datetime
from resource_helper import get_writable_path, copy_bundled_resource

class DatabaseManager:
    def __init__(self, db_path=None):
        if db_path is None:
            db_path = get_writable_path('users.db')
            copy_bundled_resource('users.db', db_path)
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.create_tables()
        self.create_default_admin()

    def create_tables(self):
        cursor = self.conn.cursor()
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                first_name TEXT,
                last_name TEXT,
                dob TEXT,
                secret_question1 TEXT,
                secret_answer1 TEXT,
                secret_question2 TEXT,
                secret_answer2 TEXT,
                secret_question3 TEXT,
                secret_answer3 TEXT,
                failed_attempts INTEGER DEFAULT 0,
                locked INTEGER DEFAULT 0
            )
        ''')
        # License table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS license (
                key TEXT PRIMARY KEY,
                used INTEGER DEFAULT 0
            )
        ''')
        self.conn.commit()

    def create_default_admin(self):
        cursor = self.conn.cursor()
        
        # Create default admin user
        if not self.get_user('admin'):
            password_hash = bcrypt.hashpw(b"password", bcrypt.gensalt()).decode('utf-8')
            cursor.execute('''
                INSERT INTO users (username, password_hash)
                VALUES (?, ?)
            ''', ('admin', password_hash))
            self.conn.commit()
        
        # Create ratna user
        if not self.get_user('ratna'):
            password_hash = bcrypt.hashpw(b"ratna", bcrypt.gensalt()).decode('utf-8')
            cursor.execute('''
                INSERT INTO users (username, password_hash, first_name, last_name)
                VALUES (?, ?, ?, ?)
            ''', ('ratna', password_hash, 'Ratna', 'User'))
            self.conn.commit()
        
        # Create s3micro user
        if not self.get_user('s3micro'):
            password_hash = bcrypt.hashpw(b"s3micro", bcrypt.gensalt()).decode('utf-8')
            cursor.execute('''
                INSERT INTO users (username, password_hash, first_name, last_name)
                VALUES (?, ?, ?, ?)
            ''', ('s3micro', password_hash, 'S3Micro', 'User'))
            self.conn.commit()

    def get_user(self, username):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT username, password_hash, failed_attempts, locked,
                first_name, last_name, dob, 
                secret_question1, secret_answer1,
                secret_question2, secret_answer2,
                secret_question3, secret_answer3
            FROM users WHERE username = ?
        ''', (username,))
        return cursor.fetchone()

    def increment_failed_attempt(self, username):
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE users 
            SET failed_attempts = failed_attempts + 1 
            WHERE username = ?
        ''', (username,))
        self.conn.commit()

    def lock_user(self, username):
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE users 
            SET locked = 1 
            WHERE username = ?
        ''', (username,))
        self.conn.commit()

    def reset_user(self, username):
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE users 
            SET failed_attempts = 0, locked = 0 
            WHERE username = ?
        ''', (username,))
        self.conn.commit()
    # Add other database methods from previous implementation
    # (get_user, increment_failed_attempt, lock_user, reset_user, etc.)

    def create_user(self, user_data):
        cursor = self.conn.cursor()
        try:
            password_hash = bcrypt.hashpw(user_data['password'].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            cursor.execute('''
                INSERT INTO users VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0
                )
            ''', (
                user_data['username'],
                password_hash,
                user_data['first_name'],
                user_data['last_name'],
                user_data['dob'],
                user_data['questions'][0][0],
                bcrypt.hashpw(user_data['questions'][0][1].encode('utf-8'), bcrypt.gensalt()).decode('utf-8'),
                user_data['questions'][1][0],
                bcrypt.hashpw(user_data['questions'][1][1].encode('utf-8'), bcrypt.gensalt()).decode('utf-8'),
                user_data['questions'][2][0],
                bcrypt.hashpw(user_data['questions'][2][1].encode('utf-8'), bcrypt.gensalt()).decode('utf-8'),
            ))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
    def verify_license_key(self, key):
        # cursor = self.conn.cursor()
        # cursor.execute('''
        #     SELECT * FROM license WHERE key = ? AND used = 0
        # ''', (key,))
        # return cursor.fetchone() is not None
        return True

    def update_password(self, username, new_password):
        cursor = self.conn.cursor()
        password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        cursor.execute('''
            UPDATE users SET password_hash = ?
            WHERE username = ?
        ''', (password_hash, username))
        self.conn.commit()

    def close(self):
        self.conn.close()