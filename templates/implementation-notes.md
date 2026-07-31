# implementation-notes

The builder subagent maintains this file. It is a delivery requirement, not a
courtesy: **a delivery that arrives without a notes update has not been
delivered**, and the orchestrator sends it back before running any gate.

Keep the four headings. Append per iteration; never overwrite earlier entries —
this file is the trail of what the loop actually decided.

The judge reads **偏離情況** against `SPEC.yaml`: a deviation that is not
recorded here is a blocking issue on its own, and a recorded one is judged on
whether its reason holds.

At every human checkpoint the orchestrator puts **開放式問題** in front of the
person. Whatever they rule on gets written back into `SPEC.yaml`, so the same
question is never asked twice.

## 設計決策

Choices made where the spec was silent. One line each: what you chose, and what
the spec left open that forced the choice.

- (iteration 1) ...

## 偏離情況

Places you deliberately did something the spec does not say, or says otherwise.
Name the spec line, what you did instead, and why.

- (iteration 1) ...

## 價值取捨

Alternatives you considered and rejected, and what made this one win. This is
what stops the next iteration re-exploring a dead end.

- (iteration 1) ...

## 開放式問題

Things you want the human to confirm or change. Ask a decidable question, not
"is this OK?".

- (iteration 1) ...
