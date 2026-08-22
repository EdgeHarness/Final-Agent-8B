"""Persistent memory ("learning") store.

Facts persist across episodes in a JSONL file. Retrieval is simple keyword
overlap - deliberately cheap so it runs identically for every model size.
The harness condition auto-injects relevant memories into the system prompt;
the raw condition only sees memories if the model calls recall_memories itself.
"""
import json
import os
import re

_WORD = re.compile(r"[a-z0-9]+")
_STOP = {"the", "a", "an", "to", "of", "and", "or", "for", "with", "my", "me",
         "i", "is", "are", "in", "on", "at", "it", "that", "this", "be", "do"}


def _tokens(text):
    return {w for w in _WORD.findall(text.lower()) if w not in _STOP}


def _overlap(query_tokens, fact_tokens):
    """Count shared tokens, treating one as a prefix of the other from four
    characters up.

    Exact set intersection missed the product's own example: "Remember that I
    prefer meetings after 14:00" saved as a fact, then a later task mentioning
    "meeting preferences", shares no token at all - meeting/meetings and
    prefer/prefers are different strings. A prefix match is the cheapest thing
    that catches English plurals and verb endings without a stemmer, and it
    stays deterministic across model sizes, which is why this file is
    keyword-based in the first place.
    """
    score = 0
    for q in query_tokens:
        for f in fact_tokens:
            if q == f or (len(q) >= 4 and len(f) >= 4
                          and (q.startswith(f) or f.startswith(q))):
                score += 1
                break
    return score


class MemoryStore:
    def __init__(self, path):
        self.path = path
        self.facts = []
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    # The agent appends to this file mid-run, so a crash or a
                    # full disk leaves a half-written last line. Refusing to
                    # parse it used to raise here, which meant one torn line
                    # made the agent folder unopenable for every future run -
                    # the whole memory lost to recover one record. Skip what
                    # cannot be read and keep the rest. (webui/server.py's
                    # reader has always done this; the harness had not.)
                    try:
                        fact = json.loads(line)["fact"]
                    except (ValueError, KeyError, TypeError):
                        continue
                    if fact not in self.facts:
                        self.facts.append(fact)

    def save(self, fact):
        fact = str(fact).strip()
        if not fact:
            return "nothing to save"
        # Only memory_k facts (3 or 4) reach the system prompt. A model that
        # re-saves the same preference every run would spend all of those slots
        # on one fact and crowd out everything else it knows.
        if fact in self.facts:
            return f"already in long-term memory: {fact}"
        self.facts.append(fact)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"fact": fact}, ensure_ascii=False) + "\n")
        return f"saved to long-term memory: {fact}"

    def search(self, query, k=3):
        q = _tokens(str(query))
        scored = []
        for fact in self.facts:
            overlap = _overlap(q, _tokens(fact))
            if overlap:
                scored.append((overlap, fact))
        scored.sort(key=lambda t: -t[0])
        return [fact for _, fact in scored[:k]]

    def all(self):
        return list(self.facts)
