/**
 * Landing page for Decalove — a simple, atmospheric introduction to the game.
 *
 * Uses the existing generated character previews and one background from
 * public/images/ so there is no extra asset pipeline to maintain.
 */

import { useState, useEffect } from "react";

const CHARACTERS = [
  {
    id: "aiko",
    name: "Aiko Serizawa",
    role: "Class Representative",
    preview: "/images/characters/_preview_aiko.jpg",
    color: "#e05a72",
  },
  {
    id: "ren",
    name: "Ren Hoshikawa",
    role: "Art Club President",
    preview: "/images/characters/_preview_ren.jpg",
    color: "#f2b544",
  },
  {
    id: "mika",
    name: "Mika Todoroki",
    role: "Track Team Ace",
    preview: "/images/characters/_preview_mika.jpg",
    color: "#4bb3a0",
  },
  {
    id: "haruto",
    name: "Haruto Amemiya",
    role: "Library Aide",
    preview: "/images/characters/_preview_haruto.jpg",
    color: "#6c7ae0",
  },
];

interface LandingPageProps {
  onPlay: () => void;
}

export function LandingPage({ onPlay }: LandingPageProps) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    // Fade in on mount.
    const timer = setTimeout(() => setVisible(true), 50);
    return () => clearTimeout(timer);
  }, []);

  return (
    <div
      className={`min-h-screen bg-vn-void text-white transition-opacity duration-700 ${visible ? "opacity-100" : "opacity-0"}`}
      style={{ overflow: "auto" }}
    >
      {/* ── Hero ── */}
      <section className="relative h-screen w-full overflow-hidden">
        <nav className="landing-writing-nav" aria-label="Main navigation">
          <a href="#/courses">Writing courses</a>
          <a href="#/studio">Script & novel studio ↗</a>
        </nav>
        {/* Background — rooftop sunset, dimmed */}
        <img
          src="/images/bg/rooftop_sunset.png"
          alt=""
          className="absolute inset-0 h-full w-full object-cover opacity-40"
        />
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-vn-void" />

        <div className="relative z-10 flex h-full flex-col items-center justify-center px-6">
          <h1
            className="text-center text-[72px] font-light tracking-widest"
            style={{ textShadow: "0 2px 24px rgba(0,0,0,0.7)" }}
          >
            Decalove
          </h1>
          <p
            className="mt-4 max-w-[600px] text-center text-[20px] leading-relaxed text-white/70"
            style={{ textShadow: "0 1px 8px rgba(0,0,0,0.6)" }}
          >
            An AI-written visual novel set in a Japanese high school.
            <br />
            Every story is unique. Every choice matters.
          </p>
          <button
            type="button"
            onClick={onPlay}
            className="mt-10 cursor-pointer border-2 border-vn-accent px-10 py-3 text-[22px] tracking-wide text-vn-accent transition-all duration-300 hover:bg-vn-accent hover:text-white"
          >
            Play Now
          </button>
          <div className="landing-writing-links"><a href="#/courses">Learn the craft</a><span aria-hidden="true">·</span><a href="#/studio">Write your own story ↗</a></div>
        </div>

        {/* Scroll hint */}
        <div className="absolute inset-x-0 bottom-8 z-10 flex justify-center">
          <span className="animate-bounce text-[14px] tracking-widest text-white/30 uppercase">
            scroll
          </span>
        </div>
      </section>

      {/* ── About ── */}
      <section className="mx-auto max-w-[900px] px-6 py-20">
        <h2 className="text-center text-[36px] font-light tracking-wide text-white/90">
          A story written as you read it
        </h2>
        <p className="mx-auto mt-6 max-w-[640px] text-center text-[18px] leading-relaxed text-white/50">
          Six weeks into the school year, a transfer student walks into Class
          2-B. Everyone else has already decided who they are. You haven't.
          Navigate friendships, rivalries, and quiet moments in a story that
          responds to every choice you make.
        </p>

        <div className="mt-16 grid grid-cols-1 gap-8 sm:grid-cols-3">
          <Feature
            title="AI-Generated Story"
            description="Every playthrough writes a new narrative. No two stories are the same."
          />
          <Feature
            title="Real Choices"
            description="Type what you want to say, or pick from story-driven options. The story adapts."
          />
          <Feature
            title="Living Characters"
            description="Four classmates with their own personalities, secrets, and arcs that evolve with you."
          />
        </div>
      </section>

      {/* ── Characters ── */}
      <section className="mx-auto max-w-[1000px] px-6 py-16">
        <h2 className="text-center text-[36px] font-light tracking-wide text-white/90">
          Meet the cast
        </h2>
        <div className="mt-12 grid grid-cols-2 gap-6 sm:grid-cols-4">
          {CHARACTERS.map((char) => (
            <CharacterCard key={char.id} {...char} />
          ))}
        </div>
      </section>

      {/* ── CTA ── */}
      <section className="py-20 text-center">
        <p className="text-[18px] text-white/40">
          Ready to begin?
        </p>
        <button
          type="button"
          onClick={onPlay}
          className="mt-6 cursor-pointer border-2 border-vn-accent px-10 py-3 text-[22px] tracking-wide text-vn-accent transition-all duration-300 hover:bg-vn-accent hover:text-white"
        >
          Start Your Story
        </button>
      </section>

      {/* ── Footer ── */}
      <footer className="border-t border-white/5 py-8 text-center text-[14px] text-white/20">
        Decalove — AI-directed visual novel
      </footer>
    </div>
  );
}

function Feature({ title, description }: { title: string; description: string }) {
  return (
    <div className="text-center">
      <h3 className="text-[20px] text-vn-accent">{title}</h3>
      <p className="mt-2 text-[16px] leading-relaxed text-white/45">{description}</p>
    </div>
  );
}

function CharacterCard({
  name,
  role,
  preview,
  color,
}: {
  name: string;
  role: string;
  preview: string;
  color: string;
}) {
  return (
    <div className="group flex flex-col items-center">
      <div
        className="h-[220px] w-[160px] overflow-hidden rounded-sm"
        style={{ boxShadow: `0 0 20px ${color}22` }}
      >
        <img
          src={preview}
          alt={name}
          className="h-full w-full object-cover object-top transition-transform duration-500 group-hover:scale-105"
        />
      </div>
      <p className="mt-3 text-[16px] text-white/80" style={{ color }}>{name}</p>
      <p className="text-[13px] text-white/35">{role}</p>
    </div>
  );
}
