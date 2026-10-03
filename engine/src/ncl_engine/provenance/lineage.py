"""Small builders for contract-level provenance graphs."""

from __future__ import annotations

from datetime import datetime

from ncl_engine.domain.models import ProvenanceEdge, ProvenanceGraph, ProvenanceNode
from ncl_engine.provenance.hashing import stable_id
from ncl_engine.sources.transport import SourceSnapshot


def source_node(snapshot: SourceSnapshot, label: str) -> ProvenanceNode:
    return ProvenanceNode(
        id=stable_id("prvnode", snapshot.request_key_sha256, snapshot.body_sha256),
        kind="raw_input",
        label=label,
        source_id=snapshot.source_id.value,
        request_key_sha256=snapshot.request_key_sha256,
        fixture_interaction_id=snapshot.interaction_id,
        available_offline=snapshot.origin.value == "fixture",
        origin=snapshot.origin.value,
        sha256=snapshot.body_sha256,
        source_url=snapshot.request.url,
        fetched_at=snapshot.retrieved_at,
    )


def derived_graph(
    *,
    artifact_id: str,
    label: str,
    algorithm_version: str,
    created_at: datetime,
    inputs: list[ProvenanceNode],
    available_offline: bool,
) -> ProvenanceGraph:
    graph_id = stable_id("prv", artifact_id, algorithm_version)
    algorithm_id = stable_id("prvnode", algorithm_version)
    derived_id = stable_id("prvnode", artifact_id)
    algorithm = ProvenanceNode(
        id=algorithm_id,
        kind="algorithm",
        label=algorithm_version,
        source_id=None,
        request_key_sha256=None,
        fixture_interaction_id=None,
        available_offline=True,
        algorithm_version=algorithm_version,
    )
    derived = ProvenanceNode(
        id=derived_id,
        kind="derived",
        label=label,
        source_id=None,
        request_key_sha256=None,
        fixture_interaction_id=None,
        available_offline=available_offline,
    )
    edges = [
        ProvenanceEdge.model_validate({"from": node.id, "to": derived_id, "relation": "input_to"})
        for node in inputs
    ]
    edges.append(
        ProvenanceEdge.model_validate(
            {"from": derived_id, "to": algorithm_id, "relation": "generated_by"}
        )
    )
    return ProvenanceGraph(
        id=graph_id,
        root_artifact_id=artifact_id,
        created_at=created_at,
        nodes=[*inputs, algorithm, derived],
        edges=edges,
    )
