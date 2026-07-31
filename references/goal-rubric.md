# Goal Rubric (Stage 1)

Push the user's goal until two competent agents could not disagree on "done".

## A good goal names
- The concrete OUTCOME artifact, not the activity ("a ranked 5-item shortlist",
  not "help me pick topics").
- The state that PROVES the loop finished (definition_of_done).
- Scope boundaries: included, excluded, max depth.
- Context sources the builder must READ instead of assume.
- Who consumes the result (you / a reader / a downstream agent).

## Strict-mode critique prompts (ask every one)
- "If two agents disagreed, what artifact settles it?"
- "Which words here are subjective and need a measurable proxy?"
- "What must be read before the builder drafts a plan?"
- "What is explicitly out of scope?"
- "Can this split into plan / delivery / verification artifacts?"

## Anti-patterns (block, don't accept)
- "Improve / make better / make good" with no target artifact.
- "Research X" with no decision the research supports.
- Success depends on info the loop never gathers.
- Endless polishing with no stop state.

## Before -> after
Weak:   "Clean up the onboarding docs."
Better: "Produce docs/quickstart.md that takes a new contributor from a fresh
         clone to a passing test run: Prerequisites / Install / Run tests /
         Troubleshooting, every step a copy-pasteable command, no TODOs."

Weak:   "Make the API faster."
Better: "Cut p95 latency on GET /search below 200ms measured by bench/search.py
         against the fixture corpus, with no endpoint returning different
         results than it does today."
