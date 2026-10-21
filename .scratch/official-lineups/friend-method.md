# A friend's lineup method, checked against our findings

Handoff, 2026-10-21. Tickets `issues/01`–`05` stand; this note says how the friend's method fits them.

## The method as reported

1. Codex scanned the API the game uses to load lineups and found it comes from Ying Di (王者营地, `com.tencent.gamehelper.smoba`).
2. They installed Ying Di on a phone and used USB debugging to work out how to fetch every lineup's details.
3. Claude translated all the lineups with a glossary for this game.
4. They patched everything into the game, about 5–6 MB of text.

## How it lines up with what we measured

- **The official lineups are not from Ying Di.** The Official recommendation tab decodes share codes from a local config bin (`1_F79FB1A213A9DA90`, `ResSeasonAILineupDataBin`) with no request (lab notebook, 2026-10-21). Every name on the screenshot is in that bin.
- **Community lineups are network text.** *More lineups* and master lineups come from the game server (`CSQueryPlayerLineupV2`, `CSQueryLineupDetail`) and a signed CDN link. Submissions go to Ying Di (`CSSubmitCampLineup` returns a Ying Di `DocID`). So Ying Di is a plausible source for the community lineups' text, but the game does not read it from a file. Writing files cannot change what the server sends.
- **So the patched 5–6 MB must have landed in a local file.** Most likely the translated codes went into the official lineup bin (or a bin like it), or community lineups were added to it. Either way it is the same route as tickets 04–05, and it meets ticket 02's question: does the game accept a rewritten bin?
- **Glossary plus Claude** matches ticket 03: our terminology table and the catalog supplement are that glossary.

## What to ask the friend

1. Which file or asset hash did the patch write, and in which package and data layer?
2. Did the Official recommendation tab show the translations? Did *Use* still load the lineup, and did a match play to its end with no QTS-failure popup?
3. Did they recompute a checksum, or did the bin load without one?
4. Did they add lineups the game does not ship (the "all lineups" from Ying Di), or translate only the ones already there?
5. The Ying Di endpoints and the request signing they used, if lineups beyond the shipped ones are wanted.

A yes to question 2 is device evidence that answers ticket 02 for that bin. Record it in the lab notebook with their build and data version before relying on it.

## What changes in the tickets

- **Nothing yet.** Tickets 01–03 run as written.
- **If the friend confirms a working patch,** ticket 02 can start from their asset and method.
- **Fetching community lineups from Ying Di** would be a new effort, not part of these tickets. It uses a third party's private API with a user's account, and adds content the game does not ship. That is the user's call.
