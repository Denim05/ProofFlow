import hashlib
import os
import time
import uuid
from typing import Optional, Tuple
from fastapi import HTTPException, UploadFile, status
import pymupdf

from app.core.config import settings
from app.core.logging import logger

MAGIC_SIGNATURES = {
    "application/pdf": [b"%PDF"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/jpg": [b"\xff\xd8\xff"],
    "image/webp": [b"RIFF"],
}

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}


class LocalStorageService:
    """Manages secure streaming ingestion, signature verification, and private storage of evidence files."""

    def __init__(self):
        self.storage_root = os.path.abspath(settings.EVIDENCE_STORAGE_DIR)
        self.temp_root = os.path.abspath(settings.TEMP_STORAGE_DIR)
        self._active_temp_paths: set = set()
        os.makedirs(self.storage_root, exist_ok=True)
        os.makedirs(self.temp_root, exist_ok=True)

    def _resolve_safe_path(self, relative_path: str) -> str:
        """Resolves path and guarantees it resides within storage_root to prevent path traversal."""
        from pathlib import Path

        root = Path(self.storage_root).resolve()
        candidate = (root / relative_path).resolve()
        if not candidate.is_relative_to(root):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid storage path: directory traversal prohibited.",
            )
        return str(candidate)

    async def save_upload_stream(
        self,
        upload_file: UploadFile,
        case_id: str,
        evidence_id: str,
    ) -> Tuple[str, str, int, str]:
        """Streams an uploaded file chunk-by-chunk with size limiting, signature checking, and atomic commit.

        Returns:
            Tuple of (storage_relative_path, media_type, file_size_bytes, sha256_hash).
        """
        filename = upload_file.filename or "unknown"
        ext = os.path.splitext(filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Unsupported file extension '{ext}'. Allowed extensions: {sorted(ALLOWED_EXTENSIONS)}",
            )

        # Generate temporary staging path and register active in-flight upload
        temp_filename = f"{uuid.uuid4().hex}.tmp"
        temp_path = os.path.join(self.temp_root, temp_filename)
        abs_temp_path = os.path.abspath(temp_path)
        self._active_temp_paths.add(abs_temp_path)

        hasher = hashlib.sha256()
        bytes_read = 0
        detected_mime = None
        chunk_size = 65536  # 64 KB

        try:
            with open(temp_path, "wb") as f_out:
                chunk = await upload_file.read(chunk_size)
                if not chunk or len(chunk) == 0:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="File is empty (0 bytes).",
                    )

                # Check magic signatures on first chunk
                for mime, signatures in MAGIC_SIGNATURES.items():
                    if any(chunk.startswith(sig) for sig in signatures):
                        detected_mime = "image/jpeg" if mime == "image/jpg" else mime
                        break

                if not detected_mime:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="File header magic bytes do not match any permitted document or image format.",
                    )

                # Verify declared content type aligns with detected magic signature
                declared_type = (upload_file.content_type or "").lower().split(";")[0].strip()
                if declared_type and declared_type not in ("application/octet-stream", ""):
                    # Normalize jpeg/jpg
                    norm_declared = "image/jpeg" if declared_type == "image/jpg" else declared_type
                    if norm_declared != detected_mime:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Declared Content-Type '{declared_type}' does not match verified signature '{detected_mime}'.",
                        )

                # Write chunk 0
                bytes_read += len(chunk)
                if bytes_read > settings.MAX_EVIDENCE_FILE_SIZE_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=f"File exceeds maximum permitted size of {settings.MAX_EVIDENCE_FILE_SIZE_BYTES} bytes.",
                    )
                hasher.update(chunk)
                f_out.write(chunk)

                # Stream remaining chunks
                while True:
                    chunk = await upload_file.read(chunk_size)
                    if not chunk:
                        break
                    bytes_read += len(chunk)
                    if bytes_read > settings.MAX_EVIDENCE_FILE_SIZE_BYTES:
                        raise HTTPException(
                            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                            detail=f"File exceeds maximum permitted size of {settings.MAX_EVIDENCE_FILE_SIZE_BYTES} bytes.",
                        )
                    hasher.update(chunk)
                    f_out.write(chunk)

            # Secondary deep validation for PDF integrity
            if detected_mime == "application/pdf":
                pdf_doc = None
                try:
                    with open(temp_path, "rb") as f_check:
                        pdf_data = f_check.read()
                    pdf_doc = pymupdf.open(stream=pdf_data, filetype="pdf")
                    if pdf_doc.is_encrypted:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="PDF is password-protected or encrypted. Unencrypted document required.",
                        )
                    page_count = len(pdf_doc)
                    if page_count == 0:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="PDF contains 0 pages.",
                        )
                except HTTPException:
                    raise
                except Exception as exc:
                    logger.warning("PDF validation failed for %s: %s", filename, str(exc))
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Corrupted or malformed PDF file.",
                    )
                finally:
                    if pdf_doc is not None:
                        try:
                            pdf_doc.close()
                        except Exception:
                            pass

            # Atomic commit to permanent storage
            sha256 = hasher.hexdigest()
            case_dir = os.path.join(self.storage_root, case_id)
            os.makedirs(case_dir, exist_ok=True)

            final_filename = f"{evidence_id}.bin"
            final_path = os.path.join(case_dir, final_filename)
            os.replace(temp_path, final_path)

            rel_path = f"{case_id}/{final_filename}"
            return rel_path, detected_mime, bytes_read, sha256

        finally:
            self._active_temp_paths.discard(abs_temp_path)
            # Guarantee removal of temporary staging file on failure or success
            if os.path.exists(temp_path):
                import gc

                gc.collect()
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def read_evidence_bytes(self, storage_relative_path: str) -> bytes:
        """Safely reads raw binary content for processing."""
        full_path = self._resolve_safe_path(storage_relative_path)
        if not os.path.exists(full_path):
            raise FileNotFoundError(f"Evidence file not found: {storage_relative_path}")
        with open(full_path, "rb") as f:
            return f.read()

    def remove_evidence_file(self, storage_relative_path: str) -> None:
        """Removes an evidence file on rollback or case purge."""
        full_path = self._resolve_safe_path(storage_relative_path)
        if os.path.exists(full_path):
            try:
                os.remove(full_path)
            except OSError:
                pass

    def cleanup_abandoned_temp_files(
        self,
        max_age_seconds: int = 3600,
        now: Optional[float] = None,
    ) -> int:
        """Safely cleans up abandoned upload temporary files older than max_age_seconds.

        Security guarantees:
        - Only inspects the configured temp_root directory (never storage_root).
        - Strictly filters for files ending with '.tmp' created by the staging pipeline.
        - Preserves fresh/active upload temporary files (newer than cutoff).
        - Preserves non-.tmp files and all permanent evidence files.
        - Handles missing directories and filesystem errors gracefully without crashing.
        - Path traversal safe: verifies each file resides directly inside temp_root.

        Returns:
            int: Number of stale temporary files successfully deleted.
        """
        if not os.path.exists(self.temp_root):
            return 0

        current_time = now if now is not None else time.time()
        cutoff_time = current_time - max(0, max_age_seconds)
        deleted_count = 0

        try:
            from pathlib import Path
            temp_root_path = Path(self.temp_root).resolve()

            with os.scandir(self.temp_root) as entries:
                for entry in entries:
                    try:
                        # Only target regular files ending in .tmp
                        if not entry.is_file(follow_symlinks=False):
                            continue
                        if not entry.name.endswith(".tmp"):
                            continue

                        # Verify path containment within temp_root
                        resolved_entry = Path(entry.path).resolve()
                        if not resolved_entry.is_relative_to(temp_root_path):
                            continue

                        # Never delete active in-flight uploads even if modification time is old
                        if str(resolved_entry) in self._active_temp_paths:
                            logger.debug("Skipping active in-flight temporary upload: %s", entry.name)
                            continue

                        stat_info = entry.stat(follow_symlinks=False)
                        # Check modification time against cutoff
                        if stat_info.st_mtime <= cutoff_time:
                            try:
                                os.remove(entry.path)
                                deleted_count += 1
                                logger.debug("Deleted stale temp file: %s", entry.name)
                            except FileNotFoundError:
                                pass
                            except OSError as err:
                                logger.warning("Could not remove stale temp file %s: %s", entry.name, err)
                    except (FileNotFoundError, PermissionError):
                        continue
                    except Exception as err:
                        logger.warning("Error inspecting temp entry %s: %s", entry.name, err)
                        continue
        except Exception as exc:
            logger.warning("Error scanning temp directory for cleanup: %s", exc)

        return deleted_count


storage_service = LocalStorageService()
