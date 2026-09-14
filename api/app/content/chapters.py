"""Second Year, Second Chances: one shared project, four different reasons to care.

The AI uses these as scene briefs. The offline narrator uses the same concrete details
and character voices, so a provider outage does not turn the story into generic filler.
None of these outlines are completed events; only delivered prose establishes canon.
"""

from app.content.world import Chapter


STORY_PREMISE = (
    'Class 2-B is making a small festival exhibit called "A Place for Us": handwritten '
    'postcards about ordinary places that matter to someone. A blue notebook holds the '
    'unfinished plan. The real question is whether belonging means being useful, being '
    'understood, or choosing to stay in touch when life changes. The player may help, '
    'question the project, pursue a personal conversation, or decline. The exhibit is '
    'a shared pressure, never a compulsory quest or proof of a relationship.'
)

CHAPTERS = (
    Chapter(
        id="prologue", title="The blank page",
        question="Where can a newcomer belong without pretending to be someone else?",
        pressure="The festival proposal needs a subject; everyone has an opinion and nobody has signed up.",
        progression=(
            "Introduce the blue notebook and one person's reason to care. Keep the invitation small.",
            "Let two definitions of belonging conflict. Find out what the player actually wants.",
            "Leave one specific invitation open. Carry an accepted task or a refusal into the next chapter.",
        ),
        details=(
            'A blue notebook has "A Place for Us" written on its cover, with a question mark squeezed in afterward.',
            "The sample postcard shows an empty bench. Someone has pencilled in: 'Who were you waiting for?'",
            "The volunteer column is blank. The column headed 'Things we need' runs onto a second page.",
            "A corner of the festival notice has been folded into a tiny triangle, then flattened again.",
            "On the last page, there is room for a place that nobody else has thought to name.",
        ),
        lines={
            "aiko": ("It is a proposal. The question mark is Ren's contribution.", "One postcard each. Something ordinary. We do not need to impress the whole school.", "You can look without putting your name down. I should have said that first."),
            "ren": ("An exhibit about places. Riveting. Unless we put the embarrassing stories on the back.", "I'd draw the vending machine that steals my coins. Longest relationship I've had.", "You get a blank card too. No tragic origin story required."),
            "mika": ("The bench by the track. Easy. Best place to eat bread when nobody's timing you.", "What? Places can be good because you stop there. I know how stopping works.", "Pick somewhere you actually like. We'll survive if it isn't the school."),
            "haruto": ("A postcard has two sides. People keep forgetting that.", "The front is what you show everyone. The back is usually for one person.", "Leaving it blank is an answer. A temporary one, perhaps."),
        },
        choices=("Ask {target} who the postcard would be for.", "Offer to help {target} with one small part.", "Tell {target} you are not ready to sign up."),
    ),
    Chapter(
        id="first_weeks", title="What we carry",
        question="Can accepting help feel different from owing someone?",
        pressure="The exhibit needs real work, and small tasks expose obligations the cast already carries.",
        progression=(
            "Return to an actual earlier offer or refusal. Show who is doing the unglamorous work.",
            "Make one task conflict with a personal obligation. Offer help without assuming access to a secret.",
            "Let somebody set a boundary or share responsibility. Keep track of the exact promise made.",
        ),
        details=(
            "The supply estimate counts every sheet twice: once for the final card, once for getting it wrong.",
            "A shopping receipt is tucked into the blue notebook. The cheapest item has three alternatives beside it.",
            "Two names share a line on the task list. Most of the other lines have only one.",
            "A practice card has a beautiful border and nothing in the middle.",
            "The notebook will not close around all the loose pages. Its elastic strap has begun to fray.",
        ),
        lines={
            "aiko": ("Sorting is useful. You do not have to take the whole stack.", "I keep writing 'I'll do it' because it is faster than explaining how.", "That is not the same as having time. Apparently."),
            "ren": ("I've made four borders. At this rate we'll exhibit a very confident rectangle.", "Once something is finished, people can decide what they think of it.", "No, don't tell me it's brilliant yet. Tell me which bit you looked at first."),
            "mika": ("Seated jobs count. I'm announcing that before anybody looks surprised.", "I can cut the cards. Someone else can race across the school for tape.", "Don't make that face. Delegating sounds much better than being sensible."),
            "haruto": ("I can check the words. I cannot choose what somebody meant.", "People hand you both jobs if you do not separate them.", "One page at a time is a perfectly respectable speed."),
        },
        choices=("Ask {target} which task can wait.", "Offer to share one task with {target}.", "Tell {target} honestly how much time you have."),
    ),
    Chapter(
        id="festival", title="Room for the unfinished",
        question="Will they show something honest, or hide it until it is perfect?",
        pressure="The festival is approaching. There is space for a smaller exhibit, not time for a perfect one.",
        progression=(
            "Bring an established plan up against the deadline. Do not invent a betrayal to create tension.",
            "Force a practical tradeoff: scale back, share unfinished work, or let a task go. The player chooses their part.",
            "Show the cost and the small payoff of the chosen approach. An imperfect result can still matter.",
        ),
        details=(
            "The final layout leaves a deliberate gap between the postcards. There are fewer cards than the first sketch promised.",
            "The blue notebook lies open to a list headed 'Enough'. It is much shorter than the original list.",
            "One sample card still has an eraser mark through its neatest sentence.",
            "The printed festival schedule has no space for an extra day of preparation.",
            "A handwritten caption fits where the elaborate title was supposed to go.",
        ),
        lines={
            "aiko": ("We can make it smaller. I know that is allowed. I wrote the rules.", "I would like to stop adding things just because I can see that they need doing.", "Which part would you miss if it weren't there? That is probably the part to keep."),
            "ren": ("If I call the pencil marks a stylistic choice, do I get to leave them?", "I'm joking. Mostly. I like that you can see where I changed my mind.", "Maybe the rough edge is the interesting bit. Horrifying development for my work ethic."),
            "mika": ("We are not sprinting through the last hour. That is how things get dropped.", "I vote we keep the crooked one. Somebody worked hard on that crooked one.", "Finishing together still counts as finishing."),
            "haruto": ("The caption does not have to explain the whole thing.", "It can leave someone a reason to ask.", "A gap is not always something you have failed to fill."),
        },
        choices=("Ask {target} to keep the imperfect card.", "Offer to help {target} simplify the plan.", "Tell {target} which part matters to you."),
    ),
    Chapter(
        id="summer", title="Without the timetable",
        question="Who seeks someone out when there is no shared task making it easy?",
        pressure="The festival deadline is over. Empty hours and plans beyond school make invitations more personal.",
        progression=(
            "Acknowledge what actually happened at the festival. Show the absence of the old routine.",
            "Give the focused character an independent plan. Reveal private background only if trust and history support it.",
            "Make room for a voluntary invitation or an honest distance. Do not treat staying nearby as the only loving choice.",
        ),
        details=(
            "The festival date in the blue notebook is crossed out. The next page has no timetable.",
            "A spare postcard is small enough to fit in a pocket without folding.",
            "The address lines on the back look more demanding than the blank space on the front.",
            "The old supply receipt has faded at its creases. The pencilled notes are still legible.",
            "There is no deadline beside the next empty box. For once, leaving it empty is possible.",
        ),
        lines={
            "aiko": ("There is nothing to organise this afternoon. I checked twice.", "It turns out 'What would you like to do?' is a difficult question without a list.", "I could start with tea. That is a plan small enough to mean."),
            "ren": ("Postcards are a suspiciously practical invention. Pictures for people bad at saying things.", "You can like a place and still wonder what is beyond it.", "That sounded rehearsed. Pretend I said something irritating instead."),
            "mika": ("A walk can have a bench in the middle. Several benches. A whole bench strategy.", "I want an afternoon that nobody describes as a personal best.", "Yes, I'm still competitive. I'll be exceptionally good at having a day off."),
            "haruto": ("Writing 'nothing happened' still tells someone you were thinking of them.", "I used to think a letter needed news to justify itself.", "Perhaps the address is reason enough."),
        },
        choices=("Invite {target} to spend an afternoon together.", "Ask {target} about plans beyond school.", "Give {target} room to make their own plans."),
    ),
    Chapter(
        id="resolution", title="The other side of the card",
        question="What will they choose to keep, and what can they let change?",
        pressure="Routines will change again. Earlier promises need an answer, not a larger declaration.",
        progression=(
            "Return to a concrete detail from delivered history. Resolve one outstanding promise without inventing its outcome.",
            "Let closeness or distance show in a practical choice. Respect friendship as fully as romance.",
            "Prepare an earned goodbye or next meeting. End on the notebook or postcard only if it became part of this playthrough.",
        ),
        details=(
            "The blue notebook is thicker now. Its last page is still mostly empty.",
            "The question mark on the cover has almost rubbed away; its dent remains in the cardboard.",
            "A spare postcard has room for a few ordinary sentences, and no more.",
            "The elastic strap leaves a line across the cover when it is lifted.",
            "There is no box on the final page for a perfect answer.",
        ),
        lines={
            "aiko": ("I would rather make a promise I can keep than a beautiful one.", "One afternoon. No committee. I think I could manage that.", "You do not have to earn the invitation by being useful."),
            "ren": ("I could write something profound on the back. Ruin my reputation completely.", "Or I could tell the truth in a normal-sized sentence.", "I think I'd like to try that."),
            "mika": ("I'm not making a speech. Nobody here trained for a speech.", "I want there to be another afternoon. It doesn't have to look like this one.", "That's all. Quite a lot, actually."),
            "haruto": ("The back of the card is still there when you turn it over.", "You do not lose one side by letting someone see the other.", "That is all the literary analysis I have for today."),
        },
        choices=("Tell {target} what you want to keep in touch about.", "Ask {target} what an ordinary next meeting could look like.", "Thank {target} without making a promise you cannot keep."),
    ),
)
