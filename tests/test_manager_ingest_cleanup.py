from agents.manager import _cleanup_download_tmp


def test_cleanup_download_tmp_removes_pdf_and_markdown(tmp_path):
    tmp_dir = tmp_path / "_tmp"
    tmp_dir.mkdir()
    md_path = tmp_dir / "source.md"
    pdf_path = tmp_dir / "source.pdf"
    md_path.write_text("extracted text", encoding="utf-8")
    pdf_path.write_bytes(b"%PDF")

    _cleanup_download_tmp(str(md_path))

    assert not md_path.exists()
    assert not pdf_path.exists()
    assert not tmp_dir.exists()


def test_cleanup_download_tmp_keeps_nonempty_directory(tmp_path):
    tmp_dir = tmp_path / "_tmp"
    tmp_dir.mkdir()
    md_path = tmp_dir / "source.md"
    pdf_path = tmp_dir / "source.pdf"
    other_path = tmp_dir / "other.md"
    md_path.write_text("extracted text", encoding="utf-8")
    pdf_path.write_bytes(b"%PDF")
    other_path.write_text("other", encoding="utf-8")

    _cleanup_download_tmp(str(md_path))

    assert not md_path.exists()
    assert not pdf_path.exists()
    assert other_path.exists()
    assert tmp_dir.exists()
