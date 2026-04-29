Using `project.md` as your specification, do the following:

1. **Plan first.** Draft an explicit, step-by-step plan for completing the project before writing any code. The plan should cover implementation, concise inline documentation, and test file creation.

2. **Complete the project.** Follow the plan, then write a `README.md` that includes:
   - How to run the code
   - Written answers to any questions required by the spec

**Data folder contents:**
- `questions.txt` — sample questions (feel free to read this)
- `wiki-subset-20140602.tar.gz` — compressed archive of Wikipedia text files
- Many wiki page files named like `enwiki-20140602-pages-articles.xml-*.txt`
- Dotfiles named like `._enwiki-20140602-pages-articles.xml-*.txt` — these are macOS metadata artifacts and can be ignored

**Important:** Do not load multiple wiki files into your context at once. You may read `questions.txt` and one or two wiki files as examples to understand the format, but no more.