"""Project typed read identities without publishing server input paths."""


def private_reads(record, groups=None):
    paths = {v for values in (groups or {}).values() for v in values if isinstance(v, str) and v}
    for source in record.get("sources", []):
        if source.get("option") in ("--hifi", "--ont", "--reads") and source.get("original_path"):
            paths.add(source["original_path"])
    reading = False
    for arg in record.get("argv", []):
        if arg.startswith("-"):
            reading = arg in ("--hifi", "--ont", "--reads")
        elif reading and arg:
            paths.add(arg)
    return sorted(paths, key=len, reverse=True)


def hide_paths(value, paths):
    if not paths:
        return value
    if isinstance(value, dict):
        return {hide_paths(k, paths): hide_paths(v, paths) for k, v in value.items()}
    if isinstance(value, list):
        return [hide_paths(v, paths) for v in value]
    if isinstance(value, str):
        for path in paths:
            if value == path:
                return "[private reads]"
            if len(path) > 1 and path in value:
                value = value.replace(path, "[private reads]")
    return value


def public_inputs(data, paths):
    safe = hide_paths(data, paths)
    return {
        **safe,
        "sources": [
            {k: r[k] for k in ("option", "name", "sha256") if k in r}
            if r.get("option") in ("--hifi", "--ont", "--reads")
            else r
            for r in safe.get("sources", [])
        ],
    }


def recipe_paths(recipe):
    paths = {
        r["path"]
        for r in recipe.get("reads", [])
        if isinstance(r, dict) and isinstance(r.get("path"), str) and r["path"]
    }
    selection = recipe.get("original_selection") or {}
    for key in ("selected", "ignored"):
        paths.update(v for group in (selection.get(key) or {}).values() for v in group if isinstance(v, str) and v)
    return sorted(paths, key=len, reverse=True)
