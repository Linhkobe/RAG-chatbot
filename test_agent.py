from google.genai import errors
import time
import streamlit as st
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage

from mongodb import get_mongo_client, json_to_messages, insert_chat_session, update_chat_session
from auth import register_user, authentificate_user
from pdf_loader_embedding import reconnect_to_pinecone, process_pdf_to_vector_store, retrieve_relevant_context

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
    
# MongoDB connection
db = get_mongo_client()

# Initialize authentification in session_state
if "authentificated" not in st.session_state:
    st.session_state.authentificated = False
if "username" not in st.session_state:
    st.session_state.username = None
    
if not st.session_state.authentificated:
    st.subheader("Authentification for RAG chatbot")
    
    tab_login, tab_register = st.tabs(["Sign in", "Sign up"])
    
    with tab_login:
        login_user = st.text_input("Login name", key = "login_user")
        login_pass = st.text_input("Password", type = "password", key = "login_pass")
        if st.button("Login", type = "primary"):
            if login_user and login_pass:
                success, msg = authentificate_user(db, login_user, login_pass)
                if success:
                    st.session_state.authentificated = True
                    st.session_state.username = login_user
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
            else:
                st.warning("Please fill in information")
                
    with tab_register:
        reg_user = st.text_input("New login name", key = "reg_user")
        reg_pass = st.text_input("New password", key = "reg_pass")
        reg_pass_confirm = st.text_input("Confirm password", type = "password", key = "reg_pass_confirm")
        if st.button("Create new account"):
            if reg_user and reg_pass and reg_pass_confirm:
                if reg_pass != reg_pass_confirm:
                    st.error("Not matching password")
                else:
                    success, msg = register_user(db, reg_user ,reg_pass)
                    if success:
                        st.success(msg)
                    else:
                        st.error(msg)
            else:
                st.warning("Please fill in information")

else:
    if "all_chats" not in st.session_state:
        from mongodb import load_all_user_chats
        st.session_state.all_chats = load_all_user_chats()
    
    if "current_chat_id" not in st.session_state:
        st.session_state.current_chat_id = None
        
    with st.sidebar:
        
        if st.button("Logout"):
            st.session_state.authentificated = False
            st.session_state.username = None
            if "all_chats" in st.session_state:
                del st.session_state.all_chats
            st.session_state.current_chat_id = None
            st.rerun()
        
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
                    placeholder.markdown("Generating answer")
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




    