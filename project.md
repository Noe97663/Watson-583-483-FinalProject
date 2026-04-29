# CSC 483/583: Programming Project

## Building (a part of) Watson

## Due before 11:59 P.M., May 6th

For this project you must submit:

- A repository containing all the source code.
- A project report in PDF format that must contain at least:
    - Instructions on how to compile (if needed) and run the code.
    - Description of the code. You don’t have to describe every function implemented.
       But you should describe the main part of the code and indicate where each
       question is addressed.
    - Results, i.e., the output of your code, for all the questions that required pro-
       gramming.
    - Answers for all questions that do not require programming.

Answers are always graded by inspecting both code and documentation. Missing code
yields no credit. Missing documentation yields partial credit (if code exists and produces
correct results).

The project is worth 200 points of your final grade. It will be graded out of 200 points
for undergraduate students and 250 for graduate students (and normalized down to 200).
Undergraduate students do not have to solve the task marked “grad students only.” How-
ever, if undergraduate students address this task, the additional points will count as extra
points towards the final grade!


IBM’s Watson is a Question Answering (QA) system that “can compete at the human
champion level in real time on the TV quiz show, Jeopardy.” This, as we will see in class,
is a complex undertaking. However, the answers to many of the Jeopardy questions are
actually titles of Wikipedia pages. For example, the answer to the clue “This woman who
won consecutive heptathlons at the Olympics went to UCLA on a basketball scholarship”
is “Jackie Joyner-Kersee”, who has a Wikipedia page with the same title: [http://en.](http://en.)
wikipedia.org/wiki/Jackie_Joyner-Kersee. In these situations, the task reduces to
the classification of Wikipedia pages, that is, finding which page is the most likely answer
to the given clue. This is the focus of this project.

In this project you will use the following data (see D2L project folder):

- 100 questions from previous Jeopardy games, whose answers appear as Wikipedia
    pages. The questions are listed in a single file, with 4 lines per question, in the
    following format: CATEGORY CLUE ANSWER NEWLINE. For example:
    NEWSPAPERS
    The dominant paper in our nation’s capital, it’s among the top 10 U.S. papers in circulation
    The Washington Post
- A collection of approximately 280,000 Wikipedia pages, which include the correct
    answers for the above 100 questions. The pages are stored in 80 files (thus each file
    contains several thousand pages). Each page starts with its title, encased in double
    square brackets. For example, BBC’s page starts with “[[BBC]]”.

Your project should address the following points:

1) (50 pts) Core implementation – indexing and retrieval: Index the Wikipedia
collection with a state of the art Information Retrieval (IR) system such as Lucene
(http://lucene.apache.org/) or Whoosh (https://whoosh.readthedocs.io/en/
latest/intro.html). Make sure that each Wikipedia page appears as a separate
document in the index (rather than creating a document from each of the 80 files).
Describe how you prepared the terms for indexing (stemming, lemmatization, stop
words, etc.). What issues specific to Wikipedia content did you discover, and how
did you address them? Implement the retrieval component, which takes as query
the Jeopardy clue and returns the title of the Wikipedia page that is most similar.
Describe how you built the query from the clue. For example, are you using all the
words in the clue or a subset? If the latter, what is the best algorithm for selecting
the subset of words from the clue? Are you using the category of the question?

2) (50 pts) Coding with LLMs: For this project you must use large language models
(LLMs) to help you with coding! Answer the following questions in your report:

- What LLMs did you use and how did you prompt them? For example, here are
    a couple of Claude Code “skills,” i.e., improved prompts for coding: https://


```
github.com/forrestchang/andrej-karpathy-skills and https://github.
com/EveryInc/compound-engineering-plugin.
```
- How exactly did you use LLMs? That is, did you “vibe code” the entire project
    from scratch? Did you architect the project yourself and ask the LLM to write
    specific parts of the code? Did you use the LLM to provide hints/debug your
    code, i.e., like a better Stack Overflow?
- What worked and what did not? Be as specific as you can.

3) (50 pts) Measuring performance: Measure the performance of your Jeopardy sys-
tem, using one of the metrics discussed in class, e.g., precision at 1 (P@1), normalized
discounted cumulative gain (NDCG), or mean reciprocal rank (MRR). Note: not all
the above metrics are relevant here! Justify your choice, and then report performance
using the metric of your choice.

4) (50 pts) Error analysis: Perform an error analysis of your best system. How many
questions were answered correctly/incorrectly? Why do you think the correct ques-
tions can be answered by such a simple system? What problems do you observe for
the questions answered incorrectly? Try to group the errors into a few classes and
discuss them.

5) (50 pts) Improved implementation (GRAD STUDENTS ONLY): Improve the
above standard IR system based in your error analysis. For this task you have more
freedom in choosing a solution and I encourage you to use your imagination. For
example, probably the simplest solution is to ask a large language model to rerank
the topk answer produced by the retrieval system. Or you could implement a
positional index instead of a bag of words; you could use a parser to extract syntactic
dependencies and index these dependencies rather than (or in addition to) words;
you could use supervised learning to implement a reranking system that re-orders
the top 10 (say) pages returned by the original IR system (hopefully bringing the
correct answer to the top), etc.

Note: We will follow the same grading scheme for any custom project. That is:

1. Core implementation: 50 points
2. Description of LLM usage: 50 points
3. Evaluation: 50 points
4. Error analysis: 50 points
5. Improved implementation: 50 points (grad students only)


