#!/usr/bin/env python3
"""Local artifact creation and provider-neutral storage contracts.

Cloud-named adapters in this module are synthetic contract fakes only. They do
not authenticate, perform network I/O, or establish provider verification.
"""
from __future__ import annotations

import csv
import base64
import hashlib
import html
import io
import json
import os
import re
import secrets
import stat
import time
import zipfile
from pathlib import Path, PurePosixPath
from typing import Callable, NamedTuple
from urllib.parse import parse_qs, urlsplit
from defusedxml import ElementTree
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

MIME_TYPES = {
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
}
SYNTHETIC_PROVIDERS = {"google-drive", "onedrive", "dropbox", "box", "s3-compatible"}
RUNTIME_ARTIFACT_DIRS = {"artifact-output", ".artifact-shares"}
SENSITIVE_RE = re.compile(rb"(?i)(password|secret|api[_ -]?key|access[_ -]?token|private key|credential)")
MAX_SHARE_BYTES = 64 * 1024 * 1024


class ArtifactError(RuntimeError):
    pass


class AdapterDisabled(ArtifactError):
    pass


class ChecksumMismatch(ArtifactError):
    pass


class IdempotencyConflict(ArtifactError):
    pass


class ShareDenied(ArtifactError):
    pass


class UnknownEffect(ArtifactError):
    def __init__(self, operation_id: str):
        self.operation_id = operation_id
        super().__init__(f"operation effect is unknown; reconcile {operation_id}")


class UploadRequest(NamedTuple):
    source: Path
    object_name: str
    idempotency_key: str
    permission_scope: str
    retention: str


class ObjectRecord(NamedTuple):
    provider: str
    account_id: str
    target_id: str
    object_id: str
    path: str | None
    sha256: str
    version: str
    permission_scope: str
    retention: str
    revoked: bool
    synthetic: bool
    verified_status: str
    size: int


def _deletion_audit_event(record: ObjectRecord) -> dict[str, str | int]:
    """Return a correlation-safe tombstone without content or raw identities."""
    digest = lambda value: "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()
    return {
        "action": "artifact-deleted",
        "provider": record.provider,
        "object_id_digest": digest(record.object_id),
        "account_id_digest": digest(record.account_id),
        "target_id_digest": digest(record.target_id),
        "version": record.version,
        "recorded_at": int(time.time()),
    }


DELETION_AUDIT_KEYS = {
    "action", "provider", "object_id_digest", "account_id_digest",
    "target_id_digest", "version", "recorded_at",
}


def _validated_deletion_audit_event(value: object, provider: str) -> dict[str, str | int]:
    if not isinstance(value, dict) or set(value) != DELETION_AUDIT_KEYS:
        raise ValueError("deletion audit has unexpected fields")
    if value.get("action") != "artifact-deleted" or value.get("provider") != provider:
        raise ValueError("deletion audit identity mismatch")
    if not isinstance(value.get("version"), str) or not value["version"].strip():
        raise ValueError("deletion audit version is invalid")
    recorded_at = value.get("recorded_at")
    if isinstance(recorded_at, bool) or not isinstance(recorded_at, int) or recorded_at < 0:
        raise ValueError("deletion audit time is invalid")
    for field in ("object_id_digest", "account_id_digest", "target_id_digest"):
        if not isinstance(value.get(field), str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", value[field]):
            raise ValueError("deletion audit digest is invalid")
    return dict(value)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _private_dir(path: Path) -> Path:
    """Create a private directory using descriptor-relative, no-follow traversal."""
    path = Path(path).absolute()
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    directory_fd = os.open(path.anchor, flags)
    try:
        for index, part in enumerate(path.parts[1:]):
            try:
                os.mkdir(part, 0o700, dir_fd=directory_fd)
            except FileExistsError:
                pass
            try:
                child_fd = os.open(part, flags, dir_fd=directory_fd)
            except OSError as error:
                raise ValueError(f"unsafe symlink or non-directory component: {path}") from error
            os.close(directory_fd)
            directory_fd = child_fd
            if index == len(path.parts[1:]) - 1:
                info = os.fstat(directory_fd)
                if info.st_uid != os.getuid() or info.st_nlink < 2:
                    raise ValueError(f"unsafe directory ownership/link count: {path}")
                os.fchmod(directory_fd, 0o700)
    finally:
        os.close(directory_fd)
    return path


def _open_safe_source(path: Path) -> tuple[int, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid():
        os.close(fd)
        raise ValueError("source must be an owned regular file with exactly one link")
    if stat.S_IMODE(info.st_mode) & 0o077:
        os.close(fd)
        raise ValueError("source mode must deny all group and other access")
    return fd, info


def _hash_fd(fd: int) -> str:
    digest = hashlib.sha256()
    os.lseek(fd, 0, os.SEEK_SET)
    while True:
        block = os.read(fd, 1024 * 1024)
        if not block:
            break
        digest.update(block)
    os.lseek(fd, 0, os.SEEK_SET)
    return digest.hexdigest()


def _validate_policy(permission_scope: str, retention: str) -> None:
    if not permission_scope.strip() or not retention.strip():
        raise ValueError("permission and retention policy must be nonempty")


def _signed_bytes(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


class ProtectedPolicyResolver:
    """Verifier-only view of policy records signed by a pinned authority key."""
    def __init__(self, state_path: Path, verification_key: bytes, *, issuer: str):
        self.state_path = Path(state_path).absolute()
        self._verification_key = Ed25519PublicKey.from_public_bytes(bytes(verification_key))
        self._issuer = issuer

    def _read(self) -> dict:
        try:
            fd, _ = _open_safe_source(self.state_path)
            try:
                envelope = json.loads(os.read(fd, os.fstat(fd).st_size).decode())
            finally:
                os.close(fd)
            unsigned = {"issuer": envelope["issuer"], "policies": envelope["policies"]}
            self._verification_key.verify(base64.b64decode(envelope["signature"], validate=True), _signed_bytes(unsigned))
            if envelope["issuer"] != self._issuer:
                raise InvalidSignature
            return envelope["policies"]
        except (OSError, KeyError, ValueError, TypeError, json.JSONDecodeError, InvalidSignature) as error:
            raise ChecksumMismatch("authoritative policy signature mismatch") from error

    def get(self, object_id: str) -> tuple[str, str]:
        value = self._read().get(object_id)
        if not isinstance(value, list) or len(value) != 2:
            raise ChecksumMismatch("authoritative policy is missing")
        return value[0], value[1]


class StoragePolicyAuthority:
    """Privileged issuer; decisions are fetched from an authenticated resolver context."""
    def __init__(self, signing_key: Ed25519PrivateKey, state_path: Path, *, issuer: str,
                 trusted_policy_resolver: Callable[[str], dict]):
        if not isinstance(signing_key, Ed25519PrivateKey) or not issuer or not callable(trusted_policy_resolver):
            raise ValueError("private signing key, issuer, and trusted resolver are required")
        self._key, self._path, self._issuer = signing_key, Path(state_path).absolute(), issuer
        self._resolver = trusted_policy_resolver
        _private_dir(self._path.parent)

    def issue(self, decision_id: str) -> dict:
        decision = dict(self._resolver(decision_id))
        required = {"object_id", "permission_scope", "retention"}
        if set(decision) != required:
            raise ValueError("trusted policy decision has invalid fields")
        _validate_policy(decision["permission_scope"], decision["retention"])
        policies = {}
        if self._path.exists():
            try:
                fd, _ = _open_safe_source(self._path)
                try:
                    envelope = json.loads(os.read(fd, os.fstat(fd).st_size).decode())
                finally:
                    os.close(fd)
                unsigned = {"issuer": envelope["issuer"], "policies": envelope["policies"]}
                self._key.public_key().verify(
                    base64.b64decode(envelope["signature"], validate=True), _signed_bytes(unsigned)
                )
                if envelope["issuer"] != self._issuer:
                    raise InvalidSignature
                policies = envelope["policies"]
            except (OSError, KeyError, ValueError, TypeError, json.JSONDecodeError, InvalidSignature) as error:
                raise ChecksumMismatch("existing authoritative policy signature mismatch") from error
        policies[decision["object_id"]] = [decision["permission_scope"], decision["retention"]]
        unsigned = {"issuer": self._issuer, "policies": policies}
        envelope = dict(unsigned, signature=base64.b64encode(self._key.sign(_signed_bytes(unsigned))).decode())
        temporary = self._path.with_name(f".{self._path.name}.{secrets.token_hex(8)}.tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            os.write(fd, _signed_bytes(envelope)); os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(temporary, self._path)
        return decision


class TLSProbeAuthority:
    """Privileged issuer that signs metadata obtained only from a trusted probe resolver."""
    def __init__(self, signing_key: Ed25519PrivateKey, *, issuer: str,
                 trusted_probe_resolver: Callable[[str], dict]):
        if not isinstance(signing_key, Ed25519PrivateKey) or not issuer or not callable(trusted_probe_resolver):
            raise ValueError("private signing key, issuer, and trusted probe resolver are required")
        self._key, self._issuer, self._resolver = signing_key, issuer, trusted_probe_resolver

    def issue(self, probe_id: str) -> dict:
        metadata = dict(self._resolver(probe_id))
        required = {"url", "host", "audience", "auth_policy", "collected_at", "expires_at",
                    "certificate_identity", "tunnel_identity", "revoked"}
        if set(metadata) != required:
            raise ValueError("trusted probe metadata has invalid fields")
        receipt = {"issuer": self._issuer, **metadata}
        receipt["signature"] = base64.b64encode(self._key.sign(_signed_bytes(receipt))).decode()
        return receipt


class TLSReceiptVerifier:
    """Verifier-only TLS/access receipt consumer with a pinned Ed25519 public key."""
    def __init__(self, verification_key: bytes, *, issuer: str, max_receipt_age: int = 300):
        self._verification_key = Ed25519PublicKey.from_public_bytes(bytes(verification_key))
        self._issuer, self.max_receipt_age = issuer, max_receipt_age

    def verify(self, receipt: object, *, route: str, audience: str, auth_policy: str, expires_in: int) -> dict:
        if not isinstance(receipt, dict):
            raise ShareDenied("trusted TLS/access receipt signature is invalid")
        try:
            unsigned = {key: value for key, value in receipt.items() if key != "signature"}
            self._verification_key.verify(base64.b64decode(receipt["signature"], validate=True), _signed_bytes(unsigned))
        except (KeyError, ValueError, TypeError, InvalidSignature) as error:
            raise ShareDenied("trusted TLS/access receipt signature is invalid") from error
        parsed = urlsplit(route)
        now = time.time()
        if (receipt.get("issuer") != self._issuer or receipt.get("url") != route or
                receipt.get("host") != (parsed.hostname or "").lower().rstrip(".") or
                receipt.get("audience") != audience or receipt.get("auth_policy") != auth_policy or
                receipt.get("revoked") is not False or
                not (receipt.get("certificate_identity") or receipt.get("tunnel_identity"))):
            raise ShareDenied("trusted TLS/access receipt does not match the requested exposure")
        try:
            collected = float(receipt["collected_at"]); expiry = float(receipt["expires_at"])
        except (KeyError, TypeError, ValueError):
            raise ShareDenied("trusted TLS/access receipt timestamps are invalid") from None
        if collected > now + 1 or now - collected > self.max_receipt_age or expiry <= now or expiry + 1 < now + expires_in:
            raise ShareDenied("trusted TLS/access receipt is stale or expires too soon")
        return dict(receipt)


def _safe_relative(name: str) -> Path:
    posix = PurePosixPath(name)
    if not name or posix.is_absolute() or ".." in posix.parts or any(part in ("", ".") for part in posix.parts):
        raise ValueError("object name must be a non-empty safe relative path")
    if "\\" in name:
        raise ValueError("backslashes are not allowed in object names")
    return Path(*posix.parts)


def _xml(value: object) -> str:
    return html.escape(str(value), quote=True)


def _zip_write(path: Path, members: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in members.items():
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, value.encode("utf-8"))


def _csv_bytes(content: dict) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow([content["title"]])
    writer.writerow(content["columns"])
    writer.writerows(content["rows"])
    for paragraph in content.get("paragraphs", []):
        writer.writerow([paragraph])
    return stream.getvalue().encode("utf-8")


def _xlsx(path: Path, content: dict) -> None:
    rows = [[content["title"]], *[[paragraph] for paragraph in content.get("paragraphs", [])], content["columns"], *content["rows"]]
    cells = []
    for row_number, row in enumerate(rows, 1):
        rendered = []
        for column_number, value in enumerate(row, 1):
            column = ""
            number = column_number
            while number:
                number, remainder = divmod(number - 1, 26)
                column = chr(65 + remainder) + column
            reference = f"{column}{row_number}"
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                rendered.append(f'<c r="{reference}"><v>{value}</v></c>')
            else:
                rendered.append(f'<c r="{reference}" t="inlineStr"><is><t>{_xml(value)}</t></is></c>')
        cells.append(f'<row r="{row_number}">{"".join(rendered)}</row>')
    sheet = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' \
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' \
        + "".join(cells) + "</sheetData></worksheet>"
    _zip_write(path, {
        "[Content_Types].xml": '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
        "_rels/.rels": '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Report" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/worksheets/sheet1.xml": sheet,
    })


def _docx(path: Path, content: dict) -> None:
    paragraphs = [content["title"], *content.get("paragraphs", [])]
    rows = [content["columns"], *content["rows"]]
    body = "".join(f'<w:p><w:r><w:t>{_xml(text)}</w:t></w:r></w:p>' for text in paragraphs)
    table = "".join('<w:tr>' + "".join(f'<w:tc><w:p><w:r><w:t>{_xml(cell)}</w:t></w:r></w:p></w:tc>' for cell in row) + '</w:tr>' for row in rows)
    document = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' + body + '<w:tbl>' + table + '</w:tbl><w:sectPr/></w:body></w:document>'
    _zip_write(path, {
        "[Content_Types].xml": '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        "_rels/.rels": '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        "word/document.xml": document,
    })


def _pdf(path: Path, content: dict) -> None:
    lines = [content["title"], *content.get("paragraphs", []), " | ".join(map(str, content["columns"]))]
    lines.extend(" | ".join(map(str, row)) for row in content["rows"])
    characters = list(dict.fromkeys("".join(map(str, lines))))
    cid_by_character = {character: index + 1 for index, character in enumerate(characters)}
    def encoded(text: str) -> str:
        return "".join(f"{cid_by_character[character]:04X}" for character in text)
    commands = ["BT /F1 14 Tf 72 740 Td"]
    for index, line in enumerate(lines):
        if index:
            commands.append("0 -22 Td")
        commands.append(f"<{encoded(str(line))}> Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("ascii")
    mappings = []
    for character, cid in cid_by_character.items():
        mappings.append(f"<{cid:04X}> <{character.encode('utf-16-be').hex().upper()}>")
    cmap = ("/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n"
            "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
            "/CMapName /ArtifactUnicode def\n/CMapType 2 def\n1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n"
            f"{len(mappings)} beginbfchar\n" + "\n".join(mappings) +
            "\nendbfchar\nendcmap\nCMapName currentdict /CMap defineresource pop\nend\nend").encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type0 /BaseFont /ArtifactUnicode /Encoding /Identity-H /DescendantFonts [6 0 R] /ToUnicode 7 0 R >>",
        b"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /ArtifactUnicode /CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> /DW 600 >>",
        b"<< /Length " + str(len(cmap)).encode() + b" >>\nstream\n" + cmap + b"\nendstream",
    ]
    result = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(result))
        result.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(result)
    result.extend(f"xref\n0 {len(objects)+1}\n".encode())
    result.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        result.extend(f"{offset:010d} 00000 n \n".encode())
    result.extend(f"trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    path.write_bytes(result)


def inspect_artifact(path: Path, format_name: str) -> str:
    path = Path(path)
    raw = path.read_bytes()
    if format_name == "csv":
        return raw.decode("utf-8")
    if format_name == "pdf":
        try:
            if not raw.startswith(b"%PDF-") or not raw.rstrip().endswith(b"%%EOF"):
                raise ValueError("invalid PDF boundaries")
            start_match = re.search(rb"startxref\s+(\d+)\s+%%EOF\s*$", raw)
            if not start_match:
                raise ValueError("missing startxref")
            xref_offset = int(start_match.group(1))
            if xref_offset >= len(raw) or not raw[xref_offset:].startswith(b"xref\n"):
                raise ValueError("invalid xref offset")
            xref_match = re.match(rb"xref\n0 (\d+)\n(.*?)trailer\s*<<(.*?)>>", raw[xref_offset:], re.S)
            if not xref_match:
                raise ValueError("malformed xref or trailer")
            object_count = int(xref_match.group(1))
            entries = re.findall(rb"(?m)^(\d{10}) (\d{5}) ([nf]) \s*$", xref_match.group(2))
            if len(entries) != object_count or entries[0][2] != b"f":
                raise ValueError("incomplete xref table")
            objects: dict[int, bytes] = {}
            for object_number, (offset_bytes, generation, in_use) in enumerate(entries[1:], 1):
                if in_use != b"n" or generation != b"00000":
                    continue
                offset = int(offset_bytes)
                marker = f"{object_number} 0 obj\n".encode()
                if not raw[offset:].startswith(marker):
                    raise ValueError("xref entry does not address its object")
                end = raw.find(b"\nendobj", offset + len(marker))
                if end < 0:
                    raise ValueError("unterminated PDF object")
                objects[object_number] = raw[offset + len(marker):end]
            trailer = xref_match.group(3)
            root_match = re.search(rb"/Root\s+(\d+)\s+0\s+R", trailer)
            size_match = re.search(rb"/Size\s+(\d+)", trailer)
            if not root_match or not size_match or int(size_match.group(1)) != object_count:
                raise ValueError("invalid PDF trailer")
            catalog = objects[int(root_match.group(1))]
            for object_body in objects.values():
                for referenced in re.findall(rb"(\d+)\s+0\s+R", object_body):
                    if int(referenced) not in objects:
                        raise ValueError("PDF references a missing object")
            pages_ref = re.search(rb"/Pages\s+(\d+)\s+0\s+R", catalog)
            if b"/Type /Catalog" not in catalog or not pages_ref:
                raise ValueError("invalid PDF catalog")
            pages = objects[int(pages_ref.group(1))]
            if b"/Type /Pages" not in pages:
                raise ValueError("invalid PDF pages object")
            kids_match = re.search(rb"/Kids\s*\[(.*?)\]", pages, re.S)
            if not kids_match:
                raise ValueError("missing PDF page kids")
            kids = [int(item) for item in re.findall(rb"(\d+)\s+0\s+R", kids_match.group(1))]
            count = re.search(rb"/Count\s+(\d+)", pages)
            if not count or int(count.group(1)) != len(kids) or not kids:
                raise ValueError("invalid PDF page tree")
            content_objects = []
            for page_number in kids:
                page = objects[page_number]
                content_ref = re.search(rb"/Contents\s+(\d+)\s+0\s+R", page)
                parent_ref = re.search(rb"/Parent\s+(\d+)\s+0\s+R", page)
                resources = re.search(rb"/Resources\s*<<\s*/Font\s*<<(.*?)>>\s*>>", page, re.S)
                if (not re.search(rb"/Type\s+/Page(?:\s|/)", page) or not content_ref or not parent_ref or
                        int(parent_ref.group(1)) != int(pages_ref.group(1)) or not resources):
                    raise ValueError("invalid PDF page")
                fonts = {name.decode("ascii"): int(reference) for name, reference in
                         re.findall(rb"/(\w+)\s+(\d+)\s+0\s+R", resources.group(1))}
                if not fonts:
                    raise ValueError("PDF page has no font resources")
                for font_number in fonts.values():
                    font = objects[font_number]
                    if not re.search(rb"/Type\s+/Font(?:\s|/)", font):
                        raise ValueError("PDF font resource is not a font")
                    descendant = re.search(rb"/DescendantFonts\s*\[\s*(\d+)\s+0\s+R\s*\]", font)
                    unicode_ref = re.search(rb"/ToUnicode\s+(\d+)\s+0\s+R", font)
                    if descendant and not re.search(rb"/Type\s+/Font(?:\s|/)", objects[int(descendant.group(1))]):
                        raise ValueError("PDF descendant font is not a font")
                    if unicode_ref and b"stream\n" not in objects[int(unicode_ref.group(1))]:
                        raise ValueError("PDF ToUnicode reference is not a stream")
                content = objects[int(content_ref.group(1))]
                stream_match = re.search(rb"/Length\s+(\d+)\s*>>\nstream\n(.*?)\nendstream$", content, re.S)
                if not stream_match or int(stream_match.group(1)) != len(stream_match.group(2)):
                    raise ValueError("invalid PDF content stream")
                stream_bytes = stream_match.group(2)
                if not re.search(rb"\bBT\b.*\bET\b", stream_bytes, re.S) or b"Tj" not in stream_bytes:
                    raise ValueError("PDF content stream has no expected text operations")
                for selected_font in re.findall(rb"/(\w+)\s+[0-9.]+\s+Tf", stream_bytes):
                    if selected_font.decode("ascii") not in fonts:
                        raise ValueError("PDF content selects an undeclared font")
                content_objects.append(stream_match.group(2))
            page_stream = b"\n".join(content_objects)
            if b"/CMapName /ArtifactUnicode" in raw:
                mapping = {int(source, 16): bytes.fromhex(target.decode("ascii")).decode("utf-16-be")
                           for source, target in re.findall(rb"<([0-9A-Fa-f]{4})>\s*<([0-9A-Fa-f]+)>", raw)}
                logical_lines = []
                for encoded in re.findall(rb"<([0-9A-Fa-f]+)>\s*Tj", page_stream):
                    if len(encoded) % 4:
                        raise ValueError("invalid Unicode content code width")
                    logical_lines.append("".join(mapping[int(encoded[index:index + 4], 16)]
                                                 for index in range(0, len(encoded), 4)))
                if not logical_lines:
                    raise ValueError("missing Unicode PDF page text")
                return "\n".join(logical_lines)
            literal_lines = [value.replace(rb"\(", b"(").replace(rb"\)", b")").replace(rb"\\", b"\\").decode("latin-1")
                             for value in re.findall(rb"\((.*?)(?<!\\)\)\s*Tj", page_stream)]
            if not literal_lines or not "".join(literal_lines).strip():
                raise ValueError("PDF has no extractable page text")
            return "\n".join(literal_lines)
        except Exception as error:
            raise ArtifactError("invalid PDF structure or page text") from error
    if format_name not in {"xlsx", "docx"}:
        raise ArtifactError(f"unsupported artifact format: {format_name}")
    if not zipfile.is_zipfile(path):
        raise ArtifactError(f"invalid {format_name} ZIP signature")
    required = "xl/worksheets/sheet1.xml" if format_name == "xlsx" else "word/document.xml"
    package_required = {"[Content_Types].xml", "_rels/.rels", required}
    if format_name == "xlsx":
        package_required |= {"xl/workbook.xml", "xl/_rels/workbook.xml.rels"}
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or not package_required.issubset(names):
                raise ValueError("missing or duplicate package member")
            for member in archive.infolist():
                member_path = PurePosixPath(member.filename)
                if member_path.is_absolute() or ".." in member_path.parts or member.flag_bits & 1:
                    raise ValueError("unsafe or encrypted package member")
                if member.file_size > MAX_SHARE_BYTES:
                    raise ValueError("oversized package member")
            if archive.testzip() is not None:
                raise ValueError("corrupt ZIP member")
            roots = {name: ElementTree.fromstring(archive.read(name)) for name in package_required}
            expected_type = ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
                             if format_name == "xlsx" else
                             "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml")
            types_root = roots["[Content_Types].xml"]
            overrides = {(node.attrib.get("PartName"), node.attrib.get("ContentType"))
                         for node in types_root if node.tag.rsplit("}", 1)[-1] == "Override"}
            main_part = "/xl/workbook.xml" if format_name == "xlsx" else "/word/document.xml"
            if types_root.tag.rsplit("}", 1)[-1] != "Types" or (main_part, expected_type) not in overrides:
                raise ValueError("incorrect package content type")
            relationships = roots["_rels/.rels"]
            office_targets = {(node.attrib.get("Target"), node.attrib.get("Type")) for node in relationships}
            expected_target = "xl/workbook.xml" if format_name == "xlsx" else "word/document.xml"
            expected_relationship = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
            if relationships.tag.rsplit("}", 1)[-1] != "Relationships" or (expected_target, expected_relationship) not in office_targets:
                raise ValueError("invalid office document relationship")
            root = roots[required]
            if format_name == "xlsx":
                spreadsheet_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
                package_rels_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
                workbook = roots["xl/workbook.xml"]
                workbook_rels = roots["xl/_rels/workbook.xml.rels"]
                worksheet_relationship = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"
                if (root.tag != f"{{{spreadsheet_ns}}}worksheet" or
                        workbook.tag != f"{{{spreadsheet_ns}}}workbook" or
                        workbook_rels.tag != f"{{{package_rels_ns}}}Relationships"):
                    raise ValueError("invalid workbook structure or worksheet relationship")
                relationship_by_id = {node.attrib.get("Id"): node for node in workbook_rels
                                      if node.attrib.get("Type") == worksheet_relationship}
                sheets_nodes = [node for node in workbook if node.tag == f"{{{spreadsheet_ns}}}sheets"]
                if len(sheets_nodes) != 1:
                    raise ValueError("workbook must contain exactly one sheets collection")
                sheets = [node for node in sheets_nodes[0] if node.tag == f"{{{spreadsheet_ns}}}sheet"]
                if not sheets:
                    raise ValueError("workbook sheets collection is empty")
                relationship_ids = []
                for sheet_node in sheets:
                    relationship_id = next((value for key, value in sheet_node.attrib.items()
                                            if key.rsplit("}", 1)[-1] == "id"), None)
                    relationship = relationship_by_id.get(relationship_id)
                    if relationship is None:
                        raise ValueError("sheet has no worksheet relationship")
                    target = relationship.attrib.get("Target", "")
                    target_path = (PurePosixPath("xl") / target)
                    if target_path.as_posix() not in names or ".." in target_path.parts:
                        raise ValueError("worksheet relationship target is invalid")
                    sheet_root = ElementTree.fromstring(archive.read(target_path.as_posix()))
                    if sheet_root.tag != f"{{{spreadsheet_ns}}}worksheet":
                        raise ValueError("worksheet relationship target is not a worksheet")
                    relationship_ids.append(relationship_id)
                if len(relationship_ids) != len(set(relationship_ids)):
                    raise ValueError("worksheet relationship is reused")
                values = [node.text or "" for node in root.iter() if node.tag.rsplit("}", 1)[-1] in {"t", "v"}]
            else:
                word_ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
                if root.tag != f"{{{word_ns}}}document":
                    raise ValueError("invalid word document root")
                body_nodes = [node for node in root if node.tag.rsplit("}", 1)[-1] == "body"]
                if len(body_nodes) != 1 or len(root) != 1:
                    raise ValueError("word document must contain exactly one body")
                body = body_nodes[0]
                grammar = {
                    "body": {"p", "tbl", "sectPr"}, "p": {"r"}, "r": {"t"}, "t": set(),
                    "tbl": {"tr"}, "tr": {"tc"}, "tc": {"p"}, "sectPr": set(),
                }
                def validate_word_node(node) -> None:
                    kind = node.tag.rsplit("}", 1)[-1]
                    if kind not in grammar or node.tag != f"{{{word_ns}}}{kind}":
                        raise ValueError("unexpected wordprocessing element")
                    for child in node:
                        child_kind = child.tag.rsplit("}", 1)[-1]
                        if child_kind not in grammar[kind] or child.tag != f"{{{word_ns}}}{child_kind}":
                            raise ValueError("invalid wordprocessing text structure")
                        validate_word_node(child)
                validate_word_node(body)
                values = [node.text or "" for node in body.iter() if node.tag.rsplit("}", 1)[-1] == "t"]
            if not values:
                raise ValueError("package has no document content")
            return " ".join(values)
    except (OSError, UnicodeError, zipfile.BadZipFile, ElementTree.ParseError, ValueError) as error:
        raise ArtifactError(f"invalid {format_name} package structure") from error


def generate_artifacts(content: dict, output_dir: Path) -> list[dict]:
    for key in ("title", "columns", "rows"):
        if key not in content:
            raise ValueError(f"missing structured content field: {key}")
    output_dir = _private_dir(Path(output_dir))
    records = []
    for format_name in ("csv", "xlsx", "docx", "pdf"):
        path = output_dir / f"synthetic-report.{format_name}"
        if path.exists() or path.is_symlink():
            raise FileExistsError(path)
        if format_name == "csv":
            path.write_bytes(_csv_bytes(content))
        elif format_name == "xlsx":
            _xlsx(path, content)
        elif format_name == "docx":
            _docx(path, content)
        else:
            _pdf(path, content)
        os.chmod(path, 0o600)
        reopened = inspect_artifact(path, format_name)
        expected_values = [str(content["title"]), *map(str, content.get("paragraphs", [])),
                           *map(str, content["columns"]),
                           *(str(cell) for row in content["rows"] for cell in row)]
        if any(value not in reopened for value in expected_values):
            raise ArtifactError(f"expected exact content missing after reopening {format_name}")
        records.append({"format": format_name, "path": str(path.absolute()), "mime": MIME_TYPES[format_name], "sha256": _sha256(path), "size": path.stat().st_size, "verified": True, "content": reopened})
    return records


def local_preview(path: Path, mime: str) -> dict:
    source = Path(path).absolute()
    source_fd, source_info = _open_safe_source(source)
    suffix = source.suffix.lower().lstrip(".")
    detected = MIME_TYPES.get(suffix)
    if detected is None:
        os.close(source_fd)
        raise ValueError("unsupported preview artifact extension")
    try:
        inspect_artifact(Path(f"/proc/self/fd/{source_fd}"), suffix)
        source_after = os.fstat(source_fd)
        if (source_info.st_dev, source_info.st_ino, source_info.st_size, source_info.st_mtime_ns) != \
                (source_after.st_dev, source_after.st_ino, source_after.st_size, source_after.st_mtime_ns):
            raise ValueError("preview source changed during validation")
    finally:
        os.close(source_fd)
    if mime != detected:
        raise ValueError("claimed MIME does not match validated artifact bytes and extension")
    return {"surface": "hermes-media", "media": f"MEDIA:{source}", "path": str(source), "mime": detected,
            "size": source_info.st_size, "delivery_status": "prepared-local-not-sent"}


class LocalFilesystemAdapter:
    provider = "local-filesystem"

    def __init__(self, account_id: str, target_id: str, root: Path, *, policy_provider: ProtectedPolicyResolver):
        if not account_id or not target_id:
            raise ValueError("exact account and target identity are required")
        self.account_id, self.target_id = account_id, target_id
        self.root = _private_dir(Path(root))
        self._audit_dir = _private_dir(self.root / ".artifact-audit")
        self._audit_path = self._audit_dir / "deletions.json"
        self.enabled = True
        self._records: dict[str, ObjectRecord] = {}
        self._keys: dict[str, tuple[str, str]] = {}
        self._policies: dict[str, tuple[str, str]] = {}
        self._audit = self._load_audit()
        self._policy_provider = policy_provider

    def _load_audit(self) -> list[dict[str, str | int]]:
        if not self._audit_path.exists():
            return []
        fd, _ = _open_safe_source(self._audit_path)
        try:
            payload = json.loads(os.read(fd, os.fstat(fd).st_size).decode("utf-8"))
        finally:
            os.close(fd)
        if not isinstance(payload, list):
            raise ValueError("deletion audit must be a list")
        return [_validated_deletion_audit_event(event, self.provider) for event in payload]

    def _save_audit(self) -> None:
        temporary = self._audit_path.with_name(f".{self._audit_path.name}.{secrets.token_hex(8)}.tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            os.write(fd, json.dumps(self._audit, sort_keys=True, separators=(",", ":")).encode("utf-8"))
            os.fsync(fd)
            info = os.fstat(fd)
            if info.st_uid != os.getuid() or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600:
                raise ValueError("deletion audit file metadata is unsafe")
        finally:
            os.close(fd)
        os.replace(temporary, self._audit_path)
        directory_fd = os.open(self._audit_dir, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    def _assert_enabled(self) -> None:
        if not self.enabled:
            raise AdapterDisabled("adapter is disabled")

    def operation_key(self, request: UploadRequest, *, digest: str | None = None, size: int | None = None) -> str:
        digest = digest or _sha256(Path(request.source))
        size = Path(request.source).stat().st_size if size is None else size
        fields = (self.provider, self.account_id, self.target_id, request.object_name, digest,
                  str(size), "1", request.permission_scope, request.retention)
        return hashlib.sha256("\0".join(fields).encode()).hexdigest()

    def upload(self, request: UploadRequest, simulate_unknown_effect: bool = False) -> ObjectRecord:
        self._assert_enabled()
        _validate_policy(request.permission_scope, request.retention)
        relative = _safe_relative(request.object_name)
        if relative.parts and relative.parts[0] == ".artifact-audit":
            raise ValueError("object name uses a reserved adapter path")
        source_fd, source_info = _open_safe_source(Path(request.source))
        digest = _hash_fd(source_fd)
        size = source_info.st_size
        fingerprint = self.operation_key(request, digest=digest, size=size)
        existing = self._keys.get(request.idempotency_key)
        if existing:
            os.close(source_fd)
            if existing[0] != fingerprint:
                raise IdempotencyConflict("idempotency key reused with a different upload")
            return self._records[existing[1]]
        destination = self.root / relative
        dir_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        parent_fd = os.open(self.root, dir_flags)
        created = False
        try:
            for part in relative.parts[:-1]:
                try:
                    os.mkdir(part, 0o700, dir_fd=parent_fd)
                except FileExistsError:
                    pass
                try:
                    child_fd = os.open(part, dir_flags, dir_fd=parent_fd)
                except OSError as error:
                    raise ValueError("object path traverses an unsafe component") from error
                child_info = os.fstat(child_fd)
                if child_info.st_uid != os.getuid() or stat.S_IMODE(child_info.st_mode) != 0o700:
                    os.close(child_fd)
                    raise ValueError("object path traverses an unsafe component")
                os.close(parent_fd)
                parent_fd = child_fd
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            try:
                destination_fd = os.open(relative.name, flags, 0o600, dir_fd=parent_fd)
            except FileExistsError:
                raise FileExistsError(destination) from None
            created = True
            try:
                while True:
                    block = os.read(source_fd, 1024 * 1024)
                    if not block:
                        break
                    os.write(destination_fd, block)
                os.fsync(destination_fd)
                written = os.fstat(destination_fd)
                if written.st_nlink != 1 or written.st_uid != os.getuid() or stat.S_IMODE(written.st_mode) != 0o600:
                    raise ValueError("unsafe uploaded object metadata")
            finally:
                os.close(destination_fd)
        except Exception:
            if created:
                destination.unlink(missing_ok=True)
            raise
        finally:
            os.close(parent_fd)
            source_after = os.fstat(source_fd)
            os.close(source_fd)
        original = (source_info.st_dev, source_info.st_ino, source_info.st_size, source_info.st_mtime_ns, source_info.st_nlink)
        after = (source_after.st_dev, source_after.st_ino, source_after.st_size, source_after.st_mtime_ns, source_after.st_nlink)
        if after != original:
            destination.unlink(missing_ok=True)
            raise ValueError("source changed during upload")
        if destination.stat().st_size != size or _sha256(destination) != digest:
            destination.unlink(missing_ok=True)
            raise ChecksumMismatch("uploaded object checksum mismatch")
        object_id = hashlib.sha256((self.target_id + "/" + relative.as_posix()).encode()).hexdigest()[:24]
        record = ObjectRecord(self.provider, self.account_id, self.target_id, object_id, str(destination), digest, "1", request.permission_scope, request.retention, False, False, "Bundled", size)
        self._records[object_id] = record
        self._policies[object_id] = (request.permission_scope, request.retention)
        if self._policy_provider.get(object_id) != (request.permission_scope, request.retention):
            self._records.pop(object_id, None); self._policies.pop(object_id, None)
            destination.unlink(missing_ok=True) if record.path else None
            raise ChecksumMismatch("authoritative policy does not authorize upload")
        self._keys[request.idempotency_key] = (fingerprint, object_id)
        return record

    def readback(self, object_id: str) -> ObjectRecord:
        record = self._records.get(object_id)
        if not record or not record.path:
            raise FileNotFoundError(object_id)
        try:
            info = os.lstat(record.path)
        except FileNotFoundError:
            raise FileNotFoundError(object_id) from None
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise ChecksumMismatch("readback filesystem metadata mismatch")
        if info.st_size != record.size or _sha256(Path(record.path)) != record.sha256:
            raise ChecksumMismatch("readback checksum mismatch")
        if self._policies.get(object_id) != (record.permission_scope, record.retention):
            raise ChecksumMismatch("readback policy mismatch")
        if self._policy_provider.get(object_id) != (record.permission_scope, record.retention):
            raise ChecksumMismatch("authoritative policy readback mismatch")
        return record

    def revoke(self, object_id: str) -> None:
        record = self.readback(object_id)
        self._records[object_id] = record._replace(revoked=True)

    def delete(self, object_id: str) -> None:
        record = self._records.get(object_id)
        if record is None:
            raise FileNotFoundError(object_id)
        self._audit.append(_deletion_audit_event(record))
        try:
            self._save_audit()
        except Exception:
            self._audit.pop()
            raise
        try:
            if record.path:
                Path(record.path).unlink()
        except Exception:
            self._audit.pop()
            self._save_audit()
            raise
        self._records.pop(object_id, None)
        self._policies.pop(object_id, None)
        self._keys = {key: value for key, value in self._keys.items() if value[1] != object_id}
        # policy lifecycle is owned by the separate privileged authority

    def audit_events(self) -> list[dict[str, str | int]]:
        return [dict(event) for event in self._audit]

    def disable(self) -> None:
        self.enabled = False

    def reconcile_unknown(self, operation_id: str) -> ObjectRecord:
        raise UnknownEffect(operation_id)


class SyntheticProviderAdapter:
    """Synthetic cloud contract fake with durable local operation state."""
    def __init__(self, provider: str, account_id: str, target_id: str, *, journal_path: Path,
                 policy_provider: ProtectedPolicyResolver):
        if provider not in SYNTHETIC_PROVIDERS or not account_id or not target_id:
            raise ValueError("supported synthetic provider and exact identities required")
        self.provider, self.account_id, self.target_id = provider, account_id, target_id
        self.enabled = True
        self._records: dict[str, ObjectRecord] = {}
        self._keys: dict[str, tuple[str, str]] = {}
        self._unknown: dict[str, tuple[str, str]] = {}
        self._unresolved_keys: dict[str, str] = {}
        self._policies: dict[str, tuple[str, str]] = {}
        self._audit: list[dict[str, str | int]] = []
        self.journal_path = Path(journal_path).absolute()
        self._policy_provider = policy_provider
        _private_dir(self.journal_path.parent)
        self._load_journal()

    def _load_journal(self) -> None:
        if self.journal_path is None:
            raise RuntimeError("operation journal is not configured")
        if not self.journal_path.exists():
            return
        fd, _ = _open_safe_source(self.journal_path)
        try:
            payload = json.loads(os.read(fd, os.fstat(fd).st_size).decode("utf-8"))
        finally:
            os.close(fd)
        if payload.get("identity") != [self.provider, self.account_id, self.target_id]:
            raise ValueError("operation journal identity mismatch")
        self._records = {key: ObjectRecord(**value) for key, value in payload.get("records", {}).items()}
        self._keys = {key: tuple(value) for key, value in payload.get("keys", {}).items()}
        self._unknown = {key: tuple(value) for key, value in payload.get("unknown", {}).items()}
        self._unresolved_keys = dict(payload.get("unresolved_keys", {}))
        self._policies = {key: tuple(value) for key, value in payload.get("policies", {}).items()}
        self._audit = [_validated_deletion_audit_event(event, self.provider) for event in payload.get("audit", [])]

    def _save_journal(self) -> None:
        if self.journal_path is None:
            return
        payload = {
            "identity": [self.provider, self.account_id, self.target_id],
            "records": {key: value._asdict() for key, value in self._records.items()},
            "keys": self._keys, "unknown": self._unknown,
            "unresolved_keys": self._unresolved_keys, "policies": self._policies,
            "audit": self._audit,
        }
        temporary = self.journal_path.with_name(f".{self.journal_path.name}.{secrets.token_hex(8)}.tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            os.write(fd, data)
            os.fsync(fd)
            if stat.S_IMODE(os.fstat(fd).st_mode) != 0o600:
                raise ValueError("operation journal mode is unsafe")
        finally:
            os.close(fd)
        os.replace(temporary, self.journal_path)
        directory_fd = os.open(self.journal_path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    def operation_key(self, request: UploadRequest, *, digest: str | None = None, size: int | None = None) -> str:
        digest = digest or _sha256(Path(request.source))
        size = Path(request.source).stat().st_size if size is None else size
        fields = (self.provider, self.account_id, self.target_id, request.object_name, digest,
                  str(size), "synthetic-v1", request.permission_scope, request.retention)
        return hashlib.sha256("\0".join(fields).encode()).hexdigest()

    def upload(self, request: UploadRequest, simulate_unknown_effect: bool = False) -> ObjectRecord:
        if not self.enabled:
            raise AdapterDisabled("adapter is disabled")
        _validate_policy(request.permission_scope, request.retention)
        source_fd, source_info = _open_safe_source(Path(request.source))
        try:
            digest = _hash_fd(source_fd)
            source_after = os.fstat(source_fd)
        finally:
            os.close(source_fd)
        before_identity = (source_info.st_dev, source_info.st_ino, source_info.st_size, source_info.st_mtime_ns,
                           source_info.st_nlink, stat.S_IMODE(source_info.st_mode), source_info.st_uid)
        after_identity = (source_after.st_dev, source_after.st_ino, source_after.st_size, source_after.st_mtime_ns,
                          source_after.st_nlink, stat.S_IMODE(source_after.st_mode), source_after.st_uid)
        if before_identity != after_identity:
            raise ValueError("source changed during upload")
        size = source_info.st_size
        fingerprint = self.operation_key(request, digest=digest, size=size)
        unresolved = self._unresolved_keys.get(request.idempotency_key)
        if unresolved:
            operation = self._unknown[unresolved]
            if operation[0] != fingerprint:
                raise IdempotencyConflict("idempotency key reused with a different upload")
            raise UnknownEffect(unresolved)
        if request.idempotency_key in self._keys:
            old, object_id = self._keys[request.idempotency_key]
            if old != fingerprint:
                raise IdempotencyConflict("idempotency key reused with a different upload")
            return self._records[object_id]
        object_id = f"synthetic-{self.provider}-{hashlib.sha256((self.target_id + request.object_name).encode()).hexdigest()[:16]}"
        record = ObjectRecord(self.provider, self.account_id, self.target_id, object_id, None, digest, "synthetic-v1", request.permission_scope, request.retention, False, True, "Optional", size)
        self._records[object_id] = record
        self._policies[object_id] = (request.permission_scope, request.retention)
        if self._policy_provider.get(object_id) != (request.permission_scope, request.retention):
            self._records.pop(object_id, None); self._policies.pop(object_id, None)
            raise ChecksumMismatch("authoritative policy does not authorize upload")
        if simulate_unknown_effect:
            operation_id = secrets.token_hex(12)
            self._unknown[operation_id] = (fingerprint, object_id)
            self._unresolved_keys[request.idempotency_key] = operation_id
            self._save_journal()
            raise UnknownEffect(operation_id)
        self._keys[request.idempotency_key] = (fingerprint, object_id)
        self._save_journal()
        return record

    def readback(self, object_id: str) -> ObjectRecord:
        if object_id not in self._records:
            raise FileNotFoundError(object_id)
        record = self._records[object_id]
        if self._policies.get(object_id) != (record.permission_scope, record.retention):
            raise ChecksumMismatch("readback policy mismatch")
        if self._policy_provider.get(object_id) != (record.permission_scope, record.retention):
            raise ChecksumMismatch("authoritative policy readback mismatch")
        return record

    def reconcile_unknown(self, operation_id: str) -> ObjectRecord:
        if operation_id not in self._unknown:
            raise UnknownEffect(operation_id)
        fingerprint, object_id = self._unknown.pop(operation_id)
        key = next(key for key, value in self._unresolved_keys.items() if value == operation_id)
        del self._unresolved_keys[key]
        self._keys[key] = (fingerprint, object_id)
        self._save_journal()
        return self.readback(object_id)

    def revoke(self, object_id: str) -> None:
        self._records[object_id] = self.readback(object_id)._replace(revoked=True)
        self._save_journal()

    def delete(self, object_id: str) -> None:
        record = self._records.get(object_id)
        if record is None:
            raise FileNotFoundError(object_id)
        prior_keys = dict(self._keys)
        prior_policy = self._policies.get(object_id)
        self._audit.append(_deletion_audit_event(record))
        del self._records[object_id]
        self._policies.pop(object_id, None)
        self._keys = {key: value for key, value in self._keys.items() if value[1] != object_id}
        # policy lifecycle is owned by the separate privileged authority
        try:
            self._save_journal()
        except Exception:
            self._records[object_id] = record
            if prior_policy is not None:
                self._policies[object_id] = prior_policy
            self._keys = prior_keys
            self._audit.pop()
            raise

    def audit_events(self) -> list[dict[str, str | int]]:
        return [dict(event) for event in self._audit]

    def disable(self) -> None:
        self.enabled = False


class TemporarySharePolicy:
    def __init__(self, enabled: bool = False, staging_root: Path | None = None, *, allowed_hosts: set[str] | None = None,
                 max_artifact_bytes: int = MAX_SHARE_BYTES, tls_verifier: TLSReceiptVerifier | None = None):
        self.enabled = enabled
        self.staging_root = Path(staging_root or ".artifact-shares").absolute()
        self.allowed_hosts = {host.lower().rstrip(".") for host in (allowed_hosts or set())}
        self.max_artifact_bytes = max_artifact_bytes
        self._tls_receipt_verifier = tls_verifier
        if enabled:
            try:
                _private_dir(self.staging_root)
            except ValueError as error:
                raise ShareDenied(str(error)) from error
        self._shares: dict[str, dict] = {}

    def _validated_route(self, route: str | None, auth_policy: str, expires_in: int) -> str:
        if not route:
            raise ShareDenied("an explicit temporary share URL is required")
        parsed = urlsplit(route)
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme != "https" or not host or parsed.username or parsed.password or parsed.fragment:
            raise ShareDenied("share URL must be an HTTPS URL without embedded credentials or fragments")
        if host not in self.allowed_hosts:
            raise ShareDenied("share URL host is not allowlisted")
        query = parse_qs(parsed.query)
        path_token = parsed.path.strip("/")
        if auth_policy == "signed-token" and not (path_token or query.get("auth") or query.get("token")):
            raise ShareDenied("signed share URL has no authentication token")
        route_expiry = query.get("expires") or query.get("expires_in")
        if route_expiry:
            try:
                if int(route_expiry[0]) <= 0 or int(route_expiry[0]) > expires_in:
                    raise ValueError
            except (TypeError, ValueError):
                raise ShareDenied("share URL expiry is invalid or exceeds requested expiry") from None
        return route

    def prepare(self, path: Path, *, target: str, auth_policy: str, expires_in: int, route: str | None = None,
                verification_receipt: dict | None = None) -> dict:
        source = Path(path)
        if not self.enabled:
            raise ShareDenied("temporary sharing is disabled by default")
        if not target:
            raise ShareDenied("an explicit target is required")
        if auth_policy not in {"signed-token", "authenticated-user"}:
            raise ShareDenied("an authenticated access policy is required")
        if not isinstance(expires_in, int) or isinstance(expires_in, bool) or expires_in <= 0 or expires_in > 86400:
            raise ShareDenied("expiry must be between 1 and 86400 seconds")
        validated_route = self._validated_route(route, auth_policy, expires_in)
        if self._tls_receipt_verifier is None:
            raise ShareDenied("a trusted TLS/access verifier is required")
        verified = self._tls_receipt_verifier.verify(verification_receipt, route=validated_route, audience=target,
                                            auth_policy=auth_policy, expires_in=expires_in)
        try:
            source_fd, source_info = _open_safe_source(source)
        except (OSError, ValueError) as error:
            raise ShareDenied("share source must be an owned regular file with exactly one link") from error
        if source_info.st_size <= 0 or source_info.st_size > self.max_artifact_bytes:
            os.close(source_fd)
            raise ShareDenied("artifact size is empty or exceeds the sharing scan limit")
        sensitive = SENSITIVE_RE.search(source.name.encode()) is not None
        carry = b""
        scanned_digest = hashlib.sha256()
        try:
            while not sensitive:
                block = os.read(source_fd, 1024 * 1024)
                if not block:
                    break
                scanned_digest.update(block)
                sensitive = SENSITIVE_RE.search(carry + block) is not None
                carry = block[-64:]
            if sensitive:
                raise ShareDenied("sensitive content cannot use temporary sharing")
            os.lseek(source_fd, 0, os.SEEK_SET)
            root = _private_dir(self.staging_root)
            share_id = secrets.token_hex(16)
            share_dir = root / share_id
            os.mkdir(share_dir, 0o700)
            staged = share_dir / source.name
            destination_fd = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            staged_digest = hashlib.sha256()
            try:
                while True:
                    block = os.read(source_fd, 1024 * 1024)
                    if not block:
                        break
                    staged_digest.update(block)
                    os.write(destination_fd, block)
                os.fsync(destination_fd)
                staged_info = os.fstat(destination_fd)
                source_after = os.fstat(source_fd)
            finally:
                os.close(destination_fd)
        finally:
            os.close(source_fd)
        source_identity = (source_info.st_dev, source_info.st_ino, source_info.st_size, source_info.st_mtime_ns,
                           source_info.st_nlink, source_info.st_uid, stat.S_IMODE(source_info.st_mode))
        after_identity = (source_after.st_dev, source_after.st_ino, source_after.st_size, source_after.st_mtime_ns,
                          source_after.st_nlink, source_after.st_uid, stat.S_IMODE(source_after.st_mode))
        if source_identity != after_identity:
            staged.unlink(missing_ok=True)
            raise ShareDenied("share source changed during preparation")
        if (staged_info.st_size != source_info.st_size or scanned_digest.digest() != staged_digest.digest() or
                stat.S_IMODE(staged_info.st_mode) != 0o600 or staged_info.st_nlink != 1):
            staged.unlink(missing_ok=True)
            raise ShareDenied("staged artifact failed size or filesystem verification")
        now = time.time()
        record = {"share_id": share_id, "target": target, "auth_policy": auth_policy, "created_at": now,
                  "expires_at": now + expires_in, "staged_path": str(staged), "size": staged_info.st_size,
                  "route": validated_route, "route_kind": "allowlisted-https", "https_verified": True,
                  "verification_issuer": verified["issuer"], "verification_expires_at": verified["expires_at"],
                  "status": "prepared-not-hosted", "listener_started": False, "revocation_supported": True,
                  "revoked": False, "expired": False}
        self._shares[share_id] = record
        return dict(record)

    def _cleanup(self, record: dict) -> None:
        staged = Path(record["staged_path"])
        staged.unlink(missing_ok=True)
        try:
            staged.parent.rmdir()
        except OSError:
            pass

    def revoke(self, share_id: str) -> None:
        record = self._shares[share_id]
        record["revoked"] = True
        record["status"] = "revoked-and-cleaned"
        self._cleanup(record)

    def status(self, share_id: str) -> dict:
        record = self._shares[share_id]
        if not record["revoked"] and time.time() >= record["expires_at"]:
            record["expired"] = True
            record["status"] = "expired-and-cleaned"
            self._cleanup(record)
        return dict(record)


def archive_privacy_errors(root: Path) -> list[str]:
    root = Path(root)
    return [f"runtime artifact directory must not be archived: {name}" for name in sorted(RUNTIME_ARTIFACT_DIRS) if (root / name).exists()]
