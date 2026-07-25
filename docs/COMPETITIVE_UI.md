# Competitive UI review

Reviewed 2026-07-24 against current AI evaluation and experiment interfaces.

| Product | Relevant surface | What works |
| --- | --- | --- |
| [Braintrust](https://www.braintrust.dev/foundations/comparing-experiments) | experiment comparison | Side-by-side scores, outputs, diff mode, cost, and per-case traces make a gate actionable. |
| [Arize Phoenix](https://arize.com/docs/phoenix/evaluation/llm-evals/evaluator-traces) | evaluator traces | Every judge result retains input, prompt, reasoning, score, and timing provenance. |
| [LangSmith](https://www.langchain.com/langsmith-platform) | evaluation | Production traces and experiments share a comparison surface with human review. |
| [Patronus](https://docs.patronus.ai/docs/evaluations/concepts) | evaluation results | Pass/fail, score, explanation, evaluator, context, gold answer, tags, and metadata remain inspectable together. |

## Direction adopted

- Make the merge verdict impossible to miss while keeping it subordinate to the
  paired evidence that produced it.
- Show baseline, candidate, delta, and confidence interval as one comparison
  instrument.
- Use a sample-level regression matrix instead of an aggregate-only chart.
- Put dataset and scorer hashes in a dedicated provenance rail.
- Use indigo for the evaluation system and coral only for blocking regressions.

The result is a CI evidence console rather than a presentation of three KPIs.
