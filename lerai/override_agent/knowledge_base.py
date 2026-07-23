"""Hybrid RAG knowledge base for Leroy markdown documentation."""

from __future__ import annotations

import os
import pathlib

from langchain_chroma import Chroma
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

try:
    from langchain_community.retrievers import EnsembleRetriever
except ImportError:
    from langchain_classic.retrievers import EnsembleRetriever

DOCS_DIR = "docs/leroy_manual/"
INDEX_DIR = "lerai/data/chroma_index/"

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
_DOCS_PATH = (_PROJECT_ROOT / DOCS_DIR).resolve()
_INDEX_PATH = (_PROJECT_ROOT / INDEX_DIR).resolve()


def _load_and_chunk_documents() -> list[Document]:
    """Load markdown docs and split them with structural metadata preserved."""
    headers_to_split_on = [
        ("#", "Header 1"),
        ("##", "Header 2"),
        ("###", "Header 3"),
        ("####", "Header 4"),
    ]
    markdown_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on
    )
    recursive_splitter = RecursiveCharacterTextSplitter(
        chunk_size=2000,
        chunk_overlap=400,
    )

    chunks: list[Document] = []
    for file_path in sorted(_DOCS_PATH.rglob("*.md")):
        text = file_path.read_text(encoding="utf-8")
        markdown_docs = markdown_splitter.split_text(text)
        for document in markdown_docs:
            document.metadata["source"] = str(file_path.relative_to(_PROJECT_ROOT))
        chunks.extend(recursive_splitter.split_documents(markdown_docs))

    return chunks


def _get_ensemble_retriever() -> EnsembleRetriever:
    """Create or load a hybrid retriever backed by Chroma and BM25."""
    os.makedirs(_INDEX_PATH, exist_ok=True)

    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )
    vector_store = Chroma(
        collection_name="leroy_docs",
        embedding_function=embeddings,
        persist_directory=str(_INDEX_PATH),
    )

    if vector_store._collection.count() == 0:
        documents = _load_and_chunk_documents()
        if not documents:
            raise ValueError(f"No markdown documents found in {_DOCS_PATH}")
        vector_store.add_documents(documents)

    db_data = vector_store.get()
    reconstructed_docs = [
        Document(page_content=page_content, metadata=metadata or {})
        for page_content, metadata in zip(
            db_data.get("documents", []),
            db_data.get("metadatas", []),
        )
        if page_content
    ]
    if not reconstructed_docs:
        raise ValueError("No indexed documents available for BM25 initialization")

    bm25_retriever = BM25Retriever.from_documents(reconstructed_docs)
    bm25_retriever.k = 5
    chroma_retriever = vector_store.as_retriever(search_kwargs={"k": 5})

    return EnsembleRetriever(
        retrievers=[bm25_retriever, chroma_retriever],
        weights=[0.5, 0.5],
    )


def search_leroy_knowledge_base(query: str) -> str:
    """Search Leroy documentation and return formatted hybrid retrieval results."""
    try:
        retriever = _get_ensemble_retriever()
        results = retriever.invoke(query)
        if not results:
            return "No relevant documentation chunks were found for your query."

        formatted_chunks: list[str] = []
        for document in results:
            metadata = document.metadata or {}
            header_lines = [
                f"{header_name}: {metadata[header_name]}"
                for header_name in ("Header 1", "Header 2", "Header 3", "Header 4")
                if metadata.get(header_name)
            ]
            if metadata.get("source"):
                header_lines.append(f"Source: {metadata['source']}")

            prefix = "\n".join(header_lines)
            content = document.page_content.strip()
            if not content:
                continue

            formatted_chunks.append(
                f"{prefix}\n\n{content}" if prefix else content
            )

        if not formatted_chunks:
            return "No relevant documentation chunks were found for your query."

        return "\n\n---\n\n".join(formatted_chunks)
    except Exception as exc:
        return (
            "Knowledge base search is currently unavailable. "
            f"Details: {exc}"
        )