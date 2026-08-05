import os
import csv
import configparser

LIST_FILE = "songlist.txt"
BASE_DIR = "."             
OUTPUT_CSV = "rb3_songs_db.csv"

def parse_ini(ini_path):
    config = configparser.ConfigParser(strict=False, allow_no_value=True)
    try:
        # 'utf-8-sig' automatically strips UTF-8 Byte Order Marks (\ufeff)
        with open(ini_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
            config.read_file(f)
        
        section = config['song'] if 'song' in config else {}
        return {k.lower(): v.strip() for k, v in section.items()}
    except Exception as e:
        print(f"Error reading {ini_path}: {e}")
        return {}

def main():
    songs_data = []

    if not os.path.exists(LIST_FILE):
        print(f"Error: {LIST_FILE} not found!")
        return

    with open(LIST_FILE, 'r', encoding='utf-8') as f:
        folder_names = [line.strip() for line in f if line.strip()]

    print(f"Found {len(folder_names)} entries in list. Indexing...")

    for folder_name in folder_names:
        folder_path = os.path.join(BASE_DIR, folder_name)

        if not os.path.isdir(folder_path):
            print(f"Skipping (not a directory): {folder_name}")
            continue

        ini_path = os.path.join(folder_path, "song.ini")
        ini_data = parse_ini(ini_path) if os.path.exists(ini_path) else {}

        try:
            audio_files = [f for f in os.listdir(folder_path) if f.endswith('.ogg')]
        except Exception as e:
            print(f"Could not list directory {folder_path}: {e}")
            audio_files = []

        def get_diff(key):
            val = ini_data.get(key, '-1')
            try:
                return int(val)
            except ValueError:
                return -1

        # Check for Pro Features & Harmonies
        has_pro_guitar = get_diff("diff_guitar_real") > -1 or get_diff("diff_guitar_real_22") > -1
        has_pro_keys = get_diff("diff_keys_real") > -1
        
        # Pro Drums is present if pro_drums flag is True or diff_drums_real > -1
        pro_drums_flag = ini_data.get("pro_drums", "").lower() in ("true", "1")
        has_pro_drums = pro_drums_flag or get_diff("diff_drums_real") > -1
        
        # Vocal Harmonies
        has_vocal_harmonies = get_diff("diff_vocals_harm") > -1

        row = {
            "Folder Name": folder_name,
            "Song Name": ini_data.get("name", "Unknown"),
            "Artist": ini_data.get("artist", "Unknown"),
            "Album": ini_data.get("album", "Unknown"),
            "Year": ini_data.get("year", "Unknown"),
            "Charter": ini_data.get("charter", "Unknown"),
            # Standard Difficulties
            "Diff Band": get_diff("diff_band"),
            "Diff Guitar": get_diff("diff_guitar"),
            "Diff Bass": get_diff("diff_bass"),
            "Diff Drums": get_diff("diff_drums"),
            "Diff Keys": get_diff("diff_keys"),
            "Diff Vocals": get_diff("diff_vocals"),
            # Pro & Harmony Difficulties
            "Diff Pro Guitar": get_diff("diff_guitar_real"),
            "Diff Pro Bass": get_diff("diff_bass_real"),
            "Diff Pro Keys": get_diff("diff_keys_real"),
            "Diff Pro Drums": get_diff("diff_drums_real"),
            "Diff Vocal Harmonies": get_diff("diff_vocals_harm"),
            # Quick Boolean Indicators
            "Has Pro Guitar": has_pro_guitar,
            "Has Pro Keys": has_pro_keys,
            "Has Pro Drums": has_pro_drums,
            "Has Vocal Harmonies": has_vocal_harmonies,
            # Audio files list
            "Audio Tracks": ", ".join(sorted(audio_files))
        }

        songs_data.append(row)

    if songs_data:
        headers = songs_data[0].keys()
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=headers)
            writer.writeheader()
            writer.writerows(songs_data)

        print(f"\nSuccessfully generated '{OUTPUT_CSV}' with {len(songs_data)} entries!")

if __name__ == "__main__":
    main()
