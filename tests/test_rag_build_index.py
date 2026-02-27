import json
from pathlib import Path

from rag import build_index


class _FakeSparseIndex:
    def __init__(self, documents):
        self.documents = documents

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "documents.jsonl").write_text("saved\n")

    @classmethod
    def from_documents(cls, documents):
        return cls(documents)


class _FakeVectorStore:
    def __init__(self, persist_dir: Path, collection_name: str) -> None:
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        self._count = 0

    def reset_collection(self) -> None:
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        (self.persist_dir / "fake.marker").write_text("reset")

    def upsert_documents(self, documents, backend, batch_size: int, progress_callback=None) -> None:
        _ = backend
        _ = batch_size
        self._count = len(documents)
        if progress_callback:
            progress_callback(1, 1, 1, len(documents), len(documents))

    def count(self) -> int:
        return self._count


class _FakeEmbeddingBackend:
    def encode(self, texts):
        return [[0.1, 0.2] for _ in texts]


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload))


def test_build_indices_writes_artifacts_and_supports_rebuild(monkeypatch, tmp_path: Path) -> None:
    cab_path = tmp_path / "cab.json"
    bulletin_path = tmp_path / "bulletin.json"
    persist_dir = tmp_path / "persist"

    _write_json(
        cab_path,
        [
            {
                "course_code": "CSCI 0111",
                "title": "Computing Foundations",
                "instructor": [],
                "meetings": ["MWF 9:00"],
                "prerequisites": None,
                "department": "CSCI",
                "description": "Intro",
                "source": "CAB",
                "course_url": "https://example/cab-1",
            }
        ],
    )
    _write_json(
        bulletin_path,
        [
            {
                "course_code": "BIOL 3001",
                "title": "Clerkship in Medicine",
                "description": "Twelve weeks.",
                "source": "bulletin",
            }
        ],
    )

    monkeypatch.setattr(build_index, "SparseKeywordIndex", _FakeSparseIndex)
    monkeypatch.setattr(build_index, "ChromaVectorStore", _FakeVectorStore)
    monkeypatch.setattr(
        build_index,
        "build_embedding_backend",
        lambda model_name=None: _FakeEmbeddingBackend(),
    )

    first = build_index.build_indices(
        cab_path=cab_path,
        bulletin_path=bulletin_path,
        persist_dir=persist_dir,
        rebuild=False,
        embedding_model=None,
        batch_size=32,
        collection_name="courses",
    )
    assert first["status"] == "built"
    assert first["documents"] == 2
    assert (persist_dir / "rag_corpus.jsonl").exists()
    assert (persist_dir / "sparse_index" / "documents.jsonl").exists()

    skipped = build_index.build_indices(
        cab_path=cab_path,
        bulletin_path=bulletin_path,
        persist_dir=persist_dir,
        rebuild=False,
        embedding_model=None,
        batch_size=32,
        collection_name="courses",
    )
    assert skipped["status"] == "skipped"

    rebuilt = build_index.build_indices(
        cab_path=cab_path,
        bulletin_path=bulletin_path,
        persist_dir=persist_dir,
        rebuild=True,
        embedding_model=None,
        batch_size=32,
        collection_name="courses",
    )
    assert rebuilt["status"] == "built"
    assert rebuilt["documents"] == 2
