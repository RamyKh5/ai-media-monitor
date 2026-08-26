import requests
import csv
import random
import os

# -----------------------------
# Configuration
# -----------------------------

DATASET = "khalidalt/SANAD"
CONFIG = "default"
SPLIT = "train"

OUTPUT_FILE = "data_collection/raw_samples/sanad_samples.csv"
# How many articles we want from each category
SAMPLES_PER_CATEGORY = {
    "Politics": 5,
    "Technology": 5,
    "Medical": 5,
    "Finance": 5,
    "Culture": 5,
    "Sports": 5,
}

# Hugging Face Dataset Server API
BASE_URL = "https://datasets-server.huggingface.co"

os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)


# -----------------------------
# Get dataset information
# -----------------------------

info_url = f"{BASE_URL}/info?dataset={DATASET}"
info = requests.get(info_url)
info.raise_for_status()

dataset_info = info.json()

print("Dataset information loaded.")


# -----------------------------
# Download rows in chunks
# -----------------------------

rows_url = f"{BASE_URL}/rows"

all_articles = []

# We inspect different positions in the dataset
# to increase variety.
OFFSETS = [
    0,
    5000,
    10000,
    20000,
    30000,
    50000,
    70000,
    90000,
    110000,
]

for offset in OFFSETS:

    print(f"Fetching rows starting at {offset}...")

    params = {
        "dataset": DATASET,
        "config": CONFIG,
        "split": SPLIT,
        "offset": offset,
        "length": 100,
    }

    response = requests.get(rows_url, params=params)

    if response.status_code != 200:
        print(f"Could not fetch offset {offset}")
        continue

    data = response.json()
   

    for item in data.get("rows", []):
        row = item["row"]

        category = row.get("category")
        text = row.get("article")

        if category in SAMPLES_PER_CATEGORY and text:
            all_articles.append({
                "category": category,
                "text": text
            })


# -----------------------------
# Select random samples
# -----------------------------

random.shuffle(all_articles)

selected_articles = []

for category, wanted in SAMPLES_PER_CATEGORY.items():

    candidates = [
        article for article in all_articles
        if article["category"] == category
    ]

    selected = candidates[:wanted]

    print(
        f"{category}: "
        f"found {len(candidates)}, "
        f"selected {len(selected)}"
    )

    selected_articles.extend(selected)


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
        fieldnames=["id", "source", "language", "category", "text"]
    )

    writer.writeheader()

    for index, article in enumerate(selected_articles, start=1):

        writer.writerow({
            "id": index,
            "source": "SANAD",
            "language": "ar",
            "category": article["category"],
            "text": article["text"]
        })


print("\nDone!")
print(f"{len(selected_articles)} articles saved.")
print(f"File: {OUTPUT_FILE}")