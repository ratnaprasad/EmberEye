import json
from vendorepojo import Vendor
class VendorDataHandler:
    """
    A class to create, store, and retrieve JSON data arrays.
    """

    def __init__(self, filename="data_array.json"):
        """
        Initializes the JsonDataArrayHandler with a filename.

        Args:
            filename (str): The name of the JSON file to use. Defaults to "data_array.json".
        """
        self.filename = filename
        self.data_array = self._load_data()

    def _load_data(self):
        """
        Loads JSON data array from the file.

        Returns:
            list: The loaded JSON data array, or an empty list if the file doesn't exist or is invalid.
        """
        try:
            with open(self.filename, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return []
        except json.JSONDecodeError:
            print(f"Warning: Invalid JSON in {self.filename}. Creating a new file.")
            return []

    def _save_data(self):
        """
        Saves the JSON data array to the file.
        """
        with open(self.filename, "w") as f:
            json.dump(self.data_array, f, indent=4)

    def add_item(self, item):
        """
        Adds an item to the data array.

        Args:
            item (dict): The item (dictionary) to add.
        """
        self.data_array.append(item)
        self._save_data()

    def get_all_items(self):
        """
        Retrieves all items from the data array.

        Returns:
            list: A copy of all items in the data array.
        """
        return self.data_array[:] # creates a shallow copy

    def get_items_by_criteria(self, criteria):
        """
        Retrieves items that match the given criteria.

        Args:
            criteria (dict): A dictionary representing the criteria to match.

        Returns:
            list: A list of items that match the criteria.
        """
        matching_items = []
        for item in self.data_array:
            match = True
            # print(item)
            vendor = Vendor.from_json(item)
            for key, value in criteria.items():
                if getattr(vendor, key) != value:
                    match = False
                    break
            if match:
                matching_items.append(item)
        return matching_items

    def delete_items_by_criteria(self, criteria):
        """
        Deletes items based on provided criteria.

        Args:
            criteria (dict): A dictionary representing the criteria to match.
        """
        self.data_array = [item for item in self.data_array if not all(item.get(key) == value for key, value in criteria.items())]
        self._save_data()

# Example Usage
handler = VendorDataHandler("EmberEye.json")

# handler.add_item(Vendor("102134", "Alice wonderland", "san fransisco","Mig-85", 360).to_json())
# handler.add_item(Vendor("102135", "Toma hawk", "New York","Mig-85, 39-33-79/1", 180).to_json())
# handler.add_item(Vendor("102136", "trustwoods", "New Jersey","Mig-85", 720).to_json())

print("All items:", handler.get_all_items())

new_york_items = handler.get_items_by_criteria({"id": "102134"})
print("Items from New York:", new_york_items)

age_30_items = handler.get_items_by_criteria({"liscensedays": 30})
print("Items with age 30:", age_30_items)

# handler.delete_items_by_criteria({"city":"New Jersey"})
# print("Items after deleting London:", handler.get_all_items())