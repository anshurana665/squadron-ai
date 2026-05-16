import os
import logging
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_core.tools import tool

logger = logging.getLogger("opensquad.rag")

_FAISS_INDEX = None
_WORKSPACE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "workspace")

def build_rag_index(file_pairs: list[tuple[str, str]], workspace_dir: str = _WORKSPACE_DIR):
    """
    Chunks text, creates embeddings, and builds the FAISS index.
    Expects a list of (content, filename).
    Also writes the files to workspace_dir so read_file can find them.
    """
    global _FAISS_INDEX
    
    logger.info(f"Building RAG index for {len(file_pairs)} files...")
    
    # Ensure workspace exists
    os.makedirs(workspace_dir, exist_ok=True)
    
    docs = []
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    
    for content, filename in file_pairs:
        # Write to disk for traditional tools
        full_path = os.path.join(workspace_dir, filename)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        try:
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            logger.warning(f"Could not write {filename} to workspace: {e}")
            
        # Create chunks for RAG
        chunks = splitter.split_text(content)
        for i, chunk in enumerate(chunks):
            docs.append(Document(page_content=chunk, metadata={"source": filename, "chunk": i}))
            
    if not docs:
        logger.warning("No documents to index.")
        return
        
    try:
        embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        _FAISS_INDEX = FAISS.from_documents(docs, embeddings)
        logger.info(f"RAG Index built successfully with {len(docs)} chunks.")
    except Exception as e:
        logger.error(f"Error building RAG index: {e}")

@tool
def semantic_search(query: str) -> str:
    """
    Mathematically searches the vector database for files related to the query.
    Use this to find code dealing with specific concepts (e.g., 'SQL database connections' or 'authentication').
    Returns the exact 3 most relevant code snippets.
    """
    global _FAISS_INDEX
    if _FAISS_INDEX is None:
        return "RAG Index not initialized. Provide file names or use search_codebase."
        
    results = _FAISS_INDEX.similarity_search(query, k=3)
    if not results:
        return "No relevant files found."
        
    formatted = []
    for r in results:
        formatted.append(f"File: {r.metadata['source']}\nSnippet:\n{r.page_content}\n")
        
    return "\n---\n".join(formatted)
