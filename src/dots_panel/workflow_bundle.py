"""Portable workflow source/export only. Never installs into an account."""
import hashlib
from pathlib import Path
import zipfile

SKILL_NAME = "manage-development-activities"
FILES = ("SKILL.md", "references/tool-contract.md", "references/task-files.md", "references/closeout.md")


def bundle_files(source):
    root = Path(source) / "skills" / SKILL_NAME
    files = {}
    for relative in FILES:
        path = root / relative
        if any(part.is_symlink() for part in (path, *path.parents)):
            raise ValueError("Workflow bundle must not contain symlinks")
        if not path.is_file():
            raise ValueError("Missing bundled workflow file: " + relative)
        content = path.read_bytes()
        content.decode("utf-8")
        files[relative] = content
    if not files["SKILL.md"].startswith(b"---\nname: manage-development-activities\n"):
        raise ValueError("Invalid workflow Skill frontmatter")
    return files


def bundle_status(source):
    files = bundle_files(source)
    return {
        "skill": SKILL_NAME,
        "bundled_source": "available",
        "account_installation": "not_verified",
        "hourly_monitor": "not_configured_by_installer",
        "files": {name: hashlib.sha256(content).hexdigest() for name, content in files.items()},
    }


def export_bundle(source, destination):
    """Build from the one authoritative copy; exclusive create prevents overwrite."""
    files = bundle_files(source)
    destination = Path(destination)
    if destination.resolve().is_relative_to(Path(source).resolve()):
        raise ValueError("Export outside the source tree to keep one authoritative copy")
    if any(part.is_symlink() for part in (destination, *destination.parents)):
        raise ValueError("Export destination must not contain symlinks")
    with destination.open("xb") as output:
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in files.items():
                archive.writestr(SKILL_NAME + "/" + name, content)
    return destination
