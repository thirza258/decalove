export function WritingNav({ active }: { active: "courses" | "studio" }) {
  return (
    <header className="writing-nav">
      <a className="writing-brand" href="#/" aria-label="Decalove home"><span aria-hidden="true">d.</span> Decalove</a>
      <nav aria-label="Main navigation">
        <a href="#/play">Play the story</a>
        <a href="#/courses" aria-current={active === "courses" ? "page" : undefined}>Writing courses</a>
        <a href="#/studio" aria-current={active === "studio" ? "page" : undefined}>Writing Studio <span aria-hidden="true">↗</span></a>
      </nav>
    </header>
  );
}
