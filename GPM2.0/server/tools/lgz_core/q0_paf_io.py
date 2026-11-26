"""Q0 PAF read-ahead independent of the frozen outer checkpoint runtime.

Legacy incident workspaces must keep their original orchestration module. The
reader deliberately has the same strict UTF-8/newline and 1 MiB buffering
semantics as the current outer reader, without replacing that protected module.
"""
from contextlib import contextmanager
from io import BufferedReader, TextIOWrapper


class _PafReadAhead(BufferedReader):
    def read1(self, size=-1):
        return self.read(size) if size >= 0 else super().read1(size)


@contextmanager
def open_paf_text(path, *, newline=None):
    with path.open("rb", buffering=0) as raw:
        with TextIOWrapper(_PafReadAhead(raw, buffer_size=1024*1024),
                           encoding="utf-8", newline=newline) as text:
            yield text


def install_legacy_paf_reader():
    """Add only the missing reader API to the genuine legacy outer module.

    Never replace the module, its file identity, checkpoint logic or hashing.
    New runtimes already provide this API and are left entirely unchanged.
    Package initialization repeats this in spawned workers as well as owners.
    """
    try:
        import run_orchestration as contract
    except ModuleNotFoundError:
        from .. import run_orchestration as contract
    if not hasattr(contract, 'open_paf_text'):
        contract.open_paf_text = open_paf_text
