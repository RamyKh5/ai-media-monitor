import os
import re
import json
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from ollama import chat
from sklearn.metrics import classification_report, accuracy_score, confusion_matrix

# ==========================================
# PATHS & CONFIGURATION
# ==========================================
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = PROJECT_ROOT / "data" / "golden_dataset_master_reviewed.csv"
OUTPUT_CSV = PROJECT_ROOT / "data" / "evaluation_results.csv"
OUTPUT_PLOT = PROJECT_ROOT / "confusion_matrix.png"

ID_COLUMN = "reviewed_id"
TEXT_COLUMN = "text"
LABEL_COLUMN = "gold_label"

PROMPT_TEMPLATE = """You are a content-risk classifier for Algerian news articles.
The input article may be written in Arabic, French, or English.
Analyze the article in its original language and classify it into exactly ONE category.

CATEGORIES:
SAFE, THREAT_OR_INCITEMENT, MISINFORMATION_HAZARD

Return ONLY valid JSON matching this schema:
{{
  "classification": "SAFE | THREAT_OR_INCITEMENT | MISINFORMATION_HAZARD",
  "confidence_score": 0.0,
  "reasoning": "Brief explanation."
}}

Article:
{article_text}"""

def plot_confusion_matrix(y_true, y_pred, labels):
    """Generates and saves a visual confusion matrix heatmap."""
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    plt.figure(figsize=(8, 6))
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', xticklabels=labels, yticklabels=labels)
    plt.xlabel('Predicted Label')
    plt.ylabel('True Label')
    plt.title('Confusion Matrix - News Article Safety Classifier')
    plt.tight_layout()
    plt.savefig(OUTPUT_PLOT)
    print(f"\n📊 Confusion matrix plot saved to: {OUTPUT_PLOT}")

def run_evaluation():
    if not DATA_PATH.exists():
        print(f"❌ Error: Dataset file not found at {DATA_PATH}")
        return

    df = pd.read_csv(DATA_PATH, encoding='utf-8-sig')
    
    # ----------------------------------------------------
    # 1. CHECKPOINT & RESUME SETUP
    # ----------------------------------------------------
    processed_ids = set()
    if OUTPUT_CSV.exists():
        df_existing = pd.read_csv(OUTPUT_CSV, encoding='utf-8-sig')
        processed_ids = set(df_existing[ID_COLUMN].astype(str))
        print(f"🔄 Resuming run! Found {len(processed_ids)} already processed articles in {OUTPUT_CSV.name}")

    print(f"🚀 Processing evaluation over {len(df)} total samples using Qwen 2.5...\n")

    # ----------------------------------------------------
    # 2. INFERENCE LOOP WITH IMMEDIATE PERSISTENCE
    # ----------------------------------------------------
    for idx, row in df.iterrows():
        article_id = str(row[ID_COLUMN])
        
        # Skip if ID was processed in a previous run
        if article_id in processed_ids:
            continue
            
        article_text = str(row[TEXT_COLUMN])
        true_label = str(row[LABEL_COLUMN]).strip()
        pred_label = "ERROR"

        try:
            response = chat(
                model='qwen2.5:7b',
                messages=[{'role': 'user', 'content': PROMPT_TEMPLATE.format(article_text=article_text)}],
                options={'temperature': 0.0}
            )
            content = response['message']['content']
            
            # Clean markdown code blocks if present
            cleaned = re.sub(r'```(?:json)?\s*([\s\S]*?)\s*```', r'\1', content).strip()
            parsed = json.loads(cleaned)
            pred_label = parsed.get("classification", "UNKNOWN").strip()
            
        except json.JSONDecodeError:
            print(f"⚠️ Warning [Row {idx+1} | ID {article_id}]: Invalid JSON output.")
            pred_label = "PARSE_ERROR"
        except Exception as e:
            print(f"❌ Error [Row {idx+1} | ID {article_id}]: {e}")
            pred_label = "API_ERROR"

        # Prepare single record
        result_row = {
            ID_COLUMN: article_id,
            "gold_label": true_label,
            "pred_label": pred_label
        }

        # Flush record immediately to CSV on disk (mode='a')
        pd.DataFrame([result_row]).to_csv(
            OUTPUT_CSV,
            mode='a',
            header=not OUTPUT_CSV.exists(),
            index=False,
            encoding='utf-8-sig'
        )
        
        print(f"Row {idx+1}/{len(df)} | ID: {article_id} | True: {true_label} | Pred: {pred_label}")

    # ----------------------------------------------------
    # 3. METRICS & VISUALIZATION (COMPUTED FROM SAVED RESULTS)
    # ----------------------------------------------------
    if not OUTPUT_CSV.exists():
        print("❌ No evaluation results found to calculate metrics.")
        return

    results_df = pd.read_csv(OUTPUT_CSV, encoding='utf-8-sig')
    y_true = results_df["gold_label"].astype(str).str.strip().tolist()
    y_pred = results_df["pred_label"].astype(str).str.strip().tolist()

    print("\n" + "="*50)
    print(f"📊 FINAL EVALUATION REPORT ({len(results_df)} Evaluated Samples)")
    print("="*50)
    print(f"Accuracy: {accuracy_score(y_true, y_pred):.4f}\n")
    print(classification_report(y_true, y_pred, zero_division=0))

    # Confusion Matrix Visualization across expected categories
    labels = ["SAFE", "THREAT_OR_INCITEMENT", "MISINFORMATION_HAZARD"]
    plot_confusion_matrix(y_true, y_pred, labels)

if __name__ == "__main__":
    run_evaluation()