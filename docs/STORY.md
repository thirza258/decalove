# Second Year, Second Chances

The player joins Class 2-B after everyone else's routines have formed. The class is
planning **A Place for Us**, a festival exhibit of postcards about ordinary places that
matter. A blue notebook holds a plan with too many tasks and too few volunteers.

The exhibit gives people reasons to meet and disagree. The story asks whether belonging
means being useful, being understood, or choosing to keep a connection when life changes.
The player can help, question the premise, pursue someone, stay quiet, or refuse a task.
Participation is never a condition for friendship or romance.

## Five chapters

| Arc | Chapter | Dramatic movement |
| --- | --- | --- |
| `prologue` | The blank page | First impressions become one specific invitation. Who has room for a newcomer? |
| `first_weeks` | What we carry | A small task exposes an older obligation. Can help come without a debt? |
| `festival` | Room for the unfinished | The deadline demands a tradeoff between an honest small exhibit and an impossible perfect one. |
| `summer` | Without the timetable | The shared task is gone. Who makes an invitation when there is no convenient excuse? |
| `resolution` | The other side of the card | An earlier promise needs an answer. What connection can survive an ordinary change? |

Each chapter has an introduction, complication and movement toward resolution. The
Director selects that brief from delivered progress and `STEPS_PER_ARC`. A queued run
does not advance the brief. These are writing objectives, not assertions that a task,
confession, or festival outcome has already happened.

## Four reasons to care

- **Aiko** wants to be dependable and fears being a burden. The task list lets her
  competence become a problem: she takes on work faster than she can admit exhaustion.
  Growth means accepting a bounded offer and making promises she can keep.
- **Ren** makes people comfortable while avoiding being seen. An unfinished postcard
  is safer than a finished work someone can judge. Their private plans for art school
  complicate the question of whether leaving a place means abandoning its people.
- **Mika** treats motion as proof that she is fine. A project with seated, shared work
  gives her room to matter without winning a race. Care should respect her independence.
- **Haruto** uses precision and books to keep a little distance. The two sides of a
  postcard give him a way to talk about public words and private meaning without turning
  every line into a speech.

The full cast sheets remain in `api/app/content/highschool.py`. Secrets are private
writer context. Trust and familiarity of at least 45 permit the prompt to suggest a
partial voluntary disclosure; they never establish that disclosure as fact. Existing
dialogue and memories take precedence, including when trust later falls.

## A scene should do something

1. Respond to the player's specific words before changing the subject.
2. Put a concrete want against a small obstacle. A refusal should still reveal something.
3. Develop an existing detail or promise instead of inventing a convenient past encounter.
4. Offer different intentions with different costs, including boundaries and hesitation.
5. Leave the next answer to the player. Buffered prose cannot assume agreement or award
   relationship growth. Transitions and new events belong before the next decision.

The static opening plants the notebook in the library. Its five continuation beats stay
there regardless of the chosen destination; the generated response handles the move.
The final run resolves established threads with a concrete image and contains no menu.
A romance, friendship, or solo ending can each complete the story.

## Where to edit and how to evaluate

`api/app/content/chapters.py` contains the shared premise, chapter questions, pressures,
progression, concrete details and character dialogue. The AI reads the premise and the
Director's current brief. The scripted narrator uses the authored details and voices
alongside its action-specific response and relationship logic.

`api/tests/test_story_stability.py` checks chapter progression, all four authored voices
across all five arcs, neutral tails, ending recovery, model timeouts and memory failures.
The long-playthrough tests check that focused relationships still grow and finish with
an earned partner. Tests establish the playback contract; judging live model prose still
requires reading actual playthroughs for repetition, believable responses and callbacks.

When reviewing a transcript, record the player's exact input, the first response, what
changed in the scene, and the next offered options. A scene fails the story review if
the same response would fit a refusal and an invitation equally well, if a character
knows an undisclosed secret, or if a summary promotes an unchosen option into history.
