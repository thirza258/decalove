export interface LessonExample {
  title: string;
  context?: string;
  before: string;
  after: string;
  explanation: string;
  breakdown?: string[];
}

export interface Lesson {
  id: string;
  title: string;
  minutes: number;
  concept: string;
  steps: string[];
  exampleTitle?: string;
  before: string;
  after: string;
  explanation: string;
  examples: LessonExample[];
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
        concept: "A situation becomes a story when someone wants a particular outcome and meeting an obstacle forces a choice. Start with something the reader could see them doing on the page: sign a paper, open a lock, cross a perimeter, or demand a confession. An emotional need—such as the need to be forgiven or to feel competent—sits underneath that immediate goal and often makes achieving it agonizing.",
        steps: [
          "Name a specific person, a concrete visible goal, and an uncompromising deadline or limiting condition.",
          "Choose an obstacle that directly challenges their standard habit of solving problems.",
          "Ground failure in a specific, personal consequence rather than abstract ruin.",
          "Give the opposing force a reasonable, defensible motive of their own.",
        ],
        exampleTitle: "Domestic Drama — The Shop Lease",
        before: "A shy baker learns to believe in herself and finally stands up for what she deserves in her community.",
        after: "Before the municipal auction on Friday at noon, Noor must convince her estranged brother Tariq to sign the bakery lease renewal. She has prepared spreadsheets, cash-flow projections, and supplier references, but Tariq will not pick up the pen until she admits she lied about why their father closed the original kitchen.",
        explanation: "Signing a lease gives the scene a tangible finish line. The deadline creates urgency. Tariq's refusal exposes the fatal gap between Noor's practical calculations and her unacknowledged emotional debt.",
        examples: [
          {
            title: "Sci-Fi / Suspense — The Orbital Quarantine",
            context: "A freelance transport pilot needs clearance to dock a failing atmospheric pod at a fortified border station.",
            before: "Jax was a brave pilot who wanted to save his passenger from the cruel space station guards before the air ran out.",
            after: "Jax has fourteen minutes before orbital drag shears off the secondary solar foil. To clear airlock nine, he has to persuade Chief Inspector Reyes to bypass biometric customs for his passenger—the very inspector Jax reported to internal affairs two cycles ago.",
            explanation: "The ticking clock is mechanical and observable, but the emotional friction comes from past betrayal. Jax cannot succeed by being brave; he has to swallow his moral superiority.",
            breakdown: [
              "Fourteen minutes sets an objective boundary that restricts conversation length.",
              "Biometric scan bypass is an observable, binary action.",
              "Reyes's reluctance is rooted in past grievance rather than villainous malice.",
            ],
          },
          {
            title: "Historical / Institutional — The Guild Archive",
            context: "An apprentice cartographer must retrieve a sealed land charter from an ailing master before an estate audit.",
            before: "Samuel hoped he could get the master's seal so he could prove his worth to the guild.",
            after: "Samuel needs Master Vane's signet pressed into the estuary survey before the bailiffs inventory the study at sundown. The master will surrender the signet freely—provided Samuel destroys the ledger documenting the forged boundary stones from thirty years prior.",
            explanation: "The goal is simple and physical, but the master's counter-condition forces an immediate ethical crisis: career legitimacy purchased through deliberate historical fraud.",
            breakdown: [
              "The bailiffs' arrival at sundown provides external pressure outside the characters' control.",
              "The obstacle is an ethical choice rather than a physical fight.",
              "Samuel cannot obtain what he wants without redefining who he is.",
            ],
          },
        ],
        exercise: "Write a two-sentence premise: someone wants a specific visible token or signed commitment before an exact deadline, but getting it requires facing an obstacle they cannot solve with their usual strengths.",
        checklist: [
          "Can an observer in the room tell the exact second the goal is won or lost?",
          "Is the deadline enforced by an external reality rather than the character's whim?",
          "Does the obstacle target the protagonist's specific psychological weakness?",
          "Does the opposing person have a legitimate, understandable reason to resist?",
        ],
      },
      {
        id: "story-cause", title: "Connect scenes through consequences", minutes: 10,
        concept: "Stories falter when scenes are linked only by 'and then'. Narrative momentum requires a causal spine of 'because of that, therefore'. Every meaningful choice must resolve the immediate dilemma while altering the terrain of the next scene, creating an unintended complication that demands another decision.",
        steps: [
          "End each scene with a decisive choice or compromise made under pressure.",
          "Make the opening dilemma of the subsequent scene a direct consequence of that choice.",
          "Ensure that well-intentioned attempts to fix the problem generate new, unexpected friction.",
          "Escalate the stakes emotionally or ethically, rather than simply doubling physical danger.",
        ],
        exampleTitle: "Domestic Drama — The Compounded Promise",
        before: "Noor calls her brother. Then there is a bad thunderstorm. Then an unexpected customer arrives at the shop.",
        after: "Because Noor promises to absorb all outstanding bakery debts herself, Tariq agrees to review the lease. Therefore, she stays working past midnight and misses the final cross-town bus. Because she is stranded in the kitchen when the rear delivery door rattles, she opens it and finds the supplier repossessing the industrial mixer.",
        explanation: "The storm and random customer are replaced by a tight causal chain. Missing the bus is the logical result of her promise; the repossessed mixer exposes her financial deceit.",
        examples: [
          {
            title: "Legal / Political Drama — The Suppressed Memo",
            context: "An associate attorney discovers an unredacted environmental report during late-night discovery.",
            before: "Elena found a secret memo in the files. Next day she attended a court hearing. Later she had a drink with her rival.",
            after: "Because Elena slips the unredacted memo into her personal satchel instead of filing it with the clerk, she spends the night drafting an emergency petition. Therefore, when her managing partner demands the file at breakfast, Elena is forced to claim the courier lost it. Because of that lie, the firm places the paralegal on immediate unpaid leave for negligence.",
            explanation: "Elena's initial moral choice to protect the document immediately harms an innocent third party, creating an agonizing secondary dilemma.",
            breakdown: [
              "Action 1 (theft) causes Action 2 (fabrication) which causes Action 3 (unintended victim).",
              "The protagonist cannot retreat to safety without admitting the first infraction.",
              "Tension increases because the ethical cost compounds.",
            ],
          },
          {
            title: "Speculative / Colony Survival — The Auxiliary Relay",
            context: "An environmental technician tries to keep life support functioning in a freezing habitat dome.",
            before: "Kira bypassed the heating circuit. Then an alarm sounded in the sector. Then the security guards came.",
            after: "Because Kira reroutes auxiliary power to keep the nursery warm, the perimeter sensor array loses voltage. Therefore, a herd of migrating drift-crawlers breaches the southern greenhouse undetected. Because the greenhouse atmosphere vents, the agricultural guild marches on central engineering demanding Kira's arrest.",
            explanation: "Kira's compassionate act directly causes a critical infrastructure failure. The antagonist is not an evil villain, but a starving populace defending their food supply.",
            breakdown: [
              "The solution to problem A directly generates catastrophe B.",
              "Each step follows standard physical and social cause-and-effect.",
              "The hero's agency remains central to the crisis.",
            ],
          },
        ],
        exercise: "Outline three linked scenes using the connective formula: '[Character] chooses [Action A]; therefore [Consequence B] occurs; because of [Consequence B], [Character] is forced into [Choice C]'.",
        checklist: [
          "Can you replace every 'and then' with 'because of that' or 'therefore'?",
          "Did the protagonist's own action trigger the new complication?",
          "Does the second scene become impossible if the first scene's decision is removed?",
          "Does each consequence limit the character's remaining options?",
        ],
      },
      {
        id: "story-ending", title: "Earn the ending", minutes: 10,
        concept: "An earned ending is not a surprise twist or a summary of virtues; it is an action that answers the central question posed by the opening. The external goal may succeed or fail, but the character's posture toward reality must undergo a definitive, irreversible shift. Ground this turn in a physical object or gesture prepared earlier in the story.",
        steps: [
          "Identify the core philosophical question asked by the protagonist's opening attempt.",
          "Force a final decision where the character can no longer cling to their old protective compromise.",
          "Deliver the emotional change through a concrete physical action rather than a speech.",
          "Leave room in the aftermath for the reader to absorb what has been gained and lost.",
        ],
        exampleTitle: "Domestic Drama — The Second Cup",
        before: "Noor finally understood that family was much more important than professional success, and they smiled warmly.",
        after: "Noor uncapped the heavy marker, slid the lease across the flour-dusted counter, and struck a thick black line through the clause requiring Tariq's savings as collateral. 'You can visit without signing,' she said. She set a second chipped cup beside the till, filled it with cardamom tea, and left the pen between them.",
        explanation: "Crossing out the debt clause costs Noor her safety net. Placing the cup offers warmth without demanding surrender. The story refrains from declaring everything healed.",
        examples: [
          {
            title: "Crime / Noir — The Locker Key",
            context: "A disgraced investigator must decide whether to publish evidence that will ruin a corrupt official or protect an innocent family.",
            before: "Jack realized vengeance was hollow, so he forgave Miller and walked home in the rain feeling better.",
            after: "Jack turned the brass key over in his palm, watching the television van park outside the courthouse steps. He walked past the microphones, stopped at the storm drain on the corner of Fourth, and let the key drop through the iron grate. He tapped Miller on the shoulder: 'Take your daughter to Portland tonight. Don't look at a newspaper.'",
            explanation: "Dropping the key is physical, irreversible, and costs Jack his public vindication. His choice values a living person over abstract retribution.",
            breakdown: [
              "The drop into the grate provides an unmistakable acoustic and physical point of no return.",
              "Jack sacrifices his own public redemption for another's safety.",
              "No monologue explaining why vengeance is bad; the action carries the entire weight.",
            ],
          },
          {
            title: "Intimate Drama — The Overgrown Glasshouse",
            context: "An estranged daughter deciding whether to bulldoze her late mother's neglected botanical conservatory.",
            before: "Claire accepted her grief and knew she was ready to start a fresh chapter in her life.",
            after: "Claire signed the deed of sale for the bungalow, but kept the rusted brass key to the glasshouse on her ring. 'Demolish the parlor,' she told the surveyor. 'The orchids in the back bed need until October to drop their seed pods.' She walked out to her car with loam still crusted beneath her thumbnails.",
            explanation: "Claire doesn't preserve the entire past nor completely destroy it. The retained key and the loam on her thumbs balance release with reverence.",
            breakdown: [
              "A compromise rooted in specific biological and physical reality.",
              "Sensory detail (loam beneath thumbnails) grounds the emotional acceptance.",
              "Refuses the false binary of total denial versus total detachment.",
            ],
          },
        ],
        exercise: "Draft an ending scene of 150 words that answers your story's opening dilemma. Reintroduce an object from scene one, but have the protagonist treat it in a completely new way.",
        checklist: [
          "Does the final action cost the protagonist something substantial?",
          "Is the resolution shown through behavior, tools, or physical space rather than speeches?",
          "Have you cut every sentence where the narrator explains the moral of the story?",
          "Does the ending acknowledge what remains unresolved?",
        ],
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
        concept: "Spoken lines in fiction are tactical maneuvers, not information deliveries. A character speaks to alter the listener's behavior: to seduce, intimidate, disarm, guilt-trip, stall, or extract an admission. When both characters have conflicting intentions, every line becomes a bid for status, leverage, or intimacy.",
        steps: [
          "Assign each character a hidden objective for the conversation before writing line one.",
          "Tag every line mentally with an action verb: deflect, trap, flatter, inspect, or test.",
          "When a tactic fails, force the speaker to switch methods rather than repeating the same phrase louder.",
          "Cut all pleasantries and greetings unless the manner of greeting is itself a weapon.",
        ],
        exampleTitle: "Personal Dispute — The Key",
        before: "'I am extremely angry with you,' she said. 'I know you are upset, but you must understand my reasoning,' he replied. 'I don't care about your reasons.'",
        after: "'You kept my key.'\n'I thought you might come back for your books.'\n'For the paperbacks, Jules? In a locked milk crate?'\n'I didn't want the rain to ruin them.'\n'Right. Hand it over.'",
        explanation: "She attacks with an accusation; he deflects with sentimental chivalry; she exposes his pretext; he retreats to practical innocence; she issues an unambiguous command.",
        examples: [
          {
            title: "Workplace / Administrative — The Budget Review",
            context: "A hospital director attempts to pressure a lead surgeon into signing off on reduced post-op staffing.",
            before: "'You need to approve these staffing numbers,' Dr. Cole said. 'I won't do it, they are unsafe,' Dr. Aris answered. 'You have to cooperate.'",
            after: "COLE: The board approved the telemetry upgrade you requested, Aris. Signed off this morning.\nARIS: That was approved in June, Marcus. Where is the nursing schedule?\nCOLE: Telemetry reduces bed checks by thirty percent. That's clinical data from Cleveland.\nARIS: Cleveland had three unattended embolisms last quarter.\nCOLE: Cleveland also kept their trauma center open.",
            explanation: "Cole attempts bribery, then scientific authority, then an existential institutional threat. Aris counters with memory, clinical fact, and moral refusal.",
            breakdown: [
              "Line 1 offers a pre-packaged favor to induce compliance.",
              "Line 2 cuts through the bribe to re-center the real point of conflict.",
              "Lines 3-5 escalate from abstract data to direct financial survival.",
            ],
          },
          {
            title: "Espionage / Suspense — The Train Compartment",
            context: "A customs inspector interrogates a traveler carrying forged immigration papers.",
            before: "'Where are you traveling to?' 'Just to visit family.' 'I believe you are telling a lie, show me your papers.'",
            after: "INSPECTOR: Salzburg is damp in November. Most travelers prefer the southern lake line.\nNADIA: My sister's children are in Salzburg.\nINSPECTOR: Ah. The school behind St. Peter's?\nNADIA: Near the river, actually.\nINSPECTOR: Remarkable. The river parish hasn't taken day pupils since the flood in forty-two, Miss Lind.",
            explanation: "The inspector doesn't yell; he lays conversational tripwires disguised as tourist chatter. Nadia parries with family details until she steps into the historical trap.",
            breakdown: [
              "Surface pleasantry masks ruthless forensic cross-examination.",
              "Each response forces the defender to commit to more verifiable fabrications.",
              "The final line lands like an iron door swinging shut.",
            ],
          },
        ],
        exercise: "Write an eight-line dialogue between two people who want opposite things (one wants an apology, the other wants to borrow twenty dollars). Neither person may name their goal directly.",
        checklist: [
          "Does every single line attempt to shift the balance of power?",
          "Does a character alter their approach when their first line fails to land?",
          "Have you purged all lines that exist solely to explain background facts to the reader?",
          "Can you identify the specific verb each line is performing?",
        ],
      },
      {
        id: "dialogue-voice", title: "Make voices distinct", minutes: 10,
        concept: "Character voice is not a collection of regional accents, phonetic spellings, or quirky catchphrases. Voice is determined by what a person notices under stress, their tolerance for silence, the vocabulary their work has given them, and how directly they are willing to state an uncomfortable truth.",
        steps: [
          "Define what each character notices first when entering a room or crisis: structure, people, exits, or cleanliness.",
          "Establish distinct rhythmic cadences: short and punchy versus circular and qualifying.",
          "Vary how each person handles defensiveness: aggression, jokes, legalisms, or retreat.",
          "Run the 'blind test': remove all speaker attribution tags to verify each voice remains recognizable.",
        ],
        exampleTitle: "Domestic Realism — The Broken Window",
        before: "'The room looks very bad,' said Ada. 'Yes, I agree, it is quite messy and damaged,' said Leon.",
        after: "ADA: That bottom rail has dry rot clear through to the masonry, and the sash cord's snapped.\nLEON: Look at the south exposure, though. If we hang white muslin, the dust won't even show.\nADA: White muslin doesn't stop three gallons of November runoff from soaking into the floorboards.\nLEON: We'll put a zinc tub underneath. Like an indoor fountain.",
        explanation: "Ada speaks with carpenter's diagnostics and physical risk; Leon responds with decorative optimism and improvised whimsy.",
        examples: [
          {
            title: "Sci-Fi / Salvage — The Derelict Airlock",
            context: "A veteran salvage mechanic and an aristocratic corporate liaison examine a derelict freighter.",
            before: "'Is it safe inside the ship?' Marcus asked. 'It looks dangerous to me,' Brin replied.",
            after: "MARCUS: The exterior seals appear remarkably pristine, given the vintage. Almost ceremonial.\nBRIN: Seals don't rot; the rubber's baked into tar. Put your gloved thumb there. See that chalky film? Nitrogen blow-out.\nMARCUS: Surely an auxiliary atmospheric bypass remains operational?\nBRIN: Means there's no air, sunshine. Tap twice on your scrubber before you step over the sill.",
            explanation: "Marcus uses abstract, latin-derived formalisms ('ceremonial', 'auxiliary atmospheric bypass'); Brin relies on sensory diagnostics and blunt monosyllabic instructions.",
            breakdown: [
              "Marcus's syntax is polysyllabic, contemplative, and detached.",
              "Brin's vocabulary is tactile: 'baked into tar', 'chalky film', 'nitrogen blow-out'.",
              "Status and experience are revealed without either character delivering an exposition dump.",
            ],
          },
          {
            title: "Historical / Country Doctor — The Refused Tincture",
            context: "A university-educated niece tries to get her stubborn country uncle to take his prescribed digitalis.",
            before: "'Uncle Arthur, you have to take this medicine,' Clara said. 'I don't believe in new medicine,' he grumbled.",
            after: "CLARA: The physician in Bristol specifically noted your pulse irregularity in the ledger.\nARTHUR: Bristol physicians survive on port wine and funeral gratuities. Put the cork back in.\nCLARA: Your ankles are swollen to the gaiters, Uncle.\nARTHUR: A man who walks five miles of marshland every morning is entitled to swollen ankles. Fetch the tea and leave the apothecary bottles on the sideboard.",
            explanation: "Clara relies on institutional authority and clinical observation; Arthur deflects with local cynicism, rural physical pride, and household commands.",
            breakdown: [
              "Clara cites external authorities ('physician in Bristol', 'noted in the ledger').",
              "Arthur grounds his defiance in lived bodily endurance and class skepticism.",
              "Their friction generates warmth and exasperation simultaneously.",
            ],
          },
        ],
        exercise: "Write a ten-line dialogue between two people inspecting a secondhand car or appliance. One character evaluates mechanical function; the other evaluates social status and memories. Avoid naming these traits.",
        checklist: [
          "If you cover the character names, can you tell who is speaking on every turn?",
          "Are differences in vocabulary driven by biography and labor rather than gimmicks?",
          "Does sentence length vary appropriately between the two characters?",
          "Have you avoided phonetic accent spellings that impede reading speed?",
        ],
      },
      {
        id: "dialogue-subtext", title: "Use silence and action beats", minutes: 10,
        concept: "Subtext is the gap between what words literally denote and what the reader infers from context, staging, and hesitation. Action beats must not be decorative fidgeting; they should alter the reading of the line, betray an emotional betrayal, or establish dominance over the physical space.",
        steps: [
          "Identify the one sentence neither character is psychologically capable of uttering aloud.",
          "Give the characters a mundane physical task that requires coordination or attention.",
          "Use a pause or physical interruption to contradict what the speaker just claimed.",
          "Let an action substitute for a spoken answer at the turning point of the scene.",
        ],
        exampleTitle: "Domestic Realism — The Teacup",
        before: "'I'm doing fine,' she said sadly, feeling very lonely and hoping he would stay.",
        after: "'I'm fine.' She lifted his damp saucer from the drainer, wiped the porcelain dry with a corner of her apron, and set it opposite her own chair. 'The kettle's still hot on the back burner.'\nHe unbuttoned his cuff, but left his coat on the peg.",
        explanation: "She claims she is fine, but her hands set a place for him. He doesn't say he will stay, but unbuttoning his cuff signals he has accepted the invitation.",
        examples: [
          {
            title: "Crime / Investigation — The Pawnshop Counter",
            context: "A detective interrogates a jeweler about a stolen signet ring.",
            before: "'I have never seen that ring in my life,' the jeweler lied nervously, sweating under his collar.",
            after: "DETECTIVE: Gold signet. Entwined serpents. Ring a bell, Emil?\nEmil fitted the brass loupe into his eye socket and didn't touch the balance wheel on the velvet pad. The watchmaker's tweezers hovered half an inch above the escapement.\nEMIL: Town's full of serpents.\nDETECTIVE: Not with eighteen-carat assay marks from Lyon.\nEmil set the tweezers down. Carefully. Exactly parallel to the steel ruler.\nEMIL: The kettle's in the back, Inspector. Help yourself.",
            explanation: "The frozen tweezers reveal Emil's sudden panic. Aligning them parallel to the ruler shows him desperately regaining composure before offering hospitality as a surrender.",
            breakdown: [
              "The physical craft tool externalizes the character's internal pulse.",
              "Setting the tweezers parallel replaces an authorial note like 'he tried to calm down'.",
              "Offering tea is a tactical capitulation without an explicit confession.",
            ],
          },
          {
            title: "Romance / Reconciliation — The Rented Skiff",
            context: "Two former lovers adrift in a wooden rowboat on a reservoir after five years of estrangement.",
            before: "'Do you ever miss what we had?' he asked. 'Sometimes I do, but things are complicated,' she said.",
            after: "JULIAN: You kept the orchard lease.\nShe trailed her fingertips through the green pond-weed, letting the water bead along her knuckles before answering.\nMIRAH: The north stone wall collapsed in March.\nJULIAN: I know how to lime mortar.\nMIRAH: I hired the Miller boy. It's done.\nShe pulled her wet hand from the lake and rested it on the gunwale, two inches from his thumb. Neither of them shifted grip.",
            explanation: "The conversation pretends to be about agricultural masonry. The wet hand resting inches from his thumb conducts the entire unspoken question of physical reunion.",
            breakdown: [
              "Fingers in the pond-weed introduce a natural delay that gives weight to her answer.",
              "Hiring the Miller boy rejects his practical offer of repair.",
              "The stationary hand on the gunwale leaves the emotional door cracked open.",
            ],
          },
        ],
        exercise: "Write six spoken lines with three purposeful action beats. Someone asks for help without admitting they are in distress, and the other person offers support through an object rather than a promise.",
        checklist: [
          "Does every physical gesture change or complicate the spoken words?",
          "Is the physical action believable and natural to the setting?",
          "Did you avoid clichéd body language like sighing, rolling eyes, or clenching fists?",
          "Can the reader infer the unspoken emotion without an explanatory narrator tag?",
        ],
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
        concept: "Theme is not a sermon, slogan, or moral lesson ('Greed is bad'). Theme is an unresolved moral or philosophical question that has no pain-free answer. A story is an engine designed to test that question under intense narrative pressure, forcing characters to choose between two mutually exclusive goods or two devastating costs.",
        steps: [
          "Convert your story's abstract topic (loyalty, truth, ambition) into an open question.",
          "Ensure that both answers to the question represent valid, defensible human values.",
          "Design a scenario where upholding one value inevitably sacrifices the other.",
          "Resist settling the question early in the draft; let the drama explore both sides honestly.",
        ],
        exampleTitle: "Ethics of Silence — The Secret",
        before: "The theme of my story is that honesty is always the best policy, even when people get hurt.",
        after: "When does keeping a promise of loyalty to an elder become active complicity in the destruction of the next generation?",
        explanation: "The question sets loyalty and intergenerational justice on a collision course. There is no simple moral victory; either path incurs substantial guilt.",
        examples: [
          {
            title: "Sci-Fi / Transhumanism — Memory Extraction",
            context: "A neurologist has the technology to erase traumatic memories from violent crime survivors.",
            before: "The theme is that artificial memory technology is evil and unnatural.",
            after: "If erasing a survivor's traumatic memory guarantees their psychological survival, but erases the only eyewitness testimony needed to convict their abuser, who holds the moral authority to erase the tape?",
            explanation: "Pits individual healing directly against collective justice. The protagonist cannot choose without inflicting real harm on someone.",
            breakdown: [
              "Reframes a technological sci-fi premise into a moral dilemma.",
              "Both outcomes (peace for the individual vs. justice for the community) are noble.",
              "Generates immediate scene tension between doctors, prosecutors, and patients.",
            ],
          },
          {
            title: "Historical / Municipal Drama — The Siege Granary",
            context: "A town magistrate during an extended winter siege must distribute dwindling flour stores.",
            before: "The theme is that leaders must be fair and not corrupt during hard times.",
            after: "Is a magistrate more honorable for enforcing an equal starvation ration that dooms the entire garrison by spring, or for secretly diverting food to the laborers digging the relief tunnel?",
            explanation: "Tests abstract legal equality against utilitarian survival. Enforcing the rules causes defeat; breaking the rules violates the public trust.",
            breakdown: [
              "No villain is required; the conflict arises from arithmetic and scarcity.",
              "Forces the protagonist to bear the burden of being hated for doing what preserves life.",
              "Provides an unbreakable spine for courtroom, political, or riot scenes.",
            ],
          },
        ],
        exercise: "Draft three distinct thematic questions for your current project. Choose the one that causes the greatest personal pain to your protagonist, and write a 100-word premise testing it.",
        checklist: [
          "Can an intelligent, ethical person argue passionately for both sides of the question?",
          "Does answering the question require a tangible, costly sacrifice?",
          "Have you eliminated all didactic words like 'should', 'must', or 'obviously'?",
          "Does the question emerge naturally from the characters' practical goals?",
        ],
      },
      {
        id: "theme-characters", title: "Give the counterargument a person", minutes: 9,
        concept: "Thematic depth collapses if the antagonist is simply a straw man designed to look foolish so the protagonist can triumph. A story becomes unforgettable when the opposing viewpoint is voiced by someone formidable, competent, and morally persuasive, whose life experience makes their stance entirely understandable.",
        steps: [
          "Write out the opposing view with as much rhetorical eloquence and emotional logic as your hero's view.",
          "Root their philosophy in a specific past trauma or protective duty, not abstract villainy.",
          "Craft a scene where the counterargument's approach successfully solves a problem the protagonist failed to fix.",
          "Allow the protagonist to be genuinely shaken by the validity of the other person's critique.",
        ],
        exampleTitle: "Family Legacy — The Forge",
        before: "The selfish sister wanted to abandon the family business to get rich in the city, while her noble brother tried to protect their heritage.",
        after: "Sari's scholarship in Antwerp would provide cash to educate her three younger siblings, but leaving required forfeiting the municipal charter. Her brother Tomas refused to surrender the forge, having quietly taken on private debt to pay their late mother's medical expenses without alarming the family.",
        explanation: "Sari's ambition is an act of economic care; Tomas's stubborn traditionalism is an act of secret sacrifice. Neither owns moral superiority.",
        examples: [
          {
            title: "Medical / Institutional — The Experimental Trial",
            context: "A young clinical researcher wants to release an unapproved therapeutic compound to treat a dying child.",
            before: "Dr. Lin was a hero who loved children, while Dr. Stone was a heartless administrator who only cared about hospital liability.",
            after: "Dr. Lin demands the pharmacy release the untested antiserum for an eight-year-old in septic shock. Chief of Staff Stone keeps the safe locked—not out of cowardice, but because seven years ago he authorized an emergency compassionate-use trial that triggered fatal renal collapse in nine adolescent patients, an incident whose inquiry transcripts sit in his bottom desk drawer.",
            explanation: "Stone's cold refusal is the product of earned grief and systemic protection. Lin's desperate empathy is balanced by Stone's hard-won awareness of catastrophic risk.",
            breakdown: [
              "The antagonist's rigidity is grounded in a specific, documented past tragedy.",
              "The reader understands why Stone is terrified of Lin's good intentions.",
              "Both doctors are motivated by the fundamental oath to do no harm.",
            ],
          },
          {
            title: "Speculative / Border Enclave — The Dome Perimeter",
            context: "A community leader must decide whether to open the energy barrier to outside climate refugees.",
            before: "Maya was compassionate and wanted to save refugees, while Commander Vance was xenophobic and cruel.",
            after: "Maya demands the blast gates open for sixty refugees stranded in the ash storm. Marshal Vance produces the hydroponic telemetry: the thermal pumps are degrading at four percent a week; admitting sixty additional bodies reduces total calorie reserves to ninety days, triggering mandatory child-rationing before the spring thaw.",
            explanation: "Vance is armed with unyielding math and a solemn fiduciary duty to his existing citizens. Maya's moral imperative to save lives collides with Vance's obligation to prevent mass starvation.",
            breakdown: [
              "The counterargument relies on verifiable logistical facts rather than prejudice.",
              "The hero is forced to confront the actual body count of her compassion.",
              "The debate cannot be solved with inspirational speeches.",
            ],
          },
        ],
        exercise: "Write a 250-word confrontation between two characters who disagree on your thematic question. Give the opposing character the most persuasive, emotionally devastating line of dialogue in the scene.",
        checklist: [
          "Does the opposing character make points that cannot easily be dismissed?",
          "Is their position rooted in love, survival, or duty rather than spite?",
          "Does the protagonist experience genuine doubt or difficulty responding?",
          "Would an audience member agree with the opponent under the same circumstances?",
        ],
      },
      {
        id: "theme-motif", title: "Let a detail gather meaning", minutes: 8,
        concept: "A motif is an ordinary physical object, sensory cue, or habitual action that recurs at major emotional junctions in the narrative. Rather than operating as a rigid, static symbol, a motif evolves: each time it appears, its physical condition, owner, or emotional significance changes, measuring how far the characters have traveled.",
        steps: [
          "Select an object or sensory element that naturally belongs in the story's everyday physical world.",
          "Introduce it in scene one with a simple, functional purpose.",
          "Bring it back during the midpoint crisis with its condition altered or its ownership challenged.",
          "Use it in the climax as the physical instrument through which a final choice is enacted.",
        ],
        exampleTitle: "The Watch — Micro-Control to Surrender",
        before: "The ticking grandfather clock in the living room was a symbol that their relationship was running out of time.",
        after: "In chapter one, he taps her wristwatch with his thumbnail whenever she hesitates at a green light. In chapter four, when he asks if she has seen his train timetable, she leaves her watch on the hall table and walks outside. At the terminal in chapter seven, as the whistle blows, he unbuckles his watch, drops it into his pocket, and waits quietly on the platform.",
        explanation: "The watch shifts from an instrument of anxious control, to an emblem of silent rebellion, to a posture of patient surrender. The text never explains the symbolism.",
        examples: [
          {
            title: "Family Realism / Generational Grief — The Cast Iron Skillet",
            context: "An heirloom cooking pan passed down through three generations of restaurant owners.",
            before: "The skillet was old and black, representing the unbroken traditions of the family.",
            after: "Beat 1: Grandmother scours the pan with coarse salt, warning Maya that soap will strip forty years of seasoned fat: 'Memory is the only grease that doesn't go rancid.'\nBeat 2: After the bankruptcy hearing, Maya finds the skillet soaking in soapy dishwater, a ring of orange rust already biting into the rim.\nBeat 3: In her tiny studio apartment, Maya sands away the rust with steel wool, coats the raw gray iron with fresh lard, and sets it over the gas flame until it smokes black again.",
            explanation: "The skillet tracks the family's health: ancestral pride, demoralized neglect, and stubborn, personal resurrection.",
            breakdown: [
              "The object undergoes physical, sensory transformations: black seasoning, orange rust, raw gray iron.",
              "Every action performed on the pan (scouring, soaking, re-seasoning) mirrors an internal psychic state.",
              "The motif requires zero authorial intrusion to explain what it means.",
            ],
          },
          {
            title: "Suspense / Espionage — The Blue Metro Token",
            context: "A courier carrying an escape token through occupied city territory.",
            before: "The brass token was a constant reminder of his longing for freedom.",
            after: "Beat 1: He flips the blue enamel token across his knuckles to steady his trembling hands during the passport check.\nBeat 2: He tries to press the token into an informant's palm for an alley key, but the boy spits on it and drops it in the gutter.\nBeat 3: At the turnstile of the last outbound ferry with sirens wailing, he retrieves the muddy token from his coat, slides it into the slot, and walks through without looking back.",
            explanation: "The token moves from a private nervous talisman, to worthless currency in an indifferent city, to the final mechanism of irreversible departure.",
            breakdown: [
              "Connects the character's internal anxiety directly to the physical environment.",
              "The token's perceived value drops and rises with the plot.",
              "The final mechanical click of the turnstile confirms the ending.",
            ],
          },
        ],
        exercise: "Track a single physical object through three distinct scenes in your story: its initial introduction, its crisis appearance, and its transformative final use. Describe only physical actions and sensory details.",
        checklist: [
          "Does the object have a legitimate practical function in the scene?",
          "Does its physical state (clean, broken, repaired, abandoned) change over time?",
          "Have you cut all narration explaining what the object 'symbolizes'?",
          "Can the reader feel the emotional shift purely through how the object is handled?",
        ],
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
        concept: "The opening of a long-form work establishes an implicit contract with the reader: it teaches them what questions will matter, what kind of energy the prose will carry, and what emotional payoff they are investing in. Clashing promises—such as opening with slapstick comedy before pivoting to bleak existential murder—frustrate readers because they break the tonal contract.",
        steps: [
          "Articulate the specific appetite your book satisfies: intellectual deduction, relational intimacy, or survival adrenaline.",
          "Construct an opening chapter that provides a miniature sample of that core pleasure.",
          "Establish the central story engine: an open mystery, an impossible rivalry, or an unavoidable quest.",
          "Calibrate narrative distance so the reader knows whether they are inhabiting a mind or observing an epic canvas.",
        ],
        exampleTitle: "Community Mystery — The Returned Letters",
        before: "A lovely, charming novel about a picturesque town where diverse eccentric residents learn to coexist happily.",
        after: "With thirty days until compulsory retirement, a rural postmaster sets out to hand-deliver seven letters returned undeliverable over forty years. Each recipient remembers the town's vanished founder differently—and each delivery strips away another layer of the community's founding myth.",
        explanation: "The 30-day deadline, seven physical letters, and investigative structure promise both cozy episodic encounters and an overarching historical reckoning.",
        examples: [
          {
            title: "Academic Mystery / Suspense — The Forged Folio",
            context: "A university archivist stumbles upon a lethal discrepancy in a newly acquired Elizabethan manuscript.",
            before: "An exciting mystery where a smart librarian solves an ancient crime before bad guys stop her.",
            after: "When an unrecorded 1594 quarto of Doctor Faustus arrives with dry modern cellulose glue binding the endpapers, assistant curator Clara Finch has until the donor banquet on Friday to prove forgery without alarming the billionaire benefactor funding her department's survival.",
            explanation: "Promises an intellectual, manuscript-level procedural with institutional political stakes. The reader expects microscopic textual clues and academic infighting.",
            breakdown: [
              "The clue is technical and precise (modern cellulose glue in a 1594 folio).",
              "The deadline (donor banquet) creates a structural ticking clock.",
              "The protagonist is trapped between intellectual integrity and institutional survival.",
            ],
          },
          {
            title: "Speculative / Planetary Frontier — The Silt Canal Toll",
            context: "A disgraced tax collector stationed at an imperial silt gate uncovers a quiet invasion.",
            before: "A sweeping fantasy saga where god-kings battle for the empire's ultimate destiny.",
            after: "Stationed at the empire's southernmost river lock, a cashiered tax collector discovers that incoming grain barges are carrying identical duplicate crews who do not speak or eat. He has until the winter freeze closes the canal to verify the manifest or accept a bribe that would buy his exiled daughter's freedom.",
            explanation: "Promises a grounded, bureaucratic perspective on an eerie speculative crisis. The scale is epic, but the lens is intimate, ledger-driven, and personal.",
            breakdown: [
              "Subverts epic fantasy tropes by anchoring the story in taxation and river logistics.",
              "Combines an eerie, high-concept mystery with a personal, familial goal.",
              "The winter freeze establishes an unyielding temporal boundary.",
            ],
          },
        ],
        exercise: "Draft a 75-word novel premise that explicitly names: (1) the viewpoint protagonist, (2) the concrete organizing task, (3) the deadline, and (4) the core reading pleasure promised to the audience.",
        checklist: [
          "Does the opening promise align with the climax of the book?",
          "Is the scope of the central problem large enough to support repeated failures?",
          "Can a reader tell within three pages whether this book is intimate or panoramic?",
          "Does the protagonist have a personal stake in the outcome?",
        ],
      },
      {
        id: "novel-outline", title: "Build a flexible chapter map", minutes: 12,
        concept: "An outline is not a rigid railway schedule; it is an architectural stress-test. A functional chapter map tracks structural change: every chapter must begin with a character pursuing an immediate goal, encountering an unexpected reversal or complication, and leaving with their tactical situation permanently altered.",
        steps: [
          "Map the four structural pillars: opening disturbance, midpoint point-of-no-return, dark night crisis, and climactic choice.",
          "Ensure every intermediate chapter changes at least one major element: knowledge, power balance, or alliance.",
          "Track subplots as thematic pressure valves that complicate the main quest rather than pausing it.",
          "Be prepared to update the map whenever drafted scenes reveal that a character's motivation has naturally shifted.",
        ],
        exampleTitle: "Episodic Progression — The Postmaster's Route",
        before: "Chapter 3: The postmaster visits the mill. Chapter 4: The postmaster visits the school and talks with the teacher.",
        after: "Chapter 3: The mill owner refuses the letter, revealing the intended recipient died ten years ago and naming the town doctor as the secret executor.\nChapter 4: At the schoolhouse, the doctor's sister begs the postmaster to burn the remaining letters before the town council reconvenes on Tuesday.",
        explanation: "Visiting a location is not a chapter. In Chapter 3, discovery of death forces a new goal; in Chapter 4, an ethical plea threatens the entire premise.",
        examples: [
          {
            title: "Whistleblower Thriller — The Effluent Report",
            context: "An environmental safety auditor tries to document corporate toxic dumping.",
            before: "Chapter 1: Mark finds poison. Chapter 2: Mark tells his boss. Chapter 3: Mark is threatened.",
            after: "Chapter 1: Mark discovers hexavalent chromium in the municipal outflow, but realizes his sampling meter is three months overdue for certification.\nChapter 2: To recalibrate without alerting management, Mark steals clean reagent from a colleague's lab, triggering an internal theft audit.\nChapter 3: Confronted with the theft charge, Mark trades his silence on the audit to gain forty-eight hours of unsupervised access to the main retention basin.",
            explanation: "Each chapter forces Mark to compromise his professional standing to preserve his investigation. The plot moves forward because his solutions generate fresh legal hazards.",
            breakdown: [
              "Chapter 1's victory is undermined by a technical flaw.",
              "Chapter 2's fix creates a brand new, immediate threat (theft audit).",
              "Chapter 3 uses the new threat to negotiate a dangerous escalation.",
            ],
          },
          {
            title: "Romance / Second Chance — The Hillside Vineyard",
            context: "Two estranged former partners forced to co-manage an inherited estate through a harvest season.",
            before: "Chapter 5: They work in the vines. Chapter 6: They have dinner and remember old times.",
            after: "Chapter 5: While pruning early buds, Elena finds that Julian has mortgaged the bottling machinery to pay off her father's secret liens.\nChapter 6: Humiliated by Julian's rescue, Elena arranges an emergency pre-sale with a rival negociant—only to learn the buyer plans to level the historic cellar.",
            explanation: "Work in the vines uncovers a financial revelation; the emotional reaction to that revelation causes an impetuous business move that threatens the entire vineyard.",
            breakdown: [
              "Personal feelings dictate commercial decisions.",
              "Each character's well-intentioned defensive move backfires.",
              "Keeps romance tied directly to labor and financial stakes.",
            ],
          },
        ],
        exercise: "Create a five-chapter sequence outline. For every chapter, list: (1) Scene Goal, (2) The Obstacle Encountered, (3) The Reversal/Turn, and (4) The Changed State of the Story at the finish.",
        checklist: [
          "Does every chapter conclude in a different emotional and tactical position than it began?",
          "Are complications driven by character decisions rather than random weather or coincidence?",
          "Does the information learned in Chapter N dictate the protagonist's goal in Chapter N+1?",
          "Could any chapter be deleted without the reader getting confused? (If so, cut or merge it).",
        ],
      },
      {
        id: "novel-draft", title: "Draft with a continuity notebook", minutes: 9,
        concept: "Long-form drafting generates hundreds of narrative promises: timelines, scars, family secrets, geography, and who knows what when. Maintaining a clean continuity notebook separates established text (immutable canon) from provisional brainstorming, preventing disastrous logic breaks and hallucinations.",
        steps: [
          "Maintain a dedicated 'Canon Ledger' recording only events, dates, and wounds that have actually appeared in finished prose.",
          "Track 'Information Asymmetry': explicitly list who knows each vital secret at any given point in the timeline.",
          "Document 'Physical Inventory': keys, cash, tools, and vehicles, noting where they were last seen or used.",
          "Write a two-sentence 'Next Scene Launchpad' at the end of every drafting session so you can resume immediately.",
        ],
        exampleTitle: "Information Guardrails — Iris and the Envelope",
        before: "Continuity notes: Everyone in the village knows about the secret letter by chapter four.",
        after: "CANON DELIVERED (Ch. 2): Iris saw the red wax seal and the postmark 'Brest, 1984'. She did NOT read the letter's contents.\nCHARACTERS WHO KNOW SENDER: Postmaster and Dr. Hallowell.\nCHARACTERS WHO DO NOT: Iris, Mayor Vance, Constable.\nPLANNED FOR CH. 5: Iris discovers the seal matches her grandmother's locket.",
        explanation: "Distinguishing delivered facts from provisional plans prevents the narrative from accidentally letting Iris act on information she has never acquired.",
        examples: [
          {
            title: "Locked-Room Mystery — The Library Study",
            context: "Tracking physical clues and timelines during an isolated country house murder.",
            before: "Notes: Lord Harrington died around ten o'clock. There is blood on the carpet and a missing letter opener.",
            after: "CANON (Ch. 3): Harrington found dead at 10:20 PM by Butler. French doors bolted from inside. Letter opener missing from mahogany desk.\nTIMELINE LOCKED: 9:45 PM - Cook delivered broth (tray on side table). 10:00 PM - Chimes heard by niece in conservatory.\nKNOWLEDGE LEDGER: Inspector knows about the scuffed paint on the sash; suspects believe death was cardiac arrest until post-mortem.",
            explanation: "A locked ledger of times, physical locks, and inspector vs. suspect knowledge prevents impossible deductions or premature accusations.",
            breakdown: [
              "Locks down verified time stamps to eliminate plot holes.",
              "Tracks physical clues that cannot be moved or altered later.",
              "Maintains the boundary between what the detective knows and what suspects assume.",
            ],
          },
          {
            title: "Sci-Fi Survival — The Depressurized Habitat",
            context: "Tracking dwindling resources and equipment damage across multiple repair shifts.",
            before: "Notes: The air is leaking fast. Suit B is broken. They need to fix the valve.",
            after: "SYSTEM CANON: Habitat oxygen at 41%. Main scrubber offline. Suit B regulator cracked in Chapter 4 (unusable).\nCREW STATUS: Chen has second-degree thermal burns on left hand (cannot grip heavy tools). Miller uninjured but hypothermic.\nINVENTORY: Two canisters of sealant foam remaining; one manual ratchet.\nNEXT SCENE TARGET: Chen must coach Miller via radio to align the manual bypass valve before O2 hits 30%.",
            explanation: "Explicit tracking of injuries, damaged suits, and remaining foam canisters prevents convenient, unearned miraculous rescues.",
            breakdown: [
              "Prevents characters from forgetting disabling physical injuries.",
              "Enforces physical constraints on problem-solving.",
              "Leaves an actionable, precise launchpad for the next drafting session.",
            ],
          },
        ],
        exercise: "Create a continuity ledger for your current story draft containing four sections: (1) Established Hard Facts, (2) Who Knows What Secret, (3) Physical Inventory / In-World Location, and (4) The Immediate Next Scene Launchpad.",
        checklist: [
          "Are all facts listed in the ledger derived directly from written scenes rather than unwritten outlines?",
          "Are secrets clearly partitioned between characters who know and characters who are in the dark?",
          "Are physical injuries, broken tools, or missing money accounted for?",
          "Can you pick up writing tomorrow without having to re-read earlier chapters to verify basic facts?",
        ],
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
        concept: "Point of view is not a technical camera angle; it is an emotional filter. In close third person, narration is confined strictly to what the viewpoint character can perceive, remember, and interpret. The narrator cannot wander into another character's head to report their hidden motives. If another person is suffering, that suffering must be deciphered through behavior, posture, voice, and doubtful interpretation.",
        steps: [
          "Select the single viewpoint consciousness that will govern the scene from first line to last.",
          "Root out 'head-hopping': eliminate all statements declaring what another character privately feels.",
          "Convert unprovable claims about other minds into observable sensory evidence or anxious speculation.",
          "Vary narrative distance intentionally: zoom out for transitions, zoom in close during moments of crisis.",
        ],
        exampleTitle: "Close Third Person — The Coat Buttons",
        before: "Mara feared he would go. He secretly felt terrible about having to leave and wanted her to ask him to stay.",
        after: "Mara watched him button his coat twice, missing the third toggle each time. He paused with his fingers resting on the brass latch, staring at the wet threshold. Perhaps he was waiting for her to say something, but the words stayed wedged behind her teeth. He stepped out into the mist and pulled the latch shut.",
        explanation: "Instead of reporting both minds omnisciently, the prose stays locked in Mara's skull. His hesitation is observed rather than stated as fact; her silence is experienced as physical resistance.",
        examples: [
          {
            title: "Espionage / Suspense — The Safehouse Kitchen",
            context: "An undercover courier observes their handler after an operation has gone compromised.",
            before: "Agent Cross was terrified that Miller suspected him. Miller was calculating whether Cross was a double agent.",
            after: "Cross set the enamel kettle over the burner and kept his shoulders flat against the tiled wall. Behind him at the oilcloth table, the rhythmic scrape of Miller's pocketknife against an apple halted. Six seconds of dead air. Cross didn't turn around. The knife resumed, peeling the skin in one paper-thin ribbon. 'You took the canal bridge,' Miller said. It wasn't a question.",
            explanation: "Cross cannot read Miller's mind; he can only listen to the knife blade, count the seconds of silence, and measure the deadly chill in the observation.",
            breakdown: [
              "Tension escalates because the protagonist cannot verify what the other person knows.",
              "Sensory observation (the stopped knife blade) replaces cheap psychic access.",
              "Dialogue serves as an ominous clue rather than an overt exposition dump.",
            ],
          },
          {
            title: "Historical / Domestic — The Governess Interview",
            context: "A young, impoverished governess sits before a wealthy prospective employer.",
            before: "Eleanor felt small and nervous. Lady Catherine thought Eleanor was far too young and unrefined for the post.",
            after: "Eleanor pressed her mittened hands flat against the frayed wool of her reticule. Across the hearth, Lady Catherine did not look up from her embroidery. The needle punched through the stretched linen with a dry, stiff pop. Her ladyship's gaze drifted briefly from Eleanor's mended collar down to the mud-splatters on her boot-toes, lingered for the space of a breath, and returned to the silk pansies.",
            explanation: "Lady Catherine's contempt is never stated by the narrator; Eleanor experiences it entirely through the dry punch of the needle and the predatory drift of the woman's gaze.",
            breakdown: [
              "Social hierarchy is established through sensory focus and silent gaze.",
              "The protagonist's internal humiliation is grounded in physical posture.",
              "Maintains absolute discipline: Lady Catherine's interior thoughts are never voiced.",
            ],
          },
        ],
        exercise: "Write a 150-word departure scene strictly in close third person. The protagonist must deduce that the other person is hiding bad news, using only physical gestures, speech cadence, and pauses. No mind-reading permitted.",
        checklist: [
          "Does every sentence originate from the viewpoint character's eyes, ears, and interpretations?",
          "Have you eliminated phrases like 'little did she know' or 'he felt guilty inside'?",
          "Are uncertain feelings marked with evidence ('perhaps', 'seemed', 'as if') rather than authorial declaration?",
          "Does the narration reflect the protagonist's specific vocabulary and prejudices?",
        ],
      },
      {
        id: "narration-detail", title: "Choose details that do two jobs", minutes: 8,
        concept: "Amateur description inventories furniture and catalogs weather. Masterful description makes every detail do double duty: establishing physical space while simultaneously revealing character history, advancing action, or applying emotional pressure. If an object does not change a character's decision or expose their psychology, cut it.",
        steps: [
          "Filter every setting detail through the character's immediate emotional state and practical task.",
          "Use physical objects that impede, interrupt, or facilitate what someone is trying to do.",
          "Anchor history in physical habits and wear-and-tear rather than retrospective exposition.",
          "Swap generic atmospheric adjectives ('gloomy room', 'sad kitchen') for precise verbs and concrete nouns.",
        ],
        exampleTitle: "Domestic Memory — The Kitchen Drawer",
        before: "The kitchen was old, sad, dusty, and full of painful childhood memories for Mara.",
        after: "The pantry drawer still required a upward jerk and a heel-kick to clear the warped runner. Mara executed the sequence without looking, spoons clattering against the zinc partition, then stood frozen with the cold handles gripped in her fist. The pencil mark her mother had drawn to ration the weekly sugar was still visible beside the brass knob.",
        explanation: "The drawer establishes physical wear, proves Mara's childhood muscle memory through unthinking habit, and turns a practical kitchen task into an emotional ambush.",
        examples: [
          {
            title: "Crime / Procedural — The Desert Motel",
            context: "A burnt-out detective searches a fugitive's abandoned roadside motel room.",
            before: "The room was cheap, dirty, and depressing. Miller felt very tired and hopeless about finding the suspect.",
            after: "Miller thumbed the wall toggle. The overhead unit rattled like a tin bucket of bolts, coughing a plume of fried dust into his eyes before settling into a high, wheezing whine. On the bedside laminate, a motel Gideon Bible lay face down, its binding cracked at Exodus, holding down a paper cup containing two crushed filterless butts and an inch of sour tap water.",
            explanation: "The dust and rattle attack Miller physically; the broken spine at Exodus and the crushed cigarette butts tell a forensic story of desperate, sleepless waiting.",
            breakdown: [
              "Replaces generic adjectives with tactile sensory verbs: 'coughed', 'rattled', 'cracked'.",
              "The Gideon Bible acts as both character clue and physical paperweight.",
              "The room feels lived-in and forensically rich without a paragraph of static description.",
            ],
          },
          {
            title: "Romance / Class Tension — The Town Overcoat",
            context: "A newly wealthy young merchant visits his childhood sweetheart in her humble cottage.",
            before: "Julian wore a very expensive, handsome winter coat that showed how rich he had become in the capital.",
            after: "Julian's new beaver-wool overcoat was heavy enough to stand upright on the hall flagstones. It brought the chill of the express coach into the parlor, smelling of tobacco, London coal-fog, and cedar shavings. When he reached across the small deal table to take her hand, the stiff, silk-lined cuffs knocked the chipped stoneware creamer onto its side.",
            explanation: "The coat demonstrates wealth, geography, and travel, but its stiffness also makes him clumsy and oversized in her modest domestic space.",
            breakdown: [
              "Sensory details (coal-fog, beaver-wool, cedar) evoke an entire world outside the cottage.",
              "The coat causes a physical accident (knocking the creamer), illustrating his emotional dislocation.",
              "Description directly creates the scene's central awkwardness.",
            ],
          },
        ],
        exercise: "Describe a familiar room in 120 words through the eyes of a character returning after a long absence. One physical flaw in the furniture must interrupt an action they are performing and trigger a memory.",
        checklist: [
          "Does every chosen detail interact directly with the character's body or task?",
          "Did you avoid generic mood words like 'gloomy', 'nostalgic', or 'cozy'?",
          "Does an object's physical condition reveal past history without needing a flashback?",
          "Can the reader tell what the character cares about based on what they notice?",
        ],
      },
      {
        id: "narration-pace", title: "Move between scene and summary", minutes: 10,
        concept: "Pacing is the art of allocating narrative real estate. If every breakfast, cab ride, and argument receives identical page length, the story feels flat and exhausting. Use summary to compress logistical time and habitual actions; decelerate into full, blow-by-blow scene only when a choice is made that alters the story's trajectory.",
        steps: [
          "Identify the exact sentence where understanding, status, or commitment shifts in the scene.",
          "Expand that pivot moment with granular physical sensory detail, acoustic texture, and micro-actions.",
          "Compress repetitive travel, search sequences, and routine logistics into brisk, rhythmic summaries.",
          "Avoid summarizing the emotional climax; dramatize the crisis line by line.",
        ],
        exampleTitle: "The Archive Search — Deceleration at the Door",
        before: "They took the bus, walked three streets in the rain, entered the archives, and searched room after room. Finally, after many hours of looking, he admitted he had sold the missing map.",
        after: "By noon they had worked through four subterranean vaults, their fingertips gray with coal dust and their catalog slips exhausted. At the threshold of Vault E, he didn't reach for the padlock. He slid the brass ring back into his coat pocket and let his knuckles rest against the damp stone jamb. 'There isn't another ledger, Mara,' he said.",
        explanation: "Hours of fruitless search are compressed into coal dust and exhausted slips. The narrative slams on the brakes the instant his hand pockets the key and refuses to open the door.",
        examples: [
          {
            title: "Survival / Mountaineering — The Crevasse",
            context: "Two climbers traversing a dangerous glacial ridge during an escalating storm.",
            before: "They climbed for three days in the snow. It was very cold and exhausting. Suddenly Peter slipped and nearly fell into a deep hole.",
            after: "For forty-eight hours they moved in lockstep across the moraine—two miles of shale and blinding sleet measured only by the rhythmic crunch of crampons biting rotten ice. But on Tuesday at dawn, three paces short of the col, Tomas froze. The nylon safety line between their harnesses went taut, twanging like a struck bass wire. In the snow between their boots, a black fracture split the ice, whispering as powder poured into the void.",
            explanation: "Two days of brutal ascent are dispatched in one rhythmic sentence. Time dilates to a crawl when the rope twangs and the fracture whispers.",
            breakdown: [
              "Summary compresses physical exhaustion into rhythmic sensory shorthand.",
              "The transition from broad summary to microscopic scene is sudden and dramatic.",
              "Acoustic details ('struck bass wire', 'whispering powder') heighten life-or-death suspense.",
            ],
          },
          {
            title: "Coming of Age / Unanswered Letters — The Winter Term",
            context: "A college freshman waiting for replies from an estranged parent.",
            before: "She wrote to her father every week for the whole semester. He never wrote back, which made her very depressed until she finally gave up.",
            after: "Between September and December, she dropped fourteen aerograms into the postbox at the college gate, each folded around a pressed leaf from the quadrangle maples. By February, the returns began arriving in an oilcloth bundle, stamped 'Refused by Addressee' in violet ink. She carried the bundle to the radiator, snipped the string with her thumb-shears, and dropped all fourteen envelopes into the wastepaper basket without breaking a single seal.",
            explanation: "Four months of hopeful letter-writing are compressed into pressed leaves and postboxes; the irreversible death of hope is dramatized in the snipping of string and dropping of envelopes.",
            breakdown: [
              "Summarizes duration through a repeated, ritualistic physical action.",
              "The emotional breaking point is rendered with stark physical restraint.",
              "Leaves the internal grief unspoken, trusting the reader to feel the weight of the unopened bundle.",
            ],
          },
        ],
        exercise: "Write a 200-word passage: begin with a one-paragraph summary compressing two weeks of fruitless effort, then transition abruptly into a five-line scene where a single unexpected sensory detail halts the routine.",
        checklist: [
          "Does the summary paragraph convey elapsed time without reading like a dry bulleted list?",
          "Is the transition into immediate scene sharp, legible, and motivated by an event?",
          "Does the crucial turning point receive the slowest, most detailed prose on the page?",
          "Have you avoided summarizing the climax after spending pages building up to it?",
        ],
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
        concept: "Polishing sentences in a scene that fundamentally does not move the story is the most common form of wasted authorial labor. Structural revision requires looking at architecture first: identify the scene's starting condition, the obstacle, the turn, and the consequence. If nothing alters character knowledge, leverage, or relationships, cut or merge the scene before adjusting a single comma.",
        steps: [
          "Write the scene's core transactional shift in one declarative sentence ('A enters needing X; leaves having lost Y').",
          "Identify and ruthlessly cut repetitive beats where characters restate their positions without escalating.",
          "Merge diffuse encounters: combine three separate conversations into one high-stakes confrontation.",
          "Check continuity dependencies: ensure that cutting or moving a beat doesn't strand essential plot clues.",
        ],
        exampleTitle: "Consolidating Redundant Beats — The Draft Notice",
        before: "Three separate scenes show Eli brooding in his cabin, refusing to open his draft notice, and arguing with his neighbor about the war.",
        after: "Eli burns his draft notice once in silence over the stove. In the very next beat, as he scrapes the charred grate, his daughter enters and drops her own induction packet on the table beside the flour sack. 'I volunteered for the medical corps, Dad,' she says. 'The bus leaves from the square at six.'",
        explanation: "Cutting Eli's repetitive brooding and neighborly arguments compresses his stubbornness into one act, immediately shattered by his daughter's active defiance.",
        examples: [
          {
            title: "Crime Thriller — The Informant's Rendezvous",
            context: "A detective tries to extract the location of a stolen shipment from a slippery informant.",
            before: "Scene 1: Detective calls informant on the phone. Scene 2: Detective meets informant at a diner, informant refuses. Scene 3: Detective corners informant in an alley and finally gets the address.",
            after: "CUT: The phone call and diner meeting.\nREVISED SCENE: The detective waits inside the informant's locked apartment in the dark. When the informant enters carrying groceries, the detective slides the diner surveillance photos across the kitchen counter, blocking the door: 'You have until your ice cream melts to tell me where the container is docked.'",
            explanation: "Three weak scenes of hesitation and negotiation are compressed into a single ambush with immediate sensory pressure and physical confinement.",
            breakdown: [
              "Eliminates two low-stakes scenes that merely postponed the confrontation.",
              "Introduces an immediate, tactile ticking clock ('until your ice cream melts').",
              "Dramatically raises the stakes and the character's assertiveness.",
            ],
          },
          {
            title: "Family Drama / Estrangement — The Estate Division",
            context: "Two siblings arguing over their deceased father's house.",
            before: "Scene 4: Sister argues about the dining table. Scene 5: Brother argues about the garage tools. Scene 6: They cry about their childhood bedroom.",
            after: "MERGED SCENE: In the driveway beside the charity donation truck, the brother holds the father's workbench vise while the sister grips the brass dining room chandelier. When the moving foreman demands to know which piece goes in the crusher, neither will let go of their metal.",
            explanation: "Diffuse squabbling across multiple rooms is condensed into an iconic visual standoff over physical heirlooms in front of an impatient third party.",
            breakdown: [
              "Externalizes internal grief through competing physical grasp on heirlooms.",
              "The charity truck creates a public, uncompromising deadline.",
              "Replaces three chapters of bickering with one unforgettable visual tableau.",
            ],
          },
        ],
        exercise: "Examine a scene from your current draft. Write its core change in one sentence. Cut every exchange that repeats information already known to the characters, and combine two separate encounters into one.",
        checklist: [
          "Does this scene fundamentally alter what the protagonist can or must do next?",
          "Would a reader miss essential plot logic if this entire scene were deleted?",
          "Have you combined repetitive arguments into a single, decisive confrontation?",
          "Did you verify that necessary clues or props weren't accidentally erased during the cut?",
        ],
      },
      {
        id: "revision-line", title: "Read aloud for clarity and rhythm", minutes: 8,
        concept: "Line editing is not about enforcing generic academic grammar; it is about tuning acoustic rhythm, eliminating throat-clearing, and removing unintentional ambiguities. Reading prose aloud reveals awkward consonant clusters, unintended rhymes, over-explained emotional reactions, and dialogue that twists the human tongue unnaturally.",
        steps: [
          "Read the entire passage aloud at normal speaking speed, marking every spot where you stumble or lose breath.",
          "Eliminate filter words ('she noticed', 'he heard', 'she felt') to bring the reader closer to raw experience.",
          "Cut double-explanations where a physical gesture is followed by an explanatory sentence explaining what the gesture meant.",
          "Vary sentence cadence: mix short staccato bursts with long, rhythmic, clause-driven sentences.",
        ],
        exampleTitle: "Acoustic Tuning — The Departing Bus",
        before: "He nodded his head in agreement with her statement, completely understanding that she was entirely correct about the undeniable fact that it was far too late to do anything about the problem.",
        after: "He nodded. Down in the street, the air brakes of the last crosstown bus hissed and pulled away.",
        explanation: "Replaces 23 words of bloated, abstract throat-clearing with a single crisp gesture and an audible, irreversible consequence.",
        examples: [
          {
            title: "Suspense / Action — The Creaking Floorboard",
            context: "A character creeping through a darkened hallway trying not to wake an intruder.",
            before: "She felt a terrible, icy dread in her stomach as she slowly and cautiously began stepping down the creaky wooden hallway, hearing the sound of the floorboards protesting beneath her light weight.",
            after: "The third runner groaned under her stockinged heel. She froze, palm flat against the cold horsehair plaster, until the breathing in the bedroom resumed.",
            explanation: "Cuts passive filter phrases ('she felt', 'hearing the sound') and weak adverbs ('slowly and cautiously') in favor of sharp sensory nouns and immediate acoustic tension.",
            breakdown: [
              "Direct sensory nouns ('horsehair plaster', 'stockinged heel') ground the scene instantly.",
              "Eliminates self-conscious emotional labeling ('terrible, icy dread').",
              "Sentence rhythm mimics the character's frozen terror and listening ear.",
            ],
          },
          {
            title: "Literary Fiction — The Morning Kitchen",
            context: "Waking up after an exhausting, grief-filled night.",
            before: "The bright morning sunlight was shining brightly through the dirty window glass, making the kitchen look very messy and showing how much dust was floating around in the stale air.",
            after: "Morning sun cut across the linoleum in sharp yellow bars, lighting up forty years of grease-stains and drifted cat dander.",
            explanation: "Replaces redundant intensifiers ('bright', 'brightly', 'very messy') with vigorous verbs ('cut', 'lighting up') and unflinching, textured domestic specifics.",
            breakdown: [
              "Replaces three weak adjectives with active verbs.",
              "Introduces tactile, unromanticized domestic reality ('grease-stains and drifted cat dander').",
              "The cadence is sharp, evocative, and rhythmic.",
            ],
          },
        ],
        exercise: "Select a 150-word paragraph from your draft. Read it aloud. Delete five unnecessary adverbs, remove every instance of 'felt' or 'saw', and rewrite the final sentence so it lands with rhythmic finality.",
        checklist: [
          "Did you read the revised text completely aloud to test breath and cadence?",
          "Have you purged filter phrases that distance the reader from sensory experience?",
          "Are physical gestures allowed to stand on their own without explanatory commentary?",
          "Is there a pleasing variety of short, medium, and long sentences throughout the paragraph?",
        ],
      },
      {
        id: "revision-ai", title: "Give AI a brief, then make the decision", minutes: 9,
        concept: "AI assistants are powerful drafting engines, but without rigorous constraints they default to smooth, generic, melodramatic prose that homogenizes character voice. Treat the model as a junior copywriter: provide precise craft briefs with strict boundaries, specify what character knowledge must be protected, and manually curate the output.",
        steps: [
          "Provide a specific craft task rather than a vague aesthetic request ('Rewrite to sharpen subtext' vs. 'Make this better').",
          "Explicitly define information boundaries: state what characters do NOT know in this scene.",
          "Enforce voice and vocabulary guardrails: forbid generic tropes, forbidden words, and premature reconciliations.",
          "Accept suggestions as raw proposals: edit, discard, and re-author the output before incorporating it into your draft.",
        ],
        exampleTitle: "Targeted Prompting — The Indirect Loan Request",
        before: "Prompt: 'Make this dialogue between Noor and Tariq way more dramatic and emotional!'",
        after: "AI BRIEF: 'Rewrite lines 14–22. Goal: Noor must ask Tariq for financial backing without explicitly mentioning the lease arrears. Voice constraints: Keep her speech brief, practical, and grounded in kitchen inventory. Boundary: Tariq does not yet know she mortgaged the delivery van. Do not resolve their estrangement.'",
        explanation: "The brief defines an exact craft objective, preserves character voice, enforces crucial knowledge boundaries, and prevents premature narrative resolution.",
        examples: [
          {
            title: "Suspense / Checkpoint Interrogation — The Smuggler's Manifest",
            context: "Refining a tense dialogue between a border guard and a nervous courier.",
            before: "Prompt: 'Rewrite this scene to make it sound like a cool spy movie with lots of tension.'",
            after: "AI BRIEF: 'Revise the 8-line exchange between Elena and the border guard. Elena's objective: deflect attention from her forged cargo manifest by admitting to a minor customs infraction (unregistered tobacco). Guard's objective: determine if she is stalling for someone behind her in line. Constraints: Maintain a cold, polite administrative tone. Forbid words like 'spy', 'secret', or 'bribe'. End with the guard holding her transit stamp suspended above the inkpad.'",
            explanation: "Replaces vague genre clichés with distinct character objectives, strict tonal constraints, forbidden tropes, and an exact physical cliffhanger beat.",
            breakdown: [
              "Assigns a realistic tactical goal to both participants.",
              "Forbids cliché genre vocabulary that triggers formulaic melodrama.",
              "Provides an exact physical tableau to end the generation.",
            ],
          },
          {
            title: "Narration / Atmospheric Description — The Abandoned Laboratory",
            context: "Expanding sensory description in an abandoned research facility.",
            before: "Prompt: 'Add lots of spooky and scary descriptive details to this abandoned laboratory.'",
            after: "AI BRIEF: 'Expand the 50-word description of the laboratory bench. Viewpoint: Dr. Cho, who designed this centrifuge facility twenty years ago before the contamination order. Focus: Notice specific tools she personally calibrated, now degraded by mold and calcified water leaks. Tone: Clinical, mournful, restrained. Forbid: Supernatural tropes, ghosts, or generic horror phrases like 'spine-chilling'.'",
            explanation: "Anchors horror in professional grief, scientific terminology, and personal memory rather than generic gothic clichés.",
            breakdown: [
              "Filters the setting through a specific, educated professional viewpoint.",
              "Replaces generic spookiness with tragic technological decay.",
              "Explicitly outlaws cheap genre tropes.",
            ],
          },
        ],
        exercise: "Draft an AI prompt for a challenging scene in your manuscript. Include: (1) The specific craft objective, (2) One fact the characters are forbidden from revealing, (3) A tone and vocabulary constraint, and (4) The physical ending beat.",
        checklist: [
          "Did you give a targeted craft directive rather than an open-ended request?",
          "Are character knowledge limits explicitly stated to prevent hallucinated revelations?",
          "Did you forbid generic phrases or clichés typical of the genre?",
          "Did you manually review and revise the output rather than pasting it unexamined into your manuscript?",
        ],
      },
    ],
  },
];
