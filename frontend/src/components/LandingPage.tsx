import type { MouseEvent } from "react";
import libraryAfternoon from "../assets/library-afternoon.jpg";
import "../landing.css";

// Keep section navigation separate from the app's hash routes.
function jumpToSection(event: MouseEvent<HTMLAnchorElement>, id: string) {
  event.preventDefault();
  const section = document.getElementById(id);
  section?.focus({ preventScroll: true });
  section?.scrollIntoView({
    behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
      ? "instant"
      : "smooth",
    block: "start",
  });
}

interface LandingPageProps {
  onPlay: () => void;
}

export function LandingPage({ onPlay }: LandingPageProps) {
  return (
    <div id="landing-top" className="landing-page" tabIndex={-1}>
      <a
        className="landing-skip-link"
        href="#landing-main"
        onClick={(event) => jumpToSection(event, "landing-main")}
      >
        Skip to content
      </a>

      <header className="landing-header landing-container">
        <a
          className="landing-brand"
          href="#/"
          aria-label="Decalove home"
          onClick={(event) => jumpToSection(event, "landing-top")}
        >
          <span className="landing-brand-mark" aria-hidden="true">d</span>
          Decalove
        </a>
        <nav className="landing-nav" aria-label="Main navigation">
          <button type="button" onClick={onPlay}>The game</button>
          <a href="#/courses">Writing courses</a>
          <a href="#/studio">Writing studio</a>
        </nav>
      </header>

      <main id="landing-main" tabIndex={-1}>
        <section className="landing-hero landing-container" aria-labelledby="landing-title">
          <div>
            <p className="landing-eyebrow">Play. Learn. Write.</p>
            <h1 id="landing-title">A place for stories.<br />And a place for <em>yours.</em></h1>
          </div>
          <div className="landing-hero-copy">
            <p>
              Step into an interactive story, learn the craft behind it,
              or bring your own ideas to the page. There’s a place for
              every side of your imagination here.
            </p>
            <a
              className="landing-text-link"
              href="#explore"
              onClick={(event) => jumpToSection(event, "explore")}
            >
              Find your starting point <span aria-hidden="true">↓</span>
            </a>
          </div>
        </section>

        <section id="explore" className="landing-explore landing-container" aria-labelledby="explore-title" tabIndex={-1}>
          <div className="landing-section-heading">
            <h2 id="explore-title">Make yourself at home.</h2>
            <p>Three ways in. Start wherever you like.</p>
          </div>

          <div className="landing-paths">
            <article className="landing-path" aria-labelledby="game-title">
              <figure className="landing-game-preview">
                <img
                  src={libraryAfternoon}
                  alt="A sunlit school library, with a blue notebook and postcards on a reading table."
                  width={1536}
                  height={1024}
                  fetchPriority="high"
                />
                <figcaption>Second Year, Second Chances</figcaption>
              </figure>
              <div className="landing-path-content">
                <p className="landing-eyebrow"><span aria-hidden="true">01 / </span>Play</p>
                <h3 id="game-title">The game</h3>
                <p className="landing-path-description">
                  Find your place in Class 2-B. Meet Aiko, Ren, Mika,
                  and Haruto in an AI-directed visual novel shaped
                  by your choices.
                </p>
                <ul className="landing-path-features">
                  <li>Four classmates to get to know</li>
                  <li>Choose a response or write your own</li>
                  <li>Friendship, romance, or a path of your own</li>
                </ul>
                <button className="landing-button" type="button" onClick={onPlay}>
                  Play the game <span aria-hidden="true">→</span>
                </button>
              </div>
            </article>

            <article className="landing-path" aria-labelledby="courses-title">
              <div className="landing-course-preview">
                <p>Your writing toolkit</p>
                <ol>
                  <li><span aria-hidden="true">01</span>Build a story that moves</li>
                  <li><span aria-hidden="true">02</span>Write dialogue with a pulse</li>
                  <li><span aria-hidden="true">03</span>Find the question underneath</li>
                </ol>
              </div>
              <div className="landing-path-content">
                <p className="landing-eyebrow"><span aria-hidden="true">02 / </span>Learn</p>
                <h3 id="courses-title">Writing courses</h3>
                <p className="landing-path-description">
                  Turn a good idea into a stronger story. Explore
                  structure, dialogue, theme, book planning, narration,
                  and revision, one lesson at a time.
                </p>
                <ul className="landing-path-features">
                  <li>6 courses and 18 practical lessons</li>
                  <li>Examples, exercises, and checklists</li>
                  <li>Take your practice into the studio</li>
                </ul>
                <a className="landing-button" href="#/courses">
                  Explore the courses <span aria-hidden="true">→</span>
                </a>
              </div>
            </article>

            <article className="landing-path" aria-labelledby="studio-title">
              <div className="landing-studio-preview">
                <div className="landing-manuscript" role="img" aria-label="Sample manuscript: A quiet afternoon. She set a second cup on the table. The kettle’s still warm, she said.">
                  <div className="landing-manuscript-label">A first draft <span>Novel</span></div>
                  <p className="landing-manuscript-title">A quiet afternoon</p>
                  <p>She set a second cup on the table.<br />“The kettle’s still warm,” she said.</p>
                </div>
              </div>
              <div className="landing-path-content">
                <p className="landing-eyebrow"><span aria-hidden="true">03 / </span>Write</p>
                <h3 id="studio-title">Writing studio</h3>
                <p className="landing-path-description">
                  Give your ideas room to grow. Plan your characters,
                  draft a script or novel, and find your next line
                  with an AI partner when you want one.
                </p>
                <ul className="landing-path-features">
                  <li>Script and novel formats</li>
                  <li>Story notes and rich-text editing</li>
                  <li>AI suggestions you review and choose</li>
                </ul>
                <a className="landing-button" href="#/studio">
                  Open the studio <span aria-hidden="true">→</span>
                </a>
              </div>
            </article>
          </div>
          <p className="landing-browser-note">All in your browser. All at your own pace.</p>
        </section>

        <section className="landing-guide landing-container" aria-labelledby="guide-title">
          <div className="landing-guide-intro">
            <p className="landing-eyebrow">A little guidance</p>
            <h2 id="guide-title">Follow your curiosity.</h2>
            <p>Come for a story. Stay for the craft.<br />There’s no required order.</p>
          </div>
          <div className="landing-questions">
            <details>
              <summary>Do I need to play before I write?<span className="landing-detail-toggle" aria-hidden="true" /></summary>
              <p>
                Start with whichever part interests you. The game, courses,
                and studio can each be used on their own. You can enjoy
                the story, work through a lesson, or jump straight into a draft.
              </p>
            </details>
            <details>
              <summary>How do the courses connect to the studio?<span className="landing-detail-toggle" aria-hidden="true" /></summary>
              <p>
                Each lesson includes a practical exercise. Choose “Practice
                in the studio” to open a new draft with the exercise,
                craft guidance, and your practice notes ready to use.
              </p>
            </details>
            <details>
              <summary>How does the AI help?<span className="landing-detail-toggle" aria-hidden="true" /></summary>
              <p>
                In the game, AI develops the story around your choices.
                In the studio, it can suggest scenes, continuations,
                or revisions. You review each suggestion and decide
                what becomes part of your manuscript.
              </p>
            </details>
          </div>
        </section>
      </main>

      <footer className="landing-footer landing-container">
        <div>
          <a className="landing-footer-brand" href="#/" onClick={(event) => jumpToSection(event, "landing-top")}>Decalove</a>
          <span>Make room for your story.</span>
        </div>
        <nav aria-label="Explore Decalove">
          <button type="button" onClick={onPlay}>The game</button>
          <a href="#/courses">Courses</a>
          <a href="#/studio">Writing studio</a>
        </nav>
      </footer>
    </div>
  );
}
