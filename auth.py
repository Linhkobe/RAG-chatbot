import bcrypt
from pymongo import MongoClient 
import os
import datetime
import jwt
import streamlit as st 

JWT_SECRET = os.environ.get("JWT_SECRET") or st.secrets.get("JWT_SECRET")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

def generate_jwt_token(username: str) -> str:
    payload = {
        "username" : username, 
        "exp" : datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=JWT_EXPIRATION_HOURS),
        "iat" : datetime.datetime.now(datetime.timezone.utc)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_jwt_token(token: str):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

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
        