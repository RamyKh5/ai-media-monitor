import requests
import csv
import os
import random

DATASET = "gustavecortal/fr_covid_news"
CONFIG = "default"
SPLIT = "train"

OUTPUT_FILE = "data_collection/raw_samples/french_covid_samples.csv"

SAMPLE_SIZE = 15

BASE_URL = "https://datasets-server.huggingface.co"
ROWS_URL = f"{BASE_URL}/rows"

os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

all_articles = []

# Fetch from different parts of the dataset for more variety
OFFSETS = [
    0,
    3000,
    6000,
    10000,
    15000,
    20000,
    25000,
    30000,
    35000,
    40000
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

        title = row.get("title")
        text = row.get("text")
        domain = row.get("domain")
        url = row.get("url")

        if text and len(text.strip()) > 200:
            all_articles.append({
                "title": title,
                "text": text,
                "domain": domain,
                "url": url
            })


# Randomly select 15 articles
random.shuffle(all_articles)

selected_articles = all_articles[:SAMPLE_SIZE]


# Save to CSV
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
            "title",
            "text",
            "domain",
            "url"
        ]
    )

    writer.writeheader()

    for index, article in enumerate(selected_articles, start=1):

        writer.writerow({
            "id": index,
            "source": "French_COVID_News",
            "language": "fr",
            "title": article["title"],
            "text": article["text"],
            "domain": article["domain"],
            "url": article["url"]
        })


print(f"\nDone! {len(selected_articles)} articles saved.")
print(f"File: {OUTPUT_FILE}")