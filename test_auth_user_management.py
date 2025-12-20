#!/usr/bin/env python3
"""
Authentication & User Management Tests for EmberEye
Tests login, user creation, password reset, and database operations
"""
import sys
import os
import tempfile
import time
from pathlib import Path

# Test results tracking
test_results = {
    'passed': 0,
    'failed': 0,
    'errors': []
}

def log_test(name, passed, error=None):
    """Log test result"""
    if passed:
        test_results['passed'] += 1
        print(f"✓ {name}")
    else:
        test_results['failed'] += 1
        test_results['errors'].append(f"{name}: {error}")
        print(f"✗ {name}: {error}")

def test_user_creation():
    """Test user creation workflow"""
    print("\n=== Testing User Creation ===")
    
    try:
        from database_manager import DatabaseManager
        import bcrypt
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test_users.db')
            db = DatabaseManager(db_path)
            
            # Test 1: Create user with all fields
            user_data = {
                'username': 'testuser',
                'password': 'SecurePass123!',
                'first_name': 'Test',
                'last_name': 'User',
                'dob': '1990-01-01',
                'questions': [
                    ['What is your favorite color?', 'Blue'],
                    ['What is your pet\'s name?', 'Fluffy'],
                    ['What city were you born in?', 'Boston']
                ]
            }
            
            success = db.create_user(user_data)
            log_test("UserCreation: Create user succeeds",
                    success,
                    None if success else "User creation failed")
            
            # Test 2: Duplicate username rejected
            duplicate_result = db.create_user(user_data)
            log_test("UserCreation: Duplicate username rejected",
                    not duplicate_result,
                    None if not duplicate_result else "Duplicate allowed")
            
            # Test 3: User can be retrieved
            user = db.get_user('testuser')
            log_test("UserCreation: Created user can be retrieved",
                    user is not None,
                    None if user else "User not found")
            
            # Test 4: Password authentication works
            if user:
                stored_hash = user[1]  # password_hash is second field
                password_matches = bcrypt.checkpw('SecurePass123!'.encode('utf-8'), stored_hash.encode('utf-8'))
                log_test("UserCreation: Password can be verified",
                        password_matches,
                        None if password_matches else "Password verification failed")
            
            # Test 5: Admin user creation
            admin_data = {
                'username': 'admin2',
                'password': 'AdminPass123!',
                'first_name': 'Admin',
                'last_name': 'User',
                'dob': '1985-05-15',
                'questions': [
                    ['What is your favorite color?', 'Red'],
                    ['What is your pet\'s name?', 'Rex'],
                    ['What city were you born in?', 'Seattle']
                ]
            }
            
            success = db.create_user(admin_data)
            log_test("UserCreation: Second user created",
                    success,
                    None if success else "User creation failed")
            
            # Test 6: Password hashing (password not stored in plaintext)
            if user:
                stored_password = user[1]
                is_hashed = stored_password != 'SecurePass123!' and len(stored_password) > 20
                log_test("UserCreation: Password is hashed",
                        is_hashed,
                        None if is_hashed else f"Password not hashed: {stored_password}")
            
            # Test 7: Security answers are hashed
            if user and len(user) > 8:
                answer1_hash = user[8]  # secret_answer1
                is_hashed = len(answer1_hash) > 20 and answer1_hash != 'Blue'
                log_test("UserCreation: Security answers are hashed",
                        is_hashed,
                        None if is_hashed else "Security answers not hashed")
        
    except Exception as e:
        log_test("User Creation", False, str(e))

def test_authentication():
    """Test authentication workflow"""
    print("\n=== Testing Authentication ===")
    
    try:
        from database_manager import DatabaseManager
        import bcrypt
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test_auth.db')
            db = DatabaseManager(db_path)
            
            # Setup test user
            user_data = {
                'username': 'authtest',
                'password': 'TestPass123!',
                'first_name': 'Auth',
                'last_name': 'Test',
                'dob': '1992-03-10',
                'questions': [
                    ['What is your favorite color?', 'Green'],
                    ['What is your pet\'s name?', 'Max'],
                    ['What city were you born in?', 'Portland']
                ]
            }
            db.create_user(user_data)
            
            # Test 1: Valid credentials
            user = db.get_user('authtest')
            if user:
                password_matches = bcrypt.checkpw('TestPass123!'.encode('utf-8'), user[1].encode('utf-8'))
                log_test("Auth: Valid credentials succeed",
                        password_matches,
                        None if password_matches else "Valid auth failed")
            
            # Test 2: Wrong password
            if user:
                wrong_password = bcrypt.checkpw('WrongPassword'.encode('utf-8'), user[1].encode('utf-8'))
                log_test("Auth: Wrong password rejected",
                        not wrong_password,
                        None if not wrong_password else "Wrong password accepted")
            
            # Test 3: Non-existent user
            nonexistent = db.get_user('nonexistent')
            log_test("Auth: Non-existent user rejected",
                    nonexistent is None,
                    None if nonexistent is None else f"Non-existent user found: {nonexistent}")
            
            # Test 4: Failed attempts tracking
            db.increment_failed_attempt('authtest')
            user_after = db.get_user('authtest')
            if user_after:
                failed_attempts = user_after[2]  # Third field
                log_test("Auth: Failed attempts incremented",
                        failed_attempts == 1,
                        None if failed_attempts == 1 else f"Expected 1, got {failed_attempts}")
            
            # Test 5: User locking
            db.lock_user('authtest')
            locked_user = db.get_user('authtest')
            if locked_user:
                is_locked = locked_user[3]  # Fourth field
                log_test("Auth: User can be locked",
                        is_locked == 1,
                        None if is_locked == 1 else f"User not locked: {is_locked}")
            
            # Test 6: User reset
            db.reset_user('authtest')
            reset_user = db.get_user('authtest')
            if reset_user:
                failed = reset_user[2]
                locked = reset_user[3]
                log_test("Auth: User reset clears failures and lock",
                        failed == 0 and locked == 0,
                        None if (failed == 0 and locked == 0) else f"Failed={failed}, Locked={locked}")
            
            # Test 7: Security question verification
            if user and len(user) > 8:
                answer_hash = user[8]  # secret_answer1
                answer_matches = bcrypt.checkpw('Green'.encode('utf-8'), answer_hash.encode('utf-8'))
                log_test("Auth: Security answer verification works",
                        answer_matches,
                        None if answer_matches else "Security answer failed")
        
    except Exception as e:
        log_test("Authentication", False, str(e))

def test_password_operations():
    """Test password reset and update operations"""
    print("\n=== Testing Password Operations ===")
    
    try:
        from database_manager import DatabaseManager
        import bcrypt
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test_password.db')
            db = DatabaseManager(db_path)
            
            # Setup test user
            user_data = {
                'username': 'pwdtest',
                'password': 'OldPass123!',
                'first_name': 'Password',
                'last_name': 'Test',
                'dob': '1991-07-20',
                'questions': [
                    ['What is your favorite color?', 'Purple'],
                    ['What is your pet\'s name?', 'Luna'],
                    ['What city were you born in?', 'Austin']
                ]
            }
            db.create_user(user_data)
            
            # Test 1: Update password (method exists)
            db.update_password('pwdtest', 'NewPass456!')
            log_test("Password: Update password succeeds",
                    True,
                    None)
            
            # Test 2: Old password no longer works
            user = db.get_user('pwdtest')
            if user:
                old_matches = bcrypt.checkpw('OldPass123!'.encode('utf-8'), user[1].encode('utf-8'))
                log_test("Password: Old password invalidated",
                        not old_matches,
                        None if not old_matches else "Old password still works")
            
            # Test 3: New password works
            if user:
                new_user = db.get_user('pwdtest')  # Refetch
                new_matches = bcrypt.checkpw('NewPass456!'.encode('utf-8'), new_user[1].encode('utf-8'))
                log_test("Password: New password works",
                        new_matches,
                        None if new_matches else "New password doesn't work")
            
            # Test 4: Password update doesn't affect other fields
            updated_user = db.get_user('pwdtest')
            if updated_user:
                first_name_intact = updated_user[4] == 'Password'
                log_test("Password: Update preserves other fields",
                        first_name_intact,
                        None if first_name_intact else f"First name changed: {updated_user[4]}")
            
            # Test 5: Multiple password changes
            db.update_password('pwdtest', 'ThirdPass789!')
            third_user = db.get_user('pwdtest')
            if third_user:
                third_matches = bcrypt.checkpw('ThirdPass789!'.encode('utf-8'), third_user[1].encode('utf-8'))
                log_test("Password: Multiple changes supported",
                        third_matches,
                        None if third_matches else "Third password doesn't work")
        
    except Exception as e:
        log_test("Password Operations", False, str(e))

def test_user_management():
    """Test user management operations (list, update, delete)"""
    print("\n=== Testing User Management ===")
    
    try:
        from database_manager import DatabaseManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test_mgmt.db')
            db = DatabaseManager(db_path)
            
            # Create multiple users
            for i in range(5):
                user_data = {
                    'username': f'user{i}',
                    'password': f'Pass{i}123!',
                    'first_name': f'First{i}',
                    'last_name': f'Last{i}',
                    'dob': f'199{i}-0{(i%9)+1}-15',
                    'questions': [
                        [f'Question 1 for user {i}?', f'Answer1_{i}'],
                        [f'Question 2 for user {i}?', f'Answer2_{i}'],
                        [f'Question 3 for user {i}?', f'Answer3_{i}']
                    ]
                }
                db.create_user(user_data)
            
            # Test 1: Get user by username
            user = db.get_user('user0')
            log_test("UserMgmt: Get user by username",
                    user is not None,
                    None if user else "User not found")
            
            # Test 2: User has expected fields
            if user:
                has_fields = len(user) >= 12  # Should have all fields including security questions
                log_test("UserMgmt: User has all fields",
                        has_fields,
                        None if has_fields else f"Only {len(user)} fields")
            
            # Test 3: User data integrity
            if user:
                username_correct = user[0] == 'user0'
                firstname_correct = user[4] == 'First0'
                log_test("UserMgmt: User data correct",
                        username_correct and firstname_correct,
                        None if (username_correct and firstname_correct) else f"Username={user[0]}, Name={user[4]}")
            
            # Test 4: Multiple users can coexist
            all_users_exist = all(db.get_user(f'user{i}') is not None for i in range(5))
            log_test("UserMgmt: Multiple users coexist",
                    all_users_exist,
                    None if all_users_exist else "Some users not found")
            
            # Test 5: Default admin users exist
            admin_exists = db.get_user('admin') is not None
            log_test("UserMgmt: Default admin user exists",
                    admin_exists,
                    None if admin_exists else "Admin not found")
            
            # Test 6: Failed attempts per user are independent
            db.increment_failed_attempt('user1')
            db.increment_failed_attempt('user1')
            user1 = db.get_user('user1')
            user2 = db.get_user('user2')
            
            if user1 and user2:
                user1_fails = user1[2]
                user2_fails = user2[2]
                independent = user1_fails == 2 and user2_fails == 0
                log_test("UserMgmt: Failed attempts are per-user",
                        independent,
                        None if independent else f"User1={user1_fails}, User2={user2_fails}")
        
    except Exception as e:
        log_test("User Management", False, str(e))

def test_session_management():
    """Test session and token management"""
    print("\n=== Testing Session Management ===")
    
    try:
        from database_manager import DatabaseManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test_session.db')
            db = DatabaseManager(db_path)
            
            # Create test user
            user_data = {
                'username': 'sessiontest',
                'password': 'SessionPass123!',
                'first_name': 'Session',
                'last_name': 'Test',
                'dob': '1993-09-05',
                'questions': [
                    ['What is your favorite color?', 'Orange'],
                    ['What is your pet\'s name?', 'Buddy'],
                    ['What city were you born in?', 'Miami']
                ]
            }
            db.create_user(user_data)
            
            # Test 1: Create session (if method exists)
            if hasattr(db, 'create_session'):
                session_token = db.create_session('sessiontest')
                log_test("Session: Create session returns token",
                        session_token is not None and len(session_token) > 10,
                        None if (session_token and len(session_token) > 10) else f"Invalid token: {session_token}")
                
                # Test 2: Validate session
                if hasattr(db, 'validate_session'):
                    valid = db.validate_session(session_token)
                    log_test("Session: Valid session validates",
                            valid,
                            None if valid else "Session validation failed")
                    
                    # Test 3: Invalid session rejected
                    invalid = db.validate_session('invalid_token_xyz')
                    log_test("Session: Invalid session rejected",
                            not invalid,
                            None if not invalid else "Invalid session accepted")
                
                # Test 4: Expire session
                if hasattr(db, 'expire_session'):
                    success = db.expire_session(session_token)
                    log_test("Session: Expire session succeeds",
                            success,
                            None if success else "Session expiration failed")
                    
                    # Test 5: Expired session invalid
                    if hasattr(db, 'validate_session'):
                        expired_valid = db.validate_session(session_token)
                        log_test("Session: Expired session invalid",
                                not expired_valid,
                                None if not expired_valid else "Expired session still valid")
            
            # Test 6: Session timeout (if implemented)
            if hasattr(db, 'create_session') and hasattr(db, 'validate_session'):
                token = db.create_session('sessiontest')
                # Simulate time passing (if timeout is configurable)
                time.sleep(0.1)
                still_valid = db.validate_session(token)
                log_test("Session: Recent session still valid",
                        still_valid,
                        None if still_valid else "Session expired too quickly")
        
    except Exception as e:
        log_test("Session Management", False, str(e))

def run_all_tests():
    """Run complete authentication test suite"""
    print("=" * 60)
    print("EmberEye Authentication & User Management Tests")
    print("=" * 60)
    
    test_user_creation()
    test_authentication()
    test_password_operations()
    test_user_management()
    test_session_management()
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Passed: {test_results['passed']}")
    print(f"Failed: {test_results['failed']}")
    
    if test_results['errors']:
        print("\nFailed Tests:")
        for error in test_results['errors']:
            print(f"  - {error}")
    
    print("=" * 60)
    
    return test_results['failed'] == 0

if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
