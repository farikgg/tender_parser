from app.core.models import ClassifiedTender, RawTender

INSURANCE_KEYWORDS = (
    "страхование", "страховой", "страховая", "страхования", "страхованию",
    "страхователь", "страховщик", "страхового", "страховым",
    "полис", "полиса", "полису",
    "ОСГПО", "ОГПО", "КАСКО", "ОСАГО",
    "медицинское страхование", "медстрахование",
    "аннуитет", "перестрахование",
    "қамсыздандыру",
)

class ClassifierService:
    """Определяет, является ли тендер связанным со страхованием."""
    def __init__(self, keywords: tuple[str, ...] = INSURANCE_KEYWORDS) -> None:
        self._keywords_lower = tuple(keyword.lower() for keyword in keywords)
        self._keywords_original = keywords

    def classify(self, raw_tender: RawTender) -> ClassifiedTender:
        tender_parts = [raw_tender.title]

        if raw_tender.description:
            tender_parts.append(raw_tender.description)

        tender = " ".join(tender_parts).lower()

        matched = [
            original
            for original, lower in zip(self._keywords_original, self._keywords_lower)
            if lower in tender
        ]

        return ClassifiedTender(
            raw=raw_tender,
            is_insurance=bool(matched),
            matched_keywords=matched,
        )
