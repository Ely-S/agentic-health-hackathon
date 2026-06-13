from __future__ import annotations

import json
import sqlite3
from collections import Counter

from backend.shared_db import DB_PATH, connect_sqlite

from .models import (
    CohortSuggestion,
    KeywordSearchRequest,
    KeywordSearchResponse,
    MetadataResponse,
    PostDetailResponse,
    PractitionerMention,
    RankedPost,
    RankedUser,
    SearchCounts,
    SearchHistoryStep,
    TreatmentSummary,
    UserPostsResponse,
    WeightedTerm,
)


WEIGHT_POINTS = {"low": 1, "medium": 2, "high": 3, "exclude": 0}
HIDDEN_TREATMENTS = {
    "supplement",
    "supplements",
    "medications",
    "medication",
    "medicine",
    "mcas",
    "pots",
    "long covid",
    "covid",
    "postural orthostatic tachycardia syndrome",
    "vaccine",
    "vaccines",
}


def _support_tier(unique_users: int, reports: int) -> str:
    if unique_users >= 30 and reports >= 50:
        return "High support"
    if unique_users >= 10 and reports >= 15:
        return "Medium support"
    if unique_users >= 5:
        return "Low support"
    return "Sparse"


def _sum_expression(parts: list[str]) -> str:
    return " + ".join(parts) if parts else "0"


def _build_scored_posts_cte(
    terms: list[WeightedTerm],
) -> tuple[str, list[str], list[str], str, str, str, int]:
    match_columns: list[str] = []
    include_columns: list[str] = []
    exclude_columns: list[str] = []
    match_expressions: list[str] = []
    params: list[str] = []

    for index, term in enumerate(terms):
        alias = f"term_{index}_match"
        like_value = f"%{term.term.lower()}%"
        params.extend([like_value, like_value, like_value])
        match_columns.append(alias)
        match_expressions.append(
            f"""
            CASE
              WHEN lower(COALESCE(title, '')) LIKE ?
                OR lower(COALESCE(body_text, '')) LIKE ?
                OR lower(COALESCE(flair, '')) LIKE ?
              THEN 1 ELSE 0
            END AS {alias}
            """.strip()
        )
        if term.weight == "exclude":
            exclude_columns.append(alias)
        else:
            include_columns.append(alias)

    cte = f"""
        WITH scored_posts AS (
          SELECT
            post_id,
            user_id,
            COALESCE(title, '') AS title,
            COALESCE(body_text, '') AS body_text,
            COALESCE(flair, '') AS flair,
            COALESCE(post_date, 0) AS post_date,
            {", ".join(match_expressions)}
          FROM posts
          WHERE length(trim(COALESCE(body_text, ''))) > 0
        )
    """
    score_expression = _sum_expression(
        [
            f"{column} * {WEIGHT_POINTS[term.weight]}"
            for column, term in zip(match_columns, terms)
            if term.weight != "exclude"
        ]
    )
    include_match_sum_expression = _sum_expression(include_columns)
    exclude_match_sum_expression = _sum_expression(exclude_columns)
    include_term_count = len(include_columns)
    cohort_condition = (
        f"({include_match_sum_expression}) > 0 AND ({exclude_match_sum_expression}) = 0"
    )
    all_include_condition = (
        f"({include_match_sum_expression}) = {include_term_count} AND ({exclude_match_sum_expression}) = 0"
    )
    return (
        cte,
        params,
        match_columns,
        score_expression,
        include_match_sum_expression,
        cohort_condition,
        all_include_condition,
        include_term_count,
    )


def _count_matches(con: sqlite3.Connection, terms: list[WeightedTerm]) -> SearchCounts:
    cte, params, _, _, _, cohort_condition, all_include_condition, _ = _build_scored_posts_cte(terms)

    counts_row = con.execute(
        f"""
        {cte}
        SELECT
          COUNT(*) AS matched_posts,
          COUNT(DISTINCT user_id) AS matched_users
        FROM scored_posts
        WHERE {cohort_condition}
        """,
        params,
    ).fetchone()

    all_terms_row = con.execute(
        f"""
        {cte}
        SELECT COUNT(*) AS all_terms_posts
        FROM scored_posts
        WHERE {all_include_condition}
        """,
        params,
    ).fetchone()

    return SearchCounts(
        matched_posts=int(counts_row["matched_posts"]),
        matched_users=int(counts_row["matched_users"]),
        all_terms_posts=int(all_terms_row["all_terms_posts"]),
    )


def _build_history(con: sqlite3.Connection, terms: list[WeightedTerm]) -> list[SearchHistoryStep]:
    history: list[SearchHistoryStep] = []
    for index in range(len(terms)):
        prefix_terms = terms[: index + 1]
        cte, params, _, _, _, cohort_condition, all_include_condition, _ = _build_scored_posts_cte(prefix_terms)
        row = con.execute(
            f"""
            {cte}
            SELECT
              SUM(CASE WHEN {cohort_condition} THEN 1 ELSE 0 END) AS any_count,
              SUM(CASE WHEN {all_include_condition} THEN 1 ELSE 0 END) AS all_count
            FROM scored_posts
            """,
            params,
        ).fetchone()
        current = prefix_terms[-1]
        history.append(
            SearchHistoryStep(
                term=current.term,
                weight=current.weight,
                points=WEIGHT_POINTS[current.weight],
                any_count=int(row["any_count"] or 0),
                all_count=int(row["all_count"] or 0),
            )
        )
    return history


def _search_posts(
    con: sqlite3.Connection,
    terms: list[WeightedTerm],
    *,
    limit: int,
    user_id: str | None = None,
) -> list[RankedPost]:
    cte, params, match_columns, score_expression, include_match_sum_expression, cohort_condition, _, _ = _build_scored_posts_cte(terms)
    user_clause = "AND user_id = ?" if user_id is not None else ""
    rows = con.execute(
        f"""
        {cte}
        SELECT
          post_id,
          user_id,
          title,
          body_text,
          flair,
          post_date,
          ({score_expression}) AS score,
          ({include_match_sum_expression}) AS matched_count,
          {", ".join(match_columns)}
        FROM scored_posts
        WHERE {cohort_condition}
          {user_clause}
        ORDER BY score DESC, matched_count DESC, post_date DESC
        LIMIT ?
        """,
        params + ([user_id] if user_id is not None else []) + [limit],
    ).fetchall()

    posts: list[RankedPost] = []
    for row in rows:
        matched_term_details = [
            terms[index] for index, column in enumerate(match_columns) if int(row[column]) == 1
        ]
        body_text = row["body_text"] or ""
        posts.append(
            RankedPost(
                post_id=row["post_id"],
                user_id=row["user_id"],
                title=row["title"] or "",
                excerpt=f"{body_text[:280].strip()}..." if len(body_text) > 280 else body_text,
                flair=row["flair"] or "Unflaird",
                post_date=int(row["post_date"] or 0),
                score=int(row["score"] or 0),
                matched_count=int(row["matched_count"] or 0),
                matched_terms=[term.term for term in matched_term_details],
                matched_term_details=matched_term_details,
            )
        )
    return posts


def _rank_users(
    con: sqlite3.Connection,
    terms: list[WeightedTerm],
    *,
    limit: int = 12,
) -> list[RankedUser]:
    def parse_grouped_terms(payload: str | None) -> list[str]:
        if not payload:
            return []
        terms_seen: set[str] = set()
        terms_out: list[str] = []
        for raw_term in payload.split("|||"):
            normalized = str(raw_term or "").strip()
            if not normalized:
                continue
            key = normalized.lower()
            if key in terms_seen:
                continue
            terms_seen.add(key)
            terms_out.append(normalized)
        return terms_out

    cte, params, _, score_expression, _, cohort_condition, _, _ = _build_scored_posts_cte(terms)
    rows = con.execute(
        f"""
        {cte}
        , user_post_totals AS (
          SELECT
            user_id,
            COUNT(*) AS total_posts,
            MIN(COALESCE(post_date, 0)) AS first_post_date
          FROM posts
          GROUP BY user_id
        ),
        user_treatment_totals AS (
          SELECT
            user_id,
            COUNT(*) AS treatment_reports
          FROM treatment_reports
          GROUP BY user_id
        ),
        user_diagnosis_totals AS (
          SELECT
            user_id,
            COUNT(DISTINCT lower(trim(COALESCE(condition_name, '')))) AS diagnoses
          FROM conditions
          WHERE
            length(trim(COALESCE(condition_name, ''))) > 0
            AND lower(COALESCE(condition_type, '')) = 'illness'
          GROUP BY user_id
        ),
        user_diagnosis_terms AS (
          SELECT
            grouped.user_id AS user_id,
            GROUP_CONCAT(grouped.term, '|||') AS diagnosis_terms
          FROM (
            SELECT DISTINCT
              user_id,
              trim(COALESCE(condition_name, '')) AS term
            FROM conditions
            WHERE
              length(trim(COALESCE(condition_name, ''))) > 0
              AND lower(COALESCE(condition_type, '')) = 'illness'
          ) AS grouped
          GROUP BY grouped.user_id
        ),
        user_treatment_terms AS (
          SELECT
            grouped.user_id AS user_id,
            GROUP_CONCAT(grouped.term, '|||') AS treatment_terms
          FROM (
            SELECT DISTINCT
              tr.user_id AS user_id,
              trim(COALESCE(t.canonical_name, '')) AS term
            FROM treatment_reports tr
            JOIN treatment t ON t.id = tr.drug_id
            WHERE length(trim(COALESCE(t.canonical_name, ''))) > 0
          ) AS grouped
          GROUP BY grouped.user_id
        )
        SELECT
          sp.user_id AS user_id,
          COUNT(*) AS matched_posts,
          SUM({score_expression}) AS total_score,
          AVG({score_expression}) AS avg_score,
          MAX(sp.post_date) AS latest_post_date,
          COALESCE(upt.total_posts, 0) AS total_posts,
          COALESCE(upt.first_post_date, 0) AS first_post_date,
          COALESCE(utt.treatment_reports, 0) AS treatment_reports,
          COALESCE(udt.diagnoses, 0) AS diagnoses,
          COALESCE(udtt.diagnosis_terms, '') AS diagnosis_terms,
          COALESCE(uttt.treatment_terms, '') AS treatment_terms
        FROM scored_posts
        AS sp
        LEFT JOIN user_post_totals upt ON upt.user_id = sp.user_id
        LEFT JOIN user_treatment_totals utt ON utt.user_id = sp.user_id
        LEFT JOIN user_diagnosis_totals udt ON udt.user_id = sp.user_id
        LEFT JOIN user_diagnosis_terms udtt ON udtt.user_id = sp.user_id
        LEFT JOIN user_treatment_terms uttt ON uttt.user_id = sp.user_id
        WHERE {cohort_condition}
        GROUP BY
          sp.user_id,
          upt.total_posts,
          upt.first_post_date,
          utt.treatment_reports,
          udt.diagnoses,
          udtt.diagnosis_terms,
          uttt.treatment_terms
        ORDER BY total_score DESC, matched_posts DESC, latest_post_date DESC
        LIMIT ?
        """,
        params + [limit],
    ).fetchall()

    return [
        RankedUser(
            user_id=row["user_id"],
            matched_posts=int(row["matched_posts"] or 0),
            total_score=int(row["total_score"] or 0),
            avg_score=round(float(row["avg_score"] or 0.0), 1),
            latest_post_date=int(row["latest_post_date"] or 0),
            treatment_reports=int(row["treatment_reports"] or 0),
            diagnoses=int(row["diagnoses"] or 0),
            first_post_date=int(row["first_post_date"] or 0),
            total_posts=int(row["total_posts"] or 0),
            diagnosis_terms=parse_grouped_terms(row["diagnosis_terms"]),
            treatment_terms=parse_grouped_terms(row["treatment_terms"]),
        )
        for row in rows
    ]


def _top_treatments(
    con: sqlite3.Connection,
    terms: list[WeightedTerm],
    *,
    min_users: int,
    limit: int,
) -> list[TreatmentSummary]:
    cte, params, _, _, _, cohort_condition, _, _ = _build_scored_posts_cte(terms)
    rows = con.execute(
        f"""
        {cte},
        matched_users AS (
          SELECT DISTINCT user_id
          FROM scored_posts
          WHERE {cohort_condition}
        )
        SELECT
          t.canonical_name AS name,
          COUNT(*) AS reports,
          COUNT(DISTINCT tr.user_id) AS unique_users,
          SUM(CASE WHEN tr.sentiment = 'positive' THEN 1 ELSE 0 END) AS positive,
          SUM(CASE WHEN tr.sentiment = 'negative' THEN 1 ELSE 0 END) AS negative,
          SUM(CASE WHEN tr.sentiment = 'mixed' THEN 1 ELSE 0 END) AS mixed,
          ROUND(100.0 * SUM(CASE WHEN tr.sentiment = 'positive' THEN 1 ELSE 0 END) / COUNT(*), 0) AS pct_positive,
          (
            1.0 * SUM(
              CASE
                WHEN tr.sentiment = 'positive' AND tr.signal_strength = 'strong' THEN 3
                WHEN tr.sentiment = 'positive' AND tr.signal_strength = 'moderate' THEN 2
                WHEN tr.sentiment = 'positive' THEN 1
                WHEN tr.sentiment = 'negative' AND tr.signal_strength = 'strong' THEN -3
                WHEN tr.sentiment = 'negative' AND tr.signal_strength = 'moderate' THEN -2
                WHEN tr.sentiment = 'negative' THEN -1
                ELSE 0
              END
            ) / COUNT(*)
          ) AS normalized_score,
          GROUP_CONCAT(COALESCE(tr.side_effects, '[]'), '|||') AS side_effect_payload
        FROM treatment_reports tr
        JOIN treatment t ON t.id = tr.drug_id
        JOIN matched_users mu ON mu.user_id = tr.user_id
        GROUP BY t.canonical_name
        HAVING COUNT(DISTINCT tr.user_id) >= ?
        ORDER BY normalized_score DESC, unique_users DESC, reports DESC
        LIMIT ?
        """,
        params + [min_users, limit * 4],
    ).fetchall()

    treatments: list[TreatmentSummary] = []
    for row in rows:
        normalized = (row["name"] or "").strip().lower()
        if not normalized or normalized in HIDDEN_TREATMENTS:
          continue

        side_effects = Counter()
        for payload in (row["side_effect_payload"] or "").split("|||"):
            if not payload:
                continue
            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError:
                parsed = []
            for effect in parsed:
                if effect:
                    side_effects[str(effect)] += 1

        treatments.append(
            TreatmentSummary(
                name=row["name"],
                support=_support_tier(int(row["unique_users"]), int(row["reports"])),
                unique_users=int(row["unique_users"]),
                reports=int(row["reports"]),
                positive=int(row["positive"] or 0),
                negative=int(row["negative"] or 0),
                mixed=int(row["mixed"] or 0),
                pct_positive=int(row["pct_positive"] or 0),
                normalized_score=round(float(row["normalized_score"] or 0.0), 2),
                side_effects=[name for name, _ in side_effects.most_common(3)],
            )
        )
        if len(treatments) >= limit:
            break

    return treatments


def _top_cohort_suggestions(
    con: sqlite3.Connection,
    terms: list[WeightedTerm],
    *,
    limit: int = 6,
) -> list[CohortSuggestion]:
    cte, params, _, _, _, cohort_condition, _, _ = _build_scored_posts_cte(terms)
    excluded_terms = {term.term.strip().lower() for term in terms}
    rows = con.execute(
        f"""
        {cte},
        matched_users AS (
          SELECT DISTINCT user_id
          FROM scored_posts
          WHERE {cohort_condition}
        ),
        cohort_size AS (
          SELECT COUNT(*) AS matched_users
          FROM matched_users
        )
        SELECT
          c.condition_name AS term,
          c.condition_type AS condition_type,
          COUNT(DISTINCT c.user_id) AS matched_users,
          ROUND(100.0 * COUNT(DISTINCT c.user_id) / NULLIF((SELECT matched_users FROM cohort_size), 0), 0) AS pct_users
        FROM conditions c
        JOIN matched_users mu ON mu.user_id = c.user_id
        WHERE length(trim(COALESCE(c.condition_name, ''))) > 0
        GROUP BY c.condition_type, c.condition_name
        ORDER BY matched_users DESC, term ASC
        LIMIT ?
        """,
        params + [limit * 4],
    ).fetchall()

    suggestions: list[CohortSuggestion] = []
    for row in rows:
        normalized = str(row["term"] or "").strip()
        if not normalized or normalized.lower() in excluded_terms:
            continue
        suggestions.append(
            CohortSuggestion(
                term=normalized,
                condition_type=str(row["condition_type"]),
                matched_users=int(row["matched_users"] or 0),
                pct_users=int(row["pct_users"] or 0),
            )
        )
        if len(suggestions) >= limit:
            break

    return suggestions


def _top_practitioners(
    con: sqlite3.Connection,
    terms: list[WeightedTerm],
    *,
    limit: int = 8,
    min_users: int = 2,
) -> list[PractitionerMention]:
    cte, params, _, _, _, cohort_condition, _, _ = _build_scored_posts_cte(terms)
    rows = con.execute(
        f"""
        {cte},
        matched_users AS (
          SELECT DISTINCT user_id
          FROM scored_posts
          WHERE {cohort_condition}
        )
        SELECT
          pm.name,
          COUNT(DISTINCT p.user_id) AS unique_users,
          COUNT(*) AS mention_count
        FROM post_practitioner_mentions pm
        JOIN posts p ON p.post_id = pm.post_id
        JOIN matched_users mu ON mu.user_id = p.user_id
        GROUP BY pm.name
        HAVING COUNT(DISTINCT p.user_id) >= ?
        ORDER BY unique_users DESC, mention_count DESC
        LIMIT ?
        """,
        params + [min_users, limit],
    ).fetchall()

    return [
        PractitionerMention(
            name=row["name"],
            unique_users=int(row["unique_users"]),
            mention_count=int(row["mention_count"]),
        )
        for row in rows
    ]


def keyword_search(request: KeywordSearchRequest) -> KeywordSearchResponse:
    with connect_sqlite(DB_PATH, row_factory=sqlite3.Row) as con:
        counts = _count_matches(con, request.terms)
        history = _build_history(con, request.terms)
        posts = _search_posts(con, request.terms, limit=request.post_limit)
        ranked_users = _rank_users(con, request.terms)
        top_treatments = _top_treatments(
            con,
            request.terms,
            min_users=request.min_treatment_users,
            limit=request.treatment_limit,
        )
        top_cohort_suggestions = _top_cohort_suggestions(con, request.terms)
        top_practitioners = _top_practitioners(con, request.terms)

    return KeywordSearchResponse(
        source=DB_PATH.name,
        query_terms=request.terms,
        counts=counts,
        cohort_history=history,
        posts=posts,
        ranked_users=ranked_users,
        top_treatments=top_treatments,
        top_cohort_suggestions=top_cohort_suggestions,
        top_practitioners=top_practitioners,
    )


def get_post_detail(post_id: str) -> PostDetailResponse | None:
    with connect_sqlite(DB_PATH, row_factory=sqlite3.Row) as con:
        row = con.execute(
            """
            SELECT
              post_id,
              user_id,
              COALESCE(title, '') AS title,
              COALESCE(body_text, '') AS body_text,
              COALESCE(flair, '') AS flair,
              COALESCE(post_date, 0) AS post_date
            FROM posts
            WHERE post_id = ?
            """,
            [post_id],
        ).fetchone()

    if row is None:
        return None

    return PostDetailResponse(
        post_id=row["post_id"],
        user_id=row["user_id"],
        title=row["title"],
        body_text=row["body_text"],
        flair=row["flair"] or "Unflaird",
        post_date=int(row["post_date"] or 0),
    )


def get_user_posts(user_id: str, terms: list[WeightedTerm], *, post_limit: int = 12) -> UserPostsResponse:
    with connect_sqlite(DB_PATH, row_factory=sqlite3.Row) as con:
        posts = _search_posts(con, terms, limit=post_limit, user_id=user_id)

    return UserPostsResponse(user_id=user_id, posts=posts)


def get_metadata() -> MetadataResponse:
    with connect_sqlite(DB_PATH, row_factory=sqlite3.Row) as con:
        post_row = con.execute("SELECT COUNT(*) AS count FROM posts").fetchone()
        treatment_row = con.execute("SELECT COUNT(*) AS count FROM treatment_reports").fetchone()
        user_row = con.execute(
            "SELECT COUNT(DISTINCT user_id) AS count FROM treatment_reports WHERE user_id IS NOT NULL"
        ).fetchone()

    return MetadataResponse(
        source=DB_PATH.name,
        post_count=int(post_row["count"]),
        treatment_report_count=int(treatment_row["count"]),
        treatment_user_count=int(user_row["count"]),
    )
