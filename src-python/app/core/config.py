"""
Application configuration.

Settings are loaded from environment variables and/or a config file
stored in ~/Library/Application Support/FileSense/config.json.
"""

from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """FileSense configuration."""

    # --- Server ---
    port: int = 9274  # Local-only port for Tauri IPC
    debug: bool = False

    # --- Paths ---
    data_dir: Path = Path.home() / "Library" / "Application Support" / "FileSense"
    watch_directories: list[Path] = [
        Path.home() / "Documents",
        Path.home() / "Desktop",
        Path.home() / "Downloads",
    ]

    # --- Embedding ---
    embedding_provider: str = "local"  # "local" or "openai"
    local_model_name: str = "BAAI/bge-base-en-v1.5"
    openai_api_key: str = ""
    openai_model: str = "text-embedding-3-small"

    # --- Indexing ---
    chunk_size: int = 500         # Target tokens per chunk
    chunk_overlap: int = 50       # Overlap between chunks
    batch_size: int = 64          # Embedding batch size
    debounce_seconds: float = 2.0 # Wait before processing file changes
    max_file_size_mb: int = 50    # Skip files larger than this

    # --- Search ---
    default_top_k: int = 20       # Default number of results
    min_similarity: float = 0.10  # Minimum cosine similarity threshold

    # --- Supported file types ---
    supported_extensions: set[str] = {
        # Documents
        ".pdf", ".docx", ".doc", ".pptx", ".xlsx", ".csv", ".tsv",
        # Text
        ".txt", ".md", ".markdown", ".rst", ".rtf",
        # Code
        ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs",
        ".c", ".cpp", ".h", ".hpp", ".cs", ".rb", ".php", ".swift",
        ".kt", ".scala", ".sh", ".bash", ".zsh", ".fish",
        # Config
        ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
        ".xml", ".html", ".css", ".scss", ".less",
        # Data
        ".sql", ".graphql", ".proto",
        # Notes
        ".org", ".tex", ".bib",
    }

    model_config = {"env_prefix": "FILESENSE_"}

    def ensure_dirs(self) -> None:
        """Create data directories if they don't exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "vectors").mkdir(exist_ok=True)


settings = Settings()
settings.ensure_dirs()
