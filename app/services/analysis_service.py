import re
import json
import csv
from collections import Counter, defaultdict
import os

import text2emotion as te  # type: ignore


def get_speaker_from_line_txt(line):
    """Helper to extract speaker from a single TXT line."""
    speaker_pattern = re.compile(r"^\s*([\w\s.-]+?)\s*[:]\s+", re.IGNORECASE)
    match = speaker_pattern.match(line)
    if match:
        return match.group(1).strip()
    # Fallback for lines that might just be "SpeakerName:text" without strict pattern
    if ":" in line:
        possible_speaker = line.split(":", 1)[0].strip()
        if len(possible_speaker) < 50 and not possible_speaker.isdigit():
            return possible_speaker
    return None


def get_speaker_from_json_item(item):
    """Helper to extract speaker from a JSON message item."""
    if isinstance(item, dict):
        keys_to_check = ["speaker", "user", "author", "name", "user_id"]
        for key in keys_to_check:
            if key in item and item[key]:
                return str(item[key])
    return None


def get_speaker_from_csv_row(row, fieldnames):
    """Helper to extract speaker from a CSV row (dict)."""
    speaker_col_names = ["speaker", "user", "author", "speaker_id", "from", "name"]
    actual_speaker_col = None
    if fieldnames:
        for name_actual in fieldnames:
            for name_potential in speaker_col_names:
                if name_potential.lower() == name_actual.lower():
                    actual_speaker_col = name_actual
                    break
            if actual_speaker_col:
                break

    if actual_speaker_col and actual_speaker_col in row and row[actual_speaker_col]:
        return str(row[actual_speaker_col])

    # Fallback if specific column not found but it's a plain CSV reader row (list)
    if not actual_speaker_col and isinstance(row, list) and row:
        possible_speaker = row[0].strip()
        if (
            len(possible_speaker) < 50
            and not possible_speaker.isdigit()
            and ":" not in possible_speaker
        ):
            return possible_speaker

    # If it's a dict but our named cols weren't found
    # Try the first value if it looks like a speaker (heuristic)
    elif isinstance(row, dict) and not actual_speaker_col:
        if row:
            first_key = list(row.keys())[0]
            possible_speaker = str(row[first_key]).strip()
            if (
                len(possible_speaker) < 50
                and not possible_speaker.isdigit()
                and ":" not in possible_speaker
            ):
                return possible_speaker
    return None


def calculate_interaction_frequency(filepath):
    """
    Calculates interaction frequency between speakers based on turn sequence.
    Returns nodes and links for a force graph.
    """
    interactions = defaultdict(int)
    speakers_in_convo = set()
    last_speaker = None
    filename = os.path.basename(filepath)

    try:
        if filename.endswith(".txt"):
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    current_speaker = get_speaker_from_line_txt(line)
                    if current_speaker:
                        speakers_in_convo.add(current_speaker)
                        if last_speaker and last_speaker != current_speaker:
                            interactions[(last_speaker, current_speaker)] += 1
                        last_speaker = current_speaker

        elif filename.endswith(".json"):
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Assuming data is a list of message objects
                messages = []
                if isinstance(data, list):
                    messages = data
                elif (
                    isinstance(data, dict)
                    and "transcript" in data
                    and isinstance(data["transcript"], list)
                ):
                    messages = data["transcript"]
                elif (
                    isinstance(data, dict)
                    and "log" in data
                    and "messages" in data["log"]
                    and isinstance(data["log"]["messages"], list)
                ):
                    messages = data["log"]["messages"]

                for item in messages:
                    current_speaker = get_speaker_from_json_item(item)
                    if current_speaker:
                        speakers_in_convo.add(current_speaker)
                        if last_speaker and last_speaker != current_speaker:
                            interactions[(last_speaker, current_speaker)] += 1
                        last_speaker = current_speaker

        elif filename.endswith(".csv"):
            with open(filepath, "r", encoding="utf-8", newline="") as f:
                # Try DictReader first
                try:
                    # Need to "peek" at header or reset if we read it once for DictReader
                    # For simplicity, we'll just attempt DictReader. If it fails due to no header,
                    # the plain reader fallback in get_speaker_from_csv_row might catch some.
                    temp_f_for_sniffer = open(
                        filepath, "r", encoding="utf-8", newline=""
                    )
                    has_header = csv.Sniffer().has_header(temp_f_for_sniffer.read(1024))
                    temp_f_for_sniffer.close()
                    f.seek(0)  # Reset file pointer

                    if has_header:
                        reader = csv.DictReader(f)
                        fieldnames = reader.fieldnames
                        for row in reader:
                            current_speaker = get_speaker_from_csv_row(row, fieldnames)
                            if current_speaker:
                                speakers_in_convo.add(current_speaker)
                                if last_speaker and last_speaker != current_speaker:
                                    interactions[(last_speaker, current_speaker)] += 1
                                last_speaker = current_speaker
                    else:  # No header, use plain csv.reader
                        reader = csv.reader(f)
                        for row_list in reader:
                            # Pass the row list and no fieldnames to the helper
                            current_speaker = get_speaker_from_csv_row(row_list, None)
                            if current_speaker:
                                speakers_in_convo.add(current_speaker)
                                if last_speaker and last_speaker != current_speaker:
                                    interactions[(last_speaker, current_speaker)] += 1
                                last_speaker = current_speaker
                except csv.Error as e_csv:  # Sniffer can fail on some CSVs
                    f.seek(0)
                    reader = csv.reader(f)
                    # Skip header if it seems to exist by checking content (heuristic)
                    # For now, assume simple CSV, process all rows
                    # header = next(reader, None)
                    for row_list in reader:
                        current_speaker = get_speaker_from_csv_row(row_list, None)
                        if current_speaker:
                            speakers_in_convo.add(current_speaker)
                            if last_speaker and last_speaker != current_speaker:
                                interactions[(last_speaker, current_speaker)] += 1
                            last_speaker = current_speaker

    except Exception as e:
        print(f"Error calculating interaction frequency for {filepath}: {e}")
        return {"error": f"Could not calculate interaction frequency: {e}"}

    nodes = [{"id": speaker} for speaker in speakers_in_convo]
    links = [
        {"source": source, "target": target, "value": value}
        for (source, target), value in interactions.items()
    ]

    return {"nodes": nodes, "links": links}


def identify_speakers_from_txt(filepath):
    speakers = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                speaker = get_speaker_from_line_txt(line)
                if speaker:
                    speakers.append(speaker)
    except Exception as e:
        print(f"Error reading or parsing TXT file for speaker ID: {e}")
        return Counter()  # Return empty counter on error
    return Counter(speakers)


def identify_speakers_from_json(filepath):
    speakers = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            messages = []
            if isinstance(data, list):
                messages = data
            elif (
                isinstance(data, dict)
                and "transcript" in data
                and isinstance(data["transcript"], list)
            ):
                messages = data["transcript"]
            elif (
                isinstance(data, dict)
                and "log" in data
                and "messages" in data["log"]
                and isinstance(data["log"]["messages"], list)
            ):
                messages = data["log"]["messages"]

            for item in messages:
                speaker = get_speaker_from_json_item(item)
                if speaker:
                    speakers.append(speaker)
    except Exception as e:
        print(f"Error processing JSON file for speaker ID: {e}")
        return Counter()
    return Counter(speakers)


def identify_speakers_from_csv(filepath):
    speakers = []
    try:
        with open(filepath, "r", encoding="utf-8", newline="") as f:
            temp_f_for_sniffer = open(filepath, "r", encoding="utf-8", newline="")
            try:
                # Read more bytes for sniffer
                has_header = csv.Sniffer().has_header(temp_f_for_sniffer.read(2048))

            # Sniffer can fail on perfectly valid CSVs if it's confused
            except csv.Error:
                has_header = True  # Assume header if sniffer fails, common case

            temp_f_for_sniffer.close()
            f.seek(0)

            if has_header:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                if not fieldnames:  # Handle empty CSV or DictReader issue
                    return Counter()
                for row in reader:
                    speaker = get_speaker_from_csv_row(row, fieldnames)
                    if speaker:
                        speakers.append(speaker)
            else:  # No header
                reader = csv.reader(f)
                for row_list in reader:
                    speaker = get_speaker_from_csv_row(row_list, None)
                    if speaker:
                        speakers.append(speaker)
    except Exception as e:
        print(f"Error processing CSV file for speaker ID: {e}")
        return Counter()
    return Counter(speakers)


def extract_speaker_statistics(filepath):
    filename = os.path.basename(filepath)
    if filename.endswith(".txt"):
        speaker_counts = identify_speakers_from_txt(filepath)
    elif filename.endswith(".json"):
        speaker_counts = identify_speakers_from_json(filepath)
    elif filename.endswith(".csv"):
        speaker_counts = identify_speakers_from_csv(filepath)
    else:
        return {"error": "Unsupported file type for speaker statistics"}

    if not speaker_counts:
        return {
            "error": "Could not identify any speakers or file might be empty/misformatted for speakers."
        }

    total_messages = sum(speaker_counts.values())
    speaker_stats = {
        "total_messages": total_messages,
        "speakers_found": list(speaker_counts.keys()),
        "message_count_per_speaker": dict(speaker_counts),
    }
    return speaker_stats


def analyze_emotions_with_text2emotion(text_content_list):
    results = []
    for text in text_content_list:
        if not text or not isinstance(text, str) or text.isspace():
            results.append(
                {"text": text, "emotions": {}, "error": "Empty or invalid input text"}
            )
            continue
        try:
            emotion_scores = te.get_emotion(text)
            results.append({"text": text, "emotions": emotion_scores})
        except Exception as e:
            results.append(
                {
                    "text": text,
                    "emotions": {},
                    "error": f"Error during emotion analysis: {str(e)}",
                }
            )
    return {"emotion_analysis_engine": "text2emotion", "results": results}


def extract_text_from_file(filepath):
    texts = []
    filename = os.path.basename(filepath)
    try:
        if filename.endswith(".txt"):
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line_content = line.strip()
                    if not line_content:
                        continue
                    match = re.match(r"^\s*([\w\s.-]+?)\s*[:]\s*(.*)", line_content)
                    # Ensure text part is not empty
                    if match and match.group(2).strip():
                        texts.append(match.group(2).strip())
                    # No speaker tag, assume whole line is text
                    elif not match and line_content:
                        texts.append(line_content)

        elif filename.endswith(".json"):
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                messages_data = []
                if isinstance(data, list):
                    messages_data = data
                elif (
                    isinstance(data, dict)
                    and "transcript" in data
                    and isinstance(data["transcript"], list)
                ):
                    messages_data = data["transcript"]
                elif (
                    isinstance(data, dict)
                    and "log" in data
                    and "messages" in data["log"]
                    and isinstance(data["log"]["messages"], list)
                ):
                    messages_data = data["log"]["messages"]

                for item in messages_data:
                    if isinstance(item, dict):
                        for key in [
                            "text",
                            "message",
                            "line",
                            "content",
                            "utterance",
                            "msg",
                        ]:
                            if (
                                key in item
                                and isinstance(item[key], str)
                                and item[key].strip()
                            ):
                                texts.append(item[key].strip())
                                break
                        # Watson specific path for some logs
                        if (
                            "response" in item
                            and isinstance(item["response"], dict)
                            and "output" in item["response"]
                            and isinstance(item["response"]["output"], dict)
                            and isinstance(
                                item["response"]["output"].get("generic"), list
                            )
                            and item["response"]["output"]["generic"]
                            and isinstance(
                                item["response"]["output"]["generic"][0], dict
                            )
                            and item["response"]["output"]["generic"][0].get("text")
                        ):
                            texts.append(
                                item["response"]["output"]["generic"][0]["text"].strip()
                            )

        elif filename.endswith(".csv"):
            with open(filepath, "r", encoding="utf-8", newline="") as f:
                temp_f_for_sniffer_text = open(
                    filepath, "r", encoding="utf-8", newline=""
                )
                try:
                    has_header_text = csv.Sniffer().has_header(
                        temp_f_for_sniffer_text.read(2048)
                    )
                except csv.Error:
                    has_header_text = True  # Assume header on sniffer error
                temp_f_for_sniffer_text.close()
                f.seek(0)

                if has_header_text:
                    reader = csv.DictReader(f)
                    text_col_names = [
                        "text",
                        "message",
                        "content",
                        "utterance",
                        "line",
                        "transcript",
                        "msg",
                    ]
                    actual_text_col = None
                    if reader.fieldnames:
                        for name_actual in reader.fieldnames:
                            for name_potential in text_col_names:
                                if name_potential.lower() == name_actual.lower():
                                    actual_text_col = name_actual
                                    break
                            if actual_text_col:
                                break

                    if actual_text_col:
                        for row in reader:
                            if (
                                row.get(actual_text_col)
                                and isinstance(row[actual_text_col], str)
                                and row[actual_text_col].strip()
                            ):
                                texts.append(row[actual_text_col].strip())
                else:  # No header
                    reader = csv.reader(f)
                    for row in reader:
                        # Heuristic: take the first non-empty cell as text, or last if multiple
                        text_candidate = ""
                        if len(row) > 1:
                            text_candidate = row[-1].strip()  # last column often text
                        elif row:
                            text_candidate = row[0].strip()

                        if text_candidate:
                            texts.append(text_candidate)
    except Exception as e:
        print(f"Error extracting text from file {filepath}: {e}")
        return {"error": f"Could not extract text: {e}"}

    return [t for t in texts if t and t.strip()]  # Final filter for empty strings


# --- Persuasion Scoring (v1.0 - Heuristics) ---

ETHOS_LEXICON = [
    # Credibility, Authority, Character
    "expert",
    "expertise",
    "authority",
    "authoritative",
    "credentials",
    "experience",
    "experienced",
    "proven",
    "track record",
    "reliable",
    "trustworthy",
    "honest",
    "integrity",
    "sincere",
    "research shows",
    "studies indicate",
    "according to experts",
    "dr.",
    "professor",
    "we believe",
    "our commitment",
    "our values",
    "ethically",
    "responsible",
]

PATHOS_LEXICON = [
    # Emotions, Values, Stories
    "imagine",
    "feel",
    "feeling",
    "heart",
    "soul",
    "spirit",
    "passion",
    "passionate",
    "hope",
    "dream",
    "aspire",
    "desire",
    "yearn",
    "joy",
    "happy",
    "delight",
    "pleasure",
    "wonderful",
    "amazing",
    "fantastic",
    "miracle",
    "sad",
    "sorrow",
    "pain",
    "suffering",
    "heartbreaking",
    "tragic",
    "unfortunate",
    "fear",
    "afraid",
    "danger",
    "risk",
    "threat",
    "anxiety",
    "worry",
    "anger",
    "outrage",
    "frustration",
    "injustice",
    "unfair",
    "love",
    "compassion",
    "empathy",
    "care",
    "kindness",
    "sympathy",
    "urgent",
    "critical",
    "immediate",
    "now",
    "crisis",
    "must act",
    "story",
    "tale",
    "narrative",
    "journey",
    "vulnerable",
    "struggle",
    "victory",
    "our children",
    "our future",
    "community",
    "family",
    "shared values",
    "common good",
]

LOGOS_LEXICON = [
    # Logic, Reason, Evidence, Data
    "logic",
    "logical",
    "reason",
    "rational",
    "rationale",
    "sound argument",
    "evidence",
    "proof",
    "data",
    "statistics",
    "facts",
    "figures",
    "numbers",
    "chart",
    "graph",
    "analysis",
    "analyze",
    "analytical",
    "study",
    "research",
    "findings",
    "because",
    "therefore",
    "consequently",
    "as a result",
    "thus",
    "hence",
    "ergo",
    "if...then",
    "since",
    "given that",
    "it follows that",
    "clear",
    "clearly",
    "obvious",
    "evidently",
    "plainly",
    "demonstrates",
    "shows",
    "indicates",
    "points to",
    "verifies",
    "confirms",
    "hypothesis",
    "theory",
    "principle",
    "premise",
    "conclusion",
    "compare",
    "contrast",
    "differentiate",
    "classify",
    "organize",
    "systematic",
]


def calculate_persuasion_scores_heuristic(text_content_list):
    """
    Calculates heuristic persuasion scores (ethos, pathos, logos) for a list of texts.
    Each text in the list is an utterance.
    Returns a list of scores, one for each input text.
    """
    results = []

    # Pre-compile regex for faster matching (basic word boundary matching)
    # Using \b for word boundaries for more accuracy
    ethos_patterns = [
        re.compile(r"\b" + re.escape(word) + r"\b", re.IGNORECASE)
        for word in ETHOS_LEXICON
    ]
    pathos_patterns = [
        re.compile(r"\b" + re.escape(word) + r"\b", re.IGNORECASE)
        for word in PATHOS_LEXICON
    ]
    logos_patterns = [
        re.compile(r"\b" + re.escape(word) + r"\b", re.IGNORECASE)
        for word in LOGOS_LEXICON
    ]

    for text in text_content_list:
        if not text or not isinstance(text, str) or text.isspace():
            results.append(
                {
                    "text": text,
                    "ethos_score": 0,
                    "pathos_score": 0,
                    "logos_score": 0,
                    "ethos_matches": [],
                    "pathos_matches": [],
                    "logos_matches": [],
                    "error": "Empty or invalid input text",
                }
            )
            continue

        ethos_score = 0
        pathos_score = 0
        logos_score = 0
        ethos_matches = []
        pathos_matches = []
        logos_matches = []

        # Simple word count based scoring for now
        words_in_text = len(text.split())  # For potential normalization, not used yet

        for pattern in ethos_patterns:
            matches = pattern.findall(text)
            if matches:
                ethos_score += len(matches)
                ethos_matches.extend(matches)
        for pattern in pathos_patterns:
            matches = pattern.findall(text)
            if matches:
                pathos_score += len(matches)
                pathos_matches.extend(matches)
        for pattern in logos_patterns:
            matches = pattern.findall(text)
            if matches:
                logos_score += len(matches)
                logos_matches.extend(matches)

        results.append(
            {
                "text": text,
                "ethos_score": ethos_score,
                "pathos_score": pathos_score,
                "logos_score": logos_score,
                "ethos_matches": list(set(ethos_matches)),  # Unique matches
                "pathos_matches": list(set(pathos_matches)),
                "logos_matches": list(set(logos_matches)),
                # "words_in_text": words_in_text # Optional, if normalization is desired later
            }
        )

    return {"persuasion_analysis_engine": "heuristic_lexicon_v1", "results": results}


# --- Fallacy & Manipulation Detection (v1.0 - Rule-Based) ---

# Keywords/phrases for Ad Hominem (very basic)
AD_HOMINEM_KEYWORDS = [
    "idiot",
    "stupid",
    "moron",
    "ignorant",
    "fool",
    "jerk",
    "loser",
    "naive",
    "you are dumb",
    "you're a joke",
    "he is a liar",
    "she is incompetent",
    "they are clueless",
    "personal attack",  # Explicit mention
]
# More sophisticated Ad Hominem would require NLP to distinguish between general insults and attacks on argument.

# Keywords/phrases for False Dichotomy (very basic)
FALSE_DICHOTOMY_PHRASES = [
    "either...or",  # Needs context, as "either X or Y" can be valid
    "it's either...or...",
    "you are either with us or against us",
    "either you agree or you don't",
    "there are only two types of people",
    "no middle ground",
    "black and white thinking",
]  # This is very heuristic. "either...or" is common and often not a fallacy.

# Keywords for basic Guilt Tripping
GUILT_TRIPPING_KEYWORDS = [
    "if you cared",
    "if you loved me",
    "you would understand if",
    "don't you feel bad",
    "after all I've done for you",
    "I sacrificed so much",
    "you owe me",
    "making me feel guilty",
    "you always make me",  # Accusation of it
]

# Keywords for very basic Gaslighting indicators
GASLIGHTING_KEYWORDS = [
    "you're imagining things",
    "that never happened",
    "you are crazy",
    "you're being irrational",
    "you're too sensitive",
    "don't be so dramatic",
    "I never said that",
    "you're misremembering",
    "it's all in your head",
    "you're making it up",
]


def detect_fallacies_and_manipulation_heuristic(text_content_list):
    """
    Detects basic fallacies and manipulation tactics in a list of texts using heuristics.
    Each text in the list is an utterance.
    Returns a list of detections, one for each input text.
    """
    results = []

    # Pre-compile regex for keywords (case-insensitive, word boundaries)
    ad_hominem_patterns = [
        re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)
        for kw in AD_HOMINEM_KEYWORDS
    ]
    # For phrases, we might need more direct string searching or more complex regex if they vary
    # False dichotomy is harder with simple keywords due to "either...or" being common.
    # We'll do simple phrase checking for it.

    guilt_tripping_patterns = [
        re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)
        for kw in GUILT_TRIPPING_KEYWORDS
    ]
    gaslighting_patterns = [
        re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)
        for kw in GASLIGHTING_KEYWORDS
    ]

    for text in text_content_list:
        if not text or not isinstance(text, str) or text.isspace():
            results.append(
                {
                    "text": text,
                    "detected_fallacies": [],
                    "detected_manipulations": [],
                    "error": "Empty or invalid input text",
                }
            )
            continue

        detected_fallacies = []
        detected_manipulations = []
        text_lower = text.lower()  # For phrase searching

        # Ad Hominem
        for pattern in ad_hominem_patterns:
            matches = pattern.findall(text)
            if matches:
                detected_fallacies.append(
                    {"type": "Ad Hominem", "keywords_matched": list(set(matches))}
                )
                break  # Count first type of fallacy match for simplicity in this version

        # False Dichotomy (simple phrase check)
        for phrase in FALSE_DICHOTOMY_PHRASES:
            if phrase.lower() in text_lower:  # Simple substring check for phrases
                # Check for "either...or" with a bit more context if possible (very basic)
                if phrase == "either...or":
                    if (
                        "either " in text_lower
                        and " or " in text_lower.split("either ")[-1]
                    ):
                        detected_fallacies.append(
                            {"type": "False Dichotomy", "phrase_matched": phrase}
                        )
                        break
                else:
                    detected_fallacies.append(
                        {"type": "False Dichotomy", "phrase_matched": phrase}
                    )
                    break

        # Guilt Tripping
        for pattern in guilt_tripping_patterns:
            matches = pattern.findall(text)
            if matches:
                detected_manipulations.append(
                    {"type": "Guilt Tripping", "keywords_matched": list(set(matches))}
                )
                break

        # Gaslighting
        for pattern in gaslighting_patterns:
            matches = pattern.findall(text)
            if matches:
                detected_manipulations.append(
                    {
                        "type": "Gaslighting (potential)",
                        "keywords_matched": list(set(matches)),
                    }
                )
                break

        # Remove duplicates if a text triggers same type multiple ways (though break prevents this for now)
        # Example: unique_fallacies = [dict(t) for t in {tuple(d.items()) for d in detected_fallacies}]

        results.append(
            {
                "text": text,
                "detected_fallacies": detected_fallacies,
                "detected_manipulations": detected_manipulations,
            }
        )

    return {"tactic_detection_engine": "heuristic_lexicon_v1", "results": results}
