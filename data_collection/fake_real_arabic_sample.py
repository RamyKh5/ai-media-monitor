import requests
import csv
import io
import os
import random

OUTPUT_FILE = "data_collection/raw_samples/fake_real_arabic_samples.csv"
SAMPLE_SIZE = 30

# Direct link to the fake-news CSV
URL = (
    "https://huggingface.co/datasets/"
    "sanaa-11/fake-real-arabic-news/resolve/main/"
    "fake-news.csv"
)

os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

print("Downloading candidate data...")

response = requests.get(URL)
response.raise_for_status()

# Read CSV directly from memory
content = response.content.decode("utf-8-sig")
reader = csv.DictReader(io.StringIO(content))

all_candidates = []

for row in reader:
    text = row.get("content", "").strip()
    label = row.get("label", "").strip()

    if text and len(text) > 100:
        all_candidates.append({
            "text": text,
            "original_label": label
        })

print(f"Found {len(all_candidates)} candidates.")

# Remove duplicates
unique_candidates = []
seen = set()

for candidate in all_candidates:
    normalized = candidate["text"]

    if normalized not in seen:
        seen.add(normalized)
        unique_candidates.append(candidate)

random.shuffle(unique_candidates)

selected_articles = unique_candidates[:SAMPLE_SIZE]


# Save the 30 candidates
with open(
    OUTPUT_FILE,
    "w",
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
            "text"
        ]
    )

    writer.writeheader()

    for index, article in enumerate(selected_articles, start=1):

        writer.writerow({
            "id": index,
            "source": "fake-real-arabic-news",
            "language": "ar",
            "original_label": article["original_label"],
            "text": article["text"]
        })

print(f"\nDone! {len(selected_articles)} candidates saved.")
print(f"File: {OUTPUT_FILE}")