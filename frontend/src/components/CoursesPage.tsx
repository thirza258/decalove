import { useState } from "react";
import { COURSES } from "../writing/courses";
import { NARRATIVE_PROJECT, WORKSHOPS } from "../writing/workshops";
import { WritingNav } from "./WritingNav";
import { useWritingWorkspace } from "../writing/workspaceContext";
import type { CourseProgress } from "../writing/workspace";

export default function CoursesPage({ onPractice }: { onPractice: (prompt: string) => void }) {
  const workspace = useWritingWorkspace();
  const progress = workspace.data.progress;
  const error = workspace.error;
  const [selected, setSelected] = useState<string | null>(null);
  const course = COURSES.find((c) => c.lessons.some((l) => l.id === selected));
  const lesson = course?.lessons.find((l) => l.id === selected);
  const total = COURSES.reduce((n, c) => n + c.lessons.length, 0);
  const completed = COURSES.flatMap((c) => c.lessons).filter((l) => progress.completed.includes(l.id)).length;

  function updateProgress(next: CourseProgress) {
    workspace.update((data) => ({ ...data, progress: next }));
  }

  if (course && lesson) {
    const workshop = WORKSHOPS[lesson.id];
    const index = course.lessons.indexOf(lesson);
    const done = progress.completed.includes(lesson.id);
    return (
      <div className="writing-app">
        <WritingNav active="courses" />
        <main className="lesson-layout">
          <aside className="lesson-outline">
            <button className="text-button" onClick={() => setSelected(null)}>← All courses</button>
            <p className="eyebrow">Course {course.number}</p>
            <h2>{course.title}</h2>
            <p>{course.outcome}</p>
            <nav aria-label="Course lessons">
              {course.lessons.map((item, i) => (
                <button key={item.id} aria-current={item.id === lesson.id ? "step" : undefined} onClick={() => setSelected(item.id)}>
                  <span>{progress.completed.includes(item.id) ? "✓" : String(i + 1).padStart(2, "0")}</span>{item.title}
                </button>
              ))}
            </nav>
            <a className="text-button" href="#/studio">Open your writing desk ↗</a>
          </aside>
          <article className="lesson-article" key={lesson.id}>
            <p className="eyebrow">Lesson {index + 1} of {course.lessons.length} <span>·</span> {lesson.minutes + 12} minutes, including practice</p>
            <h1>{lesson.title}</h1>
            <p className="lesson-concept">{lesson.concept}</p>
            <div className="lesson-outcome"><p className="eyebrow">What you will make</p><p>{workshop.deliverable}</p></div>
            <h2>Take a closer look</h2>
            {workshop.reading.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
            <h2>Try this approach</h2>
            <ol className="lesson-steps">{lesson.steps.map((step) => <li key={step}>{step}</li>)}</ol>
            <div className="lesson-examples">
              <section><h3>A starting point</h3><p>{lesson.before}</p></section>
              <section><h3>A more specific version</h3><p>{lesson.after}</p></section>
            </div>
            <p>{lesson.explanation}</p>
            <h2>Read the example closely</h2>
            <ul className="lesson-annotations">{workshop.annotations.map((note) => <li key={note}>{note}</li>)}</ul>
            <section className="lesson-pitfalls"><h2>Watch for these habits</h2><ul>{workshop.pitfalls.map((pitfall) => <li key={pitfall}>{pitfall}</li>)}</ul></section>
            <section className="lesson-exercise">
              <p className="eyebrow">Your turn</p>
              <h2>Put it on the page.</h2>
              <p>{lesson.exercise}</p>
              <h3>Build it in passes</h3>
              <ol className="lesson-steps">{workshop.practice.map((step) => <li key={step}>{step}</li>)}</ol>
              <label htmlFor="exercise-response">Your practice notes</label>
              <textarea id="exercise-response" rows={6} placeholder="Try a line, sketch a scene, or work through the exercise…" maxLength={2000}
                value={progress.exercises[lesson.id] ?? ""}
                onChange={(e) => updateProgress({ ...progress, exercises: { ...progress.exercises, [lesson.id]: e.target.value } })} />
              <button className="writing-button primary" onClick={() => onPractice(`${lesson.exercise}\n\nGoal: ${workshop.deliverable}\n\nCraft guidance: ${workshop.revision}${progress.exercises[lesson.id] ? `\n\nMy practice notes:\n${progress.exercises[lesson.id]}` : ""}`)}>Practice in the studio <span aria-hidden="true">↗</span></button>
              <small>Opens a new draft with this exercise and your notes as the AI brief.</small>
            </section>
            <h2>Read it back</h2>
            <ul className="lesson-checklist">{lesson.checklist.map((item) => <li key={item}>{item}</li>)}</ul>
            <details className="lesson-coach"><summary>A focused revision brief for your AI partner</summary><p>{workshop.revision}</p><small>Add the facts your story must preserve, select a passage in the studio, and choose “Rewrite selected passage”. Review the result against your checklist.</small></details>
            {error && <div className="writing-error" role="alert">{error}<br /><button className="text-button" onClick={workspace.retry}>Retry saving</button></div>}
            <footer className="lesson-footer">
              <button className="writing-button" aria-pressed={done} onClick={() => updateProgress({ ...progress, completed: done ? progress.completed.filter((id) => id !== lesson.id) : [...progress.completed, lesson.id] })}>{done ? "✓ Lesson completed" : "Mark lesson complete"}</button>
              <button className="text-button" onClick={() => setSelected(course.lessons[index + 1]?.id ?? null)}>{index + 1 < course.lessons.length ? "Next lesson →" : "Back to courses →"}</button>
            </footer>
          </article>
        </main>
      </div>
    );
  }

  return (
    <div className="writing-app">
      <WritingNav active="courses" />
      <main className="courses-main">
        <section className="courses-hero">
          <div>
            <p className="eyebrow"><span className="small-star" aria-hidden="true">✳</span> The Decalove writing room</p>
            <h1>Good stories start<br />with <em>good questions.</em></h1>
            <p>Learn the craft, try it on the page, and find your own voice.<br className="desktop-break" /> Short, practical courses for the stories only you can tell.</p>
            <a className="writing-button primary" href="#/studio">Start writing <span aria-hidden="true">↗</span></a>
          </div>
          <div className="course-note" aria-label="Your learning progress">
            <span className="course-note-pin" aria-hidden="true">✳</span>
            <p>A little practice.<br />A better next draft.</p>
            <div className="course-note-rule" />
            <strong>{completed}<span> / {total}</span></strong>
            <small>lessons completed</small>
            <progress value={completed} max={total} aria-label="Lessons completed" />
            <small>{workspace.status === "saved" ? workspace.temporary ? "Temporary server storage" : "Progress saved to your workspace" : "Progress waiting to save"}</small>
          </div>
        </section>
        <div className="courses-section-title"><h2>Your writing toolkit</h2><span>6 courses · 18 lessons · At your own pace</span></div>
        <div className="course-grid">
          {COURSES.map((item) => {
            const count = item.lessons.filter((l) => progress.completed.includes(l.id)).length;
            const next = item.lessons.find((l) => !progress.completed.includes(l.id)) ?? item.lessons[0];
            return (
              <button className={`course-card ${item.color}`} key={item.id} onClick={() => setSelected(next.id)}>
                <div className="course-card-top"><span className="course-number">{item.number}</span><span>{count === item.lessons.length ? "✓ Complete" : `${item.lessons.reduce((n, l) => n + l.minutes + 12, 0)} min`}</span></div>
                <h3>{item.title}</h3>
                <p>{item.description}</p>
                <div className="course-card-bottom"><span>{count ? `${count}/3 lessons complete` : "3 lessons + writing exercises"}</span><span aria-hidden="true">↗</span></div>
              </button>
            );
          })}
        </div>
        <section className="narrative-project">
          <p className="eyebrow">Your final writing project</p><h2>{NARRATIVE_PROJECT.title}</h2><p>{NARRATIVE_PROJECT.introduction}</p>
          <ol>{NARRATIVE_PROJECT.stages.map(([lines, title, task]) => <li key={lines}><span>{lines}</span><div><h3>{title}</h3><p>{task}</p></div></li>)}</ol>
          <details><summary>Review your scene: six questions before the next draft</summary><p>For each area, note one thing already working and one change to try. Revise the weakest area first, then reread the whole scene.</p><ul>{NARRATIVE_PROJECT.rubric.map((item) => <li key={item}>{item}</li>)}</ul></details>
          <button className="writing-button primary" onClick={() => onPractice(`Help me draft a complete scene with 50 dialogue lines and purposeful narration.\n${NARRATIVE_PROJECT.stages.map(([lines, title, task]) => `${lines}: ${title}. ${task}`).join("\n")}\nUse my story brief and characters. Keep their voices distinct and their knowledge consistent.`)}>Start the scene project ↗</button>
        </section>
        {error && <div className="writing-error" role="alert">{error}<br /><button className="text-button" onClick={workspace.retry}>Retry saving</button></div>}
        <section className="courses-bottom"><div><p className="eyebrow">From learning to making</p><h2>Your next scene is a blank page away.</h2><p>Draft dialogue, build a novel, and ask AI for a second perspective.</p></div><a className="writing-button" href="#/studio">Open Writing Studio ↗</a></section>
      </main>
      <footer className="writing-footer">Decalove <span>Make room for your story.</span></footer>
    </div>
  );
}
