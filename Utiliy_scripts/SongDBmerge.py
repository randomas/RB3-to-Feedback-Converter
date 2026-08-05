import os
import re
import csv
import difflib

# File paths
MAIN_DB_FILE = "rb3_songs_db.csv"
TUNING_FILE = "rockband_tunings.csv"
OUTPUT_FILE = "rb3_songs_db_merged.csv"
REPORT_FILE = "unmerged_tunings_report.csv"

# Minimum similarity score (0.0 to 1.0) to accept a match
SIMILARITY_THRESHOLD = 0.75

def normalize_string(text):
    """Strips punctuation, spaces, brackets, and converts to lowercase."""
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r'\(.*?\)', '', text)  # Remove parentheticals like (RB3 version) or (Live)
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'[^a-z0-9]', '', text)  # Keep alphanumeric only
    return text

def normalize_shortname(shortname):
    """Normalizes tuning shortnames, stripping common RB numeric/live suffixes."""
    if not shortname:
        return ""
    text = normalize_string(shortname)
    text = re.sub(r'live\d*$', '', text)
    text = re.sub(r'\d+$', '', text)
    return text

def calculate_similarity(a, b):
    """Calculates Levenshtein similarity ratio between two normalized strings."""
    if not a or not b:
        return 0.0
    
    # Direct match or exact substring match boost
    if a == b:
        return 1.0
    if (a in b or b in a) and len(a) >= 4 and len(b) >= 4:
        return max(difflib.SequenceMatcher(None, a, b).ratio(), 0.85)
        
    return difflib.SequenceMatcher(None, a, b).ratio()

def main():
    if not os.path.exists(MAIN_DB_FILE):
        print(f"Error: Could not find '{MAIN_DB_FILE}'. Falling back to 'rb3_songs_db.csv'...")
        main_file = "rb3_songs_db.csv" if os.path.exists("rb3_songs_db.csv") else MAIN_DB_FILE
    else:
        main_file = MAIN_DB_FILE

    if not os.path.exists(TUNING_FILE):
        print(f"Error: Could not find '{TUNING_FILE}'. Falling back to 'rockband_tunings.csv'...")
        tuning_file = "rockband_tunings.csv" if os.path.exists("rockband_tunings.csv") else TUNING_FILE
    else:
        tuning_file = TUNING_FILE

    print(f"Reading {main_file} and {tuning_file}...")
    
    # Load main database
    with open(main_file, 'r', encoding='utf-8', errors='ignore') as f:
        reader = csv.DictReader(f)
        main_rows = list(reader)
        fieldnames = reader.fieldnames.copy()

    # Load tunings database
    with open(tuning_file, 'r', encoding='utf-8', errors='ignore') as f:
        reader = csv.DictReader(f)
        tuning_rows = list(reader)

    # Ensure tuning headers exist in fieldnames
    if "Guitar Tuning" not in fieldnames:
        fieldnames.append("Guitar Tuning")
    if "Bass Tuning" not in fieldnames:
        fieldnames.append("Bass Tuning")

    # Pre-clean main DB entries for fast matching
    for row in main_rows:
        row['_clean_song'] = normalize_string(row.get('Song Name', ''))
        row['_clean_folder'] = normalize_string(row.get('Folder Name', ''))
        # Set default tuning
        row['Guitar Tuning'] = "0 0 0 0 0 0"
        row['Bass Tuning'] = "0 0 0 0"

    matched_count = 0
    unmerged_rows = []

    for t_row in tuning_rows:
        t_name = t_row.get('Song Name', '')
        t_clean = normalize_shortname(t_name)
        g_tuning = t_row.get('Guitar Tuning', '0 0 0 0 0 0')
        b_tuning = t_row.get('Bass Tuning', '0 0 0 0')
        
        best_score = 0.0
        best_match_row = None

        for m_row in main_rows:
            score_song = calculate_similarity(t_clean, m_row['_clean_song'])
            score_folder = calculate_similarity(t_clean, m_row['_clean_folder'])
            score = max(score_song, score_folder)

            if score > best_score:
                best_score = score
                best_match_row = m_row

        if best_score >= SIMILARITY_THRESHOLD and best_match_row is not None:
            best_match_row['Guitar Tuning'] = g_tuning
            best_match_row['Bass Tuning'] = b_tuning
            matched_count += 1
            print(f"Matched: '{t_name}' -> '{best_match_row['Song Name']}' (Score: {best_score:.2f})")
        else:
            closest_candidate = f"{best_match_row['Song Name']} ({best_match_row.get('Artist', 'Unknown Artist')})" if best_match_row else "None"
            unmerged_rows.append({
                "Tuning Shortname": t_name,
                "Guitar Tuning": g_tuning,
                "Bass Tuning": b_tuning,
                "Closest DB Candidate": closest_candidate,
                "Similarity Score": f"{best_score:.2f}"
            })

    # Clean temporary internal matching keys
    for row in main_rows:
        row.pop('_clean_song', None)
        row.pop('_clean_folder', None)

    # Write merged CSV
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(main_rows)

    # Write unmerged report CSV
    report_fieldnames = ["Tuning Shortname", "Guitar Tuning", "Bass Tuning", "Closest DB Candidate", "Similarity Score"]
    with open(REPORT_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=report_fieldnames)
        writer.writeheader()
        writer.writerows(unmerged_rows)

    print(f"\nDone! Successfully matched {matched_count}/{len(tuning_rows)} tuning entries.")
    print(f"Merged output saved to: {OUTPUT_FILE}")
    print(f"Unmerged report ({len(unmerged_rows)} entries) saved to: {REPORT_FILE}")

if __name__ == "__main__":
    main()
