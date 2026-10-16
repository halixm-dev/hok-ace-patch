# 01: Reference check

**What to build:** a by-hand research-tool check, run from the project root like the offline graphics check, that proves every pointer in the docs still lands. It scans every tracked Markdown file, the staging entry point's docstring, the research tools and the build scripts for repo paths (backticked or linked). It reports any path that doesn't exist, and any mention of a name on a retired-names list that later tickets extend. Exit code 0 means clean; otherwise it prints one failure per line. This is the guard every later ticket runs. See the spec's Testing Decisions.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Passes on today's tree with an empty retired-names list
- [ ] Reports a deliberately broken path, and a deliberately retired name, with file and line
- [ ] Ignores paths under generated or gitignored roots (build output, dist, artifacts, work data), so dumps and outputs never count as references
- [ ] Imports nothing from the app or the pipeline, and nothing imports it
