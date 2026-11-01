import { useState } from "react";
import "../landing.css";

interface LegalPageProps {
  initialTab?: "privacy" | "terms";
  onHome: () => void;
}

export function LegalPage({ initialTab = "privacy", onHome }: LegalPageProps) {
  const [tab, setTab] = useState<"privacy" | "terms">(initialTab);

  return (
    <div className="landing-page" style={{ paddingBottom: "80px" }}>
      {/* Header */}
      <header className="landing-header landing-container">
        <a
          className="landing-brand"
          href="#/"
          onClick={(e) => {
            e.preventDefault();
            onHome();
          }}
        >
          <span className="landing-brand-mark" aria-hidden="true">d</span>
          Decalove
        </a>
        <nav className="landing-nav" aria-label="Main navigation">
          <button type="button" onClick={onHome}>&larr; Back to Home</button>
          <a href="#/play">The game</a>
          <a href="#/courses">Courses</a>
          <a href="#/studio">Writing studio</a>
        </nav>
      </header>

      {/* Main Content */}
      <main className="landing-container" style={{ marginTop: "48px", maxWidth: "860px" }}>
        <p className="landing-eyebrow">TRANSPARENCY &amp; TRUST</p>
        <h1 style={{ font: "400 clamp(32px, 3.5vw, 48px)/1.15 Georgia, serif", margin: "0 0 16px" }}>
          Legal &amp; Privacy Policies
        </h1>
        <p style={{ color: "var(--landing-muted)", fontSize: "16px", margin: "0 0 32px" }}>
          Details regarding our self-hosted architecture, local story storage, and OpenRouter AI integrations.
        </p>

        {/* Tab switcher */}
        <div style={{ display: "flex", gap: "12px", marginBottom: "40px" }}>
          <button
            type="button"
            onClick={() => setTab("privacy")}
            style={{
              padding: "10px 20px",
              borderRadius: "20px",
              border: "1px solid var(--landing-green)",
              background: tab === "privacy" ? "var(--landing-green)" : "transparent",
              color: tab === "privacy" ? "var(--landing-paper)" : "var(--landing-ink)",
              fontWeight: 600,
              fontSize: "14px",
              cursor: "pointer",
              transition: "all 0.2s ease",
            }}
          >
            Privacy Policy
          </button>
          <button
            type="button"
            onClick={() => setTab("terms")}
            style={{
              padding: "10px 20px",
              borderRadius: "20px",
              border: "1px solid var(--landing-green)",
              background: tab === "terms" ? "var(--landing-green)" : "transparent",
              color: tab === "terms" ? "var(--landing-paper)" : "var(--landing-ink)",
              fontWeight: 600,
              fontSize: "14px",
              cursor: "pointer",
              transition: "all 0.2s ease",
            }}
          >
            Terms of Service
          </button>
        </div>

        {tab === "privacy" ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "32px", lineHeight: "1.8" }}>
            <section style={{ background: "#ffffff", padding: "32px", borderRadius: "12px", border: "1px solid var(--landing-line)" }}>
              <h2 style={{ font: "600 22px Georgia, serif", margin: "0 0 12px", color: "var(--landing-green)" }}>
                1. 100% Self-Hosted &amp; Private Storytelling
              </h2>
              <p style={{ margin: "0 0 12px", color: "var(--landing-ink)" }}>
                Decalove is an open-source, fully self-hosted interactive visual novel engine, writing courses platform, and creative studio.
                All player choices, relationship affinities, branch progressions, user manuscripts, storyboards, and local drafts
                are kept entirely within your self-hosted containers (MongoDB, MinIO, Redis) and your browser&apos;s local storage.
              </p>
              <p style={{ margin: 0, color: "var(--landing-muted)" }}>
                We do not track players, run external analytics, or monetize your creative writing.
                Your story data and uploaded assets are never shared with advertising networks or third-party data brokers.
              </p>
            </section>

            <section style={{ background: "#ffffff", padding: "32px", borderRadius: "12px", border: "1px solid var(--landing-line)" }}>
              <h2 style={{ font: "600 22px Georgia, serif", margin: "0 0 12px", color: "var(--landing-green)" }}>
                2. Narrative AI Generation via OpenRouter
              </h2>
              <p style={{ margin: "0 0 12px", color: "var(--landing-ink)" }}>
                When dynamic story generation or writing studio suggestions are active, narrative beats and dialogue options are powered by <strong>OpenRouter</strong>.
              </p>
              <p style={{ margin: "0 0 12px", color: "var(--landing-muted)" }}>
                When the story engine requests a scene continuation or when you request prose revisions in the studio:
              </p>
              <ul style={{ margin: "0 0 16px", paddingLeft: "24px", color: "var(--landing-muted)" }}>
                <li>Only the immediate character context, prompt scenario, and preceding dialogue turns are sent to OpenRouter.</li>
                <li>No secret keys, host database files, or unrelated private files leave your self-hosted instance.</li>
              </ul>
              <div style={{ padding: "16px", background: "var(--landing-paper)", borderRadius: "8px", border: "1px solid var(--landing-line)" }}>
                <p style={{ margin: "0 0 8px", fontSize: "13px", fontWeight: 600, color: "var(--landing-green)" }}>
                  OpenRouter Terms and Policies:
                </p>
                <div style={{ display: "flex", gap: "24px", fontSize: "14px" }}>
                  <a
                    href="https://openrouter.ai/privacy"
                    target="_blank"
                    rel="noreferrer noopener"
                    style={{ color: "var(--landing-green)", textDecoration: "underline" }}
                  >
                    OpenRouter Privacy Policy &rarr;
                  </a>
                  <a
                    href="https://openrouter.ai/terms"
                    target="_blank"
                    rel="noreferrer noopener"
                    style={{ color: "var(--landing-green)", textDecoration: "underline" }}
                  >
                    OpenRouter Terms of Service &rarr;
                  </a>
                </div>
              </div>
            </section>

            <section style={{ background: "#ffffff", padding: "32px", borderRadius: "12px", border: "1px solid var(--landing-line)" }}>
              <h2 style={{ font: "600 22px Georgia, serif", margin: "0 0 12px", color: "var(--landing-green)" }}>
                3. User Control &amp; Data Erasure
              </h2>
              <p style={{ margin: 0, color: "var(--landing-muted)" }}>
                Because Decalove operates in a self-hosted architecture, you have full sovereignty over your data.
                You can reset your game progress, delete writing projects, or purge local database volumes at any time.
              </p>
            </section>

            <section style={{ background: "#ffffff", padding: "32px", borderRadius: "12px", border: "1px solid var(--landing-line)" }}>
              <h2 style={{ font: "600 22px Georgia, serif", margin: "0 0 12px", color: "var(--landing-green)" }}>
                4. Privacy Contact
              </h2>
              <p style={{ margin: 0, color: "var(--landing-muted)" }}>
                For any inquiries or privacy-related questions regarding Decalove, please contact:{" "}
                <a href="mailto:nevatalapp@gmail.com" style={{ color: "var(--landing-green)", fontWeight: 600, textDecoration: "underline" }}>
                  nevatalapp@gmail.com
                </a>
              </p>
            </section>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "32px", lineHeight: "1.8" }}>
            <section style={{ background: "#ffffff", padding: "32px", borderRadius: "12px", border: "1px solid var(--landing-line)" }}>
              <h2 style={{ font: "600 22px Georgia, serif", margin: "0 0 12px", color: "var(--landing-green)" }}>
                1. Acceptance of Terms
              </h2>
              <p style={{ margin: 0, color: "var(--landing-muted)" }}>
                By accessing, hosting, or playing Decalove, you agree to these Terms of Service.
                Decalove is an interactive creative platform and artistic narrative experience.
              </p>
            </section>

            <section style={{ background: "#ffffff", padding: "32px", borderRadius: "12px", border: "1px solid var(--landing-line)" }}>
              <h2 style={{ font: "600 22px Georgia, serif", margin: "0 0 12px", color: "var(--landing-green)" }}>
                2. Creative &amp; Fictional Content
              </h2>
              <p style={{ margin: "0 0 12px", color: "var(--landing-muted)" }}>
                Characters, places, and events depicted in Second Year, Second Chances and writing exercises are works of fiction.
                Any resemblance to actual persons, living or dead, or actual events is purely coincidental.
              </p>
              <p style={{ margin: 0, color: "var(--landing-muted)" }}>
                Authors in the writing studio retain full copyright and artistic ownership of manuscripts they author.
              </p>
            </section>

            <section style={{ background: "#ffffff", padding: "32px", borderRadius: "12px", border: "1px solid var(--landing-line)" }}>
              <h2 style={{ font: "600 22px Georgia, serif", margin: "0 0 12px", color: "var(--landing-green)" }}>
                3. OpenRouter AI Guidelines
              </h2>
              <p style={{ margin: "0 0 12px", color: "var(--landing-muted)" }}>
                When leveraging generative narrative features, you agree to comply with upstream provider policies:
              </p>
              <div style={{ display: "flex", gap: "24px", fontSize: "14px" }}>
                <a
                  href="https://openrouter.ai/terms"
                  target="_blank"
                  rel="noreferrer noopener"
                  style={{ color: "var(--landing-green)", textDecoration: "underline" }}
                >
                  OpenRouter Terms of Service &rarr;
                </a>
                <a
                  href="https://openrouter.ai/privacy"
                  target="_blank"
                  rel="noreferrer noopener"
                  style={{ color: "var(--landing-green)", textDecoration: "underline" }}
                >
                  OpenRouter Privacy Policy &rarr;
                </a>
              </div>
            </section>

            <section style={{ background: "#ffffff", padding: "32px", borderRadius: "12px", border: "1px solid var(--landing-line)" }}>
              <h2 style={{ font: "600 22px Georgia, serif", margin: "0 0 12px", color: "var(--landing-green)" }}>
                4. Disclaimer of Warranty &amp; Liability
              </h2>
              <p style={{ margin: 0, color: "var(--landing-muted)" }}>
                Decalove is provided &ldquo;as is&rdquo;, without warranty of any kind. Under no circumstances shall the developers
                or contributors be held liable for any damages arising out of the use or inability to use this software.
              </p>
            </section>

            <section style={{ background: "#ffffff", padding: "32px", borderRadius: "12px", border: "1px solid var(--landing-line)" }}>
              <h2 style={{ font: "600 22px Georgia, serif", margin: "0 0 12px", color: "var(--landing-green)" }}>
                5. Terms Contact
              </h2>
              <p style={{ margin: 0, color: "var(--landing-muted)" }}>
                For questions regarding these Terms of Service, contact:{" "}
                <a href="mailto:nevatalapp@gmail.com" style={{ color: "var(--landing-green)", fontWeight: 600, textDecoration: "underline" }}>
                  nevatalapp@gmail.com
                </a>
              </p>
            </section>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="landing-footer landing-container" style={{ marginTop: "64px" }}>
        <div>
          <a className="landing-footer-brand" href="#/" onClick={(e) => { e.preventDefault(); onHome(); }}>Decalove</a>
          <span>Make room for your story. · Contact: nevatalapp@gmail.com</span>
          <p style={{ fontSize: "11px", color: "var(--landing-muted)", margin: "4px 0 0" }}>This project is under nevatal.id for educational purposes.</p>
        </div>
      </footer>
    </div>
  );
}
