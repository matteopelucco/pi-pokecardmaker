#!/usr/bin/env python3
"""
neutral_json_generator.py (versione con output basato su 'id')

Cambi principali:
- slug/filename derivati da id (univoco), NON da name
- validazione: ogni config deve avere id
- validazione: id non duplicati tra configs
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

try:
    import yaml  # type: ignore
except Exception:
    yaml = None

JsonObj = Union[Dict[str, Any], List[Any], str, int, float, bool, None]
PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_data(path: Path) -> Any:
    ext = path.suffix.lower()
    if ext == ".json":
        return json.loads(read_text(path))
    if ext in (".yml", ".yaml"):
        if yaml is None:
            raise RuntimeError(
                "Supporto YAML non disponibile. Installa con: pip install pyyaml\n"
                "Oppure usa file .json."
            )
        return yaml.safe_load(read_text(path))
    raise ValueError(f"Formato non supportato: {path.name} (usa .json, .yml, .yaml)")


def dump_json(obj: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def deep_merge(base: Any, override: Any) -> Any:
    if isinstance(base, dict) and isinstance(override, dict):
        out = dict(base)
        for k, v in override.items():
            out[k] = deep_merge(out.get(k), v)
        return out
    if override is None:
        return base
    return override


def get_dotted(data: Dict[str, Any], key: str) -> Any:
    cur: Any = data
    for part in key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise KeyError(key)
        cur = cur[part]
    return cur


def has_dotted(data: Dict[str, Any], key: str) -> bool:
    try:
        _ = get_dotted(data, key)
        return True
    except Exception:
        return False


def find_placeholders(obj: JsonObj) -> List[str]:
    found: List[str] = []
    if isinstance(obj, str):
        found.extend([m.group(1) for m in PLACEHOLDER_RE.finditer(obj)])
    elif isinstance(obj, list):
        for v in obj:
            found.extend(find_placeholders(v))
    elif isinstance(obj, dict):
        for v in obj.values():
            found.extend(find_placeholders(v))
    return found


def render_placeholders(obj: JsonObj, variables: Dict[str, Any], *, strict: bool) -> JsonObj:
    if isinstance(obj, str):
        def repl(m: re.Match) -> str:
            k = m.group(1)
            try:
                v = get_dotted(variables, k) if "." in k else variables[k]
            except Exception:
                if strict:
                    raise KeyError(f"Placeholder mancante: {k}")
                return m.group(0)
            return "" if v is None else str(v)

        return PLACEHOLDER_RE.sub(repl, obj)

    if isinstance(obj, list):
        return [render_placeholders(v, variables, strict=strict) for v in obj]

    if isinstance(obj, dict):
        return {k: render_placeholders(v, variables, strict=strict) for k, v in obj.items()}

    return obj


def list_config_files(configs_dir: Path) -> List[Path]:
    if not configs_dir.exists() or not configs_dir.is_dir():
        raise FileNotFoundError(f"Cartella configs non trovata: {configs_dir}")
    allowed = {".json", ".yml", ".yaml"}
    files = [p for p in configs_dir.iterdir() if p.is_file() and p.suffix.lower() in allowed]
    return sorted(files, key=lambda p: p.name)


@dataclass
class RecordResult:
    source_file: str
    record_id: str
    rendered: Dict[str, Any]


def require_keys(variables: Dict[str, Any], keys: List[str]) -> None:
    missing = [k for k in keys if not has_dotted(variables, k)]
    if missing:
        raise KeyError(f"Chiavi richieste mancanti in variables: {', '.join(missing)}")


def normalize_id(value: Any) -> str:
    """
    Converte l'id in stringa sicura per filename.
    Supporta id numerici o stringhe tipo 'ABC-123'.
    """
    if value is None:
        raise KeyError("id mancante")
    s = str(value).strip()
    if not s:
        raise ValueError("id vuoto")
    # Sostituisce caratteri non sicuri per filename
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", s)
    return s


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Generatore batch JSON neutro (template + configs).")
    ap.add_argument("--template", required=True, help="Template JSON con placeholder {{var}}")
    ap.add_argument("--defaults", required=False, help="Defaults globali (.json/.yml) opzionale")
    ap.add_argument("--configs-dir", required=True, help="Cartella configs/*.json|yml|yaml")
    ap.add_argument("--out", required=True, help="Output file JSON (lista di record)")
    ap.add_argument("--split", action="store_true", help="Crea anche out_dir/<id>.json per record")
    ap.add_argument("--out-dir", default=None, help="Cartella output per --split (default: cartella di --out)")
    ap.add_argument("--strict", action="store_true", help="Errore se placeholder mancanti")
    ap.add_argument("--id-key", default="id", help="Chiave variabili per id univoco (default: id)")
    ap.add_argument("--require-keys", nargs="*", default=[], help="Lista chiavi obbligatorie (supporta dotted keys)")
    args = ap.parse_args(argv)

    template_path = Path(args.template)
    defaults_path = Path(args.defaults) if args.defaults else None
    configs_dir = Path(args.configs_dir)
    out_path = Path(args.out)

    template = load_data(template_path)
    if not isinstance(template, dict):
        raise ValueError("Il template deve essere un oggetto JSON (dict) alla radice.")

    defaults: Dict[str, Any] = {}
    if defaults_path:
        d = load_data(defaults_path)
        if d is None:
            defaults = {}
        elif not isinstance(d, dict):
            raise ValueError("defaults deve essere un oggetto (dict).")
        else:
            defaults = d

    config_files = list_config_files(configs_dir)
    if not config_files:
        raise RuntimeError(f"Nessuna config trovata in {configs_dir}.")

    ph = sorted(set(find_placeholders(template)))
    if ph:
        print(f"[i] Placeholder nel template ({len(ph)}): {', '.join(ph)}")

    # Per garantire unicità id
    seen_ids: set[str] = set()

    results: List[RecordResult] = []
    for cfg_path in config_files:
        cfg = load_data(cfg_path)
        if not isinstance(cfg, dict):
            raise ValueError(f"Config {cfg_path.name} deve essere un oggetto (dict).")

        variables = deep_merge(defaults, cfg)
        if not isinstance(variables, dict):
            raise ValueError(f"Merge non produce dict per {cfg_path.name}.")

        if args.require_keys:
            require_keys(variables, args.require_keys)

        # ID obbligatorio e univoco
        raw_id = variables.get(args.id_key)
        record_id = normalize_id(raw_id)
        if record_id in seen_ids:
            raise ValueError(f"ID duplicato '{record_id}' trovato in {cfg_path.name}")
        seen_ids.add(record_id)

        rendered = render_placeholders(template, variables, strict=args.strict)
        if not isinstance(rendered, dict):
            raise ValueError("Render deve produrre un dict alla radice.")

        results.append(RecordResult(
            source_file=cfg_path.name,
            record_id=record_id,
            rendered=rendered
        ))

    all_rendered = [r.rendered for r in results]
    dump_json(all_rendered, out_path)
    print(f"[ok] Creato: {out_path}  (records: {len(results)})")

    if args.split:
        out_dir = Path(args.out_dir) if args.out_dir else out_path.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        for r in results:
            dump_json(r.rendered, out_dir / f"{r.record_id}.json")
        print(f"[ok] Split: creati {len(results)} file in {out_dir} (filename = id.json)")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"[errore] {e}", file=sys.stderr)
        raise
