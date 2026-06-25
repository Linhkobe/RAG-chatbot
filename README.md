# Multi-user RAG chatbot with Gemeni, MongoDB and Pinecone 

## 1. Objective of the project 
The primary objective of this project is to build a full-stack, enterprise-grade AI chatbot : 
* Production-ready security : Implement a strict authentification system to ensure data isolation between multiple tenants. 

* Contextual intelligence (RAG) : empowers users to dynamically -upload PDF documents and hols context-aware conversation. 

* Modular programming approach : separating authentification, database, embedding generation, and UI layer to maintain clean and scalable source code. 

## 2. Techstack & architecture decisions 

| Technology | Role | Why This Technology? |
| :--- | :--- | :--- |
| **Streamlit** | Frontend UI | Accelerates UI development with native session state management, ideal for handling ongoing chat interactions without full JavaScript frameworks. |
| **Gemini 2.5 Flash** | Core LLM | Offers fast generation speeds, a massive context window, and native support via the official Google GenAI SDK. |
| **Gemini Embedding 2** | Embedding Model | Generates high-quality 768-dimensional semantic vectors that perfectly align with the Gemini LLM's comprehension layers. |
| **MongoDB Atlas** | NoSQL Database | Highly flexible document structure allows seamless conversion of LangChain `HumanMessage` / `AIMessage` objects into JSON arrays for persistence. |
| **Pinecone** | Vector Database | A cloud-native, fully managed vector database optimized for extremely fast similarity searches. Supports dynamic vector spacing using custom namespaces. |
| **Bcrypt** | Password Hashing | Industrial standard for crypto-hashing. Uses a slow-hashing function with automatic salt generation to guard against Rainbow Table and Brute-Force attacks. |

## 3. Project structure
- streamlit/secrets.toml    # Encrypted local API keys & DB connection strings
- auth.py                   # Decoupled logic for password hashing, registration, & login
- mongodb.py                # CRUD utilities for storing/retrieving user sessions & message formats
- pdf_loader_embedding.py   # PDF text extraction, text chunking, and Pinecone vector store flows
- test_agent.py             # Main application orchestrator containing the Streamlit UI components
- requirements.txt          # Defined python dependencies

## 4. How does the data flow 
A. Data storage strategy 
- User accounts : saved under "users" collection in MongoDB. Passwords undergo a salt-and-hash cycle via bcrypt before entry. 
- Coversations : saved under the "chat_sessions" collection in MongoDB. Every doculent explicitely trachs a "user_id" field to enforce strict data-multitenancy.
- Vector documents : chunks extracted from user-uploaded PDF files are stored inside Pinecone under an isolated "namespace" mapped directly to the activce "chat_id". 

B. User Scenarios & Execution Path

* Scenario 1: User uploads PDF and asks a question (RAG flow)
- Upload & Chunking : the system reads pages via library "pypdf", breaks raw text into 1000-character (with 200-character overlap) to preserve context boundaries. 
- Indexing : segments pass through Google's embedding model gemeni-embedding-2 to output 768-dimension floats, which are pushed to Pinecone flagged under the current "chat_id" namespace. 
- Retrieval : when a query arrives, it's embedded using the same embedding model, the system pulls the top 3 most semantically identical text pieces out of Pinecone vector database. 
- Synthesis : the retrieved text chunks are stiched together along with the chat history into a prompt and passed to LLM model Gemini 2.5 Flash to output a precise answer.

* Scenario 2: User only asks questions (standard chat flow)
- History packaging: the platform pulls current conversation logs out of Streamlit's local "session_state". 
- Context assembly: it bypasses Pinecone call completely, the pormpt string contains only the user"s message paired with pass messages. 
- Execution: the structured LangChain payload goes directly to Gemini 2.5 Flash, returning a standrad, fast contextual response. 

## 5. CI/CD process 
The repository maintains a deployment feedback loop: 
- Automated package assembly: upstream pushes onto Github trigger remote listeners to match, configure and install python dependencies specified in "requirements.txt" file. 
- Synchronization: environment configurations and API parameters are bound safely on server parameters without putting production credentials out in open source. 

## 6. Deployment 
The platform is fully deployable via cloud platforms such as Streamlit Community Cloud, render or Haiku: 
- Connect your version-controller Github repo to the target hosting solution. 
- Set up your production environment API keys (such as MONGO_URI, PINECONE_API_KEY,...)
- The platform executes streamlit run test_agent.py automatically exposing the secure SSL interface globally. 

## 7. Future extensions 
To expand this platform into a commercial SaaS application, the following milestones are planned: 
- Custom text splitter 
- JWT Token Sessions: Transition from pure Streamlit state variables to secure, time-expiring JSON Web Tokens (JWT) for secure state control.
- Multimodal Processing: Open the attachment popover options to support real-time audio and image ingestion via Gemini's native multimodal vision capabilities.