# 08: Staging contract into the docstring

**What to build:** the staging summary contract (the returned payload's fields, the `mode` values and what each entry carries, the skipped lists and what reads them, pass order, and the APK/builder gating) lives in the staging entry point's own docstring, verbatim apart from glossary terms. It then changes in the same edit as the code. The instructions keep two lines naming where it is. The staging behaviour doesn't change.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] The docstring holds the full contract, and the instructions hold only a two-line pointer
- [ ] The exe build and the offline graphics check pass unchanged
- [ ] The reference check passes
