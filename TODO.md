Specification Q5

Spec Q5 — "Improved implementation" (50 pts, grad-only / extra credit):                                                                         
  
  ▎ Improve the above standard IR system based in your error analysis. For this task you have more freedom in choosing a solution and I encourage   ▎ you to use your imagination. For example, probably the simplest solution is to ask a large language model to rerank the top-k answers produced  ▎  by the retrieval system. Or you could implement a positional index instead of a bag of words; you could use a parser to extract syntactic    
  ▎ dependencies and index these dependencies rather than (or in addition to) words; you could use supervised learning to implement a reranking 
  ▎ system that re-orders the top 10 (say) pages returned by the original IR system (hopefully bringing the correct answer to the top), etc.

  Reading the spec carefully:

  1. It's grad-only / extra credit — undergrads get full credit at 200/200 without it; grads need it for the full 250→200 normalization. Doing it 
  as an undergrad means bonus points.
  2. It must be motivated by your own error analysis (Q4). The improvement isn't "pick a fancy technique" — it's "name the error class that's     
  hurting you, then build something that targets that class." So Q4 and Q5 are tied: weak Q4 → weak justification for Q5.
  3. Freedom in solution. The spec lists examples — they're suggestions, not requirements:
    - LLM reranker over top-K (called out as "probably the simplest"). Feed the top-10 titles + clue + category to an LLM, ask it to pick the     
  best. Targets inferential errors (e.g. "rebel with a cause" → James Dean, where lexical retrieval can't bridge through the Rebel Without a Cause
   film) and pun/wordplay errors ("TIN" MEN).
    - Positional / phrase index. Bag-of-words loses word order; a positional index lets you score exact phrases natively. We approximated this    
  with ^3 quoted-phrase boosts at query time, but a real positional index would handle it more cleanly.
    - Syntactic-dependency index. Parse each page (and the clue) into dependencies (e.g. nsubj(painted, Tintoretto)) and index those. Helps when  
  the answer's role in a sentence matters, not just term overlap.
    - Learned reranker. Train a model (LambdaMART, a small neural ranker, or a fine-tuned BERT cross-encoder) to re-order the top-10. Features    
  could include BM25 score, title-clue overlap, category-body overlap, page length, link counts, etc.
  4. What the spec is not asking for. It's not "replace your IR system." The improvement sits on top of the standard IR. The spec is explicit that
   the IR pipeline from Q1 is the substrate.

  Where our project currently sits:

  We did a rule-based reranker (meta-page demotion, decoy demotion, contiguous-phrase promotion) plus query-side phrase boosts. That's a
  defensible Q5 — it's grounded in our error analysis and produces a measurable gain (+5 P@1, +0.04 MRR). But it's the weakest of the spec's      
  example menu: it doesn't bring any signal beyond lexical overlap.

  Strongest next step that fits the spec: the LLM reranker. Concretely:

  - For each clue, take our top-10 hits.
  - Build a prompt: clue, category, list of (title, ~200-word page snippet) pairs.
  - Ask Claude to return the index of the best answer.
  - Score the result against gold.

  This would directly target the three error classes our Q4 calls out as unreachable for BM25:
  - Inferential clues ("rebel with a cause" → James Dean via Rebel Without a Cause).
  - Pun categories ("TIN" MEN → answers contain "tin": Tintoretto).
  - Indirect category lookups ("The Naples Museum of Art" → Florida, not the museum).

  Estimated lift based on similar setups in the literature: from 25% P@1 to 50–70% P@1, which is the regime the actual Watson achieved (and it's  
  exactly the gap I mentioned in the previous answer). Cost is one API call per clue × 100 clues — trivial.

  Want me to implement the LLM-reranker variant as a third mode (--mode llm)? That would be a stronger Q5 submission than the current rule-based  
  one.

Grading so far

 Honest assessment, going through the rubric:                                                                                                    
                                                                                                                                                  
  Q1 — Core implementation (50 pts) → 45/50                                                                                                          
  - ✅ Whoosh BM25F index, one doc per page, Porter stemming, stopwords, title boost.                                                             
  - ✅ Wiki-specific issues identified and addressed (redirects, [tpl]/[ref] markup, image embeds, CATEGORIES line, duplicate titles).
  - ✅ Query construction is described and justified (no subset selection — defended).
  - ⚠️ The variant-comparison table in the README (clue+category alone, etc.) cites P@1 numbers that I gave from prior runs but didn't re-verify  
  in a single pass with the current code. A grader who recomputes them might not get the same digits.
  - ⚠️ The "duplicate page titles" handling is described in the README but I haven't verified it's actually implemented in build_index.py this    
  session.

  Q2 — LLM usage (50 pts) → 42/50

  - ✅ Honest, specific account: which model, how prompted, what worked, what didn't.
  - ⚠️ Light on concrete examples of prompts and failures. The "what did not work" section names categories (over-aggressive rerank, AndGroup vs  
  OrGroup, punctuation) but no quoted prompt-and-response pairs. A stronger answer would include 2–3 verbatim prompt snippets.
  - ⚠️ Doesn't mention this session's redesign at all, which is the most interesting LLM-collaboration story (diagnosing the regression, narrowing
   the boost rule, comparing v1 vs v2 numbers). That's a real gap.

  Q3 — Performance (50 pts) → 45/50

  - ✅ Justifies metric choice (P@1 + MRR; rules out NDCG/recall/F1 with reasoning).
  - ✅ Reports both modes, full P@1/P@5/P@10/MRR table, B-sweep table, gain/regression breakdown.
  - ⚠️ No statistical significance discussion (paired bootstrap, McNemar). At n=100 with +5 P@1, "is this real?" is a fair question.
  - ⚠️ No held-out / cross-validated number. The B sweep was done on the same 100 questions we report on — that's mild test-set tuning. Defensible
   because the spec gives only those 100, but should be acknowledged.

  Q4 — Error analysis (50 pts) → 35/50

  - ✅ Six error classes named with concrete examples.
  - ✅ Concrete count (25 / 30 / 45 split).
  - ❌ No per-class counts. The classes are listed qualitatively; a grader expects "Topical-decoy: 12 / Inferential: 8 / Pun: 5 / …". I haven't   
  actually bucketed the 75 misses.
  - ❌ No discussion of why the easy ones get answered correctly with concrete IDF-style evidence (the README hand-waves at "rare content-bearing 
  tokens" — a histogram of clue-IDF vs correctness would be much stronger).
  - ⚠️ The error analysis isn't tied tightly to the Q5 design choices. The link is there in spirit but not made explicit ("error class X →        
  improvement Y → measured gain Z").

  Q5 — Improved implementation (50 pts, grad-only) → 30/50

  - ✅ Rule-based rerank + phrase boost + run boost is grounded in error analysis.
  - ✅ Beats baseline by a real margin (+5 P@1, +0.04 MRR), with gain/loss breakdown.
  - ✅ "What was tried and rejected" is a strong addition.
  - ❌ This is the weakest item on the spec's example menu. The spec calls out LLM rerank as "probably the simplest" — and the heaviest-lifting   
  option for our actual error classes (inferential, pun, indirect lookup). We haven't done it.
  - ❌ +5 P@1 is a modest delta. A reranker would plausibly add 20–40 more.

  Other deductions

  - ❌ No PDF report. Spec explicitly requires "A project report in PDF format." README is structured well but not converted. Likely –10 to –15   
  pts off the top if graded strictly.
  - ⚠️ No requirements.txt verification this session.

  Total

  ┌───────────────────────────────────┬───────────────────┬─────┐
  │               item                │      earned       │ of  │
  ├───────────────────────────────────┼───────────────────┼─────┤
  │ Q1 Core                           │                45 │  50 │
  ├───────────────────────────────────┼───────────────────┼─────┤
  │ Q2 LLM usage                      │                42 │  50 │
  ├───────────────────────────────────┼───────────────────┼─────┤
  │ Q3 Evaluation                     │                45 │  50 │
  ├───────────────────────────────────┼───────────────────┼─────┤
  │ Q4 Error analysis                 │                35 │  50 │
  ├───────────────────────────────────┼───────────────────┼─────┤
  │ Q5 Improved (extra for undergrad) │                30 │  50 │
  ├───────────────────────────────────┼───────────────────┼─────┤
  │ Subtotal (undergrad scale, /200)  │               167 │ 200 │
  ├───────────────────────────────────┼───────────────────┼─────┤
  │ PDF deduction                     │               –12 │     │
  ├───────────────────────────────────┼───────────────────┼─────┤
  │ Undergrad final estimate          │ ~155 / 200 (~78%) │     │
  └───────────────────────────────────┴───────────────────┴─────┘

  Adding Q5 as extra credit on top: ~155 + 30 = ~185 / 200 (~93%) — if the PDF gets produced and the grader counts the extra-credit cap
  generously.

  Biggest leverage if you have time:
  1. Make the PDF (1 hr; recovers ~10–15 pts).
  2. Bucket the 75 errors with counts in error_analysis.py output (1 hr; recovers ~5–8 pts on Q4).
  3. Implement the LLM reranker as mode=llm (2–3 hrs; could move Q5 from 30 → 45+).

  In that order — the PDF is non-negotiable per the spec, the error counts are cheap, and the LLM rerank is the highest-ceiling but biggest-effort
   item.