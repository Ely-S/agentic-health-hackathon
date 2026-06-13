#!/usr/bin/env python3
"""Extract named persons/doctors/practitioners from posts.db using spaCy NER."""

# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "spacy",
#   "click",
#   "en-core-web-lg @ https://github.com/explosion/spacy-models/releases/download/en_core_web_lg-3.8.0/en_core_web_lg-3.8.0-py3-none-any.whl",
# ]
# ///

import sqlite3
import re
from collections import Counter
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "posts.db"
SPACY_MODEL = "en_core_web_lg"

PRACTITIONER_PATTERNS = re.compile(
    r"\b(Dr\.?|Doctor|Prof\.?|Professor|Nurse|NP|PA|Physician|Specialist|"
    r"Neurologist|Cardiologist|Rheumatologist|Immunologist|Pulmonologist|"
    r"Psychiatrist|Psychologist|Therapist|Practitioner|Clinician|Surgeon|"
    r"Internist|GP|PCP|MD|DO|PhD|RN|ARNP)\b",
    re.IGNORECASE,
)

# spaCy PERSON-tagged tokens that are not actually people
BLOCKLIST: set[str] = {
    # Viruses / conditions / syndromes
    "Covid", "Long Covid", "COVID-19", "covid", "pre-Covid", "long covid", "lomg covid",
    "My Long Covid", "SIBO", "ANA", "ana", "Ana", "Hashimoto", "Hashimotos",
    "Epstein-Barr", "Epstein Barr", "Epstein", "Sjogren", "Ehlers", "Ehlers Danlos",
    "Raynaud", "Parosmia", "Parkinsons", "Erythromelalgia", "Myalgic Encephalomyelitis",
    "Chiari", "Crohns", "Candida", "Brain Fog", "Auriculotemporal", "GFAP", "GPCR",
    "Herxeimer", "Horner", "Zonulin", "Nanoplastics", "C4a", "MAO", "M.E.",
    "Spike", "negación de sonda",
    # Drugs / medications
    "Paxlovid", "Nattokinase", "nattokinase", "Guanfacine", "Guanfacin", "Tirzepatide",
    "tirzepatide", "Tirz", "Mestinon", "Maraviroc", "Maravoric", "Cromolyn",
    "Cromolyn Sodium", "Famotidine", "Famatodine", "Ivabradine", "Midodrine",
    "Ketotifen", "Montelukast", "Xyzal", "Azelastine", "Cetirizine", "Daratumumab",
    "Sipavibart", "VYD2311", "Clonodine", "Rapamycine", "Rapamycin", "Meldonium",
    "Vyvanse", "Dextromethorphan", "Amifampridine", "Truvada", "Semaglutide",
    "Serrapeptase", "Semax", "Nasalcrom", "Pycnogenol", "Valcyclovir", "Bisoprolol",
    "Adderall", "Metropolol", "Propranalol", "Propanolol", "Rituximab", "Quviviq",
    "Nalcrom", "Thymalin", "TB500", "Xifaxan", "Mounjaro", "Ssri", "Effexor",
    "Bisoprolol", "Adempas", "Xlear", "Xlear Nasal Spray", "Zepbound", "Invivyd",
    "-Migraine Botox", "Truvada", "Alinia",
    # Supplements
    "Zeolite", "Creatine", "Benfotiamine", "Luteolin", "Akkermansia", "Gou Teng",
    "Butyrate", "Monolaurin", "Gaba", "TA1", "ss31", "ldn", "Thorne", "serra", "Serra",
    "Serra", "Serrapeptase",
    # Vaccine / pharma brands
    "Novavax", "J&J",
    # Generic medical role words (not names)
    "Dr", "Drs", "ED", "Neurology", "Pulmonary", "Opthalmologist", "Nuero",
    "My Dr", "My dr", "Bedbound",
    # Organizations / institutions
    "Scripps", "Bateman Horne", "Bateman Horne Center", "Uniklinik Marburg",
    "Lifemark", "MyChart", "EBOO", "Attomarker", "Visible", "Brigham",
    # Activities / states
    "Pilates", "Yoga Nidra", "Nidra", "Keto",
    # Internet slang / abbreviations / noise
    "max", "dm", "Dm", "Ty", "al", "jack", "glp", "GLP", "GF", "xx", "Yo", "Wdym",
    "Je", "Lmk", "Jak", "tysm", "Rthm", "mito", "Ando", "Reta",
    # Famous non-medical public figures / fictional / religious
    "Claude", "God", "Jesus", "Jesus Christ", "Godspeed", "Superman", "Biden",
    "Bluesky", "YouTube", "Tiktok", "twitter", "Albert Heijn",
    # Emoji / symbols / URLs
    "♥️", "🫶🏻",
    # Too generic to be meaningful as a name
    "Zamasu", "Amatica", "Yess", "Valentine", "Wdym", "bush",
}

# Normalise for case-insensitive lookup
_BLOCKLIST_LOWER = {s.lower() for s in BLOCKLIST}


def is_blocked(name: str) -> bool:
    return name.lower() in _BLOCKLIST_LOWER


def load_posts(db_path: Path) -> list[tuple[str, str]]:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT post_id, body_text FROM posts WHERE body_text != ''")
    rows = cur.fetchall()
    conn.close()
    return rows


def is_likely_practitioner(text: str, ent_start_char: int) -> bool:
    window = text[max(0, ent_start_char - 60) : ent_start_char]
    return bool(PRACTITIONER_PATTERNS.search(window))


def save_to_db(db_path: Path, person_counter: Counter, practitioner_counter: Counter) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript("""
        DROP TABLE IF EXISTS practitioner_names;
        CREATE TABLE practitioner_names (
            name                TEXT PRIMARY KEY,
            total_mentions      INTEGER NOT NULL DEFAULT 0,
            practitioner_mentions INTEGER NOT NULL DEFAULT 0
        );
    """)
    rows = [
        (name, count, practitioner_counter.get(name, 0))
        for name, count in person_counter.most_common()
    ]
    cur.executemany(
        "INSERT INTO practitioner_names (name, total_mentions, practitioner_mentions) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    print(f"Saved {len(rows):,} records to practitioner_names table in {db_path}")


def main():
    import spacy

    print(f"Loading spaCy model '{SPACY_MODEL}'...")
    nlp = spacy.load(SPACY_MODEL)

    print(f"Loading posts from {DB_PATH}...")
    posts = load_posts(DB_PATH)
    print(f"Processing {len(posts):,} posts...")

    person_counter: Counter = Counter()
    practitioner_counter: Counter = Counter()
    mentions: dict[str, list[str]] = {}

    batch_size = 500
    texts = [(pid, body) for pid, body in posts]

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        if i % 5000 == 0:
            print(f"  {i:,}/{len(texts):,}...")

        docs = list(nlp.pipe([body for _, body in batch], batch_size=batch_size))

        for (post_id, body), doc in zip(batch, docs):
            found = []
            for ent in doc.ents:
                if ent.label_ != "PERSON":
                    continue
                name = ent.text.strip()
                if len(name) < 2 or is_blocked(name):
                    continue
                person_counter[name] += 1
                if is_likely_practitioner(body, ent.start_char):
                    practitioner_counter[name] += 1
                found.append(name)
            if found:
                mentions[post_id] = found

    print(f"\n{'='*60}")
    print(f"Total unique person names found: {len(person_counter):,}")
    print(f"Names appearing near practitioner titles: {len(practitioner_counter):,}")
    print(f"Posts containing at least one name: {len(mentions):,}")

    print(f"\n--- Top 50 most-mentioned people ---")
    for name, count in person_counter.most_common(50):
        marker = " [practitioner]" if name in practitioner_counter else ""
        print(f"  {count:>5}x  {name}{marker}")

    print(f"\n--- Top 30 likely practitioners/doctors ---")
    for name, count in practitioner_counter.most_common(30):
        print(f"  {count:>5}x  {name}")

    # Write TSV
    out_path = Path(__file__).parent.parent / "named_persons.tsv"
    with open(out_path, "w") as f:
        f.write("name\ttotal_mentions\tpractitioner_mentions\n")
        for name, count in person_counter.most_common():
            pcount = practitioner_counter.get(name, 0)
            f.write(f"{name}\t{count}\t{pcount}\n")
    print(f"\nFull results written to {out_path}")

    # Write to DB
    save_to_db(DB_PATH, person_counter, practitioner_counter)


if __name__ == "__main__":
    main()
