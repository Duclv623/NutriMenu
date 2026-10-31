import re
import unicodedata

import numpy as np
from rank_bm25 import BM25Okapi

from rag_app.domain import Hit
from rag_app.store import Store

STOPWORDS = set(
    "toi ban minh la va cua co cho thi voi duoc nen nhu nao gi nhung cac mot ve trong khi hay khong the nay ay lam sao bao nhieu nguoi benh tieu duong dai thao duong".split()
)


def fold(text: str) -> str:
    text = text.lower().replace("đ", "d")
    return "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c))


def tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", fold(text))
    unigrams = [w for w in words if w not in STOPWORDS]
    bigrams = [
        a + "_" + b
        for a, b in zip(words, words[1:], strict=False)
        if a not in STOPWORDS or b not in STOPWORDS
    ]
    return unigrams + bigrams


def is_noodle_meal_advice(query: str) -> bool:
    q = fold(query)
    return bool(
        re.search(r'\b(?:an|bua sang|sang)\b.*\b(?:pho|bun|(?<!banh )mi|mien|hu tieu)\b', q)
        and not re.search(r'\b(?:so sanh|nhanh hon|chi so duong huyet|calo|kcal|thanh phan|thuc don|bang)\b', q)
        and not re.search(r'\bGI\b', query)
    )


def expand_query(query: str) -> str:
    terms = {
        "carb": "glucid carbohydrate chất bột đường",
        "calo": "năng lượng kcal",
        "đạm": "protein protid",
        "tiểu đường": "đái tháo đường",
        "ăn vặt": "bữa phụ",
        "mỡ": "lipid chất béo",
        "chất xơ": "rau ngũ cốc",
        "không thêm đường": "no added sugar",
        "không đường": "sugar free sugar substitutes moderation",
        "zero sugar": "sugar free sugar substitutes moderation",
        "đường ăn kiêng": "sugar substitutes sugar alcohols",
        "chất tạo ngọt": "sugar substitutes sugar alcohols",
        "polyol": "sugar alcohols",
        "đọc nhãn": "food labels serving size total carbs added sugars",
        "khẩu phần": "serving size servings per container",
        "ngũ cốc": "cereals whole grain fiber added sugar",
        "nêm": "seasoning herbs spices sodium",
        "sữa chua": "yogurt dairy carbohydrates",
        "sữa không đường": "unsweetened dairy carbohydrates nutrition facts label",
    }
    expanded = query + " " + " ".join(v for k, v in terms.items() if fold(k) in fold(query))
    if re.search(r'\b(?:an|bua sang|sang)\b.*\b(?:pho|bun|mi|mien|hu tieu)\b', fold(query)):
        # Everyday dish questions still need meal/portion principles when the
        # approved sources cannot prescribe a particular bowl of that dish.
        expanded += " meal planning portion size eating out carbohydrate"
        if is_noodle_meal_advice(query):
            expanded += " noodle dishes less noodles more vegetables clear soup lean meat"
    return expanded


class Retriever:
    def __init__(self, store: Store):
        self.chunks, self.vectors, self.metadata = store.load_index()
        self.bm25 = (
            BM25Okapi([tokens(c.section + "\n" + c.text) for c in self.chunks])
            if self.chunks
            else None
        )

    def search(
        self,
        query: str,
        top_k: int = 5,
        query_vector=None,
        min_dense: float = 0.3,
        mode: str = "hybrid",
    ) -> list[Hit]:
        if not self.chunks or not tokens(query):
            return []
        lexical_query = fold(expand_query(query))
        # Source names constrain the source, but should not outrank the actual
        # topic through repeated boilerplate words such as 'dinh dưỡng'.
        lexical_query = re.sub(r"\b(?:benh vien noi tiet(?: trung uong)?|vien dinh duong|bo y te|niddk|qd 5481|5481)\b", " ", lexical_query)
        lexical = np.asarray(self.bm25.get_scores(tokens(lexical_query)), dtype=float)
        named = []
        query_folded = fold(query)
        for source, aliases in {
            "byt5481-nutrition": ("bo y te", "5481"),
            "nin-healthy-meals": ("vien dinh duong",),
            "endocrine-diet": ("benh vien noi tiet",),
            "niddk-healthy-living": ("niddk",),
            "vtn-fct-2007": ("2007", "fct", "bang thanh phan"),
        }.items():
            if any(alias in query_folded for alias in aliases):
                named.append(source)
        allowed = {i for i, c in enumerate(self.chunks) if not named or c.source_id in named
                   or 'nin-healthy-meals' in named and (c.source_id.startswith('nin-') or 'dinh duong' in fold(c.title))}
        # Requested intake quantities need portion evidence; a plate-area diagram
        # cannot determine how much of a named mixed dish somebody should eat.
        from rag_app.safety import is_intake_quantity_request
        current_question = query.rsplit('\nCâu hỏi tiếp: ', 1)[-1]
        if is_intake_quantity_request(current_question) and not re.search(r'\bdia\b|\bplate\b', query_folded):
            allowed = {i for i in allowed if not re.search(
                r'phuong phap dia|the plate method|chia dia', fold(self.chunks[i].section))}
        if named == ['nin-healthy-meals']:
            allowed={i for i,c in enumerate(self.chunks) if c.source_id.startswith('nin-')}
        # Snack-specific evidence cannot decide a breakfast/general-food query.
        snack_question = re.search(r"\b(?:bua phu|an vat|giua (?:cac )?bua|ha duong huyet|truoc khi (?:di )?ngu)\b", fold(expand_query(query)))
        if not snack_question:
            allowed = {i for i in allowed if 'b) su dung bua phu' not in fold(self.chunks[i].section)}
        # A sugar claim on a food label asks how to account for that food,
        # not whether insulin users should start counting carbohydrates.
        label_carb_question = (
            re.search(r'\b(?:tinh|dem)\b.*\b(?:carb|carbohydrate)\b', query_folded)
            and re.search(r'\b(?:khong duong|khong them duong|zero sugar|nhan)\b', query_folded)
            and 'insulin' not in query_folded
        )
        if label_carb_question:
            allowed = {i for i in allowed if not (
                re.search(r'\bdem (?:luong )?(?:carbohydrate|carb)\b', fold(self.chunks[i].section))
                and 'insulin' in fold(self.chunks[i].text)
            )}
        table_request = re.search(r"\b(?:bang|thuc don|tham khao|mau|thu [2-7]|chu nhat)\b", query_folded)
        meal_slot = re.search(r"\b(?:bua|buoi) (?:sang|trua|toi)\b", query_folded)
        suitability = re.search(r"\b(?:an|uong)\b.*\b(?:duoc (?:khong|ko)|nhu the nao|the nao|co on)\b", query_folded)
        if meal_slot and not suitability:
            table_request = True
        # Naming breakfast while asking suitability is not a request for a
        # sample menu. Menu quantities cannot establish personal suitability.
        if not table_request:
            # A sample menu lists foods but does not prove their biochemical
            # classification or recommendations. Keep it for explicit table asks.
            allowed = {i for i in allowed if not any(loc.startswith('t') for loc in self.chunks[i].locators)}
        # Explicit narrow subjects should retain their own evidence, rather than
        # generic energy paragraphs that share many words with the follow-up.
        subjects = [term for term in ("bua phu", "can bang nang luong", "can nang ly tuong") if term in query_folded]
        if subjects:
            matching = {i for i in allowed if any(term in fold(self.chunks[i].text) for term in subjects)}
            if matching:
                allowed = matching
        # A request naming a subsection needs evidence from that subsection.
        # This preserves distinctions when overview and detail give different ranges.
        heading = re.search(r"\bmuc (chat beo|nang luong|chat dam|glucid|protein|protid|lipid|chat xo)\b", query_folded)
        if heading:
            label = heading.group(1)
            aliases = {"lipid": "chat beo", "protein": "chat dam", "protid": "chat dam"}
            matching = {i for i in allowed if aliases.get(label, label) in fold(self.chunks[i].section)}
            if matching:
                allowed = matching
        dense = None
        if query_vector is not None and self.vectors is not None:
            q = np.asarray(query_vector, dtype=np.float32)
            if q.ndim != 1 or len(q) != self.vectors.shape[1] or not np.isfinite(q).all():
                raise ValueError("Embedding model/dimension mismatch; cần index lại")
            norms = np.maximum(np.linalg.norm(self.vectors, axis=1) * np.linalg.norm(q), 1e-10)
            dense = (self.vectors @ q) / norms
        ranks = []
        if mode != "dense":
            ranks.append([int(i) for i in np.argsort(-lexical) if i in allowed and lexical[i] > 0])
        if dense is not None and mode != "lexical":
            ranks.append([int(i) for i in np.argsort(-dense) if i in allowed and dense[i] >= min_dense])
        scores: dict[int, float] = {}
        for ranked in ranks:
            for rank, i in enumerate(ranked[:30], start=1):
                scores[i] = scores.get(i, 0) + 1 / (60 + rank)
        selected = sorted(scores, key=lambda i: (-scores[i], self.chunks[i].id))[:top_k]
        if len(named) > 1:
            representatives = []
            for source in named:
                candidates = [i for i in allowed if self.chunks[i].source_id == source and lexical[i] > 0]
                if candidates:
                    representative = max(candidates, key=lambda i: scores.get(i, 0) + lexical[i] * 0.000001)
                    representatives.append(representative)
            selected = list(dict.fromkeys(representatives + selected))[:top_k]
        # RRF can crowd out the strongest keyword match when broad dense matches
        # also have modest lexical scores. Keep one slot for that direct evidence.
        if mode == "hybrid" and dense is not None and ranks and ranks[0]:
            best_lexical = ranks[0][0]
            if best_lexical not in selected:
                selected = selected[: max(0, top_k - 1)] + [best_lexical]
        # Preserve component-level ordering advice alongside generic portion
        # evidence. Vietnamese wording can otherwise crowd out the English
        # noodle-specific excerpt in both lexical and hybrid retrieval.
        if is_noodle_meal_advice(query):
            practical = [i for i in allowed if self.chunks[i].source_id == 'singhealth-noodle-choices']
            if practical:
                representative = max(practical, key=lambda i: lexical[i])
                if representative not in selected:
                    selected = selected[:max(0, top_k - 1)] + [representative]
        # Keep a source's explicitly linked qualification with its definition.
        # Example: "no added sugar" needs the same handout's moderation caveat.
        # Never use arbitrary neighbouring chunks or cross-source assumptions.
        companions = []
        for i in selected:
            chunk = self.chunks[i]
            for j in allowed:
                other = self.chunks[j]
                related = (other.source_id == chunk.source_id and other.section in chunk.related_sections
                           or f'{other.source_id}::{other.section}' in chunk.related_sections)
                if (related
                        and j not in selected and j not in companions):
                    companions.append(j)
        protected = {i for i in selected if self.chunks[i].related_sections}
        if len(named) > 1:
            protected.update(selected[:min(len(named), top_k)])
        if ranks and ranks[0]:
            protected.add(ranks[0][0])
        for j in companions[:max(0, top_k - 1)]:
            if len(selected) >= top_k:
                removable = [i for i in reversed(selected) if i not in protected]
                if not removable:
                    break
                selected.remove(removable[0])
            selected.insert(1, j)
            protected.add(j)
        return [
            Hit(
                chunk=self.chunks[i],
                score=scores.get(i, 0),
                lexical_score=float(lexical[i]),
                dense_score=None if dense is None else float(dense[i]),
            )
            for i in selected
        ]
