"""Validate planning traceability, not implementation correctness or completeness.

Runtime evidence and independent review still need inspection. This utility refuses
missing scope or unsupported status promotion; it cannot certify the product.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check():
    specification_path = ROOT / "docs/features.json"
    features = json.loads(specification_path.read_text())
    manifest = json.loads((ROOT / "docs/implementation-manifest.json").read_text())
    errors = []

    def require(condition, message):
        if not condition:
            errors.append(message)

    require(manifest.get("schemaVersion") == 1, "Unsupported manifest schema")
    require(
        manifest["specification"]["sha256"]
        == hashlib.sha256(specification_path.read_bytes()).hexdigest(),
        "Feature specification changed: reassess traceability and prior evidence",
    )
    planned = {f["id"]: f for f in manifest["features"]}
    source = {f["id"]: f for f in features}
    jobs = {j["id"]: j for j in manifest["jobs"]}
    require(len(planned) == len(manifest["features"]), "Duplicate feature IDs")
    require(set(planned) == set(source), "Manifest must retain every specified feature")
    require(len(jobs) == len(manifest["jobs"]), "Duplicate job IDs")

    job_states = {"queued", "implementing", "awaiting_review", "changes_requested", "verified"}
    feature_states = {"not_started", "in_progress", "awaiting_review", "verified"}
    criterion_states = {"not_started", "in_progress", "implemented_unverified", "verified"}
    for job in jobs.values():
        jid = job["id"]
        require(job["status"] in job_states, f"{jid}: invalid state")
        require(set(job["featureIds"]) <= set(source), f"{jid}: unknown feature")
        require(set(job["dependsOn"]) <= set(jobs), f"{jid}: unknown dependency")
        require(jid not in job["dependsOn"], f"{jid}: self-dependency")
        if job["status"] == "verified":
            require(bool(job["implementationAgent"]), f"{jid}: missing implementer")
            require(bool(job["reviewAgent"]), f"{jid}: missing independent reviewer")
            require(job["implementationAgent"] != job["reviewAgent"], f"{jid}: self-review")
            require(bool(job["commits"]), f"{jid}: no pinned revision")
            require(bool(job["evidence"]), f"{jid}: no verification evidence")
            for finding in job["findings"]:
                require(finding.get("status") == "verified_fixed", f"{jid}: unresolved finding")

    active, visited = set(), set()

    def visit(jid):
        if jid in active:
            errors.append(f"Cyclic job dependency: {jid}")
            return
        if jid in visited or jid not in jobs:
            return
        active.add(jid)
        for dependency in jobs[jid]["dependsOn"]:
            visit(dependency)
        active.remove(jid)
        visited.add(jid)

    for jid in jobs:
        visit(jid)

    for fid, spec in source.items():
        if fid not in planned:
            continue
        item = planned[fid]
        require(item["status"] in feature_states, f"{fid}: invalid state")
        require(item["context"] == spec["context"], f"{fid}: context drift")
        require(item["title"] == spec["title"], f"{fid}: title drift")
        expected_jobs = {j["id"] for j in jobs.values() if fid in j["featureIds"]}
        require(set(item["jobs"]) == expected_jobs, f"{fid}: inconsistent job coverage")
        require(bool(expected_jobs - {"J02", "J27", "J28"}), f"{fid}: no feature implementation job")
        criteria = item["acceptanceCriteria"]
        require(
            [c["statement"] for c in criteria] == spec["acceptanceCriteria"],
            f"{fid}: original acceptance criteria missing or changed",
        )
        for index, criterion in enumerate(criteria, 1):
            require(criterion["id"] == f"{fid}.AC{index:02}", f"{fid}: invalid criterion ID")
            require(criterion["status"] in criterion_states, f"{fid}: invalid criterion state")
            if criterion["status"] == "verified":
                require(bool(criterion["evidence"]), f"{criterion['id']}: missing evidence")
        if item["status"] == "verified":
            require(all(c["status"] == "verified" for c in criteria), f"{fid}: incomplete criteria")
            require(bool(item["sourcePaths"]), f"{fid}: no implementation paths")
            require(bool(item["runtimeEvidence"]), f"{fid}: no runtime evidence")
            require(bool(item["independentReviews"]), f"{fid}: no independent reviews")
            for path in item["sourcePaths"]:
                require((ROOT / path).exists(), f"{fid}: missing source path {path}")

    require(bool(manifest["releaseGates"]), "Release gates must remain explicit")
    for gate in manifest["releaseGates"]:
        require(gate["status"] in {"unverified", "in_progress", "verified"}, f"{gate['id']}: invalid state")
        if gate["status"] == "verified":
            require(bool(gate["evidence"]), f"{gate['id']}: missing release evidence")

    if errors:
        raise SystemExit("\n".join(errors))
    verified_features = sum(f["status"] == "verified" for f in planned.values())
    verified_jobs = sum(j["status"] == "verified" for j in jobs.values())
    print(
        f"Traceability valid: {len(features)} features, "
        f"{sum(len(f['acceptanceCriteria']) for f in features)} criteria, {len(jobs)} jobs. "
        f"Recorded verified: {verified_features} features, {verified_jobs} jobs. "
        "This check does not establish functional or legal completion."
    )


if __name__ == "__main__":
    check()
