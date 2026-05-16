from langchain_core.tools import tool
import os

# Adapt workspace path to dynamically locate the local 'workspace' directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKSPACE_DIR = os.path.join(BASE_DIR, "opensquad", "workspace")

@tool
def read_file(filepath: str) -> str:
    """
    Reads the exact content of a specific file in the repository.
    Use this when you need to see the implementation details of a script.
    """
    try:
        # Prevent path traversal attacks
        full_path = os.path.abspath(os.path.join(WORKSPACE_DIR, filepath))
        if not full_path.startswith(WORKSPACE_DIR):
            return "Error: Path traversal detected. Access denied."
            
        with open(full_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"

@tool
def search_codebase(keyword: str) -> str:
    """
    Searches all files in the repository for a specific keyword, function name, or variable.
    Returns a list of files and the line numbers where the keyword was found.
    """
    results = []
    for root, _, files in os.walk(WORKSPACE_DIR):
        for file in files:
            if file.endswith(('.py', '.js', '.html', '.css', '.cpp')):
                path = os.path.join(root, file)
                try:
                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        for i, line in enumerate(f):
                            if keyword in line:
                                rel_path = os.path.relpath(path, WORKSPACE_DIR)
                                results.append(f"File: {rel_path} | Line {i+1}: {line.strip()}")
                except Exception:
                    pass # Ignore unreadable files
    
    if not results:
        return f"Keyword '{keyword}' not found in the codebase."
    return "\n".join(results[:20]) # Limit to top 20 results to save tokens
