export interface Workshop {
  reading: string[];
  annotations: string[];
  practice: string[];
  pitfalls: string[];
  deliverable: string;
  revision: string;
}

/** Original craft notes. These are exercises and useful techniques, not universal rules. */
export const WORKSHOPS: Record<string, Workshop> = {
  "story-want": {
    reading: [
      "Separate the character's want from their need. A want gives the scene a visible direction: get a signature, hide a mistake, catch a train. A need concerns the way they relate to themselves or others: accept help, tolerate uncertainty, tell the truth. A character does not have to understand that need. The friction between the two gives an ordinary task emotional weight.",
      "Build the obstacle from the situation and the character's habits. If Noor handles every problem by making a better plan, an estranged brother who wants an apology makes planning insufficient. You do not need a villain or a catastrophe. A reasonable refusal can be stronger than an arbitrary disaster because it forces the protagonist to engage with another person's agency.",
      "Stakes are the meaning of an outcome, not just its size. Losing a shop might mean debt, the disappearance of a family ritual, or proof of a private fear. Choose the consequence your character would notice first. Then plant evidence of it before asking the reader to care about failure.",
    ],
    annotations: ["'Before the shop closes on Friday' creates a limit that can affect choices.", "The signature is an observable goal; an abstract wish to become confident is harder to dramatise.", "The unrehearsed apology suggests why this particular person cannot solve the task easily."],
    practice: ["List one external want and one unspoken emotional need.", "Write the obstacle from the other person's point of view. Why is their resistance reasonable?", "Choose one object that makes the stakes visible: a lease, an empty shelf, a returned key.", "Draft the first 200 words, beginning close to an attempt. End with a small refusal.", "Read it back without your notes. Can a reader infer the goal from the scene itself?"],
    pitfalls: ["Opening with a biography before the character tries anything.", "Giving the protagonist a goal while every important event happens to them by coincidence.", "Calling something important without showing its personal cost."],
    deliverable: "A two-sentence premise and a 200-word opening with a goal, resistance, and a specific stake.",
    revision: "Strengthen the protagonist's visible goal and personal stakes. Preserve the setting and established facts. Let resistance come from a believable competing want.",
  },
  "story-cause": {
    reading: [
      "A scene can be built around goal, resistance, response, and a changed situation. Those parts need not appear as four obvious beats, and a scene can end in partial success. The key is that the result changes what someone can do next. A successful lie may solve the immediate problem while making the next honest conversation harder.",
      "After a consequential event, give the protagonist enough space to interpret it. Reaction becomes story movement when it leads to a decision: the person feels betrayed, considers two imperfect options, and chooses a course of action. Without that bridge, a plot may move quickly while the character seems absent from it.",
      "Escalation does not require a larger threat in every chapter. You can increase intimacy, reduce available time, expose a contradiction, or make a familiar tactic stop working. Varying the kind of pressure keeps a story from becoming a sequence of louder versions of the same argument.",
    ],
    annotations: ["The promise creates an obligation that Noor's next action must answer.", "Missing the bus follows from her decision to stay, so the inconvenience belongs to the story's causal chain.", "Selling the oven contradicts keeping the shop open; the return reveals a new problem rather than repeating the old one."],
    practice: ["Put five possible scenes on separate lines.", "Between each pair, write what changed and why the next scene follows.", "Where the link is only 'and then', add a decision or remove the scene.", "Include a reaction beat before one major change of plan.", "Draft the transition between two scenes so a reader can follow the cause without an explanatory recap."],
    pitfalls: ["Using coincidence repeatedly to rescue the protagonist.", "Mistaking activity, travel, or new locations for change.", "Ending every scene with a disaster until consequences stop feeling distinct."],
    deliverable: "A five-scene causal outline and one drafted transition.",
    revision: "Identify the decision that connects each scene to the next. Strengthen weak causal links without adding unrelated incidents or changing delivered events.",
  },
  "story-ending": {
    reading: [
      "Look back at what the opening teaches the reader to ask. Will these people reconnect? Will the hidden truth be told? Can the protagonist finish a task without repeating an old harm? An ending feels earned when the final choice addresses that pressure, even if the answer is ambiguous or the external goal fails.",
      "Prepare the means of resolution before you use them. If a skill, object, piece of information, or secondary character makes the ending possible, give it a meaningful earlier place in the story. Preparation is not the same as making the outcome obvious: the reader can know that Noor can change a contract without knowing whether she will accept the cost.",
      "Distinguish the climax from the aftermath. The climax is the choice or confrontation that settles the central pressure. The aftermath lets us see what living with that outcome looks like. A quiet final image can work because the preceding action has already supplied its meaning.",
    ],
    annotations: ["Crossing out the debt clause changes the practical arrangement, so the emotional shift has a consequence.", "'You can visit without signing' separates affection from usefulness.", "The second cup offers a future possibility; it does not pretend the brother has forgiven everything."],
    practice: ["Write the story's opening question in one sentence.", "List two possible answers, including one that costs the protagonist the original goal.", "Choose an earlier detail that could make the final choice possible.", "Draft the choice, its immediate cost, and a short aftermath.", "Remove the final explanatory paragraph and check whether the image still carries the meaning."],
    pitfalls: ["Introducing a convenient solution in the final scene with no preparation.", "Declaring a relationship repaired without an action that earns the change.", "Resolving every minor uncertainty until the ending has no breathing room."],
    deliverable: "A 400-word ending with a prepared choice, a consequence, and a final image.",
    revision: "Make the final choice answer the opening pressure through action. Keep the cost visible and remove explanations that merely restate the final image.",
  },
  "dialogue-intention": {
    reading: [
      "Before writing a conversation, decide what each person hopes will be different when it ends. One may want a promise; the other wants to postpone a decision. Those intentions shape what they hear as well as what they say. A practical question can sound like an accusation to someone expecting blame.",
      "Treat a line as a tactic rather than a package of information. 'You kept my key' tests an explanation and makes an accusation. If the response fails, the next line should adapt: ask directly, joke, bargain, change the subject, or withdraw. Repeated words can be purposeful, but repeated tactics with identical results usually stall a scene.",
      "Real conversations contain filler, but fictional dialogue selects the parts that carry voice, pressure, or connection. Greetings and pauses are useful when their form matters. A warm greeting after a betrayal does something different from a neutral greeting between strangers. Keep the social texture that changes our reading.",
    ],
    annotations: ["The key gives both characters a safe concrete subject.", "Jules turns the accusation into a tentative invitation by imagining a return.", "'For the key' narrows the meaning, and the final line shows Jules accepting the boundary."],
    practice: ["Write each speaker's desired outcome in a private note.", "Draft twelve spoken turns without narration.", "Beside each line, name its tactic and the response it receives.", "Replace two repeated tactics with a change of approach.", "Add only the action beats needed to show a shift in power, attention, or willingness."],
    pitfalls: ["Letting characters ignore the specific words they just heard.", "Making every reply witty at the expense of the emotional situation.", "Having characters explain shared history solely for the reader."],
    deliverable: "Twelve dialogue lines with changing tactics and a visible relational turn.",
    revision: "Make each reply respond to the previous line and give each speaker a distinct intention. Change tactics where the conversation repeats itself.",
  },
  "dialogue-voice": {
    reading: [
      "Build a voice from a few interacting choices: what the person notices, how directly they ask, the length of their phrases, and the vocabulary their life makes available. A character who repairs equipment might use precise concrete language; under emotional pressure, that precision might become a way to avoid naming a feeling.",
      "Voice changes with audience and circumstances. The same person can speak differently to a sibling, a supervisor, and a stranger without becoming inconsistent. Track what they are protecting in each relationship. Formality, interruption, jokes, or unusual politeness can reveal a shift more subtly than a new accent or catchphrase.",
      "Give similar characters meaningful differences without making anyone a caricature. Avoid relying on stereotypes about age, background, or occupation. One distinctive concern and a particular rhythm can do more than exaggerated dialect. Read their lines aloud and ask whether the pattern feels like a person making choices.",
    ],
    annotations: ["Ada notices a functional hazard first; Leon imagines the appearance of the room.", "Leon's 'we could' offers an accommodating solution rather than a direct rebuttal.", "Ada's final line returns to her practical concern while responding precisely to the flowers."],
    practice: ["Make a voice card for two characters: attention, rhythm, vocabulary, and avoidance.", "Write the same request in each voice without changing its meaning.", "Draft ten dialogue lines where those two approaches create friction.", "Rewrite two lines as if the characters were overheard by someone they respect.", "Hide the names and check whether the voices remain distinguishable without becoming repetitive."],
    pitfalls: ["Assigning everyone the author's favourite phrasing.", "Using a catchphrase in every exchange as a substitute for intention.", "Keeping a voice so rigid that it cannot respond to fear, tenderness, or context."],
    deliverable: "Two voice cards and a conversation that survives the no-name test.",
    revision: "Differentiate the speakers through attention, rhythm, and vocabulary while preserving their goals. Avoid new catchphrases, exaggerated dialect, and stereotyped voices.",
  },
  "dialogue-subtext": {
    reading: [
      "Subtext needs enough context to be readable. If we know a person wants company, an offer of tea can carry an invitation they are afraid to make directly. If the scene supplies no reason for the offer to matter, withholding every feeling may produce vagueness rather than depth. Establish the want, then let speech approach it indirectly.",
      "Action beats can pace a response and alter its meaning. A person who washes an already clean cup may be avoiding eye contact; a person who puts the cup within reach may be making an offer. Keep the action physically possible and related to the setting. Repeated sighs and clenched fists quickly stop communicating anything specific.",
      "Silence is an action when someone could answer and chooses not to, or when the delay changes the other person's next move. Show what fills the interval: a task continuing, a chair moved, a sentence abandoned. Allow direct speech at turning points too. A plain answer after a scene of evasion can have unusual force.",
    ],
    annotations: ["'I'm fine' offers a surface answer that may be socially convenient.", "Moving the cup reverses an earlier act of putting it away, making the wish for company visible.", "The warm kettle creates an invitation that the other character can accept or decline."],
    practice: ["Write the unsaid request in plain language before drafting.", "Give the speaker a task and a reason direct asking feels difficult.", "Write six spoken turns with three meaningful action beats.", "Let the listener misread one signal, then notice a more specific one.", "End with either a direct request or a deliberate refusal to ask, and show its consequence."],
    pitfalls: ["Explaining the hidden emotion immediately after showing it.", "Making every line mysterious so the reader cannot locate the actual conflict.", "Using actions that decorate a pause but never affect the exchange."],
    deliverable: "A scene of indirect asking with readable subtext and a consequential silence.",
    revision: "Strengthen the unsaid request using specific actions and context. Remove redundant emotional explanations while keeping the surface conversation understandable.",
  },
  "theme-question": {
    reading: [
      "A thematic question is a tool for choosing meaningful pressure. 'Loyalty' names a subject; 'When does loyalty become complicity?' suggests scenes where protecting one person harms another. The question should connect to what your characters actually want, rather than arriving as an argument unrelated to the plot.",
      "Let the draft investigate instead of proving an answer you have already made too easy. Give the protagonist a belief that works in some situations and fails in others. Their first answer can be understandable but incomplete. As circumstances change, the same value may require a different action.",
      "Theme can remain subtle. You do not need characters to debate the question aloud. A withheld letter, a refused favour, or a promise with a condition can place values in conflict. Readers infer a story's concerns from the choices it makes important and the consequences it allows those choices to have.",
    ],
    annotations: ["The promise makes silence a form of loyalty rather than simple cowardice.", "Harm to someone else introduces a competing responsibility.", "The question leaves room for context: whose secret, what harm, and what alternatives exist?"],
    practice: ["Write your topic as one word, then generate three questions about it.", "Choose the question with the strongest connection to the protagonist's immediate goal.", "List a defensible answer and a situation where it becomes costly.", "Design a scene with two imperfect choices and no convenient third solution.", "Draft the choice without using the abstract words in your thematic question."],
    pitfalls: ["Treating theme as a slogan repeated by the narrator.", "Giving one answer all the benefits and the other all the harm.", "Pausing the plot for a discussion that does not change anyone's next action."],
    deliverable: "One thematic question, two defensible answers, and a scene that tests them.",
    revision: "Express the thematic conflict through a costly practical choice. Give both values a fair case and remove any speech that simply states the lesson.",
  },
  "theme-characters": {
    reading: [
      "A character can embody a belief without always behaving consistently with it. Someone who values independence may still want to be asked to stay. That contradiction creates material for story if it has a cause: pride, fear, habit, or a past experience. Contradiction becomes arbitrary only when it exists to move the plot with no human reason.",
      "Make the counterargument attractive. Give the person expressing it something useful to offer and something real to lose. If the brother's wish to keep the workshop open preserves jobs and a family connection, the reader can understand him even when his demand is unfair. Sympathy and agreement are different things.",
      "Pressure should reach both positions. Let the protagonist's approach cause a failure, and let the other person's approach solve a problem. The story can still arrive at a clear answer; that answer gains force when it survives a credible challenge instead of defeating a straw opponent.",
    ],
    annotations: ["Training makes leaving constructive, rather than merely selfish.", "The workshop gives staying a cost and a benefit that other people can feel.", "The secret job application exposes the brother's competing desires and opens a more difficult conversation."],
    practice: ["Write each character's answer to the thematic question.", "Give each answer an origin in a specific experience, not a generic personality label.", "List one benefit and one cost of each approach.", "Draft a conversation where one person reveals a contradiction in their own position.", "Let the response affect a practical decision rather than ending with mutual speeches."],
    pitfalls: ["Making the counterargument foolish so the protagonist can win easily.", "Using personal trauma only as a shortcut explanation for every belief.", "Reducing a character to the philosophical position they represent."],
    deliverable: "Two belief profiles and a scene in which both positions are tested.",
    revision: "Give the opposing character a credible concern and a useful insight. Preserve the disagreement while revealing a contradiction in each person's position.",
  },
  "theme-motif": {
    reading: [
      "A recurring detail works best when it already belongs to the story's physical world. It can be used, lost, repaired, refused, or passed between people. Those actions let meaning accumulate naturally. An object introduced only to symbolise a feeling may feel less alive than an ordinary tool that becomes important through use.",
      "Plan variation rather than identical repetition. The first appearance can establish a habit; the next can expose its cost; the last can alter it. This is one possible pattern, not a requirement for every story. The important question is what the reader knows at each return that they did not know before.",
      "Resist explaining every connection. Place the detail where the character's action makes the change legible, and give the reader enough separation between appearances to notice its return. A motif can also remain unresolved when the story is about uncertainty; it need not become a tidy symbol with one fixed meaning.",
    ],
    annotations: ["Correcting the watch makes time a form of control in the first encounter.", "Stopping the questions shows distance through an absence of the earlier habit.", "Turning the watch down changes its use, giving patience a physical form."],
    practice: ["List five useful objects or recurring actions already present in your draft.", "Choose one connected to a relationship or conflict.", "Write three appearances with a different owner, use, or emotional context each time.", "Make at least one appearance affect what someone can do in the scene.", "Remove any sentence explaining what the object symbolises and assess whether the pattern remains clear."],
    pitfalls: ["Repeating a symbol without changing its context.", "Adding so many motifs that none receives meaningful attention.", "Forcing an object into a scene where no character would naturally notice it."],
    deliverable: "Three linked appearances of one motif, each doing practical and emotional work.",
    revision: "Develop the recurring detail through changed use or context. Keep it physically useful in the scene and remove explicit explanations of its symbolism.",
  },
  "novel-promise": {
    reading: [
      "Think of a book's promise as an expectation about the experience ahead. The first chapter's questions, narrative voice, and attention tell readers what to look for. If the opening spends its energy on an intimate relationship, a later investigation can fit, but the relationship should continue to matter to how that investigation unfolds.",
      "Choose a scope you can sustain. A novel usually needs room for repeated attempts, discoveries, and changing relationships. That room can come from one compact setting or an expansive world. More locations and lore do not automatically create a stronger book; a central problem with several consequential approaches often provides a clearer spine.",
      "Point of view is part of the promise. A postmaster may know everyone's routines but misunderstand their private lives. That combination creates both access and limitation. Ask what your chosen perspective lets the reader discover gradually, and what important scenes it would prevent you from showing directly.",
    ],
    annotations: ["Thirty days provides a manageable time frame for a book-length task.", "Seven returned letters suggest varied encounters connected by one practical goal.", "Conflicting memories create an ongoing question that can change as evidence accumulates."],
    practice: ["Describe the feeling or curiosity you want a reader to carry between chapters.", "Write a central problem that can survive more than one attempt to solve it.", "Choose a viewpoint and list what it knows, guesses, and cannot access.", "Draft a 100-word pitch without listing the entire plot.", "Write the opening page and check whether it actually offers the experience in the pitch."],
    pitfalls: ["Promising a different kind of book in the opening merely to create a hook.", "Confusing a large world with a sustainable story problem.", "Choosing a viewpoint that conveniently knows every fact the plot needs."],
    deliverable: "A reader promise, a short book pitch, and an opening page aligned with both.",
    revision: "Align the opening with the book's central promise. Establish a specific ongoing question through the chosen viewpoint without front-loading background information.",
  },
  "novel-outline": {
    reading: [
      "A chapter map helps you see how the main problem develops across a longer work. For each chapter, record the attempted goal, new resistance, turning point, and changed situation. A chapter can contain several scenes, but the map should reveal why this particular stretch of the book belongs where it does.",
      "Track subplots by their relationship to the main story. A friendship, family responsibility, or professional problem earns space when it pressures a choice, complicates a value, or changes what support is available. Subplots can have their own pleasures and rhythms, but they should not simply pause the central story whenever it becomes difficult.",
      "Use an outline flexibly. Discovery during drafting may reveal that a planned reversal no longer fits the characters. Revise the map to reflect what is actually on the page. A useful outline makes cause and effect easier to examine; it should not require characters to act against their established intentions to reach a scheduled event.",
    ],
    annotations: ["The mill scene gives the protagonist information they did not have on arrival.", "That information creates the purpose of the school visit.", "The request to destroy the letters changes the moral and practical meaning of the original delivery task."],
    practice: ["Mark the opening disruption, a central reversal, and a possible final decision.", "Write six chapter cards with a goal, obstacle, turn, and consequence.", "Add a subplot to three cards and identify the pressure it adds to the main choice.", "Check for chapters that end in the same emotional position in which they began.", "Draft one chapter, then update the outline using only what you actually established."],
    pitfalls: ["Outlining only locations or topics rather than changes.", "Adding a subplot that never affects the protagonist's decisions.", "Forcing a planned twist after the draft has made it implausible."],
    deliverable: "Six chapter cards, a connected subplot, and an updated map after one drafted chapter.",
    revision: "Strengthen the causal link between chapter endings and subsequent goals. Connect the subplot to a meaningful decision and preserve character motivation.",
  },
  "novel-draft": {
    reading: [
      "Keep two separate kinds of notes: established continuity and possible future material. Established continuity records what the reader has seen, including chronology, location, promises, injuries, possessions, and character knowledge. Future material records plans you may change. Mixing them can cause a later chapter to refer to an event that was never actually written.",
      "A drafting routine should reduce the cost of beginning. Decide on a small unit you can reliably complete: one exchange, twenty minutes, or a scene attempt. At the end, leave a specific next action rather than a vague instruction to continue. Progress is easier to resume when the next problem is already visible.",
      "For AI assistance, provide a compact continuity note plus the current passage. State which information is private to the writer and which characters know it. After accepting a suggestion, update continuity from the text you kept, not from the suggestion's summary. An attractive proposal is not part of the manuscript until you choose it.",
    ],
    annotations: ["Seeing an unopened envelope establishes access to the object, not knowledge of its contents.", "'Planned for chapter 5' prevents a future possibility from masquerading as a completed event.", "Naming who knows the sender's identity gives a continuation a usable knowledge boundary."],
    practice: ["Create headings for established facts, character knowledge, open promises, and future possibilities.", "Fill them from the manuscript rather than from memory.", "Choose a drafting target that fits one ordinary session.", "Draft the next scene and check every callback against the continuity note.", "Update the note only after deciding which new material to keep."],
    pitfalls: ["Treating an outline as proof that its events have happened.", "Giving every character the writer's complete knowledge.", "Setting a routine so ambitious that missing one session makes returning difficult."],
    deliverable: "A continuity notebook, a realistic drafting routine, and one checked continuation.",
    revision: "Check this continuation against established facts and character knowledge. Flag unsupported callbacks; do not promote future plans into completed events.",
  },
  "narration-pov": {
    reading: [
      "Separate the narrator's position from the grammatical person. First person uses 'I', but can be reflective or immediate. Third person can remain close to one mind or speak from a broader perspective. Choose what kind of access the scene needs, then make changes of access intentional enough for the reader to follow.",
      "Narrative distance controls how close the prose feels to experience. A distant sentence might summarise a difficult winter; a close sentence might notice one cold button under a thumb. Moving closer at a decision can intensify attention, while moving outward can help with transitions. Neither distance is inherently better.",
      "In a limited viewpoint, distinguish observation, interpretation, and knowledge. Mara can see a missed button, infer nervousness, and be wrong about its cause. That uncertainty can create tension without withholding facts unfairly. If the prose states the other person's hidden wish as fact, it has changed its access and should do so deliberately.",
    ],
    annotations: ["The coat button supplies something Mara can actually observe.", "'Perhaps' marks an interpretation as uncertain rather than confirmed knowledge.", "Her inability to ask brings the narration back to the one interior experience the scene has chosen to enter."],
    practice: ["Choose a viewpoint and tense, and write the limits of what the narrator can know.", "Draft the departure scene from close range.", "Underline every claim about the other person's private feelings.", "Replace unsupported claims with evidence, inference, or a direct question.", "Rewrite the first two sentences from a greater distance, then move deliberately closer at the moment of choice."],
    pitfalls: ["Changing minds mid-paragraph without establishing an omniscient approach.", "Using 'she saw' or 'he felt' in every sentence when direct perception would be clearer.", "Treating a viewpoint character's assumption as an objective fact."],
    deliverable: "A 250-word scene with consistent access and one deliberate change of narrative distance.",
    revision: "Maintain the chosen viewpoint and tense. Distinguish observable details from guesses about other minds, and move closer at the consequential choice.",
  },
  "narration-detail": {
    reading: [
      "Description is selective attention. A person entering a room to apologise notices different things from someone searching it for evidence. Let the immediate goal shape the details you include. This makes a setting feel experienced rather than inventoried and gives description a reason to occupy the reader's attention.",
      "A detail can establish the world, reveal history, and affect movement at once. The stubborn drawer tells us about the kitchen's condition; opening it automatically reveals a learned habit; standing still afterward suggests that the familiar action now hurts. Several meanings arise from one continuous physical event.",
      "Specificity does not require unusual vocabulary. A plain noun attached to a precise action often carries more than several emotional adjectives. Use sensory details when they contribute to orientation or meaning. A smell that triggers a mistaken expectation may matter more than a paragraph listing every colour in the room.",
    ],
    annotations: ["The drawer's resistance makes the setting physical rather than decorative.", "Opening it without thinking implies a repeated earlier habit without a flashback.", "The spoons interrupt the task and let the familiar room become emotionally unfamiliar."],
    practice: ["Give the viewpoint character a practical reason to enter the room.", "List five possible details, then choose only three they would notice for that reason.", "Make one detail alter an action.", "Write a short paragraph in which a habit reveals history without explaining the whole history.", "Remove generic emotional adjectives and see whether the physical sequence still communicates feeling."],
    pitfalls: ["Describing every object with equal emphasis.", "Using atmosphere words where the reader needs concrete orientation.", "Stopping an urgent action for details the viewpoint character would not notice."],
    deliverable: "A 200-word description that also advances a task and reveals a relationship to the place.",
    revision: "Replace generic description with details selected by the viewpoint character's goal. Let one physical detail change their action and imply history.",
  },
  "narration-pace": {
    reading: [
      "Pacing concerns how much attention a moment receives, not only how fast events happen. A short paragraph can cover months; a page can hold a few seconds. Slow down where the reader needs to experience uncertainty, recognition, or choice. Move quickly across repeated actions whose differences do not matter.",
      "Summary can carry voice and meaning instead of functioning as a neutral bridge. 'For a week, he arrived five minutes earlier and still found the chair empty' compresses repetition while developing an emotional pattern. The next fully rendered scene can then break that pattern and make the change felt.",
      "Sentence and paragraph rhythm contribute to pace, but context determines their effect. A short sentence can feel abrupt after a long reflective passage; several short sentences can instead become monotonous. Read for where attention rests and where the reader needs a breath, rather than applying one sentence-length rule to every scene.",
    ],
    annotations: ["'By noon' compresses the repeated search and gives it duration.", "The last door creates a natural limit to the sequence.", "Keeping the key in a pocket slows the moment where a practical search turns into an interpersonal revelation."],
    practice: ["Choose a repeated activity and summarise three attempts in one paragraph.", "Select the attempt where the pattern changes.", "Expand that moment into dialogue, action, and perception.", "Cut a logistical transition and check whether the scene remains easy to follow.", "Read aloud, marking where you rush and where you want more time. Revise one paragraph break."],
    pitfalls: ["Dramatising every trip, greeting, and routine task at the same length.", "Summarising the emotional turning point after spending pages on setup.", "Using only short sentences to signal tension until the rhythm becomes flat."],
    deliverable: "One compressed sequence followed by a fully rendered turning point.",
    revision: "Compress repeated logistics and expand the moment that changes the scene. Preserve spatial clarity and vary sentence rhythm according to attention.",
  },
  "revision-structure": {
    reading: [
      "Read a draft first as a reader, then as a maker. Record where you became curious, confused, impatient, or moved before deciding how to fix anything. A felt problem may have several causes: slow pacing could come from repetition, an unclear goal, or a missing consequence rather than sentence length.",
      "Make a reverse outline from the draft that exists. Give each scene one line describing what changes. This exposes missing transitions and repeated beats more reliably than comparing the draft with the plan you remember. Include changes in knowledge, trust, obligation, and willingness, not only physical events.",
      "Prioritise revisions by dependency. Clarify the scene's purpose and sequence before polishing its wording. If you remove a scene, inspect what later material relied on it: a promise, an introduced object, or a piece of knowledge may need a new home. Structural revision is also continuity work.",
    ],
    annotations: ["The repeated refusals establish a trait but may stop developing it.", "The daughter's letter changes the conditions under which Eli refuses.", "His question creates a new action and a new piece of uncertainty for the next beat."],
    practice: ["Read without editing and note three reader reactions.", "Write a reverse outline of the scene's actual changes.", "Choose the highest-impact issue and propose two possible fixes.", "Revise the structure, then check any promises or facts moved by the change.", "Read again to see whether the original reader problem improved before beginning line edits."],
    pitfalls: ["Treating every uncomfortable sentence as a sentence-level problem.", "Deleting setup without checking what later scenes rely on it.", "Revising toward a generic formula instead of the intended reading experience."],
    deliverable: "A reader-response note, a reverse outline, and one structural revision with continuity checked.",
    revision: "Identify what changes in the scene and remove repeated beats. Preserve required setup and show how the ending creates a new condition for what follows.",
  },
  "revision-line": {
    reading: [
      "Clarity begins with the reader's ability to follow the sequence. Check who is speaking, what each pronoun refers to, and whether an action can happen in the stated order. A graceful sentence cannot compensate for a hand reaching through a closed door or a character responding before they receive information.",
      "Look for duplicated work. A gesture may already communicate agreement; a second clause explaining agreement may add nothing. But do not cut mechanically: repetition can reveal hesitation, obsession, or emphasis. Ask what changes in the reader's experience when you remove the phrase.",
      "Protect voice during compression. Some narrators circle a point, some notice an odd comparison, and some speak in fragments. The aim is deliberate texture, not uniform smoothness. Read the revised passage beside the original and keep the version that best serves the character, scene, and intended rhythm.",
    ],
    annotations: ["Nodding already carries the idea of agreement in this context.", "The bus makes lateness observable and consequential.", "The cut works because the outside action matters; replacing every explanation with an unrelated image would not improve clarity."],
    practice: ["Read 250 words aloud and mark every place you stumble.", "Clarify one pronoun and one physical action.", "Remove three redundant phrases, then restore any repetition that serves voice.", "Vary one repeated sentence opening or rhythm.", "Compare both versions and name a distinctive phrase you deliberately protected."],
    pitfalls: ["Shortening every sentence until the narrator loses rhythm.", "Replacing simple words with elaborate synonyms during editing.", "Removing all repetition without considering its dramatic purpose."],
    deliverable: "An original and revised passage with three edits explained and one voice choice preserved.",
    revision: "Clarify action and references, remove redundant explanation, and preserve distinctive voice. Do not flatten deliberate rhythm into uniformly short sentences.",
  },
  "revision-ai": {
    reading: [
      "A useful AI brief names the current problem, the desired change, and the boundaries. Include the scene goal, point of view, tense, relevant character knowledge, and any exact phrasing that must survive. More background is not always more useful; prioritise facts that constrain the next passage.",
      "Separate generating from evaluating. First decide what you want to test. Then read the proposal against that intention, checking continuity and voice before admiring polished sentences. A fluent paragraph can still skip a difficult response, invent a shared memory, or reveal a secret the speaker does not know.",
      "Keep the author's decision visible. Compare the original and proposal, accept only useful changes, and rewrite the accepted material where necessary. If the suggestion misses the point, revise the brief by describing the mismatch rather than merely asking for a better version. Never treat a generated summary as proof of events that you did not keep.",
    ],
    annotations: ["'Asks for help indirectly' identifies a specific craft change.", "Practical vocabulary protects Noor's voice instead of requesting a generic improvement.", "The knowledge boundary and unresolved disagreement prevent an attractive rewrite from changing the story's facts or ending the scene early."],
    practice: ["Choose a passage and name exactly one problem you want to improve.", "Write a brief with the goal, viewpoint, two facts to preserve, and one thing to avoid.", "Generate a proposal and check every new factual claim against the manuscript.", "Keep one useful change, reject one unsuitable change, and explain both decisions.", "Make a final manual revision so the accepted passage fits the neighbouring text."],
    pitfalls: ["Accepting polished language without checking what it implies happened.", "Asking for several contradictory improvements in one vague prompt.", "Letting every revision pull the character toward the assistant's default voice."],
    deliverable: "A targeted AI brief, a reviewed proposal, and a manually revised final passage.",
    revision: "Make one targeted revision while preserving the specified facts, viewpoint, and character voice. Avoid invented callbacks and premature resolution; leave the final decision to the author.",
  },
};

export const NARRATIVE_PROJECT = {
  title: "Build a complete 50-line scene",
  introduction: "Bring the courses together in one scene. These ranges are practice scaffolding: use them to notice movement, then vary them when the story calls for it.",
  stages: [
    ["Lines 1–10", "Establish the encounter", "Orient us in a place. Give each speaker a different immediate want. Plant one useful physical detail."],
    ["Lines 11–20", "Meet resistance", "Let the first approach fail for a believable reason. Respond to the refusal instead of repeating the request."],
    ["Lines 21–30", "Change the understanding", "Reveal information or a contradiction that changes the conversation. Respect who could know the new fact."],
    ["Lines 31–40", "Make a costly choice", "Give someone two imperfect approaches. Let action, silence, and narration help the choice become legible."],
    ["Lines 41–50", "Show the consequence", "Resolve the scene's immediate question while allowing a future problem to remain. Return to the earlier detail with changed meaning."],
  ],
  rubric: [
    "Intention: I can identify what each person wants and where their tactic changes.",
    "Causality: each important response changes the next move; the turn is prepared.",
    "Voice: the speakers notice and phrase things differently without caricature.",
    "Narration: viewpoint stays clear, action is physically coherent, and details affect the scene.",
    "Theme: a practical choice tests competing values without an explanatory moral.",
    "Continuity: memories, knowledge, and promises are supported by what was actually written.",
  ],
};
