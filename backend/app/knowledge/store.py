import hashlib
from pathlib import Path

from app.schemas.styling import CollectedArticle, KnowledgeRecord, OutfitObservation


def _record_name(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]


class FashionKnowledgeStore:
    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.records_dir = self.data_dir / "records"
        self.raw_dir = self.data_dir / "raw"
        self.images_dir = self.data_dir / "images"

    def ensure_dirs(self) -> None:
        self.records_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)

    def save_collected(self, article: CollectedArticle) -> Path:
        self.ensure_dirs()
        path = self.raw_dir / f"{_record_name(article.source_url)}.json"
        path.write_text(article.model_dump_json(indent=2), encoding="utf-8")
        return path

    def save_record(self, record: KnowledgeRecord) -> Path:
        self.ensure_dirs()
        path = self.records_dir / f"{_record_name(record.article.source_url)}.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(record.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(path)
        return path

    def load_records(self) -> list[KnowledgeRecord]:
        if not self.records_dir.exists():
            return []
        records: list[KnowledgeRecord] = []
        for path in sorted(self.records_dir.glob("*.json")):
            records.append(KnowledgeRecord.model_validate_json(path.read_text(encoding="utf-8")))
        return records

    def observations(self) -> list[OutfitObservation]:
        return [observation for record in self.load_records() for observation in record.extraction.observations]
