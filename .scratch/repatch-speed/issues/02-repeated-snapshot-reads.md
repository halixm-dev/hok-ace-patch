# Measure and remove repeated snapshot reads

Status: claimed

Blocked by: 01

Profile the snapshot checkpoint and the checks that run before the first refusal. Drop repeated
content reads only when the same complete proof covers their inputs. Keep the live layer audit,
checks at the build's input and publication, and independent validation when reopening a past
checkpoint. Use the bridge continuation and snapshot checks to prove same-size corruption,
extra files and an interrupted publication still fail closed.

## Comments

- 2026-11-20: In the first Root snapshot, the stream took 85.271 s, checkpoint identity
  53.454 s, and checkpoint publication 150.416 s. The first build then spent 227.585 s
  reaching the stuck-update refusal. The second snapshot repulled 3.27 GB after 115 MB
  of its content changed. Keep these as separate hypotheses when measuring the candidate.
- 2026-11-20: The exact pre-download snapshot was reconstructed from the capture and verified
  against all 803 phone hashes. On the PC, master profiled at 34.2 s for five full reads during
  snapshot publication, then 46.9 s for six full snapshot reads and APK, engine and delta
  verification before the stuck-update refusal. Re-download planning took 53.9 s, with 39.0 s
  in mixed-package inspection. It selected the same nine files as the phone. Prioritize the
  redundant reads in checkpoint publication and at build entry. Keep the pre-rename audit and
  the read-back of the committed receipt, and rehash after a process restart.
