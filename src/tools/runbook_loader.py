import os
from pathlib import Path
from typing import Any

import chromadb
from sentence_transformers import SentenceTransformer

RUNBOOKS_DIR = Path(__file__).parent.parent / "data" / "runbooks"
CHROMA_DIR = Path(__file__).parent.parent.parent / ".chroma"
COLLECTION_NAME = "sre_runbooks"

_model: SentenceTransformer | None = None
_collection: Any = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def _get_collection() -> Any:
    global _collection
    if _collection is not None:
        return _collection

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    existing = [c.name for c in client.list_collections()]

    if COLLECTION_NAME in existing:
        _collection = client.get_collection(COLLECTION_NAME)
        print(f"[runbook_loader] Loaded existing ChromaDB collection '{COLLECTION_NAME}' "
              f"({_collection.count()} documents)")
        return _collection

    print("[runbook_loader] Building ChromaDB collection from runbooks...")
    _collection = client.create_collection(COLLECTION_NAME)
    _build_collection(_collection)
    return _collection


def _build_collection(collection: Any) -> None:
    model = _get_model()
    txt_files = sorted(RUNBOOKS_DIR.glob("*.txt"))

    if not txt_files:
        raise FileNotFoundError(f"No .txt runbooks found in {RUNBOOKS_DIR}")

    ids, documents, embeddings, metadatas = [], [], [], []

    for path in txt_files:
        content = path.read_text(encoding="utf-8").strip()
        title = path.stem.replace("_", " ").title()
        embedding = model.encode(content).tolist()

        doc_id = path.stem
        ids.append(doc_id)
        documents.append(content)
        embeddings.append(embedding)
        metadatas.append({"title": title, "filename": path.name})
        print(f"  Embedded: {title}")

    collection.add(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)
    print(f"[runbook_loader] Stored {len(ids)} runbooks in ChromaDB.")


def search_runbooks(query: str, n_results: int = 3) -> list[dict]:
    """Return the top-n most relevant runbooks for a given query."""
    collection = _get_collection()
    model = _get_model()

    query_embedding = model.encode(query).tolist()
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(n_results, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    output = []
    for doc, meta, distance in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        # ChromaDB returns L2 distance; convert to a 0-1 similarity score
        similarity_score = round(1 / (1 + distance), 4)
        output.append({
            "title": meta["title"],
            "content": doc,
            "similarity_score": similarity_score,
        })

    return output


if __name__ == "__main__":
    query = "database connection timeout"
    print(f"\nSearching runbooks for: '{query}'\n{'=' * 50}")

    results = search_runbooks(query, n_results=3)
    for i, r in enumerate(results, 1):
        print(f"\n[{i}] {r['title']}  (similarity: {r['similarity_score']})")
        print("-" * 40)
        preview = r["content"][:400].replace("\n", " ")
        print(preview + "...")
