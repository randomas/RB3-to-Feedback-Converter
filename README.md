# RB3-to-Feedback-Converter
# Rock Band 3 to Feedpak Converter Toolkit

A collection of Python utilities designed to index, parse, and convert **Rock Band 3** (and custom) song folders into the standard **Feedpak** format (`.feedpak`).

This toolkit parses metadata, audio stems, and MIDI tracks (including Pro Guitar, Pro Bass, Pro Keys, Pro Drums, Vocals, and Timeline events) to output valid Feedpak archives and custom song databases.

---

## Table of Contents

* [Overview](#overview)
* [Requirements & Dependencies](#requirements--dependencies)
* [Script Descriptions](#script-descriptions)
* [Usage Workflow](#usage-workflow)
* [1. Indexing Songs (generate_db.py)](#1-indexing-songs-generate_dbpy)
* [2. Single Song Conversion (rb3_converter.py)](#2-single-song-conversion-rb3_converterpy)
* [3. Batch Conversion (batch_convert.py)](#3-batch-conversion-batch_convertpy)
* [MIDI Parsing Details](#midi-parsing-details)
---

## Overview

The repository consists of four interconnected Python scripts:

1. `generate_db.py` — Scans local song directories and generates a CSV database with track information, difficulties, and feature flags.
2. `rb_parser.py` — High-level MIDI engine that extracts tempo maps, time signatures, notes, lyrics, drum hits, and key annotations from `notes.mid`.
3. `rb3_converter.py` — Converts an individual Rock Band song folder into a single `.feedpak` file containing `manifest.yaml`, stems, artwork, and arrangement JSON files.
4. `batch_convert.py` — Reads the generated CSV database, filters songs containing specific criteria (e.g., Pro Guitar or Pro Keys), and converts them in bulk.

---

## Requirements & Dependencies

This toolkit requires **Python 3.7+**.

### Required Python Libraries

Install the required third-party libraries via `pip`:

```bash
pip install mido pyyaml

```

* `mido`: Used by `rb_parser.py` for reading and parsing standard MIDI files.
* `pyyaml`: Used by `rb3_converter.py` to construct and dump `manifest.yaml` files.

---

## Script Descriptions

### `generate_db.py`

Indexes song metadata from `song.ini` files for directories listed in `songlist.txt`.

* Extracts song metadata (Title, Artist, Album, Year, Charter).
* Parses difficulty levels for standard and Pro instruments.
* Detects available audio stems (`.ogg`).
* Exports all collected information to `rb3_songs_db.csv`.

### `rb_parser.py`

The underlying parser module invoked during conversion. It reads `notes.mid` and extracts:

* **Tempo Map & Time Signatures:** Accurately converts MIDI ticks into absolute timestamps (in seconds).
* **Pro Guitar / Pro Bass:** Extracts Expert-level fret/string notes and velocities.
* **Pro Keys:** Converts `PART REAL_KEYS_X` pitch data into staff notation (`notation_keys.json`) and string/fret wire-format data.
* **Pro Drums:** Handles kick, snare, cymbals, and detects active tom markers for yellow/blue/green lanes.
* **Vocals & Lyrics:** Extracts lyric text and vocal note pitch durations.
* **Timeline & Key Signatures:** Maps song sections (`[section ...]` / `[prc_...]`), tempo changes, time signatures, and key signatures.

### `rb3_converter.py`

Translates a single Rock Band 3 song directory into a `.feedpak` file.

* Calls `rb_parser.py` to extract MIDI elements into temporary JSON files.
* Reads metadata from `song.ini` and builds a `manifest.yaml` (Feedpak spec v1.19.0).
* Bundles `.ogg` stems, cover artwork, and generated JSON charts into a compressed `.feedpak` zip package.
* Automatically cleans up temporary disk files afterwards.

### `batch_convert.py`

Automates mass conversions using `rb3_songs_db.csv`.

* Filters songs that feature **Pro Guitar** or **Pro Keys**.
* Checks file paths on disk.
* Includes a `--dry-run` flag to preview matching files before performing any conversion.

---

## Usage Workflow

### 1. Indexing Songs (`generate_db.py`)


1. Run the script:
```bash
python generate_db.py [path_to_songs_directory]

```


*(If `path_to_songs_directory` is omitted, it defaults to the current working directory).*
2. Output: `rb3_songs_db.csv` containing indexed difficulty and metadata.

---

### 2. Single Song Conversion (`rb3_converter.py`)

To convert an individual song folder containing `song.ini` and `notes.mid`:

```bash
python rb3_converter.py /path/to/song_folder /path/to/output_dir

```

**Example:**

```bash
python rb3_converter.py "./songs/Boston - More Than a Feeling" "./converted_feedpaks"

```

---

### 3. Batch Conversion (`batch_convert.py`)

Batch converts all Pro-compatible songs indexed in your CSV file.

#### Step 1: Preview files to convert (Dry Run)

Use the `--dry-run` flag to inspect matching files without writing output files:

```bash
python batch_convert.py rb3_songs_db.csv /path/to/songs_dir /path/to/output_dir --dry-run

```

#### Step 2: Execute Batch Conversion

Run the conversion without `--dry-run`:

```bash
python batch_convert.py rb3_songs_db.csv /path/to/songs_dir /path/to/output_dir

```

---

## MIDI Parsing Details

| MIDI Track Name | Extracted Target | Description |
| --- | --- | --- |
| `PART REAL_GUITAR` | `combo.json` | Expert-tier Pro Guitar notes, strings, and frets. |
| `PART REAL_BASS` | `bass.json` | Expert-tier Pro Bass notes, strings, and frets. |
| `PART REAL_KEYS_X` | `notation_keys.json` / `keys.json` | Expert Real Keys split into staff notation and wire format. |
| `PART DRUMS` | `drum_tab.json` | Kick, snare, and tom-marker aware cymbal/tom hits. |
| `PART VOCALS` / `HARM1` | `lyrics.json` / `vocal_pitch.json` | Word timestamps and pitch durations. |
| `EVENTS` | `song_timeline.json` | Song sections, practice markers, tempos, and time signatures. |
