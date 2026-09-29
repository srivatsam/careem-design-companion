"""Shared Pydantic models: taste profile, perfume cards, and the reply shape every endpoint returns."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Family = Literal["floral", "fresh", "aquatic", "green", "fruity", "gourmand", "woody", "amber"]


class TasteProfile(BaseModel):
    """What we know about the user's taste. Every field optional; lists use master note names / taxonomy keys."""
    liked_notes: list[str] = Field(default_factory=list)
    disliked_notes: list[str] = Field(default_factory=list)
    families: list[str] = Field(default_factory=list)         # taxonomy family keys the user wants
    avoid_families: list[str] = Field(default_factory=list)   # e.g. "not sweet" -> gourmand
    moods: list[str] = Field(default_factory=list)            # taxonomy mood keys
    occasions: list[str] = Field(default_factory=list)
    seasons: list[str] = Field(default_factory=list)
    strength: Optional[int] = Field(default=None, ge=1, le=5)
    budget_aed: Optional[float] = None
    anchor_perfume: Optional[str] = None                      # "a perfume I already love"
    anchor_perfume_id: Optional[str] = None
    anchor_cheaper: bool = False                              # "like X but cheaper"
    brand: Optional[str] = None
    gender: Optional[str] = None                              # women | men | unisex
    guided_for: Optional[str] = None                          # self | gift_her | gift_him | gift_unsure (guided match)
    scenarios: list[str] = Field(default_factory=list)        # scenario ids the shopper pictured (app.data.scenarios)
    moments: list[str] = Field(default_factory=list)          # follow-up moment ids within those scenarios
    free_text: str = ""                                       # accumulated user wording, for semantic matching

    def merge(self, other: "TasteProfile") -> "TasteProfile":
        data = self.model_dump()
        for k, v in other.model_dump().items():
            if isinstance(v, list):
                data[k] = list(dict.fromkeys(data[k] + v))
            elif k == "free_text":
                data[k] = (data[k] + " " + v).strip()
            elif v is not None:
                data[k] = v
        return TasteProfile(**data)

    def signal_count(self) -> int:
        return sum([
            bool(self.liked_notes), bool(self.disliked_notes), bool(self.families), bool(self.avoid_families),
            bool(self.moods), bool(self.occasions), bool(self.seasons), self.strength is not None,
            self.budget_aed is not None, bool(self.anchor_perfume), bool(self.gender),
        ])

    def guided_signal_count(self) -> int:
        """"Strong" taste signals for Guided match's early-recommend rule: deliberately narrower than
        signal_count() -- gender/recipient (picked up from the instant "who is this for?" answer) must never
        count on its own, and an anchor only counts once it actually resolves in the catalogue (anchor_perfume_id),
        not just from a name the shopper typed."""
        return sum([
            bool(self.liked_notes), bool(self.disliked_notes), bool(self.families), bool(self.avoid_families),
            bool(self.moods), bool(self.occasions), self.strength is not None, self.budget_aed is not None,
            bool(self.anchor_perfume_id),
        ])


class NoteGroup(BaseModel):
    top: list[str] = Field(default_factory=list)
    heart: list[str] = Field(default_factory=list)
    base: list[str] = Field(default_factory=list)


class PerfumeCard(BaseModel):
    perfume_id: str
    name: str
    brand: str
    family: str
    family_label: str
    notes: NoteGroup
    key_notes: list[str]
    accords: list[str]
    strength: int
    strength_label: str
    price_aed: Optional[float]
    price_source: str                 # catalogue | estimated | none
    price_label: str                  # "AED 350" or "~AED 350 (est.)"
    image_url: Optional[str] = None
    product_url: Optional[str] = None
    description: str
    reason: Optional[str] = None
    match_score: Optional[int] = None  # 0..100
    rating: Optional[float] = None
    rating_count: Optional[int] = None


class LayeringSuggestion(BaseModel):
    base_perfume_id: str
    partner: PerfumeCard
    reason: str


class Chip(BaseModel):
    id: str      # less_sweet | fresher | cheaper | stronger | lighter | more_like:<perfume_id>
    label: str
    # Optional card fields, sent only with guided match's scenario and moment options (older clients ignore them).
    caption: Optional[str] = None      # one-line sub-caption under the label
    motif: Optional[str] = None        # one of app.data.scenarios.MOTIFS; the widget draws it from a static table
    family: Optional[str] = None       # the scent-family colour key for the card (one of the eight families)


class QuizQuestion(BaseModel):
    id: str      # liked_notes | disliked_notes | mood | strength | budget | guided_for | ...
    question: str
    multi: bool
    options: list[Chip]
    ask_reason: Optional[str] = None   # short "why I'm asking" hint (guided match)
    index: Optional[int] = None        # 1-based question number, guided match only
    max_index: Optional[int] = None    # max questions in this guided run (5)
    topic: Optional[str] = None        # recipient | scenario | scenario_moment | occasion | liked_scents |
                                        # disliked_scents | strength | budget | anchor_feedback | other --
                                        # lets guided match track which
                                        # topics were already asked so a model-authored question never repeats one


class AgentReply(BaseModel):
    session_id: str
    language: str
    reply: str
    picks: list[PerfumeCard] = Field(default_factory=list)
    layering: Optional[LayeringSuggestion] = None
    chips: list[Chip] = Field(default_factory=list)
    next_question: Optional[QuizQuestion] = None
    fallback_used: bool = False
    intent: str = "chat"              # chat | recommend | lookup | wishlist | declined | fallback
    profile: TasteProfile = Field(default_factory=TasteProfile)
    guided: bool = False               # this turn is part of "Guided match"
    profile_summary: list[Chip] = Field(default_factory=list)  # "what I learned" tags shown above the picks
