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

        # Sandbox Feedback table for Active Learning
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sandbox_feedback (
                feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_path TEXT NOT NULL,
                model_version TEXT NOT NULL,
                detection_data TEXT,
                confidence REAL,
                user_label TEXT,
                feedback TEXT,
                flagged INTEGER DEFAULT 0,
                reviewed_by TEXT,
                reviewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notes TEXT,
                FOREIGN KEY (reviewed_by) REFERENCES users(username)
            )
        ''')

        self.conn.commit()

    def create_default_admin(self):
        """Create default admin user"""
        cursor = self.conn.cursor()

        # Retire legacy bootstrap users.
        cursor.execute("DELETE FROM users WHERE username IN (?, ?)", ('admin', 'ratna'))
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

    def verify_user(self, username, password):
        """Verify user credentials"""
        user = self.get_user(username)
        if not user:
            return False, "User not found"

        stored_hash = user[1]
        if bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8')):
            self.reset_user(username)
            return True, user
        else:
            self.increment_failed_attempt(username)
            if user[2] + 1 >= 5:
                self.lock_user(username)
                return False, "Account locked due to too many failed attempts"
            return False, "Invalid password"

    def update_password(self, username, new_password):
        """Update user password"""
        cursor = self.conn.cursor()
        password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        cursor.execute('''
            UPDATE users
            SET password_hash = ?
            WHERE username = ?
        ''', (password_hash, username))
        self.conn.commit()

    def get_training_projects(self, username=None):
        """Get training projects"""
        cursor = self.conn.cursor()
        if username:
            cursor.execute('''
                SELECT * FROM training_projects WHERE created_by = ?
            ''', (username,))
        else:
            cursor.execute('''
                SELECT * FROM training_projects
            ''')
        return cursor.fetchall()

    def create_training_project(self, project_data):
        """Create new training project"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO training_projects (project_name, description, model_size, epochs, batch_size, device, status, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            project_data['project_name'],
            project_data.get('description', ''),
            project_data.get('model_size', 'n'),
            project_data.get('epochs', 150),
            project_data.get('batch_size', 16),
            project_data.get('device', 'auto'),
            'draft',
            project_data['created_by']
        ))
        self.conn.commit()
        return cursor.lastrowid

    def update_project_status(self, project_id, status):
        """Update project status"""
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE training_projects
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE project_id = ?
        ''', (status, project_id))
        self.conn.commit()

    def add_training_run(self, project_id):
        """Add training run record"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO training_runs (project_id)
            VALUES (?)
        ''', (project_id,))
        self.conn.commit()
        return cursor.lastrowid

    def update_training_run(self, run_id, status, accuracy=None, loss=None, model_path=None):
        """Update training run status"""
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE training_runs
            SET status = ?, end_time = CURRENT_TIMESTAMP,
                final_accuracy = ?, final_loss = ?, best_model_path = ?
            WHERE run_id = ?
        ''', (status, accuracy, loss, model_path, run_id))
        self.conn.commit()

    def get_training_runs(self, project_id):
        """Get training runs for project"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM training_runs WHERE project_id = ?
        ''', (project_id,))
        return cursor.fetchall()

    def get_datasets(self):
        """Get datasets list"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM datasets
        ''')
        return cursor.fetchall()

    # Sandbox Feedback methods for Active Learning
    def add_sandbox_feedback(self, image_path, model_version, detection_data, confidence, user_label, feedback, flagged, reviewed_by, notes=''):
        """Add sandbox feedback for active learning"""
        import json
        cursor = self.conn.cursor()
        detection_json = json.dumps(detection_data) if detection_data else None
        cursor.execute('''
            INSERT INTO sandbox_feedback (image_path, model_version, detection_data, confidence, user_label, feedback, flagged, reviewed_by, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (image_path, model_version, detection_json, confidence, user_label, feedback, flagged, reviewed_by, notes))
        self.conn.commit()
        return cursor.lastrowid

    def get_sandbox_feedback(self, limit=100):
        """Get sandbox feedback records"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM sandbox_feedback ORDER BY reviewed_at DESC LIMIT ?
        ''', (limit,))
        return cursor.fetchall()

    def get_flagged_items(self):
        """Get flagged items for review"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM sandbox_feedback WHERE flagged = 1 ORDER BY reviewed_at DESC
        ''')
        return cursor.fetchall()

    def get_feedback_count(self):
        """Get total count of feedback items"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM sandbox_feedback')
        result = cursor.fetchone()
        return result[0] if result else 0

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()

    def __del__(self):
        self.close()
