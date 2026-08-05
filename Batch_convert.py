import os
import csv
import argparse
from rb3_converter import convert_to_feedpak, resolve_tuning

def parse_int(val):
    try:
        return int(val)
    except (ValueError, TypeError):
        return -1

def batch_convert(csv_path, base_songs_dir, output_folder, dry_run=False):
    if not os.path.exists(csv_path):
        print(f"Error: CSV file not found at {csv_path}")
        return

    filtered_rows = []
    total_csv_count = 0

    with open(csv_path, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        # The merged CSV (rb3_songs_db_merged_with_tunings.csv) has these
        # extra columns; the plain rb3_songs_db.csv doesn't. Detect which
        # one we were given so this still works with either.
        has_tuning_columns = reader.fieldnames is not None and \
            'S.SterrGtuning' in reader.fieldnames and 'S.SterrBtuning' in reader.fieldnames

        for row in reader:
            total_csv_count += 1
            has_pro_guitar = row.get('Has Pro Guitar', '').strip().lower() == 'true'
            has_pro_keys = row.get('Has Pro Keys', '').strip().lower() == 'true'
            diff_pro_guitar = parse_int(row.get('Diff Pro Guitar', -1))
            diff_pro_keys = parse_int(row.get('Diff Pro Keys', -1))

            # Filter rows where either Pro Guitar / Combo or Pro Keys is present
            if has_pro_guitar or has_pro_keys or diff_pro_guitar >= 0 or diff_pro_keys >= 0:
                filtered_rows.append(row)

    total_matches = len(filtered_rows)

    if not has_tuning_columns:
        print("Note: CSV has no Songsterr tuning columns (S.SterrGtuning/S.SterrBtuning) - "
              "falling back to each song's own song.ini tuning. Point this at "
              "rb3_songs_db_merged_with_tunings.csv to use the reconciled tunings.\n")

    # Dry Run Execution
    if dry_run:
        print(f"--- DRY RUN MODE ---")
        print(f"Found {total_matches} songs matching criteria out of {total_csv_count} total songs in CSV:\n")
        
        missing_count = 0
        for row in filtered_rows:
            folder_name = row['Folder Name']
            song_folder = os.path.join(base_songs_dir, folder_name)
            
            exists = os.path.exists(song_folder)
            status = "FOUND" if exists else "MISSING ON DISK"
            if not exists:
                missing_count += 1
                
            print(f" - [{status}] {folder_name}")

        print(f"\nDry run complete. {total_matches - missing_count} folders ready to convert ({missing_count} missing on disk).")
        return

    # Normal Conversion Execution
    print(f"Converting {total_matches} files...\n")

    success_count = 0
    check_tuning_count = 0
    for row in filtered_rows:
        folder_name = row['Folder Name']
        song_folder = os.path.join(base_songs_dir, folder_name)
        
        if not os.path.exists(song_folder):
            print(f"Warning: Song folder not found on disk: {song_folder}")
            continue
            
        print(f"[{success_count + 1}/{total_matches}] Processing folder: {folder_name}")

        guitar_tuning, guitar_check = None, False
        bass_tuning, bass_check = None, False
        if has_tuning_columns:
            guitar_tuning, guitar_check = resolve_tuning(
                row.get('Guitar Tuning'), row.get('S.SterrGtuning'), None)
            bass_tuning, bass_check = resolve_tuning(
                row.get('Bass Tuning'), row.get('S.SterrBtuning'), None)
            if guitar_check or bass_check:
                check_tuning_count += 1

        try:
            convert_to_feedpak(
                song_folder, output_folder,
                guitar_tuning_override=guitar_tuning, guitar_tuning_check=guitar_check,
                bass_tuning_override=bass_tuning, bass_tuning_check=bass_check
            )
            success_count += 1
        except Exception as e:
            print(f"Error converting {folder_name}: {e}")

    print(f"\nBatch conversion complete! Successfully processed {success_count} files.")
    if has_tuning_columns:
        print(f"{check_tuning_count} song(s) flagged '(check tuning)' - RB3 and Songsterr tunings "
              f"disagreed by a non-uniform amount across strings.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch convert RB3 songs with Pro Guitar/Keys from CSV.")
    parser.add_argument("csv_path", help="Path to rb3_songs_db_merged_with_tunings.csv (or rb3_songs_db.csv for song.ini-only tuning)")
    parser.add_argument("base_songs_dir", help="Base directory containing the song folders")
    parser.add_argument("output_folder", help="Directory where .feedpak files will be saved")
    parser.add_argument("--dry-run", action="store_true", help="Preview the songs to be converted without running the conversion")
    
    args = parser.parse_args()
    batch_convert(args.csv_path, args.base_songs_dir, args.output_folder, dry_run=args.dry_run)