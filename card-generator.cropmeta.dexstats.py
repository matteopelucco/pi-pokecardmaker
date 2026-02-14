#!/usr/bin/env python3
"""
card-generator.py

Genera file JSON a partire da template + config YAML.

NOVITÀ:
- Per ogni config (es: configs/001.yml) cerca un'immagine con lo stesso nome in pictures/ (es: pictures/001.jpg).
- Se non trovata, usa defaults.jpg (o altra estensione supportata) affiancata a defaults.yml.
- In output valorizza il campo "src" delle immagini con una data-URI base64, es:
  src: "data:image/jpeg;base64,/9j/4AAQSkZJ......"

Requisiti:
  pip install pyyaml
"""

import argparse
import base64
import json
import mimetypes
import re
import sys
from pathlib import Path

import yaml


def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def deep_merge(base: dict, override: dict) -> dict:
    """
    Merge ricorsivo: override vince su base.
    """
    result = dict(base) if isinstance(base, dict) else {}
    for k, v in (override or {}).items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def render_template(template_str: str, values: dict) -> str:
    """
    Sostituisce {{ key }} con values[key].
    Supporta anche path con dot notation: {{ a.b.c }}
    """

    def lookup(path: str, ctx: dict):
        cur = ctx
        for part in path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return None
        return cur

    pattern = re.compile(r"{{\s*([a-zA-Z0-9_.-]+)\s*}}")

    def replacer(match):
        key = match.group(1)
        val = lookup(key, values)
        if val is None:
            # Mantieni il placeholder se non c'è valore (utile per debug)
            return match.group(0)
        # Se è dict/list, serializza in JSON "inline" (template JSON)
        if isinstance(val, (dict, list)):
            return json.dumps(val, ensure_ascii=False)
        return str(val)

    return pattern.sub(replacer, template_str)


def _find_image_for_stem(pictures_dir: Path, stem: str) -> Path | None:
    """
    Cerca un'immagine con nome = stem in pictures_dir, provando estensioni comuni.
    """
    exts = [".jpg", ".jpeg", ".png", ".webp"]
    for ext in exts:
        p = pictures_dir / f"{stem}{ext}"
        if p.exists() and p.is_file():
            return p
    # fallback: prova qualunque file con quel nome (case-insensitive per estensione)
    for p in pictures_dir.glob(f"{stem}.*"):
        if p.is_file() and p.suffix.lower() in exts:
            return p
    return None


def _data_uri_from_image(img_path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(img_path))
    if not mime:
        # default ragionevole
        mime = "image/jpeg"
    raw = img_path.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _inject_src_into_images(rendered: dict, data_uri: str) -> None:
    """
    Aggiorna rendered["images"][*]["src"] se presente.
    Non tocca altri campi "src" fuori da "images" per ridurre rischi di side effects.
    """
    images = rendered.get("images")
    if isinstance(images, list):
        for item in images:
            if isinstance(item, dict) and "src" in item:
                item["src"] = data_uri




# ----------------------------
# Crop metadata sidecar support
# ----------------------------

_CROP_KEYS = [
    "croppedArea",          # e.g. {"x":..., "y":..., "width":..., "height":...}
    "croppedAreaPixels",    # optional, depending on your renderer/editor
    "crop",
    "zoom",
    "rotation",
    "aspect",
]

def _iter_image_dicts(obj):
    """Yield dict items that look like image objects inside any 'images' list."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "images" and isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        yield item
            else:
                yield from _iter_image_dicts(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_image_dicts(item)

def _extract_crop_params_from_image(img_dict):
    params = {}
    for k in _CROP_KEYS:
        if k in img_dict:
            params[k] = img_dict[k]
    return params

def _apply_crop_params_to_image(img_dict, params):
    for k, v in params.items():
        img_dict[k] = v

def _sync_crop_sidecar(rendered_json, sidecar_path: Path):
    """
    Keep image-related metadata stable across generations.

    Sidecar file (next to the picture) stores:
    - crop parameters (keys in _CROP_KEYS)
    - dexStats (photo caption / didascalia)

    Rules:
    - If sidecar exists, apply its crop params to all images and (if present) force dexStats from sidecar.
    - If sidecar does not exist, extract crop params from the rendered template and write the sidecar.
    - dexStats is written to the sidecar only the first time (or if missing), so future generations keep it stable
      even if you change the YAML metadata.
    """
    image_dicts = list(_iter_image_dicts(rendered_json))
    if not image_dicts:
        return

    existing: dict = {}
    if sidecar_path.exists():
        try:
            existing = json.loads(sidecar_path.read_text(encoding="utf-8")) or {}
            if not isinstance(existing, dict):
                existing = {}
        except Exception:
            existing = {}

        # Apply stored crop params first
        _apply_crop_params_to_images(rendered_json, existing)

        # Apply stored dexStats (stable caption)
        if isinstance(existing.get("dexStats"), str) and existing["dexStats"].strip():
            rendered_json["dexStats"] = existing["dexStats"]

    # Ensure crop params exist in sidecar (take from the rendered template if missing)
    crop_params = _extract_crop_params_from_images(rendered_json)
    if not crop_params:
        return

    changed = False
    for k in _CROP_KEYS:
        if k not in existing:
            existing[k] = crop_params[k]
            changed = True

    # Ensure dexStats exists in sidecar (only set if missing)
    if "dexStats" not in existing:
        dex = rendered_json.get("dexStats")
        if isinstance(dex, str) and dex.strip():
            existing["dexStats"] = dex
            changed = True

    # If sidecar didn't exist, or we enriched it, write it back
    if (not sidecar_path.exists()) or changed:
        sidecar_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {}


def main():
    parser = argparse.ArgumentParser(description="Generate cards from template and YAML configs.")
    parser.add_argument("--template", required=True, help="Path to JSON template file (with {{placeholders}}).")
    parser.add_argument("--defaults", required=True, help="Path to defaults.yml (base config).")
    parser.add_argument("--configs-dir", required=True, help="Directory containing *.yml configs.")
    parser.add_argument("--out-dir", required=True, help="Output directory for generated JSON files.")
    parser.add_argument(
        "--pictures-dir",
        default=None,
        help=(
            "Directory containing pictures named like the configs (e.g. 001.jpg). "
            "Default: sibling 'pictures' next to configs-dir."
        ),
    )

    args = parser.parse_args()

    template_path = Path(args.template).resolve()
    defaults_path = Path(args.defaults).resolve()
    configs_dir = Path(args.configs_dir).resolve()
    out_dir = Path(args.out_dir).resolve()

    if args.pictures_dir:
        pictures_dir = Path(args.pictures_dir).resolve()
    else:
        # Convention: configs/ and pictures/ are siblings
        pictures_dir = (configs_dir.parent / "pictures").resolve()

    if not template_path.exists():
        print(f"Template not found: {template_path}", file=sys.stderr)
        sys.exit(1)
    if not defaults_path.exists():
        print(f"Defaults not found: {defaults_path}", file=sys.stderr)
        sys.exit(1)
    if not configs_dir.exists():
        print(f"Configs dir not found: {configs_dir}", file=sys.stderr)
        sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)

    template_str = read_file(template_path)
    defaults = load_yaml(defaults_path)

    # Defaults image: cerca defaults.{jpg|jpeg|png|webp} affiancata a defaults.yml
    defaults_img = _find_image_for_stem(defaults_path.parent, defaults_path.stem)

    # itera sui config yaml
    for config_path in sorted(configs_dir.glob("*.yml")):
        cfg = load_yaml(config_path)
        merged = deep_merge(defaults, cfg)

        rendered_str = render_template(template_str, merged)

        # parse JSON
        try:
            rendered = json.loads(rendered_str)
        except json.JSONDecodeError as e:
            print(f"[ERROR] JSON parse failed for {config_path.name}: {e}", file=sys.stderr)
            print("Rendered content (first 500 chars):", file=sys.stderr)
            print(rendered_str[:500], file=sys.stderr)
            sys.exit(2)

        # risolvi immagine per questa config
        img = _find_image_for_stem(pictures_dir, config_path.stem)
        if img is None:
            img = defaults_img

        if img is None:
            print(
                f"[ERROR] No picture found for '{config_path.stem}' in {pictures_dir} "
                f"and no defaults image next to {defaults_path.name}.",
                file=sys.stderr,
            )
            sys.exit(3)

        data_uri = _data_uri_from_image(img)
        _inject_src_into_images(rendered, data_uri)

        # Keep crop params stable via sidecar file (editable once, reused forever)
        sidecar = img.parent / f"{img.stem}.crop.json"
        _sync_crop_sidecar(rendered, sidecar)

        out_path = out_dir / f"{config_path.stem}.json"
        out_path.write_text(json.dumps(rendered, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Generated: {out_path} (image: {img.name})")


if __name__ == "__main__":
    main()
