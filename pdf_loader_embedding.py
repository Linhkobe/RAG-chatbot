from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_pinecone import PineconeVectorStore
import streamlit as st
import os
from google import genai 
from typing import List
from pinecone import Pinecone

# Pineconce index name:
PINECONE_INDEX_NAME = "gemini-chatbot-index"

if "PINECONE_API_KEY" in st.secrets:
    os.environ["PINECONE_API_KEY"] = st.secrets["PINECONE_API_KEY"]
    
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

# 
def reconnect_to_pinecone(chat_id):
    embeddings = GoogleGenAIEmbeddingsWrapper(model_name = "gemini-embedding-2")
    return PineconeVectorStore(
        namespace = chat_id, 
        embedding = embeddings,
        index_name = PINECONE_INDEX_NAME
    )
    
# Function to delete namespace on Pinecone 
def delete_pinecone_namespace(chat_id:str):
    try:
        api_key = os.get("PINECONE_API_KEY")
        if not api_key:
            print("Pinecone API key not found!")
            return False 
        
        pc = Pinecone(api_key = api_key)
        
        # Connect to actual index that is being used : 
        index = pc.Index(PINECONE_INDEX_NAME)
        index.delete(delete_all = True, namespace = chat_id)
        print(f"Successfully cleared Pinecone vector namespace for chat ID: {chat_id}")
        return True 
    
    except Exception as e:
        print(f"Error clearning Pinecone namespace for chat ID : {chat_id}")
        return False