"""Checked legacy-tool execution for the extension-family adapters only."""
import os
import subprocess


def shell_command(command, strict=False):
    if strict:
        # A successful samtools/redirect must not hide failed minimap2 upstream.
        return subprocess.run(["bash", "-o", "pipefail", "-c", command], check=True).returncode
    return os.system(command)


def rg_extract_script(destination):
    """rg status 1 means no matches, status >=2 is a real failure."""
    return (
        f'rg -f "$KMER_FILE" -F -B 1 -N -I "$PART_FILE" > "{destination}.raw" '
        '|| { code=$?; [ "$code" -eq 1 ] || exit "$code"; }\n'
        f'awk \'$0 != "--"\' "{destination}.raw" > "{destination}"\n'
        f'rm -f "{destination}.raw"\n'
    )


# Repeated families share large read inputs. Hash unchanged content once per
# process, fenced by inode/size/mtime/ctime and bounded to avoid retaining paths.
def content_hash(path):
    from pathlib import Path
    path = Path(path).resolve()
    before = path.stat()
    stamp = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
    import time
    # Coarse filesystem timestamps can stay identical during a same-size rewrite.
    # Do not memoize small/recent files; immutable large read inputs still share
    # their content hash once their timestamp has settled.
    if before.st_size <= 1024 * 1024 or max(before.st_mtime, before.st_ctime) >= time.time() - 2.0:
        digest = _read_hash(str(path))
    else:
        digest = _hash_at_stamp(str(path), stamp)
    after = path.stat()
    if stamp != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise ValueError(f"Input changed while hashing: {path}")
    return digest


from functools import lru_cache


@lru_cache(maxsize=256)
def _hash_at_stamp(path, stamp):
    return _read_hash(path)


def _read_hash(path):
    import hashlib
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def mapped_bam(command, bam_path, inputs):
    """A completed minimap2/samtools pipeline survives later reads-filter faults."""
    import shutil
    from pathlib import Path
    import pysam
    from ExtensionFamilies import atomic_json, fingerprint, read_json
    bam = Path(bam_path)
    bam.parent.mkdir(parents=True, exist_ok=True)
    receipt_path = Path(str(bam) + ".receipt.json")
    tools = {}
    for name in ("minimap2", "samtools"):
        path = shutil.which(name)
        if not path:
            raise FileNotFoundError(f"Required mapping tool is unavailable: {name}")
        tools[name] = (path, content_hash(path))
    identity = fingerprint({"mapping": 1, "command": command, "tools": tools,
                            "inputs": [(str(p), content_hash(p)) for p in inputs]})
    if receipt_path.exists():
        receipt = read_json(receipt_path)
        if (receipt.get("identity") != identity or not bam.is_file() or
                receipt.get("sha256") != content_hash(bam)):
            raise ValueError(f"Completed mapping changed: {bam}")
        return 0
    shell_command(command, strict=True)
    with pysam.AlignmentFile(str(bam), "rb") as alignment:
        alignment.check_truncation()
    atomic_json(receipt_path, {"identity": identity, "sha256": content_hash(bam)})
    return 0
