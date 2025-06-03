import os
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain.chains import RetrievalQA
from langchain_groq import ChatGroq

# Load API key from environment
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# ✅ Load HuggingFace Embedding model globally (once)
embedding_model = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

# === Load and split documents from uploaded PDFs ===
def load_documents(pdf_paths):
    all_docs = []
    for path in pdf_paths:
        try:
            loader = PyPDFLoader(path)
            file_docs = loader.load()
            all_docs.extend(file_docs)
        except Exception as e:
            print(f"[ERROR] Failed to load {path}: {e}")
    return all_docs

# === Create ChromaDB vector index in memory ===
def build_vector_index(documents, namespace="default"):
    if not documents:
        raise ValueError("No documents provided for indexing.")
    db = Chroma.from_documents(
        documents,
        embedding_model,
        collection_name=f"rag_{namespace}",  # ✅ unique name
        persist_directory=None
    )
    return db

# === Setup RAG Retrieval Chain ===
def get_qa_chain(vector_db):
    retriever = vector_db.as_retriever(search_type="similarity", search_kwargs={"k": 6})
    llm = ChatGroq(temperature=0, model_name="llama3-8b-8192")
    qa_chain = RetrievalQA.from_chain_type(llm=llm, retriever=retriever)
    return qa_chain

# === Ask a question to the QA chain ===
def ask_question(qa_chain, query):
    response = qa_chain.run(query)
    return response
