from app.services.text_extraction import extract_pages, extract_pdf_pages, extract_txt_pages


def test_extract_txt_pages_returns_single_untagged_page():
    pages = extract_txt_pages(b"Hello world.\n\nThis is plain text.")
    assert len(pages) == 1
    page_number, text = pages[0]
    assert page_number is None
    assert "Hello world" in text


def test_extract_txt_pages_empty_input():
    assert extract_txt_pages(b"") == []


def test_extract_pdf_pages_returns_one_entry_per_page(sample_pdf_bytes):
    pages = extract_pdf_pages(sample_pdf_bytes)
    assert len(pages) == 2
    assert pages[0][0] == 1
    assert pages[1][0] == 2
    assert "normalization" in pages[0][1].lower()
    assert "binary search tree" in pages[1][1].lower()


def test_extract_pages_dispatches_on_file_extension(sample_pdf_bytes):
    pdf_pages = extract_pages("notes.pdf", sample_pdf_bytes)
    assert pdf_pages[0][0] == 1

    txt_pages = extract_pages("notes.txt", b"plain text content")
    assert txt_pages[0][0] is None
