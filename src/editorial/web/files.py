from pathlib import Path
import os
import tempfile

from editorial.config import load_publication_config
from editorial.storage import SQLiteArticleRepository


FILE_TYPES = {
    "config_path": ("Configuration", {".yaml", ".yml"}),
    "db_path": ("Database", {".sqlite"}),
}


def file_browser(field: str, directory: str) -> dict:
    if field not in FILE_TYPES:
        raise ValueError("Unknown file type")
    path = Path(directory).expanduser().resolve(strict=True)
    if not path.is_dir():
        raise ValueError("Choose a directory")
    label, extensions = FILE_TYPES[field]
    folders = []
    files = []
    for entry in sorted(
        path.iterdir(), key=lambda item: (item.name.casefold(), item.name)
    ):
        if entry.is_dir():
            folders.append(entry)
        elif entry.is_file() and entry.suffix.lower() in extensions:
            files.append(entry)
    return {
        "field": field,
        "label": label,
        "directory": path,
        "parent": path.parent if path.parent != path else None,
        "folders": folders,
        "files": files,
        "home": Path.home(),
        "working_directory": Path.cwd(),
        "extensions": ", ".join(sorted(extensions)),
    }


def selected_file(field: str, value: str) -> Path:
    if field not in FILE_TYPES:
        raise ValueError("Unknown file type")
    path = Path(value).expanduser().resolve(strict=True)
    if not path.is_file() or path.suffix.lower() not in FILE_TYPES[field][1]:
        raise ValueError("Choose a matching file")
    return path


def create_database(config: str, directory: str, filename: str) -> tuple[Path, Path]:
    config_path = selected_file("config_path", config)
    load_publication_config(config_path)
    if not directory:
        raise ValueError("Choose a database folder")
    folder = Path(directory).expanduser().resolve(strict=True)
    if not folder.is_dir():
        raise ValueError("Choose a database folder")
    if (
        not filename
        or filename != Path(filename).name
        or "\\" in filename
        or Path(filename).suffix.lower() != ".sqlite"
    ):
        raise ValueError(
            "Use a filename ending in .sqlite, without directory separators"
        )
    destination = folder / filename
    # Publish a valid empty database atomically; link never replaces an existing file.
    with tempfile.NamedTemporaryFile(
        dir=folder, prefix=".editorial-", suffix=".sqlite"
    ) as temporary:
        SQLiteArticleRepository(temporary.name)
        os.link(temporary.name, destination)
    return config_path, destination
