import { useState } from "react";
import type { Context, Decision, Props } from "./types";
import ProfileWorkspace from "./ProfileWorkspace";
import { EntitlementWorkspace } from "./EntitlementWorkspace";
import PlanWorkspace from "./PlanWorkspace";
import "./planning.css";
const clients = new WeakMap<object, number>();
let nextClient = 0;
/** Remount before rendering any learner prose when any authorization scope changes. */
export default function PlanningWorkspace(props: Props) {
  if (!clients.has(props.client)) clients.set(props.client, ++nextClient);
  return (
    <ScopedPlanning
      key={`${clients.get(props.client)}:${props.schoolId}:${props.learnerId}:${props.currentUser.id}`}
      {...props}
    />
  );
}
function ScopedPlanning(props: Props) {
  const [refresh, setRefresh] = useState(0),
    [tab, setTab] = useState("profile"),
    [decision, setDecision] = useState<Decision | null>(null);
  const ctx: Context = {
    ...props,
    refresh,
    changed: () => setRefresh((n) => n + 1),
  };
  const names =
    props.language === "nn"
      ? {
          profile: "Støtteprofil",
          cases: "Støttesaker og vedtak",
          plans: "Planar og IOP",
        }
      : {
          profile: "Støtteprofil",
          cases: "Støttesaker og vedtak",
          plans: "Planer og IOP",
        };
  return (
    <div
      className="planning-workspace"
      lang={props.language === "nn" ? "nn" : "nb"}
    >
      <h2>
        {props.language === "nn" ? "Grunnlag og planar" : "Grunnlag og planer"}{" "}
        · {props.learnerName}
      </h2>
      <p className="planning-help">
        Tidspunkter registreres i{" "}
        {Intl.DateTimeFormat().resolvedOptions().timeZone}. Sluttidspunktet i en
        gyldighetsperiode er ikke inkludert.
      </p>
      <p>
        Kildebelagt profil, sakkyndige anbefalinger, bekreftede vedtak og
        eksakte planrevisjoner.
      </p>
      <div className="planning-tabs" role="tablist" aria-label="Planlegging">
        {Object.entries(names).map(([id, name]) => (
          <button
            key={id}
            id={`planning-tab-${id}`}
            role="tab"
            aria-selected={tab === id}
            tabIndex={tab === id ? 0 : -1}
            onKeyDown={(e) => {
              const ids = Object.keys(names);
              const index = ids.indexOf(id);
              const next =
                e.key === "ArrowRight"
                  ? ids[(index + 1) % ids.length]
                  : e.key === "ArrowLeft"
                    ? ids[(index + ids.length - 1) % ids.length]
                    : e.key === "Home"
                      ? ids[0]
                      : e.key === "End"
                        ? ids[ids.length - 1]
                        : null;
              if (next) {
                e.preventDefault();
                setTab(next);
                document.getElementById(`planning-tab-${next}`)?.focus();
              }
            }}
            aria-controls={`planning-panel-${id}`}
            type="button"
            onClick={() => setTab(id)}
          >
            {name}
          </button>
        ))}
      </div>
      <div
        id="planning-panel-profile"
        role="tabpanel"
        aria-labelledby="planning-tab-profile"
        hidden={tab !== "profile"}
      >
        <ProfileWorkspace ctx={ctx} />
      </div>
      <div
        id="planning-panel-cases"
        role="tabpanel"
        aria-labelledby="planning-tab-cases"
        hidden={tab !== "cases"}
      >
        <EntitlementWorkspace
          ctx={ctx}
          onDecision={(d) => {
            setDecision(d);
            setTab("plans");
          }}
        />
      </div>
      <div
        id="planning-panel-plans"
        role="tabpanel"
        aria-labelledby="planning-tab-plans"
        hidden={tab !== "plans"}
      >
        <PlanWorkspace ctx={ctx} decision={decision} />
      </div>
    </div>
  );
}
