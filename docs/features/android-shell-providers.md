---
feature: android-shell-providers
status: planned
updated: 2026-10-22
---

# Android patcher shell providers

## Report

**Where it stands (2026-10-22).** Designed, not built. The Android patcher is to offer three shell
providers: Shizuku (today's), Wireless debugging and Root, picked by the user on the home screen. The
work in flight is [`.scratch/shell-providers/`](../../.scratch/shell-providers/spec.md), tickets 01–04;
the root write path is decided in [ADR 0007](../adr/0007-on-a-rooted-phone-write-the-override-layer-directly.md).
Shizuku's own history stays in [android-shizuku-patcher](android-shizuku-patcher.md). Nothing has been
measured on a phone yet, and no coverage count moves.

### Journey log

- Feasibility read of the code: the worker needs only a shell process, and `ShellServiceStarter` already
  starts it without Shizuku, so any provider that can run one shell command can start it — settled by
  reading, not measured (2026-10-22).
- Grilling rounds 1–3 settled the design (2026-10-22).

## [S1] Problem

The Android patcher needs a second app, Shizuku, installed, started and authorized before it can do
anything. The goal is one app instead of two; Shizuku stays as a third provider through early testing.
Full statement: the spec's *Problem*.

## [S2] Design

Lives in the spec's *Implementation Decisions* while the work is in flight, and moves here when the
last ticket lands.

## [S3] Out of Scope

Removing Shizuku; hiding root; wireless debugging without Wi-Fi; restoring the original signature on a
phone with a re-signed normal APK; the Windows patcher. Full list: the spec's *Out of Scope*.
