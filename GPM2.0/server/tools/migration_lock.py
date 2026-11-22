"""A physical migration fence that old launchers also respect.

Only resume/rollback can reclaim a fence. The on-disk owner is intentionally
non-local to legacy readers, while the recorded actual host and a POSIX lock
on the owner inode serialize recovery without removing the legacy lock.
"""
from __future__ import annotations

import errno
import json
import os
import re
import shutil
import socket
import stat
import tempfile
import uuid

from run_all_runner import WorkspaceLock
from workspace_layout import LayoutError, MIGRATION
from workspace_migration import plain_path, rename_synced, sync_directories


HOST_PREFIX = "cgat-migration-fence/"
TERMINAL_STATES = {"committed", "rolled_back"}


def fence_id(root, owner):
    """Recognize only this exact protocol on this workspace and actual host."""
    data = owner.get("migration_fence")
    if data is None:
        return None
    if (not isinstance(data, dict) or set(data) != {"id", "host"}
            or not isinstance(data["id"], str) or re.fullmatch(r"[0-9a-f]{32}", data["id"]) is None
            or data["host"] != socket.gethostname()
            or owner.get("workspace") != str(root)
            or owner.get("hostname") != HOST_PREFIX + data["host"]
            or type(owner.get("pid")) is not int or owner["pid"] < 1
            or not isinstance(owner.get("process_start"), str) or not owner["process_start"].isdigit()):
        raise LayoutError("migration fence has a foreign host or invalid ownership")
    return data["id"]


def claim(fd):
    # Import only on this Linux Server path. No weaker fallback is safe if
    # the workspace filesystem does not support exclusive POSIX locking.
    import fcntl
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        if error.errno in {errno.EACCES, errno.EAGAIN}:
            raise LayoutError("migration fence is already held by a live controller") from error
        raise LayoutError("cannot acquire exclusive migration fence: " + str(error)) from error


class MigrationLock(WorkspaceLock):
    def __init__(self, root, run_id, *, recovery=False):
        super().__init__(root, run_id, for_migration=True)
        self.recovery = recovery
        self.bound_id = None
        self.fence_owner = None
        self.fd = None

    @property
    def owner_path(self):
        return self.lock_dir / "owner.json"

    def _same_owner_inode(self, fd):
        if self.lock_dir.is_symlink():
            return False
        try:
            actual = self.owner_path.lstat()
        except FileNotFoundError:
            return False
        opened = os.fstat(fd)
        return stat.S_ISREG(actual.st_mode) and (actual.st_dev, actual.st_ino) == (opened.st_dev, opened.st_ino)

    def holds(self):
        if not self.acquired or self.owner["pid"] != os.getpid() or self.lock_dir.is_symlink():
            return False
        if self.fd is None:
            return self.fence_owner is None and self._existing_owner() == self.owner
        return self._same_owner_inode(self.fd) and self._existing_owner() == self.fence_owner

    def acquire(self):
        if not self.recovery:
            return super().acquire()
        if self.lock_dir.is_symlink():
            raise LayoutError("migration fence must not be a symlink")
        observed = self._existing_owner()
        identity = fence_id(self.server_dir, observed)
        if identity is None:
            return super().acquire()  # unfinished transaction from before fences
        fd = os.open(self.owner_path, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise LayoutError("migration fence owner must be a regular file")
            claim(fd)
            if not self._same_owner_inode(fd) or observed != self._existing_owner():
                raise LayoutError("migration fence changed while claiming recovery")
            self.fd, self.bound_id, self.fence_owner = fd, identity, observed
            self.acquired = True
        except BaseException:
            os.close(fd)
            raise

    def arm(self, identity):
        if not self.holds():
            raise LayoutError("cannot arm migration fence without the held legacy lock")
        if self.bound_id is not None:
            if identity != self.bound_id:
                raise LayoutError("migration fence belongs to a different transaction")
            return
        host = self.owner["hostname"]
        record = {**self.owner, "hostname": HOST_PREFIX + host,
                  "migration_fence": {"id": identity, "host": host}}
        if fence_id(self.server_dir, record) != identity:
            raise LayoutError("invalid migration fence identity")
        fd, name = tempfile.mkstemp(dir=self.lock_dir, prefix=".migration-owner-")
        try:
            claim(fd)
            with os.fdopen(os.dup(fd), "w", encoding="utf-8") as stream:
                json.dump(record, stream, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            if not self.holds():
                raise LayoutError("legacy lock changed while preparing migration fence")
            os.replace(name, self.owner_path)
            self.fd, self.bound_id, self.fence_owner = fd, identity, record
            sync_directories(self.lock_dir, self.state_dir)
        finally:
            if self.fd != fd:
                os.close(fd)
                if os.path.exists(name):
                    os.unlink(name)

    def release(self):
        if self.fd is None:
            return super().release()
        try:
            # The public journal is written last. A private terminal receipt
            # alone cannot authorize unlocking an unfinished public journal.
            if self.holds():
                marker = plain_path(self.server_dir, MIGRATION)
                if not marker.is_symlink() and marker.is_file():
                    journal = json.loads(marker.read_text())
                    if (journal.get("schema") == "cgat.workspace-migration"
                            and journal.get("id") == self.bound_id and journal.get("workspace") == str(self.server_dir)
                            and journal.get("state") in TERMINAL_STATES):
                        retired = self.state_dir / f".released-lock.{uuid.uuid4().hex}"
                        rename_synced(self.lock_dir, retired)
                        shutil.rmtree(retired)
        finally:
            os.close(self.fd)
            self.fd = None
            self.acquired = False
