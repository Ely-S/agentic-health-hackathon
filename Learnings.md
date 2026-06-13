# Learnings

## 1. The Product Thesis Is Real, But It Depends on Transparency

The strongest validated idea is not “recommend treatments,” but “show what similar patients reported.” The data is good enough to support an evidence browser if the UI is explicit about:

- self-reported source data
- AI extraction limitations
- report count versus unique-patient count
- support tiers
- quote inspection

This is the right framing for the product. The value is in organizing anecdotal evidence, not turning it into faux-clinical certainty.

## 2. The Best Product Core Is a Single Exploration Loop

The most coherent product loop is:

1. define a patient profile
2. retrieve a similar cohort
3. inspect treatment evidence
4. validate through quotes and patient drill-down
5. adjust the profile and compare

Everything else is secondary. The product becomes weaker when it tries to do too many things at once.

## 3. Subtype Differences Are the Most Valuable Signal

The notebook review reinforced the most important product insight: condition combinations matter.

The clearest example was `POTS only` versus `POTS + MCAS`, where treatment signals changed materially:

- antihistamines were much stronger in the overlap group
- ivabradine was much stronger in the POTS-only group
- guanfacine also shifted between the two groups

This means the explorer should prioritize:

- combinations of diagnoses
- symptom phenotype
- prior treatment response

rather than just top-level diagnosis labels.

## 4. Symptom Selection and Prior Response Belong in the Intake

The original treatment explorer became much stronger once symptom selection and treatment-response selection were added.

Why:

- the same diagnosis label can hide very different symptom patterns
- users often think in terms of “what helps my brain fog?” rather than “what helps my condition?”
- prior negative or mixed treatment response is clinically and product-wise meaningful

This suggests the explorer should model:

- diagnoses
- symptom domains
- target symptom to improve
- prior treatment outcomes

as first-class inputs.

## 5. There Is a Real Opportunity for a Diagnosis-Pattern Mode

Treatment evidence is only one user need. A second user need is:

“I am not sure what bucket I fit into. What diagnoses recur in patients whose symptom pattern resembles mine?”

That mode is valuable if it is framed correctly:

- suggestive pattern finding, not diagnosis
- evidence-backed, not model-confident
- explicit about what is missing

The best diagnosis-mode shape is not a ranked list alone. It needs:

- why the pattern appeared
- which clues support it
- which clues are missing
- clinician conversation prompts

This produces a better user outcome than simply surfacing a diagnosis label.

## 6. Missing Evidence Is as Important as Positive Evidence

One of the strongest design lessons is that the app should not only show:

- what matches
- what helped
- what diagnoses recur

It should also show:

- missing clues
- sparse support
- incomplete severity / duration / onset data
- lack of formal testing evidence

This is especially important in diagnosis mode. The most responsible version of the product helps users see uncertainty, not just patterns.

## 7. The Dataset Has Enough Strength for an MVP, But Only for a Narrower Cohort

The database is broad, but the fully useful cohort is much smaller than the total patient count.

High-level coverage from the notebook:

- conditions: 57.7%
- treatment reports: 37.7%
- symptom trajectory: 30.8%
- onset trigger: 26.4%
- functional status: 16.5%
- duration: 16.3%

Using cleaned non-empty field presence, the strict core cohort with conditions + treatment reports + trajectory + severity is 385 patients. Older notes that cite 394 should be treated as superseded.

Implication:

- the product can work
- but not every user profile will generate equally rich outputs
- cohort quality needs to be visible in the UI

## 8. Patient Quality Is Uneven and Must Be Surfaced

The evidence is not evenly distributed across users.

There is a large long tail of low-information patients and a much smaller set of high-information patients. This affects:

- treatment ranking reliability
- quote availability
- cohort interpretability
- cluster behavior

The product should expose:

- patient quality tier
- quote availability
- cohort completeness

instead of hiding those factors in backend logic.

## 9. The Strongest Near-Term Treatment Signals Are Not All Equally Useful

The rendered analysis showed solid high-support signals for:

- low-dose naltrexone
- antihistamines
- magnesium
- nicotine patch
- nattokinase
- tirzepatide

But these are not equally product-useful.

What makes a signal useful is not just the positive percentage. It is the combination of:

- sample size
- unique patient count
- subtype variation
- quote availability
- side-effect context

This is why the product should rank by support-aware evidence rather than by positivity alone.

## 10. LDN Is a Good Demonstration Treatment

LDN is a particularly strong exemplar for demos and product development because it has:

- large sample size
- broad condition coverage
- meaningful variation by severity / trajectory / duration
- strong quote availability

It works well as a reference treatment for developing:

- evidence cards
- quote drill-down
- stratified slices
- cohort explanations

## 11. Clustering Is Still Exploratory, Not Ready for User Trust

Even after cleaning the cohort logic, clustering remains weak-to-moderate and sensitive to representation choices.

The notebook run showed:

- a relatively small strict clustering cohort
- numerical warnings in the sklearn path
- only modest cluster separation
- continued risk that verbosity and data structure drive the output

Implication:

- clustering is still useful internally
- but should not be a front-and-center patient-facing feature yet

## 12. Canonicalization Quality Is a Hard Product Dependency

The biggest analysis failure point was the naive substring condition mapping.

Observed problems:

- `me_cfs` overmatched because `me` is too broad
- `multiple_sclerosis` overmatched because `ms` is too broad
- `eds` was incompletely captured

This has a major consequence:

Diagnosis and condition-level evidence cannot be treated as product-safe until canonicalization is fixed.

The diagnosis tab is still directionally correct as a product concept, but it depends on a reviewed controlled vocabulary before it can be trusted.

## 13. Static Prototype Design Helped Clarify the Product Faster Than More Analysis Would Have

Building the mockup and then the interactive prototype exposed product requirements that were not obvious from the architecture doc alone:

- diagnosis mode needs its own evidence grammar
- the right drawer should change role depending on mode
- the product needs “why this appears” explanations, not just result cards
- symptom clues and missing clues are essential UI objects

This suggests that interface prototyping is a useful part of product discovery here, not just polish work.

## 14. The Best MVP Is a Calm, Dense, Evidence-First SPA

The most convincing product shape is:

- left rail: profile definition
- center: ranked evidence or diagnosis patterns
- right drawer: inspection and explanation

This structure can eventually support both major user intents:

- treatment exploration
- diagnosis-pattern exploration

without forcing the user into a wizard or a maze of pages.

## 15. The Right Next Technical Move Is Derived Data, Not More UI

The biggest bottleneck is no longer design direction. It is data trust.

The next major technical step should be to build reliable derived layers:

- `condition_canonical_map`
- `treatment_canonical_map`
- `field_value_normalization_map`
- `patient_quality_score`
- `treatment_signal_summary`

Once those exist, the SPA can be wired to real evidence safely. Until then, the frontend can demonstrate the workflow, but not serve as a trustworthy analytical surface.

## 16. Operating Decisions From This Round

These should now be treated as current direction rather than open questions:

- MVP centers on one loop: define profile -> retrieve similar cohort -> inspect treatment evidence -> validate via quotes/patient drill-down -> adjust profile.
- Intake should treat symptom domains, target symptom, and prior treatment outcomes as first-class inputs alongside diagnoses.
- The strict core cohort is 385 patients; broader cohorts are still useful, but the UI must explicitly show when results come from a looser evidence pool.
- Every result set should carry a cohort quality contract: matched patient count, completeness cues, quality tier, support tier, and quote availability.
- Diagnosis-pattern exploration should stay in MVP only in a simple form: a small number of suggestive patterns, clear missing clues, and clinician discussion prompts. It should not become a heavyweight second workflow until canonicalization quality improves.
- Patient-facing clustering should remain out of MVP and internal/exploratory unless the representation quality improves materially.

## 17. Browser-Side SQLite Was the Wrong Boundary

The standalone weighted keyword explorer made a hidden architectural problem obvious: browser-side SQLite was workable only as a demo hack, not as a reliable product path.

Observed failure modes:

- local file access made DB loading brittle
- CDN/runtime dependencies could leave the page stuck waiting for database access
- large client-side data bundles were possible, but clearly the wrong long-term shape
- the browser was being asked to do data-access work that belongs in a server layer

The important lesson is not just that browser SQLite is annoying. It is that once the UI needs real search, ranking, and drilldown against a nontrivial corpus, the boundary should move server-side.

## 18. The Existing Python + SQLite Stack Was Good Enough

There was no need to introduce a second backend stack.

The repo already had:

- Python
- direct SQLite access
- reusable data-loading logic
- an analyst-facing Streamlit app

That made a small FastAPI server the cleanest next move. It fit the current codebase better than:

- a Node/Express backend
- more client-side SQLite workarounds
- embedding everything directly into one-off frontend bundles

This is a good example of a broader build principle: when a codebase already has a working data/runtime spine, extending that spine is often better than adding a parallel stack.

## 19. `patientpunk.db` Is the Right Product Database

The search work clarified something that had been directionally true but not yet enforced in implementation: product-facing work should target `patientpunk.db`, not `posts.db`.

Why:

- it is the consolidated database
- it keeps posts, treatment reports, and richer patient-profile tables under one roof
- it avoids building product infrastructure around a narrower intermediate artifact

The weighted keyword explorer only needed posts plus treatment reports in its first API version, but standardizing on `patientpunk.db` now avoids a future migration later when the explorer needs:

- conditions
- variables
- unified patient context
- cohort-quality joins

## 20. The API Contract Matters More Than the Search Algorithm at First

For the first server-backed version, the important thing was not choosing the perfect search engine. It was locking a stable request/response contract.

The useful contract shape turned out to be:

- weighted query terms in
- cohort counts out
- cohort-change history out
- ranked posts out
- treatment rollups out
- post drilldown out

This matters because the retrieval layer can improve behind the same contract:

- V1: weighted `LIKE`
- V2: FTS5
- V3: precomputed search summaries or cached cohorts

That separation gives the frontend a stable surface while letting the backend evolve.

## 21. Weighted Keyword Search Is a Legitimate Secondary Intake Path

The earlier product direction emphasized guided intake, condition overlap, symptom domains, and prior treatment responses. The server-backed keyword explorer showed that a text-led cohorting path is also valuable.

Why it works:

- users often think in phrases before they think in canonicals
- keywords can bridge from vague symptom language into inspectable cohorts
- seeing cohort size change as terms accumulate is itself an interpretability feature

This does not replace structured intake. It complements it. A good product can support both:

- guided profile definition for more normalized retrieval
- weighted keyword search for exploratory, symptom-led cohort building

## 22. Post-Level Ranking and User-Level Treatment Rollups Need Different Units

One useful architectural distinction became very clear in the API implementation:

- posts are the right unit for text matching and quote inspection
- users are the right unit for treatment cohort rollups

This sounds obvious in retrospect, but it is easy to blur them if everything is done inside one frontend artifact.

The correct behavior is:

1. rank posts by weighted text match
2. derive the matched user cohort from those posts
3. aggregate treatment reports across distinct matched users
4. keep the denominators visible

That separation is important for trust. Otherwise, prolific posters can silently dominate both retrieval and treatment ranking.

## 23. FastAPI Is a Good Productization Bridge

FastAPI was not just a framework choice. It was a useful bridge between exploratory data work and product work.

It gave the project:

- typed request models
- typed response models
- small, explicit endpoints
- a clean path for serving the standalone page and the API from one place

That makes it much easier to move from:

- notebook findings
- static HTML prototypes
- local analyst tools

to something that behaves like an actual product surface.

## 24. The Main Risk Has Shifted From UI Feasibility to Data Trust

After the server work, the main unresolved issues are no longer “can the UI do this?” or “can the browser read the DB?”

Those questions are basically answered.

The higher-value unresolved risks are now:

- condition canonicalization quality
- treatment canonicalization quality
- support-tier reliability
- whether keyword retrieval should move to FTS5
- how quickly the rest of the prototype can be moved onto trusted derived tables

This is a meaningful shift. It means the project is past the pure prototyping phase for this feature and into infrastructure and evidence-quality work.
