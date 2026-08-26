import csv
import json
import os

# Paths

RAW_FOLDER = "data_collection/raw_samples"

CSV_FILES = [
    "arabic_fake_news_samples.csv",
    "fake_real_arabic_samples.csv",
    "french_covid_samples.csv",
    "sanad_samples.csv",
    "threat_incitement_synthetic.csv"
]

JSON_FILE = "ANAD_20_SAFE.json"

OUTPUT_FILE = "data_collection/combined_candidates.csv"

# Final standardized structure

FINAL_FIELDS = [
    "id",
    "source",
    "source_type",
    "language",
    "title",
    "text",
    "gold_label",
    "original_label",
    "notes"
]

combined = []
next_id = 1


# Helper: add standardized article

def add_article(
    source,
    source_type="real",
    language="",
    title="",
    text="",
    gold_label="",
    original_label="",
    notes=""
):
    global next_id

    if not text or not str(text).strip():
        return

    combined.append({
        "id": next_id,
        "source": source,
        "source_type": source_type,
        "language": language,
        "title": title or "",
        "text": text.strip(),
        "gold_label": gold_label or "",
        "original_label": original_label or "",
        "notes": notes or ""
    })

    next_id += 1


# Read CSV files

for filename in CSV_FILES:

    path = os.path.join(RAW_FOLDER, filename)

    print(f"Reading {filename}...")

    with open(path, "r", encoding="utf-8-sig") as file:

        reader = csv.DictReader(file)

        for row in reader:

            source = row.get("source", filename)
            language = row.get("language", "")
            title = row.get("title", "")
            text = row.get("text", "")

            original_label = row.get(
                "original_label",
                row.get("category", "")
            )

            gold_label = row.get("gold_label", "")

            source_type = row.get("source_type", "real")

            add_article(
                source=source,
                source_type=source_type,
                language=language,
                title=title,
                text=text,
                gold_label=gold_label,
                original_label=original_label
            )


# Read ANAD JSON

anad_path = os.path.join(RAW_FOLDER, JSON_FILE)

print(f"Reading {JSON_FILE}...")

with open(anad_path, "r", encoding="utf-8") as file:
    anad_data = json.load(file)

for article in anad_data:

    add_article(
        source=article.get("source_dataset", "ANAD"),
        source_type="real",
        language=article.get("language", "ar"),
        title="",  # ANAD JSON doesn't contain a separate title field
        text=article.get("text", ""),
        gold_label="",  # You will confirm during review
        original_label=article.get("label", "")
    )

# Save final combined dataset

with open(
    OUTPUT_FILE,
    "w",
    newline="",
    encoding="utf-8-sig"
) as file:

    writer = csv.DictWriter(
        file,
        fieldnames=FINAL_FIELDS
    )

    writer.writeheader()
    writer.writerows(combined)


print("\nDone!")
print(f"Total candidates: {len(combined)}")
print(f"Saved to: {OUTPUT_FILE}")