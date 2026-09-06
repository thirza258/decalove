/**
 * Reveals a line a character at a time.
 *
 * Lifted out of the text box because the *click* has to know whether the line is
 * still revealing: a click mid-line completes it, and only a click on a finished line
 * advances the story. That is the behaviour every visual novel has, and it cannot be
 * decided inside the component that owns the animation.
 *
 * Ren'Py leaves text speed to its preferences screen. This client has no preferences
 * screen, so it picks a speed and makes the impatient path the same click the player
 * was already going to make.
 */

import { useCallback, useEffect, useState } from "react";
import { TEXT_SPEED_CPS } from "../config";

export interface Typewriter {
  shown: string;
  done: boolean;
  complete: () => void;
}

/**
 * @param token identifies the *beat*, not the text. Two consecutive steps can carry
 *   the same words -- a repeated ambient line, a narration that echoes the one before
 *   it -- and comparing text alone would skip the reset and print the second one
 *   already finished.
 */
export function useTypewriter(text: string, token: string = text): Typewriter {
  const [count, setCount] = useState(0);
  const [showing, setShowing] = useState(token);

  // Reset during render, not in an effect: an effect would let the previous line's
  // tail paint for a frame before the new one starts revealing.
  if (showing !== token) {
    setShowing(token);
    setCount(0);
  }

  useEffect(() => {
    if (!text) return;
    const interval = window.setInterval(() => {
      setCount((n) => (n >= text.length ? n : n + 1));
    }, 1000 / TEXT_SPEED_CPS);
    return () => window.clearInterval(interval);
  }, [text, token]);

  const complete = useCallback(() => setCount(text.length), [text]);

  return { shown: text.slice(0, count), done: count >= text.length, complete };
}
