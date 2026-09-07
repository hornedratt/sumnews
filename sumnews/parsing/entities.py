"""Named-entity extraction for cross-source dedup, via the natasha library.

`EntityExtractor` loads natasha's segmenter/tagger/embedding models once (they're the expensive
part) and reuses them per article. `dedup.is_duplicate` compares the resulting entity sets.
"""

from natasha import Doc, MorphVocab, NewsEmbedding, NewsMorphTagger, NewsNERTagger, Segmenter


class EntityExtractor:
    def __init__(self) -> None:
        self._segmenter = Segmenter()
        embedding = NewsEmbedding()
        self._morph_tagger = NewsMorphTagger(embedding)
        self._ner_tagger = NewsNERTagger(embedding)
        self._morph_vocab = MorphVocab()

    def extract(self, title: str, text: str) -> list[str]:
        """Return sorted, lemmatized, case-folded PER/LOC/ORG entity names mentioned in the article."""
        doc = Doc(f"{title}\n{text}")
        doc.segment(self._segmenter)
        doc.tag_morph(self._morph_tagger)
        doc.tag_ner(self._ner_tagger)

        names: set[str] = set()
        for span in doc.spans:
            span.normalize(self._morph_vocab)
            names.add(span.normal.casefold())
        return sorted(names)
