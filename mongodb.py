from pymongo import MongoClient
import streamlit as st
from langchain_core.messages import HumanMessage, AIMessage

# MongoDB connection
def get_mongo_client():
    if "MONGO_URI" in st.secrets:
        # os.environ["MONGO_URI"] = st.secrets["MONGO_URI"]
        mongo_client = MongoClient(st.secrets["MONGO_URI"])
        db = mongo_client["chatbot_db"]
        print("MongoDB connection established")
        return db
    else:
        print("MONGO_URI not found in secrets")
        return None
    
db = get_mongo_client()

# Function to convert list of messages of LangChain to JSON format for storage in MongoDB
def messages_to_json(messages):
    db_history = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            db_history.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            db_history.append({"role": "assistant", "content": msg.content})
    return db_history

# Function to convert JSON format from MongoDB to list of messages of LangChain
def json_to_messages(db_history):
    langchain_history = []
    for msg in db_history:
        if msg["role"] == "user":
            langchain_history.append(HumanMessage(content = msg["content"]))
        elif msg["role"] == "assistant":
            langchain_history.append(
                AIMessage(content = msg["content"],
                            metadata = {}))
    return langchain_history

# Function to load all chat session of current user
def load_all_user_chats():
    user_chats = {}
    if db is not None and db.name == "chatbot_db":
        chat_collection = db["chat_sessions"]
        for chat_document in chat_collection.find({"user_id": st.session_state.username}):
            chat_id = chat_document["_id"]
            
            v_store = None
            if chat_document.get("has_pdf", False):
                from pdf_loader_embedding import reconnect_to_pinecone
                v_store = reconnect_to_pinecone(chat_id)
                print(f"Reconnected to Pinecone for session: {chat_id}")
                
            user_chats[chat_id] = {
                "title": chat_document["title"],
                "history": json_to_messages(chat_document["history"]),
                "vector_store": v_store
            }
    return user_chats

## CRUDE operations for chat sessions in MongoDB

# 1. Insert a new chat session into MongoDB
def insert_chat_session(chat_id, chat_data):
    if db is not None and db.name == "chatbot_db":
        chat_collection = db["chat_sessions"]
        chat_document = {
            "_id": chat_id,
            "user_id": st.session_state.username, 
            "title": chat_data["title"],
            "history": messages_to_json(chat_data["history"]),
            "has_pdf": False
        }
        chat_collection.insert_one(chat_document)
        print(f"Inserted new chat session with ID: {chat_id}")
    else:
        print("MongoDB connection not established. Cannot insert chat session.")
        
# 2. Retrieve a chat session from MongoDB
def retrieve_chat_session(chat_id):
    if db is not None and db.name == "chatbot_db":
        chat_collection = db["chat_sessions"]
        chat_document = chat_collection.find_one({"_id": chat_id, "user_id": st.session_state.ussername})
        if chat_document:
            print(f"Retrieved chat session with ID: {chat_id}")
            return {
                "title": chat_document["title"],
                "history": json_to_messages(chat_document["history"]),
                "has_pdf": chat_document.get("has_pdf", False)
            }
        else:
            print(f"No chat session found with ID: {chat_id}")
            return None
    else:
        print("MongoDB connection not established. Cannot retrieve chat session.")
        return None

# 3. Update a chat session in MongoDB
def update_chat_session(chat_id, chat_data):
    if db is not None and db.name == "chatbot_db":
        chat_collection = db["chat_sessions"]
        has_pdf = chat_data.get("vector_store") is not None
        chat_collection.update_one(
            {"_id": chat_id},
            {"$set": {
                "title": chat_data["title"],
                "history": messages_to_json(chat_data["history"]),
                "has_pdf": has_pdf
            }}
        )
        print(f"Updated chat session with ID: {chat_id}")
    else:
        print("MongoDB connection not established. Cannot update chat session.")
        
        
# 4. Delete chat session and its history stored on MongoDB
def delete_chat_session(chat_id):
    if db is not None and db.name == "chatbot_db":
        chat_collection = db["chat_sessions"]
        chat_collection.delete_one(
            {"_id": chat_id}
        )
        print(f"Delete chat session with ID: {chat_id}")
    else:
        print("MongoDB connection not established. Cannot delete chat session.")