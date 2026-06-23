import sys
import os
from google import genai 
from google.genai import errors
import time
import streamlit as st
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_core.messages import HumanMessage, AIMessage
from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_pinecone import PineconeVectorStore
from typing import List
from pymongo import MongoClient

st.title("Gemini-2.5-flash Chatbot")
@st.cache_resource
def initialize_client():
    #return genai.Client()
    return ChatGoogleGenerativeAI(
        model = "gemini-2.5-flash",
        temperature = 0.7)

# print("Initilizing memory with gemeini-2.5-flash")

# LLM
client = initialize_client()

# Pineconce index name:
PINECONE_INDEX_NAME = "gemini-chatbot-index"

if "PINECONE_API_KEY" in st.secrets:
    os.environ["PINECONE_API_KEY"] = st.secrets["PINECONE_API_KEY"]
    
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
    

# Document loader to allow user to upload their own PDF and use it as context for the chatbot
def load_pdf(file):
    reader = PdfReader(file)
    full_text = ""
    for page in reader.pages:
        text = page.extract_text()
        if text:
            full_text += text + "\n"
    return full_text

class GoogleGenAIEmbeddingsWrapper:
    def __init__(self, model_name: str = "gemini-embedding-2"):
        # Get the API key from environment variables, either GEMINI_API_KEY or PINECONE_API_KEY
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("PINECONE_API_KEY")
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        # For each document in the list, call the embed_content method to get the embeddings
        response = self.client.models.embed_content(
            model=self.model_name,
            contents=texts,
            config={"output_dimensionality": 768}
        )
        # Return the embeddings as a list of lists of floats
        return [e.values for e in response.embeddings]

    def embed_query(self, text: str) -> List[float]:
        # This function is used to embed the user's question when chatting
        response = self.client.models.embed_content(
            model=self.model_name,
            contents=text,
            config={"output_dimensionality": 768}
        )
        return response.embeddings[0].values

# Function to process pdf to vector store
def process_pdf_to_vector_store(file):
    documents = load_pdf(file)
    text_splitter = RecursiveCharacterTextSplitter(chunk_size = 1000, chunk_overlap = 200)
    splitted_docs = text_splitter.split_text(documents)
    
    # Create vector store
    #embeddings = OllamaEmbeddings(model = "all-minilm")
    embeddings = GoogleGenAIEmbeddingsWrapper(model_name = "gemini-embedding-2")
    current_chat_id = st.session_state.current_chat_id
    #vector_store = FAISS.from_texts(splitted_docs, embeddings)
    vector_store = PineconeVectorStore.from_texts(
        namespace = current_chat_id, 
        texts = splitted_docs, 
        embedding = embeddings,
        index_name = PINECONE_INDEX_NAME
    )
    return vector_store

# Function for retrieving relevant context from vector store
def retrieve_relevant_context(vector_store, query, top_k = 3):
    relevant_docs = vector_store.similarity_search(query, k = top_k)
    context_list = []
    for doc in relevant_docs:
        if hasattr(doc, "page_content"):
            context_list.append(doc.page_content)
        else:
            context_list.append(str(doc))
    return "\n\n".join(context_list)

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

## CRUDE operations for chat sessions in MongoDB

# 1. Insert a new chat session into MongoDB
def insert_chat_session(chat_id, chat_data):
    if db is not None and db.name == "chatbot_db":
        chat_collection = db["chat_sessions"]
        chat_document = {
            "_id": chat_id,
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
        chat_document = chat_collection.find_one({"_id": chat_id})
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


# 
def reconnect_to_pinecone(chat_id):
    embeddings = GoogleGenAIEmbeddingsWrapper(model_name = "gemini-embedding-2")
    return PineconeVectorStore(
        namespace = chat_id, 
        embedding = embeddings,
        index_name = PINECONE_INDEX_NAME
    )

if "all_chats" not in st.session_state:
    st.session_state.all_chats = {}
    if db is not None and db.name == "chatbot_db":
        chat_collection = db["chat_sessions"]
        for chat_document in chat_collection.find():
            chat_id = chat_document["_id"]
            
            # Reconnect to Pinecone vector store if the chat session has a PDF context
            v_store = None
            if chat_document.get("has_pdf", False):
                v_store = reconnect_to_pinecone(chat_id)
                print(f"Reconnected to Pinecone vector store for chat session ID: {chat_id}")
            
            st.session_state.all_chats[chat_id] = {
                "title": chat_document["title"],
                "history": json_to_messages(chat_document["history"]),
                "vector_store": v_store
            }

if "current_chat_id" not in st.session_state:
    st.session_state.current_chat_id = None
    
with st.sidebar:
    st.title("Chat Management")
    
    if st.button("New chat"):
        curent_timestamp = time.time()
        generated_id = f"Chat_{int(time.time())}"
        
        new_chat_data = {
            "title": f"Chat session {int(time.time())}",
            "history": [],
            "has_pdf": False
        }
        
        # Insert the new chat session into MongoDB
        insert_chat_session(generated_id, new_chat_data)
        # Update the session state with the new chat session
        st.session_state.all_chats[generated_id] = new_chat_data
        # Update the current chat ID to the newly created chat session
        st.session_state.current_chat_id = generated_id
    
        st.rerun()

    # Display the list of chat as a button
    for chat_id, chat_data in st.session_state.all_chats.items():
        is_current = (chat_id == st.session_state.current_chat_id)
        
        if st.button(
            chat_data["title"],
            key = chat_id, 
            type = "primary" if is_current else "secondary"
        ) : 
            st.session_state.current_chat_id = chat_id
            st.rerun()

if not st.session_state.current_chat_id:
    st.info("Click the 'New chat' to start a conversation")
else:
    active_chat = st.session_state.all_chats[st.session_state.current_chat_id]
    st.caption(f"You are in chat session: {active_chat['title']}, please type your question")
    
    if "pdf_context" not in active_chat:
        active_chat["pdf_context"] = None
        
    if "vector_store" not in active_chat:
        active_chat["vector_store"] = None
    
    # Display chat history
    for msg in active_chat["history"]:
        if isinstance(msg, HumanMessage):
            with st.chat_message("user"):
                st.write(msg.content)
        elif isinstance(msg, AIMessage):
            with st.chat_message("assistant"):
                st.write(msg.content)
                if "generation_time" in msg.metadata:
                    st.write(f"Time taken to generate response: {msg.metadata['generation_time']:.2f} seconds")
    
    st.markdown("---")
    
    chat_container = st.container()
    with st.bottom:
        with st.popover("+ Attach", use_container_width = True):
            st.markdown("Select attachment type:")
            uploaded_file = st.file_uploader(
                    "Document context (PDF)",
                    type = "pdf",
                    key = f"file_uploader_{st.session_state.current_chat_id}",
                    label_visibility = "visible"
                )
            st.caption("Future options:")
            st.button("Upload image", disabled = True, use_container_width = True)
            st.button("Upload audio", disabled = True, use_container_width = True)
            
        user_message = st.chat_input("Type your message here", key = f"user_input_{st.session_state.current_chat_id}")
        
        
    # uploaded_file = st.file_uploader("Upload a PDF document to use as context", type = "pdf")
    
    # If user cancel the PDF file, remove the vector store from the chat session
    if uploaded_file is None:
        if active_chat["vector_store"] is not None:
            active_chat["vector_store"] = None
            st.toast("PDF context removed for this chat session")
            
    # Process the PDF and create vector store if a new PDF is uploaded and there is no existing vector store for the chat session
    elif uploaded_file is not None and active_chat["vector_store"] is None:
        with st.spinner("Processing PDF..."):
            try:
                # Start time process the PDF
                start_time_pdf = time.time()
                active_chat["vector_store"] = process_pdf_to_vector_store(uploaded_file)
                end_time_pdf = time.time()
                duration_pdf = end_time_pdf - start_time_pdf
                print(f"PDF processed in {duration_pdf:.2f} seconds")
                st.success(f"PDF processed, loaded and added to chat context in {duration_pdf:.2f} seconds")

                
            except Exception as e:
                st.error(f"Error loading PDF: {str(e)}")
    
    # Input for new message
    if user_message :
        with st.chat_message("user"):
            st.write(user_message)
        #active_chat["history"].append({"role": "user", "text": user_message})
        
        final_prompt = user_message

        if uploaded_file is not None and active_chat["vector_store"]:
            relevant_context = retrieve_relevant_context(active_chat["vector_store"], user_message)
            final_prompt = f"Please answer the user's question based on the provided context and conversation history: {relevant_context}\n\nUser question: {user_message}"
        
        active_chat["history"].append(HumanMessage(content = user_message))
           
        # Call API for the active chat
        with st.chat_message("assistant"):
            placeholder = st.empty()
            try:
                message_to_send = active_chat["history"][:-1] + [HumanMessage(content = final_prompt)]
                
                start_time_generation = time.time()
                response = client.invoke(message_to_send)
                ai_content = response.content
                end_time_generation = time.time()
                
                st.write(f"Time taken to generate response: {end_time_generation - start_time_generation:.2f} seconds")
                print(f"Response generated in {end_time_generation - start_time_generation:.2f} seconds")
                placeholder.write(ai_content)
                
                # 2 mesages objects: HumanMessage and AIMessage, both have content and metadata attributes. We can store the generation time in the metadata of the AIMessage object.
                user_msg_obj = HumanMessage(content = user_message)
                ai_msg_obj = AIMessage(content = ai_content, 
                                        metadata = {"generation_time": end_time_generation - start_time_generation})
                active_chat["history"].append(ai_msg_obj)
                update_chat_session(st.session_state.current_chat_id, active_chat)
                print(f"Response generated in {end_time_generation - start_time_generation:.2f} seconds")
                   
                if len(active_chat["history"]) == 2:
                    active_chat["title"] = user_message[:20] + "..."
                    if db is not None:
                        db["chat_sessions"].update_one(
                            {"_id": st.session_state.current_chat_id},
                            {"$set": {"title": active_chat["title"]}}
                        )
                    st.rerun()
            except errors.APIError as e:
                placeholder.write("Server connection error, please try again")




    