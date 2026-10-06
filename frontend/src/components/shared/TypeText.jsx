// frontend/src/components/shared/TypeText.jsx
import PropTypes from "prop-types";
import { splitDevanagari } from "../../utils/scriptRuns.js";

/**
 * WHAT: Renders a collection title inside a `.ky-type` element. Latin text is
 *       emitted as is; each Devanagari run is wrapped in `<span class="ky-deva">`
 *       (no letter-spacing, taller line height; see styles/index.css).
 *
 * WHY:  The Devanagari font itself comes from the family stack the server sends
 *       and is downloaded by the browser only when such a run is drawn. A Latin
 *       title renders no span and requests nothing extra.
 */
export default function TypeText({ text }) {
  const runs = splitDevanagari(text);
  if (runs.length === 0) return text ?? null;
  return runs.map((run, index) =>
    run.deva ? (
      <span key={index} className="ky-deva">
        {run.text}
      </span>
    ) : (
      run.text
    ),
  );
}

TypeText.propTypes = { text: PropTypes.string };
