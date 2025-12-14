"""
Multipart form-data parser using stdlib only.
Replaces deprecated cgi.FieldStorage for Python 3.13 compatibility.
"""
from email.parser import BytesParser
from email.policy import default


def parse_multipart_formdata(content_type: str, body: bytes):
    """
    Parse multipart/form-data request body.
    
    Args:
        content_type: The Content-Type header value
        body: Raw request body bytes
        
    Returns:
        Tuple of (fields, files) where:
        - fields: dict of {name: string_value}
        - files: dict of {name: {filename, content_type, data}}
        
    Raises:
        ValueError: If not multipart/form-data
    """
    if not content_type or "multipart/form-data" not in content_type:
        raise ValueError("Not multipart/form-data")

    raw = (f"Content-Type: {content_type}\r\n"
           f"MIME-Version: 1.0\r\n"
           f"\r\n").encode("utf-8") + (body or b"")

    msg = BytesParser(policy=default).parsebytes(raw)

    fields = {}
    files = {}

    for part in msg.iter_parts():
        cd = part.get("Content-Disposition", "")
        if not cd or "form-data" not in cd:
            continue

        name = part.get_param("name", header="Content-Disposition")
        filename = part.get_param("filename", header="Content-Disposition")

        payload = part.get_payload(decode=True) or b""
        ctype = part.get_content_type()

        if filename:
            files[name] = {"filename": filename, "content_type": ctype, "data": payload}
        else:
            fields[name] = payload.decode("utf-8", errors="replace")

    return fields, files
