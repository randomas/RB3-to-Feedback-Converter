import csv
import re
import time
import difflib
import requests

# Path configurations
INPUT_CSV = "rb3_songs_db_merged.csv"
OUTPUT_CSV = "rb3_songs_db_merged_with_tunings.csv"

SEARCH_URL = "https://www.songsterr.com/api/search"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:152.0) Gecko/20100101 Firefox/152.0",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}

# GM program ranges (Songsterr's instrumentId is the 0-based GM patch number)
GUITAR_RANGE = range(24, 32)
BASS_RANGE = range(32, 40)

REQUEST_DELAY = 0.5


def clean_string(text):
    if not text:
        return ""
    text = str(text).lower()
    text = re.sub(r"\(live\)|\(rb3 version\)|\(2x bass pedal expert\+\)", "", text)
    text = re.sub(r"[^\w\s]", "", text)
    return " ".join(text.split())


def calculate_tuning_distance(tuning_list, is_bass=False):
    if not tuning_list or not isinstance(tuning_list, list):
        return "Unknown"
    try:
        actual_midi = [int(n) for n in tuning_list]
        if not is_bass:
            standard = [64, 59, 55, 50, 45, 40]
            if len(actual_midi) == 7:
                standard = [64, 59, 55, 50, 45, 40, 35]
        else:
            standard = [43, 38, 33, 28]
            if len(actual_midi) == 5:
                standard = [43, 38, 33, 28, 23]
        deltas = [
            actual_midi[i] - standard[i]
            for i in range(min(len(actual_midi), len(standard)))
        ]
        # Songsterr returns tuning high string first (1st string -> last string).
        # This DB's convention is low string first (6th/4th string -> 1st string).
        # Reverse to match.
        deltas.reverse()
        return " ".join(map(str, deltas))
    except Exception:
        return "Unknown"


def is_matching_instrument(track, id_range):
    """
    Checks if a track matches the target instrument type using GM instrumentId
    or falls back to inspecting the instrument/track name strings.
    """
    inst_id = track.get("instrumentId")
    if isinstance(inst_id, int) and inst_id in id_range:
        return True

    # Fallback: String inspection in case GM patch isn't standard
    inst_name = str(track.get("instrument", "")).lower()
    track_name = str(track.get("name", "")).lower()
    title_name = str(track.get("title", "")).lower()
    combined = f"{inst_name} {track_name} {title_name}"

    if id_range == GUITAR_RANGE:
        return ("guitar" in combined or "gtr" in combined) and "bass" not in combined
    elif id_range == BASS_RANGE:
        return "bass" in combined

    return False


def pick_track(record, popular_key, id_range):
    """Return the best track dict for guitar/bass, or None."""
    tracks = record.get("tracks", [])

    # 1) Check popular track if it matches the target instrument
    idx = record.get(popular_key)
    if isinstance(idx, int) and 0 <= idx < len(tracks):
        t = tracks[idx]
        if t.get("tuning") and is_matching_instrument(t, id_range):
            return t

    # 2) Fallback: Gather all matching candidates with tunings
    candidates = [
        t for t in tracks
        if t.get("tuning") and is_matching_instrument(t, id_range)
    ]
    if not candidates:
        return None

    # Priority ranking function
    def candidate_score(t):
        name = str(t.get("name", "")).lower()
        title = str(t.get("title", "")).lower()
        inst = str(t.get("instrument", "")).lower()
        combined = f"{name} {title} {inst}"
        
        score = t.get("views", 0)

        # Prioritize Lead / Rhythm / Main tracks over secondary tracks
        if "lead" in combined or "rhythm" in combined or "main" in combined:
            score += 1_000_000
        if id_range == GUITAR_RANGE and "guitar" in combined:
            score += 100_000
        elif id_range == BASS_RANGE and "bass" in combined:
            score += 100_000

        return score

    return max(candidates, key=candidate_score)


def find_best_record(records, artist, song):
    """Filter by artist match, then rank by title similarity, then views."""
    target_artist = clean_string(artist)
    target_title = clean_string(song)

    matches = [
        r for r in records
        if target_artist and (
            clean_string(r.get("artist", "")) == target_artist
            or clean_string(r.get("artist", "")) in target_artist
            or target_artist in clean_string(r.get("artist", ""))
        )
    ]
    pool = matches if matches else records
    if not pool:
        return None, ("no_artist_match" if not matches else "matched")

    def score(r):
        title_sim = difflib.SequenceMatcher(
            None, clean_string(r.get("title", "")), target_title
        ).ratio()
        total_views = sum(t.get("views", 0) for t in r.get("tracks", []))
        return (title_sim, total_views)

    best = max(pool, key=score)
    status = "matched" if matches else "matched_no_artist_filter"
    return best, status


def get_real_tunings(artist, song):
    """Returns (guitar_delta, bass_delta, status) for one artist/song."""
    if " - " in artist and not song:
        parts = artist.split(" - ", 1)
        artist, song = parts[0], parts[1]

    params = {
        "pattern": f"{artist} {song}",
        "inst": "undefined",
        "tuning": "undefined",
        "difficulty": "undefined",
        "size": 25,
        "from": 0,
        "more": "true",
    }

    try:
        resp = requests.get(SEARCH_URL, params=params, headers=HEADERS, timeout=10)
    except requests.RequestException as e:
        return "Unknown", "Unknown", f"request_error:{e.__class__.__name__}"

    if resp.status_code != 200:
        return "Unknown", "Unknown", f"http_error:{resp.status_code}"

    try:
        data = resp.json()
    except ValueError:
        return "Unknown", "Unknown", "bad_json"

    records = data.get("records", [])
    if not records:
        return "Unknown", "Unknown", "no_results"

    record, status = find_best_record(records, artist, song)
    if record is None:
        return "Unknown", "Unknown", status

    g_track = pick_track(record, "popularTrackGuitar", GUITAR_RANGE)
    b_track = pick_track(record, "popularTrackBass", BASS_RANGE)

    g_delta = calculate_tuning_distance(g_track["tuning"], is_bass=False) if g_track else "Unknown"
    b_delta = calculate_tuning_distance(b_track["tuning"], is_bass=True) if b_track else "Unknown"

    if g_track is None and b_track is None:
        status += "_no_guitar_or_bass_track"

    return g_delta, b_delta, status


def find_column(headers, names_to_check):
    for name in names_to_check:
        for header in headers:
            if header.strip().lower() == name.lower():
                return header
    return None


def batch_process_csv():
    print("Querying Songsterr /api/search for real tunings...")

    with open(INPUT_CSV, "r", encoding="utf-8-sig") as infile:
        reader = csv.DictReader(infile)
        headers = reader.fieldnames

        artist_key = find_column(headers, ["artist", "band"])
        song_key = find_column(headers, ["song name", "song", "title", "track"])

        if not artist_key or not song_key:
            print(f"\nError: Mapping fields missing from source headers: {headers}")
            return

        print(f"Using columns: '{artist_key}' and '{song_key}'.")

        fieldnames = headers + ["S.SterrGtuning", "S.SterrBtuning", "S.SterrStatus"]

        with open(OUTPUT_CSV, "w", encoding="utf-8", newline="") as outfile:
            writer = csv.DictWriter(outfile, fieldnames=fieldnames)
            writer.writeheader()

            count = 0
            misses = 0
            for row in reader:
                artist = row.get(artist_key, "").strip()
                song = row.get(song_key, "").strip()

                g_tune, b_tune, status = get_real_tunings(artist, song)
                flag = "" if status.startswith("matched") else "  <-- CHECK"
                print(f"Row {count + 1}: {artist} - {song} | G: {g_tune} | B: {b_tune} | {status}{flag}")
                if not status.startswith("matched"):
                    misses += 1

                row["S.SterrGtuning"] = g_tune
                row["S.SterrBtuning"] = b_tune
                row["S.SterrStatus"] = status

                writer.writerow(row)
                count += 1
                time.sleep(REQUEST_DELAY)

    print(f"\nDone. {count} rows processed, {misses} flagged for review.")
    print(f"Output written to: {OUTPUT_CSV}")


if __name__ == "__main__":
    batch_process_csv()
