import json
import base64
import hmac
import hashlib
import datetime
import uuid
from vendorepojo import Vendor
 

class LicenseKeyGenerator:
    """
    A class to generate and validate license keys.
    """

    def __init__(self, secret_key):
        """
        Initializes the LicenseKeyGenerator with a secret key.

        Args:
            secret_key (str): The secret key used for generating and validating licenses.
        """
        self.secret_key = secret_key.encode('utf-8')  # Ensure secret key is bytes

    def generate_license_key(self, activation_key, vendor,expiration_days=365):
        """
        Generates a license key based on the activation key and expiration date.

        Args:
            activation_key (str): The activation key provided by the application.
            expiration_days (int): Number of days until the license expires. Defaults to 365.

        Returns:
            str: The generated license key, or None if an error occurs.
        """
        try:
            expiration_date = datetime.datetime.now() + datetime.timedelta(days=getattr(vendor, "liscensedays"))
            expiration_str = expiration_date.strftime("%Y-%m-%d")
            vendor.update(expiration_date=expiration_str)
            # noofusers = "3"
            # vendor_name = "Key Kard"
            # data = f"{activation_key}:{expiration_str}:{noofusers}:{vendor_name}".encode('utf-8')
            data = f"{vendor.to_json()}${activation_key}".encode('utf-8')
            hashed_data = hashlib.sha256(data + self.secret_key).hexdigest()

            combined_data = f"{vendor.to_json()}${activation_key}${hashed_data}"
            encoded_license = base64.urlsafe_b64encode(combined_data.encode('utf-8')).decode('utf-8').rstrip("=") #Remove padding.

            return encoded_license

        except Exception as e:
            print(f"Error generating license key: {e}")
            return None

    def validate_license_key(self, license_key):
        """
        Validates a license key.

        Args:
            license_key (str): The license key to validate.

        Returns:
            tuple: A tuple containing (True, activation_key, expiration_date) if the license is valid,
                   or (False, None, None) if the license is invalid.
        """
        try:
            # Add back any padding that was removed.
            missing_padding = len(license_key) % 4
            if missing_padding:
                license_key += '=' * (4 - missing_padding)

            print(f"License Key (with padding): {license_key}") #Debug print

            decoded_license_bytes = base64.urlsafe_b64decode(license_key.encode('utf-8'))
            decoded_license = decoded_license_bytes.decode('utf-8')

            print(f"Decoded License: {decoded_license}") #Debug print

            vendor_dict,activation_key ,hashed_received = decoded_license.split("$")
            vendor = Vendor.from_json(vendor_dict)
            expiration_date = datetime.datetime.strptime(vendor.expiration_date, "%Y-%m-%d").date()
            data = f"{vendor.to_json()}${activation_key}".encode('utf-8')
            hashed_expected = hashlib.sha256(data + self.secret_key).hexdigest()

            if hashed_received == hashed_expected:
                if datetime.date.today() <= expiration_date:
                    return True, vendor.to_dict(), activation_key,expiration_date
                else:
                    return False, None, None, None # License expired
            else:
                return False, None, None,None # Hash mismatch
        except Exception as e:
            print(f"Error validating license key: {e}")
            return False, None, None

# Usage Example
if __name__ == "__main__":
    secret_key = "my_super_secret_key"  # Replace with a strong, unique secret key
    generator = LicenseKeyGenerator(secret_key)

    activation_key = str(uuid.uuid4()) #For test purposes. In real application, get this from the application.
    print(f"Activation Key: {activation_key}")

    # license_key = generator.generate_license_key(activation_key, Vendor("102134", "Alice wonderland", "san fransisco","Mig-85", 360))
    license_key = "eyJpZCI6ICIxMDIxMzQiLCAibmFtZSI6ICIxIiwgImFkZHJlc3MiOiAiMSIsICJjaXR5IjogIjEiLCAibGlzY2Vuc2VkYXlzIjogMSwgImV4cGlyYXRpb25fZGF0ZSI6ICIyMDI1LTAzLTIxIn0kYidNbVZtTkRBNU9EWm1OamN4TXprMU1USTVOekkyTlRSbFpURTVZMlkyTmpkak5tSmxNemxsWVRSalltUmhPV05oTWpJMU1XWmxOMk5sWVRFNE5HRTVOenBqWkRZMk5tRTBZeTB3WTJGakxUUmlaR010T0RRMFpTMDRNbU13TlRFd01UWXpPR1E2T0dVMFlUYzNZamt0WmpRd01TMDBaVGRrTFdKbE5UZ3RaVGM0WXpFME9EbGxaalZrT2pkbU5EWTBOVFl6WVRneE5qQXpObUUyT1RGaU5tUTBZVGt6WlRVeE4yWmtZelZrWlRWbU5EY3pabU5pTmpjME9EWXlPVGN5Wm1JeU0yRXhOamM1T0RBJyRlYWUyZDE1YjQ1Y2JiZjBlYWUwMWU5NDk0YTU0NGI0MzVjMzU1YzgyYmE4OTkwOGY3Njc5MGYxMDZiODE2ZmFj"    
    if license_key:
        print(f"License Key: {license_key}")

        is_valid, vendore_json,valid_activation_key, valid_expiration_date = generator.validate_license_key(license_key)

        if is_valid:
            print("License is valid.")
            print(f"Vendor details: {Vendor.from_dict(vendore_json)}")
            print(f"Activation Key: {valid_activation_key}")
            print(f"Expiration Date: {valid_expiration_date}")
                # print(f"Expiration Date: {noofusers}")
                # print(f"Expiration Date: {vendor_name}") 
        else:
            print("License is invalid.")

        #Example of an invalid license
        # invalid_license = "some_invalid_key"
        # is_valid, valid_activation_key, valid_expiration_date = generator.validate_license_key(invalid_license)
        # if is_valid:
        #     print("License is valid.")
        # else:
        #     print("License is invalid.")