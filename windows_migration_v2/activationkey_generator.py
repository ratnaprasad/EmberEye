import uuid
import hashlib
import base64
import platform
import getpass
import os

class ActivationKeyGenerator:
    """
    Generates and validates activation keys.
    """

    def __init__(self, secret_key):
        """
        Initializes the ActivationKeyGenerator with a secret key.

        Args:
            secret_key (str): The secret key used for generating and validating keys.
        """
        self.secret_key = secret_key.encode('utf-8')

    def _get_system_signature(self):
        """
        Generates a system signature based on platform and hardware information.

        Returns:
            str: The system signature.
        """
        system_info = {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "machine": platform.machine(),
            "node": platform.node(),
            "os_version": platform.version(),
            "username": getpass.getuser(),
            "cwd": os.getcwd(),
        }
        return hashlib.sha256(str(system_info).encode('utf-8')).hexdigest()

    def generate_activation_key(self, user_id, salt=None):
        """
        Generates an activation key.

        Args:
            user_id (str): The user ID.
            salt (str, optional): A salt to add randomness. Defaults to None.

        Returns:
            str: The generated activation key.
        """
        system_signature = self._get_system_signature()
        if salt is None:
            salt = str(uuid.uuid4())

        combined_data = f"{system_signature}:{user_id}:{salt}".encode('utf-8') #encode combined data.
        salted_key = hashlib.sha256(combined_data + self.secret_key).hexdigest() #hash with bytes.

        activation_key = base64.urlsafe_b64encode(f"{system_signature}:{user_id}:{salt}:{salted_key}".encode('utf-8')).decode('utf-8').rstrip("=")

        return activation_key

    def validate_activation_key(self, activation_key):
        """
        Validates an activation key.

        Args:
            activation_key (str): The activation key to validate.

        Returns:
            tuple: (True, user_id, salt) if valid, (False, None, None) otherwise.
        """
        try:
            missing_padding = len(activation_key) % 4
            if missing_padding:
                activation_key += '=' * (4 - missing_padding)

            decoded_data = base64.urlsafe_b64decode(activation_key.encode('utf-8')).decode('utf-8')
            system_signature, user_id, salt, received_salted_key = decoded_data.split(":")

            expected_system_signature = self._get_system_signature()

            if expected_system_signature != system_signature:
                return False, None, None # System signature mismatch

            combined_data = f"{system_signature}:{user_id}:{salt}".encode('utf-8')
            expected_salted_key = hashlib.sha256(combined_data + self.secret_key).hexdigest()

            if received_salted_key == expected_salted_key:
                return True, user_id, salt
            else:
                return False, None, None # Salted key mismatch

        except Exception as e:
            print(f"Error validating activation key: {e}")
            return False, None, None

# Example Usage
if __name__ == "__main__":
    secret_key = "my_super_secret_key"
    generator = ActivationKeyGenerator(secret_key)

    user_id = str(uuid.uuid4())
    activation_key = generator.generate_activation_key(user_id)

    print(f"User ID: {user_id}")
    print(f"Activation Key: {activation_key}")

    is_valid, valid_user_id, salt = generator.validate_activation_key(activation_key)

    if is_valid:
        print("Activation key is valid.")
        print(f"Valid User ID: {valid_user_id}")
        print(f"Salt: {salt}")
    else:
        print("Activation key is invalid.")