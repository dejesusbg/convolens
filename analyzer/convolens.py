import json
import re
from typing import List, Dict, Any
from collections import defaultdict, Counter
import math
from textblob import TextBlob
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)


class ConversationAnalyzer:
    def __init__(self):
        # Common logical fallacies patterns
        self.fallacy_patterns = {
            "ad_hominem": [
                r"\b(you are|you\'re)\s+(stupid|dumb|idiot|moron)",
                r"\bthat\'s\s+because\s+you\b",
                r"\bwhat\s+do\s+you\s+know\b",
                r"\byou\s+always\b",
                r"\byou\s+never\b",
            ],
            "straw_man": [
                r"\bso\s+you\'re\s+saying\b",
                r"\bwhat\s+you\'re\s+really\s+saying\b",
                r"\byou\s+think\s+that\b.*\bis\s+okay\b",
            ],
            "false_dichotomy": [
                r"\beither\s+.*\s+or\s+.*\b",
                r"\bif\s+not\s+.*\s+then\s+.*\b",
                r"\byou\'re\s+either\s+.*\s+or\s+.*\b",
            ],
            "appeal_to_emotion": [
                r"\bthink\s+of\s+the\s+children\b",
                r"\bhow\s+can\s+you\s+.*\s+when\b",
                r"\bimagine\s+if\s+.*\s+happened\s+to\s+you\b",
            ],
            "bandwagon": [
                r"\beveryone\s+(knows|agrees|thinks)\b",
                r"\bmost\s+people\s+(believe|think|agree)\b",
                r"\ball\s+the\s+experts\s+say\b",
            ],
        }

        # Persuasion indicators
        self.persuasion_indicators = {
            "emotional_appeal": [
                r"\bfeel|feeling|felt\b",
                r"\bheart\b",
                r"\blove|hate\b",
                r"\bfear|afraid|scared\b",
                r"\bangry|mad|furious\b",
            ],
            "authority": [
                r"\bexpert|specialist|professional\b",
                r"\bstudies?\s+show\b",
                r"\bresearch\s+(shows|indicates|proves)\b",
                r"\baccording\s+to\b",
            ],
            "logic": [
                r"\btherefore\b",
                r"\bbecause\b",
                r"\bsince\b",
                r"\bthus\b",
                r"\bconsequently\b",
                r"\bas\s+a\s+result\b",
            ],
            "social_proof": [
                r"\bpeople\s+(are|do|think|believe)\b",
                r"\btrend\b",
                r"\bpopular\b",
                r"\bmajority\b",
            ],
        }

        # Manipulation tactics
        self.manipulation_patterns = {
            "gaslighting": [
                r"\byou\'re\s+(overreacting|being\s+dramatic)\b",
                r"\bthat\s+never\s+happened\b",
                r"\byou\'re\s+(imagining|misremembering)\b",
            ],
            "guilt_tripping": [
                r"\bafter\s+all\s+i\'ve\s+done\b",
                r"\bi\s+thought\s+you\s+cared\b",
                r"\byou\s+never\s+.*\s+anymore\b",
            ],
            "intimidation": [
                r"\byou\'ll\s+regret\b",
                r"\bor\s+else\b",
                r"\byou\s+don\'t\s+want\s+to\s+.*\s+me\b",
            ],
        }

    def analyze_conversation(self, conversation_data: List[Dict]) -> Dict[str, Any]:
        """Main analysis function"""
        results = {
            "overview": self._get_overview(conversation_data),
            "influence_scores": self._calculate_influence_scores(conversation_data),
            "fallacies": self._detect_fallacies(conversation_data),
            "emotions": self._analyze_emotions(conversation_data),
            "manipulation": self._detect_manipulation(conversation_data),
            "persuasion_tactics": self._analyze_persuasion_tactics(conversation_data),
        }
        return results

    def _get_overview(self, data: List[Dict]) -> Dict[str, Any]:
        """Generate overview statistics"""
        speakers = set(msg["speaker"] for msg in data)
        total_messages = len(data)

        # Count total fallacies
        fallacies = self._detect_fallacies(data)
        total_fallacies = sum(f["count"] for f in fallacies.values())

        # Calculate average influence
        influence_scores = self._calculate_influence_scores(data)
        avg_influence = (
            sum(s["score"] for s in influence_scores) / len(influence_scores)
            if influence_scores
            else 0
        )

        return {
            "total_speakers": len(speakers),
            "total_messages": total_messages,
            "total_fallacies": total_fallacies,
            "avg_influence": avg_influence * 100,
        }

    def _calculate_influence_scores(self, data: List[Dict]) -> List[Dict]:
        """Calculate influence score for each speaker"""
        speaker_data = defaultdict(list)
        for msg in data:
            speaker_data[msg["speaker"]].append(msg["message"])

        influence_scores = []

        for speaker, messages in speaker_data.items():
            score = 0
            tactics = []

            for message in messages:
                message_lower = message.lower()

                # Check for persuasion tactics
                for tactic, patterns in self.persuasion_indicators.items():
                    for pattern in patterns:
                        if re.search(pattern, message_lower):
                            score += 0.1
                            if tactic not in tactics:
                                tactics.append(tactic)

                # Message length and complexity
                words = len(message.split())
                if words > 20:
                    score += 0.05

                # Sentiment strength
                blob = TextBlob(message)
                sentiment_strength = abs(blob.sentiment.polarity)
                score += sentiment_strength * 0.2

                # Question asking (engagement)
                if "?" in message:
                    score += 0.1

            # Normalize score
            max_possible_score = len(messages) * 0.5
            normalized_score = (
                min(score / max_possible_score, 1.0) if max_possible_score > 0 else 0
            )

            influence_scores.append(
                {
                    "speaker": speaker,
                    "score": normalized_score,
                    "tactics": tactics,
                    "message_count": len(messages),
                }
            )

        return sorted(influence_scores, key=lambda x: x["score"], reverse=True)

    def _detect_fallacies(self, data: List[Dict]) -> Dict[str, Dict]:
        """Detect logical fallacies in messages"""
        fallacies = defaultdict(lambda: {"count": 0, "examples": []})

        for msg in data:
            message_lower = msg["message"].lower()

            for fallacy_type, patterns in self.fallacy_patterns.items():
                for pattern in patterns:
                    if re.search(pattern, message_lower):
                        fallacies[fallacy_type]["count"] += 1
                        if len(fallacies[fallacy_type]["examples"]) < 3:
                            fallacies[fallacy_type]["examples"].append(msg["message"])

        return dict(fallacies)

    def _analyze_emotions(self, data: List[Dict]) -> Dict[str, Dict]:
        """Analyze emotional tone of each speaker"""
        speaker_emotions = defaultdict(list)

        for msg in data:
            blob = TextBlob(msg["message"])
            emotion_score = {
                "positive": max(0, blob.sentiment.polarity),
                "negative": max(0, -blob.sentiment.polarity),
                "neutral": 1 - abs(blob.sentiment.polarity),
            }
            speaker_emotions[msg["speaker"]].append(emotion_score)

        # Average emotions per speaker
        result = {}
        for speaker, emotions in speaker_emotions.items():
            avg_emotions = {
                "positive": sum(e["positive"] for e in emotions) / len(emotions),
                "negative": sum(e["negative"] for e in emotions) / len(emotions),
                "neutral": sum(e["neutral"] for e in emotions) / len(emotions),
            }
            result[speaker] = avg_emotions

        return result

    def _detect_manipulation(self, data: List[Dict]) -> Dict[str, Dict]:
        """Detect manipulation tactics"""
        manipulation = defaultdict(lambda: {"count": 0, "examples": []})

        for msg in data:
            message_lower = msg["message"].lower()

            for tactic_type, patterns in self.manipulation_patterns.items():
                for pattern in patterns:
                    if re.search(pattern, message_lower):
                        manipulation[tactic_type]["count"] += 1
                        if len(manipulation[tactic_type]["examples"]) < 3:
                            manipulation[tactic_type]["examples"].append(msg["message"])

        return dict(manipulation)

    def _analyze_persuasion_tactics(self, data: List[Dict]) -> Dict[str, Any]:
        """Analyze persuasion tactics used"""
        tactic_usage = defaultdict(int)
        speaker_tactics = defaultdict(set)

        for msg in data:
            message_lower = msg["message"].lower()
            speaker = msg["speaker"]

            for tactic, patterns in self.persuasion_indicators.items():
                for pattern in patterns:
                    if re.search(pattern, message_lower):
                        tactic_usage[tactic] += 1
                        speaker_tactics[speaker].add(tactic)

        return {
            "tactic_frequency": dict(tactic_usage),
            "speaker_tactics": {k: list(v) for k, v in speaker_tactics.items()},
        }
