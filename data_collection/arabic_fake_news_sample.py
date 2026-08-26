import requests
import csv
import os
import random

# -----------------------------
# Configuration
# -----------------------------

DATASET = "HeshamHaroon/Arabic_fake_news_dataset"
CONFIG = "default"
SPLIT = "train"

OUTPUT_FILE = "data_collection/raw_samples/arabic_fake_news_samples.csv"

SAMPLE_SIZE = 30

BASE_URL = "https://datasets-server.huggingface.co"
ROWS_URL = f"{BASE_URL}/rows"

os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)


# -----------------------------
# Collect candidates
# -----------------------------

all_candidates = []

# Dataset has ~3,133 rows.
# Fetch from different parts for variety.
OFFSETS = [
    0,
    300,
    600,
    900,
    1200,
    1500,
    1800,
    2100,
    2400,
    2700,
    3000
]

for offset in OFFSETS:

    print(f"Fetching rows starting at {offset}...")

    params = {
        "dataset": DATASET,
        "config": CONFIG,
        "split": SPLIT,
        "offset": offset,
        "length": 100
    }

    response = requests.get(ROWS_URL, params=params)

    if response.status_code != 200:
        print(f"ERROR {response.status_code} at offset {offset}")
        print(response.text)
        break

    data = response.json()

    for item in data.get("rows", []):

        row = item["row"]

        fake_items = row.get("fakes", [])
        link = row.get("link", "")

        # Each row can contain one or more fake claims
        for fake_text in fake_items:

            if fake_text and len(fake_text.strip()) > 30:
                all_candidates.append({
                    "text": fake_text.strip(),
                    "link": link
                })


# -----------------------------
# Remove duplicates
# -----------------------------

unique_candidates = []

seen = set()

for candidate in all_candidates:

    normalized = candidate["text"].strip()

    if normalized not in seen:
        seen.add(normalized)
        unique_candidates.append(candidate)


# -----------------------------
# Random selection
# -----------------------------

random.shuffle(unique_candidates)

selected_articles = unique_candidates[:SAMPLE_SIZE]


# -----------------------------
# Save to CSV
# -----------------------------

with open(
    OUTPUT_FILE,
    mode="w",
    newline="",
    encoding="utf-8"
) as file:

    writer = csv.DictWriter(
        file,
        fieldnames=[
            "id",
            "source",
            "language",
            "original_label",
            "text",
            "link"
        ]
    )

    writer.writeheader()

    for index, article in enumerate(selected_articles, start=1):

        writer.writerow({
            "id": index,
            "source": "Arabic_Fake_News_Matsda2sh",
            "language": "ar",
            "original_label": "fake",
            "text": article["text"],
            "link": article["link"]
        })


print(f"\nDone! {len(selected_articles)} candidates saved.")
print(f"File: {OUTPUT_FILE}")