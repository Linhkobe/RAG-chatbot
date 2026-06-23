import bcrypt
from pymongo import MongoClient 

# Function to identify the user
def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

# Function to verify the password
def verify_password(password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

# Function to register user
def register_user(db, username, password):
    if db is None:
        return False, "Database connection error"
    
    user_collection = db["users"]
    if user_collection.find_one({"username": username}):
        return False, "Username already existed!"
    
    hashed = hash_password(password)
    user_collection.insert_one({
        "username": username,
        "password": hashed
    })
    
    return True, "Registration successful!"

# Function to authentificate user
def authentificate_user(db, username, password):
    if db is None:
        return False, "Database connection error"
    
    user_collection = db["users"]
    user = user_collection.find_one({"username": username})
    
    if user and verify_password(password, user["password"]):
        return True, "Login successful!"
    return False, "Invalid username or password."
        