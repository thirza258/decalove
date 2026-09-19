export interface Lesson {
  id: string;
  title: string;
  minutes: number;
  concept: string;
  steps: string[];
  before: string;
  after: string;
  explanation: string;
  exercise: string;
  checklist: string[];
}
export interface Course {
  id: string;
  number: string;
  title: string;
  description: string;
  outcome: string;
  color: string;
  lessons: Lesson[];
}

export const COURSES: Course[] = [
  {
    id: "story", number: "01", title: "Build a story that moves", color: "sage",
    description: "Turn an interesting idea into characters, pressure, and a reason to turn the page.",
    outcome: "A premise and a three-scene story with a meaningful change.",
    lessons: [
      {
        id: "story-want", title: "Give someone something to want", minutes: 8,
        concept: "A situation becomes a story when someone wants a particular outcome and meeting an obstacle forces a choice. Start with something the reader could see them doing. An emotional need can sit underneath that immediate goal.",
        steps: ["Name a person, a concrete goal, and the deadline or limit that makes it urgent.", "Choose an obstacle that challenges their usual way of getting what they want.", "Ask what failure would cost this person specifically. Keep the scale appropriate to your story."],
        before: "A shy baker learns to believe in herself.",
        after: "Before the shop closes on Friday, Noor must persuade her estranged brother to sign the lease. She has rehearsed every argument except an apology.",
        explanation: "Signing a lease gives the scene a visible goal. The missing apology creates a conflict between the practical task and the relationship.",
        exercise: "Write a two-sentence premise: someone wants a specific thing before a deadline, but getting it requires a difficult personal choice.",
        checklist: ["Can a reader tell whether the goal is achieved?", "Does the obstacle require a choice?", "Would changing the protagonist change the story?"],
      },
      {
        id: "story-cause", title: "Connect scenes through consequences", minutes: 10,
        concept: "Scenes feel connected when a decision changes the conditions of the next scene. A surprise can begin a story, but consequences help sustain it. Build a chain of because and therefore rather than a list of unrelated incidents.",
        steps: ["Write the decision at the end of the first scene.", "Make the next scene's problem a consequence of that decision.", "Allow attempts to help to create a complication; escalation can be emotional rather than dangerous."],
        before: "Noor calls her brother. Then there is a storm. Then a customer arrives.",
        after: "Noor promises to keep the shop open to win her brother's signature. Because she stays, she misses the last bus. Her brother returns with an umbrella and finds her selling the oven.",
        explanation: "The promise leads to staying; staying makes the return possible. The oven reveals a contradiction that the next scene must address.",
        exercise: "Outline three scenes. End each with a choice and begin the next with a consequence of that choice. Use 'because' between them.",
        checklist: ["Does each scene change the next?", "Does the protagonist contribute to what happens?", "Is the complication different from the previous one?"],
      },
      {
        id: "story-ending", title: "Earn the ending", minutes: 10,
        concept: "An ending answers the story's central pressure through action. The external goal can succeed or fail while the character's relationship to it changes. Bring back an earlier object or gesture with a new meaning instead of explaining the lesson.",
        steps: ["Identify the question raised by the opening choice.", "Create a final choice that makes avoiding that question impossible.", "Show one concrete consequence, then leave room for the reader to feel it."],
        before: "Noor finally understood that family was more important than success.",
        after: "Noor crossed out the line making her brother responsible for the debt. 'You can visit without signing,' she said, and set a second cup beside the till.",
        explanation: "Changing the contract costs Noor something. The second cup makes a relationship possible without claiming it is already repaired.",
        exercise: "Write a final exchange that answers your opening conflict. Repeat one object from the first scene, but change what someone does with it.",
        checklist: ["Does the ending follow from earlier choices?", "Is something resolved without solving everything?", "Can you remove the sentence explaining the moral?"],
      },
    ],
  },
  {
    id: "dialogue", number: "02", title: "Write dialogue with a pulse", color: "peach",
    description: "Give every voice an intention. Make room for subtext, friction, and silence.",
    outcome: "A conversation with distinct voices and a change in the relationship.",
    lessons: [
      {
        id: "dialogue-intention", title: "Let each line try to do something", minutes: 8,
        concept: "Useful dialogue acts on another person. A speaker might reassure, provoke, evade, invite, or negotiate. When two people want different outcomes, even a polite exchange can carry tension.",
        steps: ["Write each speaker's immediate goal outside the dialogue.", "Give each line an action verb: deflect, test, bargain, confess.", "Change the tactic when it fails; avoid repeating the same argument in different words."],
        before: "'I am upset.' 'I know you are upset.' 'You should understand why.'",
        after: "'You kept my key.'\n'I thought you might come back.'\n'For the key, Jules.'\n'Right. I'll get it.'",
        explanation: "An accusation becomes a bid for reconciliation, then a boundary. The last response shows that the boundary landed.",
        exercise: "Write eight spoken turns between someone who wants to stay and someone who wants them to leave. Neither may use 'stay' or 'leave'.",
        checklist: ["Does each speaker want something?", "Does a line respond to the previous line?", "Does someone change tactics?"],
      },
      {
        id: "dialogue-voice", title: "Make voices distinct", minutes: 10,
        concept: "Voice comes from attention, vocabulary, rhythm, and what a person avoids saying. A mechanic may notice a strained hinge while a host notices an empty chair. Distinction need not rely on accents or a repeated catchphrase.",
        steps: ["Choose what each character notices first under stress.", "Decide whether they speak directly, circle the point, ask questions, or use comparisons.", "Read the exchange without speaker names. Revise places where everyone sounds interchangeable."],
        before: "'The room is bad,' said Ada. 'Yes, it is bad,' said Leon.",
        after: "ADA: That window has been painted shut.\nLEON: We could put flowers in front of it.\nADA: Flowers don't count as a fire exit.",
        explanation: "Ada attends to practical failure; Leon tries to make the room welcoming. Their ways of seeing produce both voice and disagreement.",
        exercise: "Write a ten-line argument about an ordinary room. One character notices how things work; the other notices how people will feel. Avoid stating those traits.",
        checklist: ["Are the rhythms or word choices different?", "Do voices reflect values as well as quirks?", "Can the characters surprise us without losing coherence?"],
      },
      {
        id: "dialogue-subtext", title: "Use silence and action beats", minutes: 10,
        concept: "Subtext is the distance between what is said and what the scene lets us infer. An action beat can contradict a line, delay an answer, or show who controls the space. Use it when it changes the reading, not after every sentence.",
        steps: ["Identify the thing a speaker cannot comfortably say.", "Give them a safe surface topic or a task to hide behind.", "Place one action where it makes the spoken words less certain."],
        before: "'I'm fine,' she said sadly, feeling very lonely.",
        after: "'I'm fine.' She took his cup out of the drying rack and put it back on the table. 'The kettle's still warm.'",
        explanation: "The cup and invitation reveal a wish for company. The prose leaves the feeling available for the reader to infer.",
        exercise: "Write six dialogue lines and three action beats in which someone asks for help without admitting they need it. Let the other person notice one detail.",
        checklist: ["Can the reader infer something unsaid?", "Does each action beat alter the exchange?", "Have you left some emotion unexplained?"],
      },
    ],
  },
  {
    id: "theme", number: "03", title: "Find the question underneath", color: "lilac",
    description: "Build a theme through competing values, costly choices, and recurring details.",
    outcome: "A thematic question tested by two characters and a final choice.",
    lessons: [
      {
        id: "theme-question", title: "Start with a question", minutes: 7,
        concept: "A topic is a territory: loyalty, grief, ambition. A thematic question creates room for disagreement inside that territory. You do not need a settled answer before drafting, but you need situations that put the question under pressure.",
        steps: ["Choose a topic that matters to your protagonist.", "Turn it into a question with more than one defensible answer.", "Invent a small choice where two important values collide."],
        before: "The theme is honesty. Honesty is good.",
        after: "Does a promise to keep a secret still matter when silence harms someone else?",
        explanation: "The question puts trust and responsibility in conflict. Either answer can cost the character something.",
        exercise: "Write three questions about your theme. Choose one and invent a scene where two good values cannot both be protected.",
        checklist: ["Can reasonable people disagree?", "Can the question become a scene?", "Does it matter personally to the protagonist?"],
      },
      {
        id: "theme-characters", title: "Give the counterargument a person", minutes: 9,
        concept: "Theme becomes richer when characters embody different answers without becoming mouthpieces. Give the opposing view a history, a practical benefit, and a cost. Let events challenge both sides.",
        steps: ["Write two incompatible answers to the same thematic question.", "Give each character a reason their answer once helped them.", "Design a scene where each approach solves one problem and creates another."],
        before: "The selfish sister wanted to leave. The good brother wanted her to stay.",
        after: "Leaving would pay for her training; staying would keep their father's workshop open. Her brother had quietly applied for a job elsewhere too.",
        explanation: "Neither character owns the moral answer. The brother's application exposes a contradiction worth exploring through action.",
        exercise: "Write a conversation between two people who answer your thematic question differently. Give each one a valid concern and one uncomfortable contradiction.",
        checklist: ["Does the opposing view have a fair case?", "Do characters have wants beyond the theme?", "Are both positions tested?"],
      },
      {
        id: "theme-motif", title: "Let a detail gather meaning", minutes: 8,
        concept: "A motif is a recurring detail whose context changes. Its meaning grows through use. An umbrella can begin as a loan, become evidence of an absence, and end as an invitation. Repetition alone does not create that movement.",
        steps: ["Pick an object, place, sound, or small action already useful to the plot.", "Return to it at three different emotional moments.", "Change its owner, condition, or use so each return adds meaning."],
        before: "The broken clock symbolised their broken relationship.",
        after: "First he corrected her watch. Later she stopped asking the time. At the station, he turned his watch face down and waited.",
        explanation: "The same detail moves from control to distance to patience. The story need not label its symbolism.",
        exercise: "Choose a recurring detail and write its first, middle, and last appearance. Make the final use answer your thematic question without naming the theme.",
        checklist: ["Does the detail belong naturally in the world?", "Does its context change?", "Can the reader make the connection without explanation?"],
      },
    ],
  },
  {
    id: "novel", number: "04", title: "Shape an idea into a book", color: "blue",
    description: "Move from a premise to an outline, chapter goals, and a sustainable drafting process.",
    outcome: "A flexible book outline and a plan for drafting the opening chapter.",
    lessons: [
      {
        id: "novel-promise", title: "Choose your reader's promise", minutes: 9,
        concept: "A book's opening teaches the reader what kind of experience to expect. A mystery offers questions worth investigating; an intimate family story may promise changing relationships. Genre helps describe that promise, but your particular people and problems make it yours.",
        steps: ["Name the experience you want the reader to have.", "Choose a central story problem large enough to sustain several attempts.", "Decide whose perspective gives the reader the most interesting access to it."],
        before: "A book about a town with many interesting residents.",
        after: "A retiring postmaster has thirty days to deliver seven returned letters; each recipient remembers the town's vanished founder differently.",
        explanation: "The task gives the book a spine, while the letters permit different encounters and a developing question.",
        exercise: "Write a short book pitch that identifies the protagonist, central problem, intended reading experience, and perspective. Keep it under 100 words.",
        checklist: ["What will bring the reader back?", "Can the central problem support multiple attempts?", "Does the opening offer the experience the pitch promises?"],
      },
      {
        id: "novel-outline", title: "Build a flexible chapter map", minutes: 12,
        concept: "An outline is a tool for finding cause and effect before writing every sentence. Its level of detail can vary. Track what each chapter changes rather than giving every chapter the same rigid shape.",
        steps: ["Mark the opening disruption, a major reversal, and the final decision.", "Between those points, list attempts that reveal new information or alter a relationship.", "Give each chapter a starting want, an obstacle, and a changed situation at the end."],
        before: "Chapter 3: The postmaster visits the mill. Chapter 4: The postmaster visits the school.",
        after: "Chapter 3: The mill owner refuses the letter but names its true sender. Chapter 4: At the school, that sender asks the postmaster to destroy the remaining letters.",
        explanation: "Places become chapters when encounters change what the protagonist knows and must decide next.",
        exercise: "Outline six chapters with one sentence each: the protagonist tries something, meets resistance, and leaves with a changed problem.",
        checklist: ["Does each chapter earn its place?", "Are there changes in pace and emotional intensity?", "Does the final decision grow from the preceding chapters?"],
      },
      {
        id: "novel-draft", title: "Draft with a continuity notebook", minutes: 9,
        concept: "A book accumulates promises, dates, names, and private knowledge. Keep a brief continuity record while drafting. Separate facts that are on the page from ideas you might use later, especially when asking AI to help continue a chapter.",
        steps: ["Record established facts, unresolved questions, and who knows each secret.", "Set a small repeatable drafting target based on your time rather than someone else's word count.", "End a session with a note about the next scene's immediate goal."],
        before: "Notes: Iris discovers the letters. Everyone knows the secret.",
        after: "Delivered in chapter 2: Iris saw one envelope, unopened. Planned for chapter 5: she may learn the sender's name. The postmaster knows; Iris does not.",
        explanation: "Distinguishing written events from plans prevents accidental revelations and gives an assistant reliable context.",
        exercise: "Create a continuity note for your opening: five established facts, two open questions, who knows what, and the next scene's goal. Put it in the studio's reference notes.",
        checklist: ["Are plans distinguished from completed events?", "Are names and chronology consistent?", "Is the next drafting task small enough to begin?"],
      },
    ],
  },
  {
    id: "narration", number: "05", title: "Make narration carry feeling", color: "sand",
    description: "Choose a point of view, control narrative distance, and make description do useful work.",
    outcome: "A scene whose prose reveals character while moving the action forward.",
    lessons: [
      {
        id: "narration-pov", title: "Choose who gets to know", minutes: 9,
        concept: "Point of view controls access to information. In close third person, the prose can enter one person's thoughts while other people's feelings remain interpretations. Omniscient narration can move more broadly, but that movement still benefits from an intentional voice.",
        steps: ["Choose the viewpoint character and tense for the scene.", "Mark statements that claim access to another person's private thoughts.", "Convert those claims into observable evidence or an explicitly uncertain interpretation."],
        before: "Mara feared he would go. He secretly wanted her to ask him to stay.",
        after: "Mara watched him button his coat twice, missing the same button. Perhaps he was waiting for her to say something. She could not make herself ask.",
        explanation: "The second version stays with Mara. His action suggests a possibility without presenting her guess as fact.",
        exercise: "Write a 150-word departure scene from one person's close perspective. Show the other person's feelings only through actions, words, and uncertain interpretations.",
        checklist: ["Whose senses and thoughts guide the scene?", "Does the narrator know anything they could not know?", "Are changes of perspective intentional?"],
      },
      {
        id: "narration-detail", title: "Choose details that do two jobs", minutes: 8,
        concept: "Description can establish a place and reveal the person looking at it. Specific details tend to earn more space when they affect action or emotional meaning. You do not need all five senses in every paragraph.",
        steps: ["List three things this particular character would notice.", "Choose a detail that helps or obstructs what they are trying to do.", "Use a precise noun or verb before adding several adjectives."],
        before: "The kitchen was old, sad, dusty, and full of memories.",
        after: "The drawer still needed a lift and a kick. Mara opened it without thinking, then stood with the spoons in her hand.",
        explanation: "The drawer establishes wear and remembered habit. The pause gives that familiar action an emotional consequence.",
        exercise: "Describe a familiar room in 120 words through the eyes of someone returning after years away. Let one physical detail interrupt their immediate task.",
        checklist: ["Are the details specific to the viewpoint?", "Does description interact with action?", "Can you remove an adjective and choose a better verb?"],
      },
      {
        id: "narration-pace", title: "Move between scene and summary", minutes: 10,
        concept: "Scene gives an important moment space; summary carries the reader across less consequential time. Both are useful. Slow down when a choice changes something. Compress repeated attempts unless their differences matter.",
        steps: ["Find the moment the relationship, plan, or understanding changes.", "Render that moment with an action, perception, or spoken response.", "Summarise the travel and repetition around it so the important beat has room."],
        before: "They took the bus, walked three streets, entered the building, and argued. Finally he admitted he had sold it.",
        after: "By noon they had checked every storage room. At the last door, he kept the key in his pocket. 'There isn't another room,' she said. He shook his head.",
        explanation: "The search is compressed; the withheld key slows the prose at the point where the search changes meaning.",
        exercise: "Write one paragraph that summarises a week of attempts, then a scene of six dialogue lines where the pattern finally breaks.",
        checklist: ["Does the most consequential moment have space?", "Have you compressed repetition?", "Does paragraph rhythm match the pressure of the scene?"],
      },
    ],
  },
  {
    id: "revision", number: "06", title: "Revise without losing your voice", color: "rose",
    description: "Read for purpose, edit for clarity, and use AI as a collaborator you can disagree with.",
    outcome: "A revised scene and a repeatable checklist for your next draft.",
    lessons: [
      {
        id: "revision-structure", title: "Fix the scene before the sentence", minutes: 10,
        concept: "Polishing a scene you later remove is costly. Begin revision with purpose and consequence. A quiet scene can be necessary if it changes trust or makes a future decision legible; a dramatic scene can be unnecessary if nothing carries forward.",
        steps: ["Write what changes in the scene in one sentence.", "Check whether the reader can identify the immediate goal and resistance.", "Cut, combine, or reshape repeated beats before line editing."],
        before: "Three separate scenes show Eli refusing to open the letter.",
        after: "Eli refuses once. In the next scene, his daughter opens her own letter beside him; he asks where she found it.",
        explanation: "The second encounter develops the pressure instead of simply restating the refusal.",
        exercise: "Read a scene and label its goal, obstacle, turn, and consequence. Rewrite or remove one passage that repeats information without changing its meaning.",
        checklist: ["What changes?", "What would become unclear if this scene disappeared?", "Does the ending create movement?"],
      },
      {
        id: "revision-line", title: "Read aloud for clarity and rhythm", minutes: 8,
        concept: "Line editing helps the reader experience the scene without stumbling over accidental ambiguity. Read aloud to hear repeated rhythms, overexplained emotions, and dialogue no one could comfortably say. Preserve unusual phrasing when it belongs to the voice.",
        steps: ["Check unclear pronouns and the physical order of actions.", "Look for a gesture followed by an explanation that merely repeats it.", "Vary sentence length where the pace needs to change, then read the passage aloud."],
        before: "He nodded his head in agreement, understanding that she was correct about the fact that it was late.",
        after: "He nodded. Outside, the last bus pulled away.",
        explanation: "The action is clear, and the bus makes lateness a consequence. This edit works when the missed bus matters to the scene.",
        exercise: "Revise 150 words from your draft. Remove three redundancies, clarify one action, and keep one phrase that feels unmistakably like your narrator.",
        checklist: ["Can the reader follow who does what?", "Does the dialogue sound speakable?", "Have you preserved deliberate voice?"],
      },
      {
        id: "revision-ai", title: "Give AI a brief, then make the decision", minutes: 9,
        concept: "An assistant works better with a purpose, boundaries, and relevant context. Ask for a specific change rather than 'make it better'. Treat its response as a proposal: it may smooth away a distinctive voice or invent facts that your story has not established.",
        steps: ["Supply the passage, scene goal, point of view, and facts that must remain true.", "Request one change, such as stronger subtext or less repeated exposition.", "Compare the suggestion with the original. Accept only what serves your scene and revise it in your own words."],
        before: "Make this dialogue amazing.",
        after: "Rewrite the selected line so Noor asks for help indirectly. Keep her practical vocabulary. She does not know about the sale yet. Do not resolve the disagreement.",
        explanation: "The brief describes a craft goal and protects character knowledge. The writer still decides whether the result fits.",
        exercise: "Select a passage in the studio. Ask AI for one targeted revision with two facts it must preserve. Review the proposal and explain one change you would keep or reject.",
        checklist: ["Is the requested change specific?", "Are important facts and boundaries included?", "Does the result still sound like your story?"],
      },
    ],
  },
];
