"""Shared-decision orchestration across similarity, Reddit evidence, logits, and literature."""

from __future__ import annotations

from typing import Protocol

from agentic_health_hackathon.journal_lookup.models import EvidenceSummary, ProblemProfile
from agentic_health_hackathon.shared_decision.logit import LogitCoefficientStore
from agentic_health_hackathon.shared_decision.models import (
    DecisionSupportResult,
    EvidencePosture,
    MissingCapability,
    NeighborTreatmentSignal,
    PatientIntake,
    SafetyPolicy,
    SimilarityResult,
    TreatmentOptionEvidence,
)
from agentic_health_hackathon.shared_decision.stepping import build_step_plan


class SimilarityBackend(Protocol):
    """Controlled-data backend for patient nearest-neighbor lookup."""

    def find_neighbors(self, *, intake: PatientIntake, k: int) -> SimilarityResult:
        """Return nearest neighbors for a mapped patient profile."""


class TreatmentEvidenceBackend(Protocol):
    """Controlled-data backend for nearest-neighbor treatment aggregation."""

    def rank_treatments(
        self,
        *,
        intake: PatientIntake,
        similarity: SimilarityResult,
        limit: int,
    ) -> list[NeighborTreatmentSignal]:
        """Rank treatments reported by nearest-neighbor patients."""


class LiteratureLookupBackend(Protocol):
    """Literature lookup backend, normally JournalLookupService."""

    def lookup(self, profile: ProblemProfile) -> EvidenceSummary:
        """Return a structured literature summary for a profile."""


class SharedDecisionSupportService:
    """Coordinates the product-facing shared-decision evidence layers."""

    def __init__(
        self,
        *,
        similarity_backend: SimilarityBackend | None = None,
        treatment_backend: TreatmentEvidenceBackend | None = None,
        literature_backend: LiteratureLookupBackend | None = None,
        logit_store: LogitCoefficientStore | None = None,
        safety: SafetyPolicy | None = None,
    ) -> None:
        self.similarity_backend = similarity_backend
        self.treatment_backend = treatment_backend
        self.literature_backend = literature_backend
        self.logit_store = logit_store
        self.safety = safety or SafetyPolicy()

    def prepare(
        self,
        intake: PatientIntake,
        *,
        candidate_treatment_groups: list[str] | None = None,
        include_literature: bool = False,
        k: int = 50,
        treatment_limit: int = 10,
    ) -> DecisionSupportResult:
        """Build a shared-decision evidence scaffold for one patient intake."""
        step_plan = build_step_plan(intake)
        missing: list[MissingCapability] = []

        similarity = self._find_neighbors(intake=intake, k=k, missing=missing)
        neighbor_signals = self._rank_neighbor_treatments(
            intake=intake,
            similarity=similarity,
            limit=treatment_limit,
            missing=missing,
        )

        option_groups = _option_groups(
            candidate_treatment_groups=candidate_treatment_groups,
            neighbor_signals=neighbor_signals,
            logit_store=self.logit_store,
        )
        treatment_options = [
            self._build_treatment_option(
                group=group,
                intake=intake,
                neighbor_signals=neighbor_signals,
                include_literature=include_literature,
                missing=missing,
            )
            for group in option_groups
        ]

        if self.logit_store is None:
            missing.append(
                MissingCapability(
                    capability="per-drug-category logit scoring",
                    reason="No coefficient store was provided.",
                    needed_input="cleaned_v2/drug_logit_coefficients.csv",
                )
            )

        return DecisionSupportResult(
            safety=self.safety,
            step_plan=step_plan,
            similarity=similarity,
            treatment_options=treatment_options,
            missing_capabilities=missing,
            next_actions=_next_actions(missing),
        )

    def literature_profile_for_option(
        self,
        *,
        intake: PatientIntake,
        option: TreatmentOptionEvidence,
        max_results: int = 8,
    ) -> ProblemProfile:
        """Create a journal lookup profile for a selected treatment option."""
        concept_slugs = [slug for slug in intake.condition_slugs if slug]
        query_terms = [option.display_name, *intake.symptoms[:3], *(intake.diagnoses[:3])]
        free_text = " ".join(_dedupe(query_terms)).strip()
        return ProblemProfile(
            canonical_concepts=concept_slugs,
            free_text_query=free_text or option.display_name,
            max_results=max_results,
        )

    def _find_neighbors(
        self,
        *,
        intake: PatientIntake,
        k: int,
        missing: list[MissingCapability],
    ) -> SimilarityResult | None:
        if self.similarity_backend is None:
            missing.append(
                MissingCapability(
                    capability="patient nearest-neighbor retrieval",
                    reason="No controlled-data similarity backend was provided.",
                    needed_input="cleaned_v2/model_matrix_controlled.csv",
                )
            )
            return None
        return self.similarity_backend.find_neighbors(intake=intake, k=k)

    def _rank_neighbor_treatments(
        self,
        *,
        intake: PatientIntake,
        similarity: SimilarityResult | None,
        limit: int,
        missing: list[MissingCapability],
    ) -> list[NeighborTreatmentSignal]:
        if similarity is None:
            return []
        if self.treatment_backend is None:
            missing.append(
                MissingCapability(
                    capability="nearest-neighbor treatment ranking",
                    reason="No controlled-data treatment backend was provided.",
                    needed_input="cleaned_v2/drug_sentiment.csv",
                )
            )
            return []
        return self.treatment_backend.rank_treatments(
            intake=intake,
            similarity=similarity,
            limit=limit,
        )

    def _build_treatment_option(
        self,
        *,
        group: str,
        intake: PatientIntake,
        neighbor_signals: list[NeighborTreatmentSignal],
        include_literature: bool,
        missing: list[MissingCapability],
    ) -> TreatmentOptionEvidence:
        signal = _find_signal(group, neighbor_signals)
        logit_estimate = None
        if self.logit_store is not None:
            vector = build_step_plan(intake).feature_vector
            logit_estimate = self.logit_store.score(treatment_group=group, vector=vector)

        display_name = signal.display_name if signal else group
        literature_summary = self._lookup_literature(
            intake=intake,
            display_name=display_name,
            include_literature=include_literature,
            missing=missing,
        )
        caveats = _option_caveats(signal=signal)
        if logit_estimate is not None:
            caveats.extend(logit_estimate.caveats)

        return TreatmentOptionEvidence(
            treatment_slug=group,
            display_name=display_name,
            neighbor_signal=signal,
            logit_estimate=logit_estimate,
            literature_summary=literature_summary,
            literature_query_terms=_dedupe(
                [display_name, *intake.symptoms[:3], *intake.diagnoses[:3]]
            ),
            posture=_posture(
                signal=signal,
                probability=logit_estimate.probability_helped if logit_estimate else None,
            ),
            caveats=list(dict.fromkeys(caveats)),
        )

    def _lookup_literature(
        self,
        *,
        intake: PatientIntake,
        display_name: str,
        include_literature: bool,
        missing: list[MissingCapability],
    ) -> EvidenceSummary | None:
        if not include_literature:
            return None
        if self.literature_backend is None:
            missing.append(
                MissingCapability(
                    capability="journal literature lookup",
                    reason="Literature lookup was requested but no backend was provided.",
                    needed_input="JournalLookupService",
                )
            )
            return None
        profile = ProblemProfile(
            canonical_concepts=[slug for slug in intake.condition_slugs if slug],
            free_text_query=" ".join(
                _dedupe([display_name, *intake.symptoms[:3], *intake.diagnoses[:3]])
            ),
            max_results=8,
        )
        return self.literature_backend.lookup(profile)


def _option_groups(
    *,
    candidate_treatment_groups: list[str] | None,
    neighbor_signals: list[NeighborTreatmentSignal],
    logit_store: LogitCoefficientStore | None,
) -> list[str]:
    groups = list(candidate_treatment_groups or [])
    groups.extend(signal.treatment_slug for signal in neighbor_signals)
    if not groups and logit_store is not None:
        groups.extend(logit_store.available_groups())
    return _dedupe(groups)


def _find_signal(
    group: str,
    signals: list[NeighborTreatmentSignal],
) -> NeighborTreatmentSignal | None:
    for signal in signals:
        if signal.treatment_slug == group or signal.display_name == group:
            return signal
    return None


def _posture(
    signal: NeighborTreatmentSignal | None,
    probability: float | None,
) -> EvidencePosture:
    if signal is None and probability is None:
        return "insufficient_data"
    if signal is not None:
        counts = signal.counts
        if counts.total < 5:
            return "insufficient_data"
        if counts.negative + counts.no_effect > counts.positive:
            return "caution"
    if probability is not None and probability < 0.4:
        return "caution"
    return "discuss"


def _option_caveats(signal: NeighborTreatmentSignal | None) -> list[str]:
    caveats = [
        "Patient-reported treatment evidence is observational and reporting-biased.",
        "Negative and no-effect reports should be weighted more heavily than soft positives.",
    ]
    if signal is None:
        caveats.append("No nearest-neighbor treatment signal is available yet.")
    elif signal.counts.total < 5:
        caveats.append("Small neighbor-report count, so this option should be treated as unstable.")
    return caveats


def _next_actions(missing: list[MissingCapability]) -> list[str]:
    if not missing:
        return ["Validate output wording with clinicians before showing it to patients."]
    return [
        "Wire controlled-data backends for the missing capabilities.",
        "Validate kNN neighbor coherence before ranking treatments in the UI.",
        "Show missing evidence as unavailable rather than filling with speculative claims.",
    ]


def _dedupe(values: list[str]) -> list[str]:
    cleaned = [value.strip() for value in values if value.strip()]
    return list(dict.fromkeys(cleaned))
