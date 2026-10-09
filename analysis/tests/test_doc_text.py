import zipfile

import pytest

from pulseframe_analysis import onboarding as O


def test_text_and_markdown_are_read_and_capped(tmp_path):
    f = tmp_path / "moves.md"
    f.write_text("Verse: slow sway.\n\n\n\nChorus: big group turn.  " + "x" * 9000, encoding="utf-8")
    r = O.doc_text(str(f))
    assert r["name"] == "moves.md" and r["text"].startswith("Verse: slow sway.\n\nChorus") and len(r["text"]) == O.MAX_DOC_CHARS and r["truncated"]


def test_a_word_document_gives_its_paragraphs(tmp_path):
    f = tmp_path / "choreo.docx"
    with zipfile.ZipFile(f, "w") as z:
        z.writestr("word/document.xml", '<w:document><w:body><w:p><w:r><w:t>Intro &amp; sway</w:t></w:r></w:p><w:p><w:r><w:t>Chorus: spin</w:t></w:r></w:p></w:body></w:document>')
    r = O.doc_text(str(f))
    assert "Intro & sway" in r["text"] and "Chorus: spin" in r["text"] and "<w:" not in r["text"] and "\n" in r["text"]


def test_a_pdf_is_read_and_a_bad_or_empty_file_is_refused_plainly(tmp_path):
    from pypdf import PdfWriter
    blank = tmp_path / "scan.pdf"
    w = PdfWriter(); w.add_blank_page(100, 100); w.write(str(blank))
    with pytest.raises(SystemExit, match="No text was found"):
        O.doc_text(str(blank))
    broken = tmp_path / "bad.pdf"; broken.write_bytes(b"not a pdf")
    with pytest.raises(SystemExit, match="couldn't be read"):
        O.doc_text(str(broken))
    with pytest.raises(SystemExit, match="Choose a PDF"):
        O.doc_text(str(tmp_path / "x.exe"))
    with pytest.raises(SystemExit, match="Choose a PDF"):
        O.doc_text(str(tmp_path / "missing.txt"))
    big = tmp_path / "big.txt"; big.write_bytes(b"a" * 10)
    O.MAX_DOC_BYTES, old = 5, O.MAX_DOC_BYTES
    try:
        with pytest.raises(SystemExit, match="25 MB"):
            O.doc_text(str(big))
    finally:
        O.MAX_DOC_BYTES = old
