from app.services.analysis_service import (
    extract_speaker_statistics,
    calculate_persuasion_scores_heuristic,
)
import os
import tempfile


# Example test for a service function
def test_extract_speaker_statistics_txt():
    # Create a temporary TXT file with test content
    test_content = (
        "Speaker A: Hello world\nSpeaker B: Hi there\nSpeaker A: How are you?"
    )
    # tempfile.NamedTemporaryFile needs delete=False on Windows to be reopened by another process/function
    # For same-process reading, this is fine.
    with tempfile.NamedTemporaryFile(
        mode="w", delete=False, suffix=".txt", encoding="utf-8"
    ) as tmp_file:
        tmp_file.write(test_content)
        tmp_filepath = tmp_file.name

    stats = extract_speaker_statistics(tmp_filepath)

    assert "error" not in stats
    assert stats["total_messages"] == 3
    assert len(stats["speakers_found"]) == 2
    assert "Speaker A" in stats["speakers_found"]
    assert "Speaker B" in stats["speakers_found"]
    assert stats["message_count_per_speaker"]["Speaker A"] == 2
    assert stats["message_count_per_speaker"]["Speaker B"] == 1

    os.unlink(tmp_filepath)  # Clean up the temp file


def test_persuasion_scoring_basic():
    texts = [
        "This is a logical argument because of the evidence.",  # Logos
        "I feel this is a passionate plea for our children.",  # Pathos
        "As an expert, I believe this is trustworthy.",  # Ethos
    ]
    results_data = calculate_persuasion_scores_heuristic(texts)
    results = results_data["results"]

    assert len(results) == 3

    # Check first text for logos
    assert results[0]["logos_score"] > 0
    assert results[0]["pathos_score"] == 0
    assert results[0]["ethos_score"] == 0
    assert (
        "logical" in results[0]["logos_matches"]
        or "evidence" in results[0]["logos_matches"]
    )

    # Check second text for pathos
    assert results[1]["logos_score"] == 0
    assert results[1]["pathos_score"] > 0
    assert results[1]["ethos_score"] == 0
    assert (
        "passionate" in results[1]["pathos_matches"]
        or "children" in results[1]["pathos_matches"]
    )

    # Check third text for ethos
    assert results[2]["logos_score"] == 0
    assert results[2]["pathos_score"] == 0
    assert results[2]["ethos_score"] > 0
    assert (
        "expert" in results[2]["ethos_matches"]
        or "trustworthy" in results[2]["ethos_matches"]
    )


def test_persuasion_scoring_empty_input():
    texts = [""]
    results_data = calculate_persuasion_scores_heuristic(texts)
    results = results_data["results"]
    assert len(results) == 1
    assert "error" in results[0]
    assert results[0]["ethos_score"] == 0
