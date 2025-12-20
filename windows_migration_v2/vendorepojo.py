import json

class Vendor:
    """
    A Plain Old Java Object (POJO) class to represent a person.
    """

    def __init__(self, id, name, city,address, liscensedays,expiration_date=None):
        """
        Initializes a Person object.

        Args:
            name (str): The person's name.
            city (str): The person's city.
            age (int): The person's age.
        """
        self.id = id
        self.name = name
        self.city = city
        self.address = address
        self.liscensedays = liscensedays
        self.expiration_date = expiration_date

    def __str__(self):
        """
        Returns a string representation of the Vendore object.
        """
        return f"Vendore(id='{self.id}', name='{self.name}', address='{self.address}', city={self.city}, liscensedays={self.liscensedays}, expiration_date={self.expiration_date})"

    def __repr__(self):
        """
        Returns a string representation of the Person object for debugging.
        """
        return f"Vendore(id='{self.id}', name='{self.name}', address='{self.address}', city={self.city}, liscensedays={self.liscensedays}, expiration_date={self.expiration_date})"

    def to_dict(self):
        """
        Returns a dictionary representation of the Person object.
        """
        return {
             "id": self.id,
            "name": self.name,
            "address": self.address,
            "city": self.city,
            "liscensedays": self.liscensedays,
            "expiration_date":self.expiration_date
        }


    def update(self, **kwargs):
        """
        Updates the Person object's attributes.

        Args:
            **kwargs: Keyword arguments for attributes to update.
        """
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
            else:
                self._extra_attributes[key] = value

    @classmethod
    def from_dict(cls, data):
        """
        Creates a Vendore object from a dictionary.

        Args:
            data (dict): A dictionary containing Vendore data.

        Returns:
            Vendore: A Vendore object.
        """
        return cls(data["id"],data["name"], data["city"], data["address"], data["liscensedays"], data["expiration_date"])

    @classmethod
    def from_dict(cls, data):
        """
        Creates a Person object from a dictionary.

        Args:
            data (dict): A dictionary containing person data.

        Returns:
            Vendor: A Vendor object.
        """
        return cls(data["id"],data["name"], data["city"], data["address"], data["liscensedays"], data["expiration_date"])

    def to_json(self):
        """
        Serializes the Person object to a JSON string.
        """
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str):
        """
        Deserializes a JSON string to a Person object.

        Args:
            json_str (str): A JSON string representing a Person object.

        Returns:
            Person: A Person object.
        """
        data = json.loads(json_str)
        return cls.from_dict(data)




# # Example Usage id, name, city,address, liscensedays
# vendor = Vendor("102134", "Alice", "New York","Mig-85", 360)
# print(vendor)  # Output: Person(name='Alice', city='New York', age=30)

# vendor_dict = vendor.to_dict()
# print(vendor_dict) #Output: {'name': 'Alice', 'city': 'New York', 'age': 30}

# vendor2 = vendor.from_dict({'id': '102134', 'name': 'Alice wonderland', 'address': 'Mig-85', 'city': 'san fransisco', 'liscensedays': 360, 'expiration_date': '2026-03-15'})
# print(vendor2) #Output: Person(name='Alice', city='New York', age=30)