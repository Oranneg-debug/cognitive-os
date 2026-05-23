import base64
import io
from PyPDF2 import PdfReader

def extract_text_from_pdf(pdf_base64: str) -> str:
    """Extracts text from a Base64 encoded PDF.

    Args:
        pdf_base64: The Base64 encoded string of the PDF file.

    Returns:
        The extracted text from the PDF.

    Raises:
        ValueError: If the input is not a valid Base64 string or a corrupted PDF.
    """
    try:
        pdf_bytes = base64.b64decode(pdf_base64)
        pdf_file = io.BytesIO(pdf_bytes)
        reader = PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text
    except Exception as e:
        raise ValueError(f"Failed to extract text from PDF: {e}")
