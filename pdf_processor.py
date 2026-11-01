import re
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

class PDFChunk:
    def __init__(self, text: str, page: int, chunk_id: int, source_doc: str, doc_id: Optional[str] = None, section: Optional[str] = None):
        self.text = text
        self.page = page
        self.chunk_id = chunk_id

        
        self.source_doc = source_doc
        self.doc_id = doc_id or "default_doc"
        self.section = section or f"Page {page}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "page": self.page,
            "chunk_id": self.chunk_id,
            "source_doc": self.source_doc,
            "doc_id": self.doc_id,
            "section": self.section
        }

class AcademicPDFProcessor:
    """
    Academic PDF Processing Engine
    Extracts text, preserves page numbers, identifies headings/topics,
    and breaks content into semantic chunks for RAG.
    """

    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 150):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def extract_text_from_pdf(self, pdf_path: str) -> List[Dict[str, Any]]:
        """
        Extracts text page-by-page.
        Uses PyMuPDF (fitz) if available, with pypdf and pdfminer as fallbacks.
        """
        pages_data = []
        pdf_path = str(pdf_path)

        # Method 1: Try PyMuPDF (pymupdf)
        try:
            import pymupdf as fitz
            doc = fitz.open(pdf_path)
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text("text")
                pages_data.append({
                    "page_number": page_num + 1,
                    "text": self._clean_text(text)
                })
            doc.close()

            if pages_data:
                total_chars = sum(len(p["text"]) for p in pages_data)
                empty_pages = [
                    p["page_number"]
                    for p in pages_data
                    if not p["text"].strip()
                ]
            
                print("\n===== PDF EXTRACTION REPORT =====")
                print("Total pages:", len(pages_data))
                print("Total extracted characters:", total_chars)
                print("Empty pages:", empty_pages)
            
                for p in pages_data:
                    print(
                        f"Page {p['page_number']}: "
                        f"{len(p['text'])} characters"
                    )
            
                print("=================================\n")
            
                return pages_data
        except ImportError:
            pass
        except Exception as e:
            print(f"PyMuPDF failed: {e}")

        # Method 2: Try pypdf
        try:
            import pypdf
            reader = pypdf.PdfReader(pdf_path)
            for idx, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                pages_data.append({
                    "page_number": idx + 1,
                    "text": self._clean_text(text)
                })
            if pages_data:
                return pages_data
        except ImportError:
            pass
        except Exception as e:
            print(f"pypdf failed: {e}")

        # Method 3: Fallback plain text reading if text file uploaded
        if pdf_path.endswith(".txt") or pdf_path.endswith(".md"):
            with open(pdf_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                # Split roughly into pages of ~2500 chars
                parts = [content[i:i+2500] for i in range(0, len(content), 2500)]
                for i, part in enumerate(parts):
                    pages_data.append({
                        "page_number": i + 1,
                        "text": self._clean_text(part)
                    })
                return pages_data

        if not pages_data:
            # If all else fails, return empty list
            return []

        return pages_data

    def _clean_text(self, text: str) -> str:
        """Cleans artifacts, hyphenated line wraps, and irregular spacing."""
        if not text:
            return ""
    
        # Join words split by hyphens at line breaks
        text = re.sub(r'(\w+)-\s*\n\s*(\w+)', r'\1\2', text)
    
        # Normalize non-breaking spaces
        text = text.replace('\xa0', ' ')
    
        # Normalize line endings
        text = text.replace('\r\n', '\n').replace('\r', '\n')
    
        # Remove excessive blank lines
        text = re.sub(r'\n{3,}', '\n\n', text)
    
        # Remove repeated spaces and tabs without removing line breaks
        text = re.sub(r'[ \t]+', ' ', text)
    
        return text.strip()

    def detect_sections(self, text: str) -> List[str]:
        """Detects headings like '1. Introduction', 'Module 3: Pointers', 'Algorithm 4.1'"""
        heading_patterns = [
            r'^(?:Module|Unit|Chapter)\s+\d+[:\s\w]+$',
            r'^\d+\.\d+\s+[A-Z][\w\s]+$',
            r'^[A-Z\s]{4,}$'
        ]
        headings = []
        for line in text.splitlines():
            line_str = line.strip()
            for pattern in heading_patterns:
                if re.match(pattern, line_str, re.MULTILINE) and len(line_str) < 80:
                    headings.append(line_str)
                    break
        return headings

    def create_chunks(
    self,
    pages_data: List[Dict[str, Any]],
    source_doc: str,
    doc_id: Optional[str] = None
) -> List[PDFChunk]:
        """
        Creates topic-aware chunks while preserving page numbers,
        section headings, and overlap.
        """
    
        if not doc_id:
            import hashlib
            doc_id = hashlib.sha256(
                source_doc.encode("utf-8")
            ).hexdigest()[:12]
    
        all_chunks = []
        chunk_counter = 1
        current_section = "General Content"
    
        # Recognize common academic headings
        heading_pattern = re.compile(
        r'^(?:'
        r'(?:UNIT|MODULE|CHAPTER)\s+[\dIVX]+(?:\s*[:\-].*)?'
        r'|(?:\d+(?:\.\d+)*\.?)\s+[A-Z][A-Za-z\s\-()&,]{2,}'
        r'|(?:Brute Force Technique|Selection Sort|Bubble Sort'
        r'|Sequential Search|Brute-Force String Matching'
        r'|Divide-and-Conquer Technique|Master Theorem'
        r'|Mergesort|Mergesort Algorithm|Quicksort'
        r'|Quicksort Algorithm|Binary Search'
        r'|Analysis of .+|QuickSort .+)'
        r')$',
        re.IGNORECASE
    )
    
        def save_chunk(text, page_num, section):
            nonlocal chunk_counter
    
            text = text.strip()
            if len(text) < 15:
                return
    
            all_chunks.append(
                PDFChunk(
                    text=text,
                    page=page_num,
                    chunk_id=chunk_counter,
                    source_doc=source_doc,
                    doc_id=doc_id,
                    section=section
                )
            )
            chunk_counter += 1
    
        for p_info in pages_data:
            page_num = p_info["page_number"]
            page_text = p_info["text"]
    
            if not page_text or len(page_text.strip()) < 15:
                continue
    
            lines = [
                line.strip()
                for line in page_text.splitlines()
                if line.strip()
            ]
    
            current_buffer = ""
    
            for line in lines:
    
                # Detect a standalone heading
                is_heading = (
                    len(line) < 80
                    and heading_pattern.match(line) is not None
                )
    
                if is_heading:
                    if current_buffer:
                        save_chunk(
                            current_buffer,
                            page_num,
                            current_section
                        )
                        current_buffer = ""
    
                    current_section = line
                    continue
    
                # Split long lines into sentences
                sentences = re.split(
                    r'(?<=[.!?])\s+',
                    line
                )
    
                for sentence in sentences:
                    sentence = sentence.strip()
    
                    if not sentence:
                        continue
    
                    if len(sentence) > self.chunk_size:
                        # Split exceptionally long sentences safely
                        if current_buffer:
                            save_chunk(
                                current_buffer,
                                page_num,
                                current_section
                            )
                            current_buffer = ""
    
                        for start in range(
                            0,
                            len(sentence),
                            self.chunk_size - self.chunk_overlap
                        ):
                            piece = sentence[
                                start:start + self.chunk_size
                            ]
    
                            save_chunk(
                                piece,
                                page_num,
                                current_section
                            )
    
                        continue
    
                    if (
                        len(current_buffer) + len(sentence) + 1
                        <= self.chunk_size
                    ):
                        current_buffer = (
                            f"{current_buffer} {sentence}".strip()
                        )
                    else:
                        previous_buffer = current_buffer
    
                        save_chunk(
                            previous_buffer,
                            page_num,
                            current_section
                        )
    
                        # Carry the ending of the previous chunk forward
                        overlap = previous_buffer[
                            -self.chunk_overlap:
                        ]
    
                        current_buffer = (
                            f"{overlap} {sentence}".strip()
                        )
    
            if current_buffer:
                save_chunk(
                    current_buffer,
                    page_num,
                    current_section
                )
    
        print("\n===== CHUNK CREATION REPORT =====")
        print("Total chunks created:", len(all_chunks))
    
        for chunk in all_chunks:
            print(
                f"\nChunk {chunk.chunk_id} | "
                f"Page {chunk.page} | "
                f"Section: {chunk.section} | "
                f"Characters: {len(chunk.text)}"
            )
            print(chunk.text[:500])
    
        print("=================================\n")
    
        return all_chunks

    def process_file(self, file_path: str, source_doc: Optional[str] = None, doc_id: Optional[str] = None) -> Dict[str, Any]:
        """Complete ingestion pipeline for a single file."""
        if not source_doc:
            source_doc = Path(file_path).name

        if not doc_id:
            import hashlib
            file_sig = f"{source_doc}"
            try:
                p = Path(file_path)
                file_sig = f"{source_doc}_{p.stat().st_size}_{p.stat().st_mtime}"
            except Exception:
                pass
            doc_id = hashlib.sha256(file_sig.encode("utf-8")).hexdigest()[:12]

        pages = self.extract_text_from_pdf(file_path)
        chunks = self.create_chunks(pages, source_doc, doc_id)

        return {
            "doc_id": doc_id,
            "source_doc": source_doc,
            "file_path": str(file_path),
            "total_pages": len(pages),
            "total_chunks": len(chunks),
            "pages": pages,
            "chunks": [c.to_dict() for c in chunks]
        }
