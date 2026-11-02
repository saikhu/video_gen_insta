# Production handoff

Draft v1. This records what the story needs and what remains to be demonstrated. No media has been generated for this meerkat concept in this step.

## Creative review

Review the full treatment before turning it into a screenplay. The most useful questions are whether the four personalities are distinct, whether the repair/pressure mystery is understandable, whether the displaced homes make the ending feel earned, and whether the romance feels affectionate within the adventure.

The chosen age pairing, four-character cast, visual direction, English dialogue, ancient protective system and hopeful transformation came from the conversation. New place names, model-sheet details, supporting adult, engineering-like fantasy rules, precise story incidents and sample lines are this draft's proposals.

## Character development

For each principal, make a front, three-quarter, profile and rear model sheet at matched scale. Approve neutral anatomy and fur markings before expressions. Then develop expressions for curiosity, fear, concentration, embarrassment, affection, frustration and relief, with ears and tails included.

Use one approved view per shot reference. A multi-view sheet can accidentally produce multiple characters in a frame. Preserve each individual's own left and right for accessories and markings.

The first visual test should show Tavi and Sera together in three setups: a neutral full-body comparison, a practical interaction at the model bench, and a quiet listening close-up. The same identities must persist through changes of angle and light. A short acting test should include a spoken exchange, a listening reaction and a paw/object interaction before any complete chapter is attempted.

Five speaking roles need distinct voices: Tavi, Sera, Nima, Kesh and Mara. Select them together rather than approving each in isolation. Sera's confidence and Tavi's anxiety should come from performance choices, not caricatured voice effects.

## Visual asset list

| Asset family | Minimum development needed | Continuity dependency |
|---|---|---|
| Four protagonists | approved neutral sheets, relative scale, fur IDs, accessories, expressions | all chapters |
| Mara and residents | one adult turnaround and a small reusable background cast | inhabited home, evacuation, ending |
| Eight locations | establishing view plus a simple plan of connecting entrances | stable geography in WORLD.md |
| Gallery mechanism | three alignments, fixed rim/sockets, warning seams and completed latch | clues in 1–3; rescue in 7–8; unload in 12 |
| Distribution controls | consistent test relief, route handle, interlock and advancing marker | discovery, decision and climax |
| Western outlet | sealed/open states, high catch, brake drum and sharp anchor | cause, preparation and release |
| Personal map | original face and amended face, same blot and line | romance in 10, 15 and 16 |
| Kesh's route cloth | clean, marked, torn brake-pad and patched states | logistics arc |
| Tavi's model and clamp | readable function and scale compatible with pouch | early partial theory and later correction |
| Settlement states | inhabited lower lane, evacuation, relief water and upper resettlement | meaningful transformation |

## Image, motion and edit direction

Default delivery proposal: a clean 9:16 master for each release and a continuous 9:16 film assembled from the same shots. A separate widescreen movie would need its own shot plan or deliberately wider source framing; a crop cannot recover missing picture. Final aspect-ratio strategy can be chosen during visual development.

Use motivated light and consistent fur response: warm court daylight, cool water reflections underground, restrained amber control light, late-afternoon release and a distinctly fresh next morning. Keep magic localized enough to preserve expressions and geography.

Plan roughly 10–18 shots per 90-second chapter as an initial editorial allowance. Use quicker cuts for water and mechanism action, and longer listening shots in chapters 10 and 15. Adjust after the animatic; this is not a rule requiring a new image every few seconds.

Use wide geography shots before crossings and split-group action. During the climax, the two active stations are Tavi/Nima at the distribution chamber and Sera/Kesh at the outlet. Brief community reaction shots confirm the plan's outcome. The two stations are connected by the already-established tube.

Maintain a clean movie cut. Put episode numbers, platform copy, optional recaps, end screens and credits in separate release packaging. The 24:00 board below budgets story picture, including the next-morning transition. Packaging or final credits may add time and must remain within the user's 20–30-minute target for the finished movie.

## Sound and dialogue

Build the three-note warning and quieter return tick as consistent, recognizable sound assets. They carry story information. Test them on a phone speaker and ensure music or dialogue does not mask the tick in chapters 8 and 14.

Dialogues need speaker IDs, line-level timing, overlaps, breathing and listening space. Effects include wind, cloth, paws on sand/stone, rope under load, the outlet brake, moving stone and water at changing distances. Let locations continue acoustically across edits.

A future score can support wonder, suspense and intimate scenes, with the warning sequence clearly audible. Score cues, voice choices and any music generation remain to be developed. Spoken words from a video model should not replace the planned character dialogue.

## Existing pipeline fit

Repository inspection in this task establishes these adaptation needs:

| Current behavior | Needed for this movie |
|---|---|
| `Scene` stores narration text and shots, with no character speaker/timed dialogue contract | dialogue lines and speaker identities, performance holds and explicit action timing |
| TTS synthesizes each scene's narration through one configured backend/voice | per-character voice selection, line caching and a mixed dialogue track |
| Keyframe backends accept prompts/seeds; inspected code does not pass character reference images into these workflows | verified identity conditioning and shot-specific approved reference selection |
| Jobs hold individual scene plans | shared series bible, chapter order, incoming/outgoing continuity and movie assembly |
| Current reel config targets 45–95 seconds | topic-specific 60–120-second release support; chapter 14 targets 100 seconds; separate 20–30-minute movie export |
| Face-rejection settings are forced on in machine profiles | move depiction policy to the topic before rendering expressive character faces, preserving history-track restrictions |
| QA checks technical file/audio properties | additional visual review of identity, dialogue synchronization, continuity, geography and dramatic performance |

These are implementation requirements, not completed features. The structured story record is kept under docs, outside active topic configuration, so current generation commands do not silently treat it as a supported track.

## Production sequence after story review

1. Approve or revise the treatment and character designs.
2. Write the screenplay with actual English dialogue and timed actions; retain this chapter board as the pacing reference.
3. Approve character references, environment layouts and prop states.
4. Test two-character performance, voice differentiation, identity conditioning and object interactions.
5. Build a rough full-film animatic to check the actual runtime, mechanism clarity and relationship pacing.
6. Add the necessary dialogue/series support to the pipeline, then finish a complete pilot chapter.
7. Render the remaining chapters from the accepted animatic, maintaining the shared continuity record.
8. Assemble the movie from the same approved shots and audio; verify both release cuts and continuous playback.

The current development package has no measured rendering time, generation budget, finished animatic or audience test. Creative success and actual runtime need those later checks.
