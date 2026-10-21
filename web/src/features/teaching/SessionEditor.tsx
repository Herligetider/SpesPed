import type { SessionContent, SessionField } from "./types";
import { fields } from "./types";
import { Field, lines } from "./runtime";
export default function SessionEditor({
  value,
  onChange,
  lineage,
  replacements,
  onReplacements,
}: {
  value: SessionContent;
  onChange: (value: SessionContent) => void;
  lineage?: Partial<Record<SessionField, string[]>>;
  replacements?: SessionField[];
  onReplacements?: (fields: SessionField[]) => void;
}) {
  return (
    <div className="teaching-editor">
      {fields.map(({ key, label }) => (
        <div key={key}>
          {key === "steps" ? (
            <fieldset>
              <legend>{label}</legend>
              {value.steps.map((step, index) => (
                <div className="teaching-step" key={index}>
                  <Field label={`Steg ${index + 1}`}>
                    <textarea
                      required
                      maxLength={2000}
                      value={step.instruction}
                      onChange={(event) =>
                        onChange({
                          ...value,
                          steps: value.steps.map((s, i) =>
                            i === index
                              ? { ...s, instruction: event.target.value }
                              : s,
                          ),
                        })
                      }
                    />
                  </Field>
                  <Field label={`Minutter, steg ${index + 1}`}>
                    <input
                      type="number"
                      required
                      min={0}
                      max={480}
                      value={step.minutes}
                      onChange={(event) =>
                        onChange({
                          ...value,
                          steps: value.steps.map((s, i) =>
                            i === index
                              ? { ...s, minutes: Number(event.target.value) }
                              : s,
                          ),
                        })
                      }
                    />
                  </Field>
                  {value.steps.length > 1 && (
                    <button
                      type="button"
                      onClick={() =>
                        onChange({
                          ...value,
                          steps: value.steps.filter((_, i) => i !== index),
                        })
                      }
                    >
                      Fjern steg {index + 1}
                    </button>
                  )}
                </div>
              ))}
              <button
                type="button"
                disabled={value.steps.length >= 12}
                onClick={() =>
                  onChange({
                    ...value,
                    steps: [...value.steps, { instruction: "", minutes: 0 }],
                  })
                }
              >
                Legg til steg
              </button>
            </fieldset>
          ) : key === "materials" ? (
            <Field label={`${label} – ett per linje`}>
              <textarea
                maxLength={30000}
                value={value.materials.join("\n")}
                onChange={(event) =>
                  onChange({
                    ...value,
                    materials: event.target.value.split("\n"),
                  })
                }
                onBlur={() =>
                  onChange({
                    ...value,
                    materials: lines(value.materials.join("\n")),
                  })
                }
              />
            </Field>
          ) : (
            <Field label={label}>
              <textarea
                required
                maxLength={
                  key === "title"
                    ? 320
                    : key === "goal" || key === "observation_focus"
                      ? 2000
                      : 3000
                }
                value={value[key]}
                onChange={(event) =>
                  onChange({ ...value, [key]: event.target.value })
                }
              />
            </Field>
          )}
          {Boolean(lineage?.[key]?.length) && (
            <p className="teaching-muted">
              Feltet bygger på et modellforslag. Vanlig redigering bevarer
              kildeavhengigheten.
            </p>
          )}
          {Boolean(lineage?.[key]?.length) && onReplacements && (
            <label className="teaching-check">
              <input
                type="checkbox"
                checked={replacements?.includes(key) ?? false}
                onChange={(event) =>
                  onReplacements(
                    event.target.checked
                      ? [...(replacements ?? []), key]
                      : (replacements ?? []).filter((x) => x !== key),
                  )
                }
              />
              Jeg har erstattet hele feltet «{label}» med selvstendig manuelt
              innhold og vil bryte modellavhengigheten.
            </label>
          )}
        </div>
      ))}
    </div>
  );
}
