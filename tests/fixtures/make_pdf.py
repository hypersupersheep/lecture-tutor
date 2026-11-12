"""Write a minimal multi-page text PDF from raw PDF syntax. Test fixture; no dependencies."""
from pathlib import Path

FONT_SIZE = 18
LEADING = 28
TOP = 320
MAX_LINES = 11


def _escape(line: str) -> str:
    return line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(folder: Path, pages: list[str], name: str = "slides.pdf") -> Path:
    """One PDF page per string; "\\n" starts a new text line. ASCII only. Returns the path."""
    folder.mkdir(parents=True, exist_ok=True)
    count = len(pages)
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(count))
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {count} >>".encode("ascii"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for i, text in enumerate(pages):
        lines = text.split("\n")
        if len(lines) > MAX_LINES:
            raise ValueError(f"page {i + 1}: more than {MAX_LINES} lines")
        ops = ["BT", f"/F1 {FONT_SIZE} Tf"]
        for k, line in enumerate(lines):
            ops.append(f"1 0 0 1 40 {TOP - LEADING * k} Tm")
            ops.append(f"({_escape(line)}) Tj")
        ops.append("ET")
        stream = "\n".join(ops).encode("ascii")
        objects.append(
            (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 640 360] "
                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5 + 2 * i} 0 R >>"
            ).encode("ascii")
        )
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode("ascii") + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("ascii")
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode("ascii")
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n"
    ).encode("ascii")
    path = folder / name
    path.write_bytes(bytes(out))
    return path
