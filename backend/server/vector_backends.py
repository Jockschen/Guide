from __future__ import annotations

import json
import shutil
from typing import Any

import numpy as np

from .config import settings
from .text_utils import hash_embedding


def write_optional_vector_index(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    backend = settings.vector_backend
    if backend == "chroma":
        return _write_chroma(chunks)
    if backend == "faiss":
        return _write_faiss(chunks)
    return {"backend": "sqlite", "status": "ok", "message": "使用 SQLite FTS/向量保障模式"}


def _write_chroma(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        import chromadb
    except Exception as exc:
        return {"backend": "sqlite", "status": "fallback", "message": f"Chroma 未安装: {exc}"}

    path = settings.storage_dir / "chroma"
    path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(path))
    collection = client.get_or_create_collection("lingjing_knowledge")
    try:
        existing = collection.get(include=[])
        existing_ids = existing.get("ids", [])
        if existing_ids:
            collection.delete(ids=existing_ids)
    except Exception:
        pass
    ids = [str(index + 1) for index in range(len(chunks))]
    documents = [f'{chunk["title"]}\n{chunk["content"]}' for chunk in chunks]
    embeddings = [hash_embedding(document) for document in documents]
    metadatas = [
        {
            "title": chunk["title"],
            "source_file": chunk["source_file"],
            "source_type": chunk["source_type"],
            "metadata": json.dumps(chunk["metadata"], ensure_ascii=False),
        }
        for chunk in chunks
    ]
    if ids:
        try:
            collection.upsert(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)
        except Exception:
            try:
                client.delete_collection("lingjing_knowledge")
                collection = client.get_or_create_collection("lingjing_knowledge")
                collection.upsert(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)
            except Exception:
                try:
                    shutil.rmtree(path)
                    path.mkdir(parents=True, exist_ok=True)
                    client = chromadb.PersistentClient(path=str(path))
                    collection = client.get_or_create_collection("lingjing_knowledge")
                    collection.upsert(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)
                except Exception as exc:
                    return {
                        "backend": "sqlite",
                        "status": "fallback",
                        "message": f"Chroma 索引重建失败，已使用 SQLite 保障模式: {exc}",
                    }
    return {"backend": "chroma", "status": "ok", "path": str(path), "items": len(chunks)}


def _write_faiss(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        import faiss
    except Exception as exc:
        return {"backend": "sqlite", "status": "fallback", "message": f"FAISS 未安装: {exc}"}

    index_dir = settings.storage_dir / "faiss"
    index_dir.mkdir(parents=True, exist_ok=True)
    documents = [f'{chunk["title"]}\n{chunk["content"]}' for chunk in chunks]
    vectors = np.array([hash_embedding(document) for document in documents], dtype="float32")
    index = faiss.IndexFlatIP(vectors.shape[1] if len(vectors) else 256)
    if len(vectors):
        index.add(vectors)
    faiss.write_index(index, str(index_dir / "lingjing_knowledge.faiss"))
    metadata = [
        {
            "id": index + 1,
            "title": chunk["title"],
            "source_file": chunk["source_file"],
            "source_type": chunk["source_type"],
            "content": chunk["content"],
            "metadata": chunk["metadata"],
        }
        for index, chunk in enumerate(chunks)
    ]
    (index_dir / "lingjing_knowledge.meta.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    return {"backend": "faiss", "status": "ok", "path": str(index_dir), "items": len(chunks)}
