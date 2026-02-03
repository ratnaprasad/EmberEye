"""
Database Manager for EmberEye Studio
Handles user authentication, account management, and project metadata
"""

import sqlite3
import bcrypt
from datetime import datetime
from pathlib import Path


class StudioDatabaseManager:
    """Manages user database for EmberEye Studio"""
    
    def __init__(self, db_path=None):
        if db_path is None:
            db_path = Path("studio_users.db")
        else:
            db_path = Path(db_path)
        
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self.create_tables()
        self.create_default_admin()

    def create_tables(self):
        """Create database schema for studio"""
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
                locked INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                role TEXT DEFAULT 'user'
            )
        ''')
        
        # Training Projects table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS training_projects (
                project_id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT NOT NULL UNIQUE,
                description TEXT,
                model_size TEXT DEFAULT 'n',
                epochs INTEGER DEFAULT 150,
                batch_size INTEGER DEFAULT 16,
                device TEXT DEFAULT 'auto',
                status TEXT DEFAULT 'draft',
                created_by TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES users(username)
            )
        ''')
        
        # Training Runs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS training_runs (
                run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                end_time TIMESTAMP,
                status TEXT DEFAULT 'running',
                final_accuracy REAL,
                final_loss REAL,
                best_model_path TEXT,
                FOREIGN KEY (project_id) REFERENCES training_projects(project_id)
            )
        ''')
        
        # Datasets table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS datasets (
                dataset_id INTEGER PRIMARY KEY AUTOINCREMENT,
                dataset_name TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL,
                frame_count INTEGER,
                annotation_count INTEGER,
                imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                imported_by TEXT NOT NULL,
                status TEXT DEFAULT 'imported',
                FOREIGN KEY (imported_by) REFERENCES users(username)
            )
        ''')
        
        self.conn.commit()

    def create_default_admin(self):
        """Create default admin user"""
        cursor = self.conn.cursor()
        
        # Create default admin user
        if not self.get_user('admin'):
            password_hash = bcrypt.hashpw(b"password", bcrypt.gensalt()).decode('utf-8')
            cursor.execute('''
                INSERT INTO users (username, password_hash, first_name, last_name, role)
                VALUES (?, ?, ?, ?, ?)
            ''', ('admin', password_hash, 'Admin', 'User', 'admin'))
            self.conn.commit()
        
        # Create ratna user (data scientist)
        if not self.get_user('ratna'):
            password_hash = bcrypt.hashpw(b"ratna", bcrypt.gensalt()).decode('utf-8')
            cursor.execute('''
                INSERT INTO users (username, password_hash, first_name, last_name, role)
                VALUES (?, ?, ?, ?, ?)
            ''', ('ratna', password_hash, 'Ratna', 'Scientist', 'data_scientist'))
            self.conn.commit()
        
        # Create s3micro user (reviewer)
        if not self.get_user('s3micro'):
            password_hash = bcrypt.hashpw(b"s3micro", bcrypt.gensalt()).decode('utf-8')
            cursor.execute('''
                INSERT INTO users (username, password_hash, first_name, last_name, role)
                VALUES (?, ?, ?, ?, ?)
            ''', ('s3micro', password_hash, 'S3Micro', 'Reviewer', 'reviewer'))
            self.conn.commit()

    def get_user(self, username):
        """Get user by username"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT username, password_hash, failed_attempts, locked,
                first_name, last_name, dob, 
                secret_question1, secret_answer1,
                secret_question2, secret_answer2,
                secret_question3, secret_answer3, role
            FROM users WHERE username = ?
        ''', (username,))
        return cursor.fetchone()

    def increment_failed_attempt(self, username):
        """Increment failed login attempts"""
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE users 
            SET failed_attempts = failed_attempts + 1 
            WHERE username = ?
        ''', (username,))
        self.conn.commit()

    def lock_user(self, username):
        """Lock user account"""
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE users 
            SET locked = 1 
            WHERE username = ?
        ''', (username,))
        self.conn.commit()

    def reset_user(self, username):
        """Reset failed attempts and unlock user"""
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE users 
            SET failed_attempts = 0, locked = 0 
            WHERE username = ?
        ''', (username,))
        self.conn.commit()

    def create_user(self, user_data):
        """Create new user"""
        cursor = self.conn.cursor()
        try:
            password_hash = bcrypt.hashpw(user_data['password'].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            cursor.execute('''
                INSERT INTO users VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, CURRENT_TIMESTAMP, ?
                )
            ''', (
                user_data['username'],
                password_hash,
                user_data.get('first_name', ''),
                user_data.get('last_name', ''),
                user_data.get('dob', ''),
                user_data.get('questions', [['', ''], ['', ''], ['', '']])[0][0],
                bcrypt.hashpw(user_data.get('questions', [['', ''], ['', ''], ['', '']])[0][1].encode('utf-8'), bcrypt.gensalt()).decode('utf-8'),
                user_data.get('questions', [['', ''], ['', ''], ['', '']])[1][0],
                bcrypt.hashpw(user_data.get('questions', [['', ''], ['', ''], ['', '']])[1][1].encode('utf-8'), bcrypt.gensalt()).decode('utf-8'),
                user_data.get('questions', [['', ''], ['', ''], ['', '']])[2][0],
                bcrypt.hashpw(user_data.get('questions', [['', ''], ['', ''], ['', '']])[2][1].encode('utf-8'), bcrypt.gensalt()).decode('utf-8'),
                user_data.get('role', 'user')
            ))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def update_password(self, username, new_password):
        """Update user password"""
        cursor = self.conn.cursor()
        password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        cursor.execute('''
            UPDATE users SET password_hash = ?
            WHERE username = ?
        ''', (password_hash, username))
        self.conn.commit()

    def close(self):
        """Close database connection"""
        self.conn.close()

    # Training Project methods
    def create_project(self, project_name, created_by, description="", model_size="n", epochs=150, batch_size=16):
        """Create new training project"""
        cursor = self.conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO training_projects 
                (project_name, description, model_size, epochs, batch_size, created_by)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (project_name, description, model_size, epochs, batch_size, created_by))
            self.conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None

    def get_project(self, project_id):
        """Get training project"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM training_projects WHERE project_id = ?', (project_id,))
        return cursor.fetchone()

    def get_all_projects(self):
        """Get all training projects"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM training_projects')
        return cursor.fetchall()

    def update_project_status(self, project_id, status):
        """Update project status"""
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE training_projects 
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE project_id = ?
        ''', (status, project_id))
        self.conn.commit()

    # Dataset methods
    def add_dataset(self, dataset_name, source, frame_count, annotation_count, imported_by):
        """Add imported dataset"""
        cursor = self.conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO datasets 
                (dataset_name, source, frame_count, annotation_count, imported_by)
                VALUES (?, ?, ?, ?, ?)
            ''', (dataset_name, source, frame_count, annotation_count, imported_by))
            self.conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None

    def get_all_datasets(self):
        """Get all datasets"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM datasets')
        return cursor.fetchall()
