import os
import json
import fitz  # PyMuPDF
from pathlib import Path
from tqdm import tqdm
from langdetect import detect
from collections import defaultdict

# --- CONFIG ---
INPUT_DIR = Path("/app/input")
OUTPUT_DIR = Path("/app/output")
PERSONA_FILE = INPUT_DIR / "persona_task.json"

# --- LOAD PERSONA / TASK ---
def load_persona():
    if PERSONA_FILE.exists():
        with open(PERSONA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

persona_data = load_persona()

# --- BASIC HEADING DETECTION UTILS ---
def detect_language(text):
    try:
        return detect(text)
    except:
        return "unknown"

def extract_headings(doc):
    headings = []
    font_sizes = defaultdict(int)

    for page_num, page in enumerate(doc, 1):
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    size = round(span["size"], 1)
                    font_sizes[size] += 1

    sorted_sizes = sorted(font_sizes.items(), key=lambda x: -x[1])
    if not sorted_sizes:
        return []

    h1_size = sorted_sizes[0][0]
    h2_size = sorted_sizes[1][0] if len(sorted_sizes) > 1 else h1_size - 1
    h3_size = sorted_sizes[2][0] if len(sorted_sizes) > 2 else h2_size - 1

    for page_num, page in enumerate(doc, 1):
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span["text"].strip()
                    size = round(span["size"], 1)
                    if text:
                        if size == h1_size:
                            level = "H1"
                        elif size == h2_size:
                            level = "H2"
                        elif size == h3_size:
                            level = "H3"
                        else:
                            continue
                        headings.append({
                            "document": "",
                            "section_title": text,
                            "importance_rank": 1 if level == "H1" else 2 if level == "H2" else 3,
                            "page_number": page_num
                        })
    return headings

# --- SECTION FILTERING & SUMMARY ---
def filter_relevant_sections(sections):
    keywords = ["abstract", "introduction", "summary", "conclusion"]
    keywords += persona_data.get("job_to_be_done", {}).get("task", "").lower().split()
    relevant = [s for s in sections if any(k in s["section_title"].lower() for k in keywords)]
    return relevant

def summarize_text(text, lang="en"):
    if lang != "en":
        text = text.replace("\n", " ")
    sentences = text.split(".")
    summary = ". ".join(sent.strip() for sent in sentences[:3] if sent.strip())
    return summary

# --- PROCESS ONE PDF ---
def process_pdf(filepath):
    try:
        doc = fitz.open(filepath)
        lang_text = " ".join([p.get_text() for p in doc[:min(5, len(doc))]])
        lang = detect_language(lang_text)

        headings = extract_headings(doc)
        for h in headings:
            h["document"] = filepath.name

        relevant = filter_relevant_sections(headings)

        subsection_summaries = []
        for sec in relevant:
            page_idx = sec["page_number"] - 1
            if 0 <= page_idx < len(doc):  # ✅ Fix: safe page access
                page = doc[page_idx]
                text = page.get_text()
                summary = summarize_text(text, lang)
                subsection_summaries.append({
                    "document": filepath.name,
                    "section_title": sec["section_title"],
                    "summary": summary,
                    "language": lang
                })

        output_json = {
            "metadata": {
                "filename": filepath.name,
                "language": lang,
                "num_pages": len(doc)
            },
            "extracted_sections": headings,
            "subsection_analysis": subsection_summaries
        }

        out_path = OUTPUT_DIR / f"{filepath.stem}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output_json, f, indent=2, ensure_ascii=False)

    except Exception as e:
        print(f"Error in {filepath.name}: {e}")

# --- PROCESS ALL PDFs ---
def process_all():
    OUTPUT_DIR.mkdir(exist_ok=True, parents=True)
    pdf_files = list(INPUT_DIR.glob("*.pdf"))
    for pdf in tqdm(pdf_files, desc="Processing PDFs"):
        process_pdf(pdf)

# --- CLI ENTRY ---
if __name__ == "__main__":
    process_all()
