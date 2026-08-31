"""Resume text extraction for PDF and Word (.docx) files.

PDF uses pdfplumber; .docx is just a ZIP of XML, so it is parsed with the
standard library (no python-docx/lxml dependency needed).
"""
import io
import re
import zipfile


def extract_pdf(data: bytes) -> str:
    """Extract text from a PDF file."""
    import pdfplumber

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        pages = [(page.extract_text() or "") for page in pdf.pages]
    return "\n".join(pages).strip()


def extract_docx(data: bytes) -> str:
    """Extract text from a .docx file (a ZIP containing word/document.xml)."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read("word/document.xml").decode("utf-8", "ignore")
    except (zipfile.BadZipFile, KeyError) as e:
        # L9: a corrupt file must surface as a friendly 422, not a 500.
        raise ValueError("无效的 .docx 文件（文件损坏或格式错误）") from e
    # paragraph breaks, tabs, then strip all remaining tags
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:tab[^>]*/>", "\t", xml)
    text = re.sub(r"<[^>]+>", "", xml)
    return text.strip()


def extract_text(filename: str, data: bytes) -> str:
    """Dispatch to the right extractor by file extension."""
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        text = extract_pdf(data)
    elif name.endswith(".docx"):
        text = extract_docx(data)
    elif name.endswith(".doc"):
        raise ValueError("暂不支持 .doc 老格式，请在 Word 中另存为 .docx 后再上传")
    else:
        raise ValueError("仅支持 .pdf 或 .docx 格式的简历")

    if not text or len(text.strip()) < 10:
        raise ValueError("未能从简历中提取到文字（可能是扫描件/纯图片 PDF）")
    return text.strip()
