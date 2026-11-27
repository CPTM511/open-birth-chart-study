# Open Birth Chart Study Constitution

**Version 1.0 · English**　[中文](CONSTITUTION.zh.md)

## 1. Purpose

The study starts with Bazi, Ziwei Doushu, Qizheng Siyu and Western astrology. Which patterns across ages, birth cohorts or places recur when documented birth records are processed by explicit models of these four traditions? Which patterns can be explained by shared calendars, sample selection, software limits or chance? The project preserves findings that support a hypothesis, findings that challenge it and studies that lack the information to distinguish the alternatives.

Claims about interrupted life or luck periods among younger generations, and questions about a possible civilizational discontinuity in the AI era, motivate the study. Each investigation must specify one testable meaning and an observation that would change our judgment. Chart calculations can describe a model. Observed events require an independent record. A proposed connection between the two needs its own study that can fail.

## 2. Match the claim to its evidence

| Question | Evidence needed at this level | What a report can say |
|---|---|---|
| What was originally claimed? | Traceable text, edition, period, school, scope and conflicting accounts | Attribute the statement to a specific version. Mark an untraced claim as such. |
| Did the implementation follow the rule? | Calendar and astronomical checks, executable rules, independently sourced examples, counterexamples, exceptions and boundary tests | Identify the examples this implementation reproduces and the conventions still in dispute. |
| What structure appears within the models? | Prespecified index, reference, sampling frame, comparisons and uncertainty | Quantify a contrast for the named birth years and sources. |
| Does a model predict observed events? | Independently ascertained outcomes, a defined population at risk, held-out or prospective observations, a credible baseline and prediction error | Report out-of-sample performance in the studied population and follow-up period. |
| Did AI cause a change in the world? | Dated measures of capability, exposure, adoption and outcomes, with a design that addresses alternative explanations | Distinguish task performance, labor-market change and loss-of-control events. State the assumptions for a causal claim. |

The four systems share birth inputs and several calendar and astronomical cycles. Test for shared causes before interpreting alignment. Label a period outside the registered age window as uncovered. A birth in the 2020s can be an observed record while the trajectory at adult ages is entirely modeled. Mortality requires ascertainment independently of where software stops emitting values.

## 3. Choosing and freezing a study

Begin each round with five answers short enough to fit on one page. Which explanations will it distinguish? Who is compared, against what and over which period? What difference would matter? What evidence would weaken the working hypothesis? When is the study complete, inconclusive or worth stopping? Use those answers to choose among better rules, a new source, replication and a larger sample.

Before inspecting target results, date and version the unit of analysis, eligibility, sample-size rationale, sources and permitted fallbacks, reference, rules, primary endpoint, family of comparisons, treatment of missingness and sensitivity analyses. Disclose data or results already seen. A rule developed through exploration earns a confirmatory test on fresh held-out data. Identify the actual commitment mechanism used, whether a repository freeze, external registration or journal Registered Report.

## 4. Sources and traditional rules

Trace each source from original records through eligibility, selection and completed calculations. Report denominators, exclusions and possible overlaps at each stage. Separate birth year from registration year. Document clock precision and rounding, historical time zones, daylight-saving ambiguities, location proxies and the population to which weights apply. Claim unique people only after identity has been established. Follow the registered treatment of missing clocks. Use synthetic records for checks and report aggregate demographic estimates and population projections separately.

For each traditional rule, identify the work and passage, school, prerequisites, priority, counterexamples and mitigating conditions. Distinguish historical text, a modern convention and a computational approximation. Version defensible competing interpretations separately. Record the reason for choosing or changing a rule before observing its target effect. A contributor can challenge an implementation with a single well-sourced counterexample.

## 5. Statistical inference and falsification

Define the estimand, denominator, effect unit and smallest effect of interest. Account for repeated ages within records, regional clustering, sampling design and shared inputs when constructing the reference or estimating uncertainty. State how age, birth cohort and calendar period are related in a cross-cohort comparison. Use negative controls, injected signals and appropriate held-out sources to test false alarms, detection and transfer. For causal questions, give the comparison group, temporal ordering and plausible confounders.

Report effect sizes and intervals. Explain what was held fixed and which sources of error the intervals cover. Distinguish a result that misses a significance threshold, one that rules out a prespecified magnitude under its assumptions, and one with insufficient precision. Apply the declared multiplicity correction. Label a peak year, subgroup or endpoint first noticed during exploration and test it in a subsequent independent design. More records can improve sampling precision. Geographic selection, rule coverage and measurement error each need evidence of their own.

To test a prediction about an observed event, record its conditions, direction, time window and success criterion before learning the outcome. Distinguish observed events, confirmed absence, loss to follow-up and insufficient observation time. Ascertain outcomes consistently and compare performance with a baseline using the underlying event rate or established predictors. When issuing probabilities, check calibration against observed frequencies and report false positives, missed events and their denominators.

## 6. Reproduction, privacy and release

Retain provenance and permissions, versions and digests, complete selection and transformation code, timezone and geographical mappings, dependencies, seeds, execution order and machine-readable aggregates. When redistribution is restricted, supply a tested reconstruction path from the publisher or document authorized retrieval and custody of the protected archive. Test retrieval or reconstruction in a separate directory before sealing a critical sample or reference. A digest can authenticate recovered bytes. The files or the means of regenerating them must also remain accessible to an authorized reviewer.

Before release, a reviewer independently recomputes consequential numbers from the sealed inputs and checks denominators, exclusions, units, intervals and wording. State which code was shared, what was rerun and what remains unchecked. Identify internal human review, a separately written implementation, AI-assisted checks, replication by an outside team and scholarly peer review according to what actually took place. When required inputs or verification are missing, publish the auditable state and reserve the effect estimate.

Use fields justified by the research question and the applicable permissions. Check the disclosure risk of small cells and linked tables, especially for precise birth times and places, children and rare groups. Publish aggregates, code and appropriate fixtures. Store, restrict and dispose of person-level files under their source terms. New outcome linkages require a separate ethics, permissions and data-minimization assessment. Independent mortality-outcome work is paused. Resumption requires explicit project-owner authorization and a separate protocol frozen before access to the outcomes being tested, using rigorously held-out or prospectively observed data.

## 7. Decisions, amendments and accountability

The proposer records the question and what could refute it. The analyst records the decisions actually made. The reviewer states their independence and objections. The maintainer owns the release decision. A small team may combine roles and must disclose overlap, specific AI contributions, funding and conflicts of interest. Contributors may submit evidence-backed corrections through an issue or pull request. Preserve material disagreements and the grounds for resolving them.

Release every registered comparison, including null results, unavailable sources and failed validation. For a material error, identify the affected version, whether results had already been seen, the scope of the impact and the repair evidence. Link the correction beside the earlier claim. Mark a conclusion as withdrawn if its basis fails. New models and explanations awaiting validation belong in a subsequent version. Public summaries and social posts carry the same denominator and scope as the research report.

This charter governs future work from its adoption on the default branch. Propose amendments in public and record the rationale, dated version, affected decisions and first round governed by the change. Evaluate earlier rounds under their original frozen protocols and preserve that history. At the close of a round, use the remaining uncertainty to choose the next investigation or to pause.

Project records include the [research questions](docs/RESEARCH_QUESTIONS.md), [four-system implementation boundaries](docs/four_system_readiness.md), [contribution process](CONTRIBUTING.md) and [source terms](data_expansion/DATA_LICENSES.md). Methodological references include [preregistration](https://www.cos.io/initiatives/prereg), [STROBE reporting guidance](https://www.strobe-statement.org/), [RECORD guidance for routinely collected data](https://doi.org/10.1371/journal.pmed.1001885) and the [FAIR principles](https://www.gofair.foundation/fair-principles).
