def event_is_path_producing(event):
    return event["action"] in {
        "fill",
        "patch",
        "refill",
        "extend_telomere",
    } or (
        event["action"] == "replace"
        and event.get("edit", {}).get("replacement_kind") == "source"
    )

def reverse_complement(sequence):
    return sequence.translate(
        str.maketrans("ACGTRYSWKMBDHVN", "TGCAYRSWMKVHDBN")
    )[::-1]
