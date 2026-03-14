from pathlib import Path
from PIL import Image, ImageOps

# ==============================
# CONFIGURAZIONE STAMPA
# ==============================

INPUT_FOLDER = Path("./cards")
OUTPUT_FOLDER = Path("./cards-for-printing")

DPI = 300
TRIM_WIDTH_MM = 67
TRIM_HEIGHT_MM = 92
BLEED_MM = 3

# ==============================
# FUNZIONI UTILI
# ==============================

def mm_to_px(mm, dpi):
    return int(round(mm / 25.4 * dpi))

def find_black_trim_bbox(img, threshold=40):
    gray = img.convert("L")
    mask = gray.point(lambda p: 255 if p < threshold else 0, mode="L")
    return mask.getbbox()

def process_image(img):
    trim_w = mm_to_px(TRIM_WIDTH_MM, DPI)
    trim_h = mm_to_px(TRIM_HEIGHT_MM, DPI)
    bleed_px = mm_to_px(BLEED_MM, DPI)

    out_w = trim_w + 2 * bleed_px
    out_h = trim_h + 2 * bleed_px

    # 1️⃣ Cropping automatico sul riquadro nero
    bbox = find_black_trim_bbox(img)
    if bbox:
        img = img.crop(bbox)

    # 2️⃣ Mantieni proporzioni corrette
    target_ratio = trim_w / trim_h
    current_ratio = img.width / img.height

    if abs(current_ratio - target_ratio) > 0.01:
        if current_ratio > target_ratio:
            new_width = int(img.height * target_ratio)
            left = (img.width - new_width) // 2
            img = img.crop((left, 0, left + new_width, img.height))
        else:
            new_height = int(img.width / target_ratio)
            top = (img.height - new_height) // 2
            img = img.crop((0, top, img.width, top + new_height))

    # 3️⃣ Ridimensiona alla misura finale di taglio
    img = img.resize((trim_w, trim_h), Image.Resampling.LANCZOS)

    # 4️⃣ Crea canvas con bleed
    canvas = Image.new("RGB", (out_w, out_h))
    canvas.paste(img, (bleed_px, bleed_px))

    return canvas

# ==============================
# ESECUZIONE
# ==============================

def main():
    OUTPUT_FOLDER.mkdir(exist_ok=True)

    for file in INPUT_FOLDER.iterdir():
        if file.suffix.lower() in [".png", ".jpg", ".jpeg"]:
            with Image.open(file) as img:
                img = img.convert("RGB")
                fixed = process_image(img)

                output_path = OUTPUT_FOLDER / file.name
                fixed.save(output_path, dpi=(DPI, DPI), quality=95)

                print(f"✔ Salvata: {output_path}")

    print("\nOperazione completata.")

if __name__ == "__main__":
    main()