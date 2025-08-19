import os
from io import BytesIO
from functools import lru_cache

from uuid import uuid4
from werkzeug.utils import secure_filename

from supabase import create_client
from pypdf import PdfReader

# Embeddings / Vector store
# from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import PGVector
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.docstore.document import Document

# LLM + QA chain
from langchain.chains import RetrievalQA
from langchain_groq import ChatGroq

from sqlalchemy import create_engine, text

# === ENV / Clients ===
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE = os.getenv("SUPABASE_SERVICE_ROLE")
PDF_BUCKET = "pdfs"  # created in Step 1

PG_CONN = os.getenv("DATABASE_URL")  # same DB used by your app
ENGINE_ARGS = {
    "pool_size": 1,
    "max_overflow": 0,
    "pool_pre_ping": True,
    "pool_recycle": 1800,
}

VECTOR_COLLECTION = "doc_assistant_embeddings"  # name for pgvector collection

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE)

EMBED_BACKEND = os.getenv("EMBED_BACKEND", "hf_inference")  # default to remote on Render
EMBED_MODEL_NAME = os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

@lru_cache(maxsize=1)
def get_embedding_model():
    if EMBED_BACKEND == "hf_inference":
        # Remote embeddings (tiny memory). Needs HUGGINGFACEHUB_API_TOKEN in env.
        from langchain_community.embeddings import HuggingFaceInferenceAPIEmbeddings
        return HuggingFaceInferenceAPIEmbeddings(
            api_key=os.getenv("HUGGINGFACEHUB_API_TOKEN"),
            model_name=EMBED_MODEL_NAME,
        )
    else:
        # Local fallback (NOT recommended on Render Free; can OOM)
        from langchain_huggingface import HuggingFaceEmbeddings
        return HuggingFaceEmbeddings(model_name=EMBED_MODEL_NAME)

# Splitter for PDF text
splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)


# === Storage helpers ===
from uuid import uuid4
from werkzeug.utils import secure_filename

def upload_pdf_to_storage(file_storage, owner_id: str, subdir: str | None = None) -> str:
    """
    Upload a PDF to Supabase Storage.
    Returns a storage path like "<owner_id>/<subdir>/<unique>_<name>.pdf" (subdir optional).
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE env vars.")

    # Sanitize and make it unique
    base_name = secure_filename(file_storage.filename) or "document.pdf"
    unique_prefix = uuid4().hex[:8]
    final_name = f"{unique_prefix}_{base_name}"

    dir_path = f"{owner_id}/{subdir}" if subdir else f"{owner_id}"
    path = f"{dir_path}/{final_name}"

    data = file_storage.read()
    # Keep it simple: no boolean file_options (avoids header type issues)
    supabase.storage.from_(PDF_BUCKET).upload(path=path, file=data)

    # Reset stream if needed elsewhere
    try:
        file_storage.stream.seek(0)
    except Exception:
        pass

    return path



def download_pdf_bytes(path: str) -> bytes:
    """Download a PDF from Supabase Storage and return raw bytes."""
    return supabase.storage.from_(PDF_BUCKET).download(path)


# === PDF → Documents ===
def pdf_bytes_to_documents(pdf_bytes: bytes, metadata: dict) -> list[Document]:
    """
    Convert PDF bytes into chunked LangChain Documents with metadata.
    """
    reader = PdfReader(BytesIO(pdf_bytes))
    docs: list[Document] = []

    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            chunks = splitter.split_text(text)
            for chunk in chunks:
                docs.append(
                    Document(
                        page_content=chunk,
                        metadata={**metadata, "page": i},
                    )
                )
    return docs


# === Indexing (pgvector) ===
def upsert_documents(docs: list[Document], namespace: str = "default") -> None:
    """
    Insert/update docs into pgvector collection.
    """
    collection = (
        VECTOR_COLLECTION if namespace == "default" else f"{VECTOR_COLLECTION}_{namespace}"
    )
    PGVector.from_documents(
        documents=docs,
        embedding=get_embedding_model(),
        collection_name=collection,
        connection_string=PG_CONN,
        engine_args=ENGINE_ARGS,
    )


def index_pdf_from_storage_path(path: str, owner_id: str, title: str | None = None, namespace: str = "default") -> int:
    """
    Download a PDF from storage, chunk, embed, upsert into pgvector.
    Returns # of chunks indexed.
    """
    raw = download_pdf_bytes(path)
    meta = {"owner_id": owner_id, "storage_path": path}
    if title:
        meta["title"] = title
    docs = pdf_bytes_to_documents(raw, metadata=meta)
    if not docs:
        return 0
    upsert_documents(docs, namespace=namespace)
    return len(docs)


# === Backward-compatible API ===
def build_vector_index(documents, namespace: str = "default"):
    """
    For compatibility with your previous code:
    - Instead of Chroma, this builds/returns a PGVector store.
    """
    collection = (
        VECTOR_COLLECTION if namespace == "default" else f"{VECTOR_COLLECTION}_{namespace}"
    )
    store = PGVector.from_documents(
        documents=documents,
        embedding=get_embedding_model(),
        collection_name=collection,
        connection_string=PG_CONN,
        engine_args=ENGINE_ARGS,
    )
    return store


# === RAG chain ===
def get_qa_chain(vector_db_or_retriever):
    """
    Accept either a vector store (with .as_retriever) or a retriever directly.
    """
    if hasattr(vector_db_or_retriever, "as_retriever"):
        retriever = vector_db_or_retriever.as_retriever(search_kwargs={"k": 6})
    else:
        retriever = vector_db_or_retriever

    llm = ChatGroq(temperature=0, model_name="llama3-8b-8192")
    qa_chain = RetrievalQA.from_chain_type(llm=llm, retriever=retriever)
    return qa_chain


def ask_question(qa_chain, query: str) -> str:
    return qa_chain.run(query)


def get_retriever(k: int = 6, namespace: str = "default"):
    """
    Build a retriever backed by pgvector (no need to rebuild index each time).
    """
    collection = (
        VECTOR_COLLECTION if namespace == "default" else f"{VECTOR_COLLECTION}_{namespace}"
    )
    store = PGVector(
        embedding_function=get_embedding_model(),
        collection_name=collection,
        connection_string=PG_CONN,
         engine_args=ENGINE_ARGS, 
    )
    return store.as_retriever(search_kwargs={"k": k})


# Reuse your DATABASE_URL
_sql_engine = create_engine(
    PG_CONN,
    future=True,
    pool_size=1,
    max_overflow=0,
    pool_pre_ping=True,
    pool_recycle=1800,
)

def delete_storage_for_session(owner_id: str, session_namespace: str) -> int:
    """
    Delete ALL objects under pdfs/<owner_id>/<session_namespace>/ in Supabase Storage.
    Returns number of objects removed.
    """
    prefix = f"{owner_id}/{session_namespace}"
    # list files directly under the session folder
    items = supabase.storage.from_(PDF_BUCKET).list(path=prefix)
    if not items:
        return 0
    paths = [f"{prefix}/{obj['name']}" for obj in items]  # full paths to files
    if paths:
        supabase.storage.from_(PDF_BUCKET).remove(paths)
    return len(paths)


def delete_embeddings_namespace(session_namespace: str) -> bool:
    """
    Delete the pgvector 'collection' and all embeddings for a given session namespace.
    We named collections as f"{VECTOR_COLLECTION}_{namespace}".
    Returns True if a collection was found and deleted.
    """
    collection = f"{VECTOR_COLLECTION}_{session_namespace}" if session_namespace != "default" else VECTOR_COLLECTION
    with _sql_engine.begin() as conn:
        coll_id = conn.execute(
            text("SELECT id FROM langchain_pg_collection WHERE name = :name"),
            {"name": collection},
        ).scalar()
        if not coll_id:
            return False
        # delete embeddings then the collection row
        conn.execute(text("DELETE FROM langchain_pg_embedding WHERE collection_id = :cid"), {"cid": coll_id})
        conn.execute(text("DELETE FROM langchain_pg_collection WHERE id = :cid"), {"cid": coll_id})
    return True