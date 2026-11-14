"""System topology: nodes and the ordered series flow path.

Release 1 supports a single series path from the reservoir node to the
downstream boundary node. The topology is built from configuration and
validated here so that any malformed arrangement (branches, loops, gaps,
dangling references) is rejected with a clear error instead of producing a
silently wrong calculation. Branched networks (annulus, crossover, swab
cavities, manifolds) need a network solver and are planned for Release 3.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.simulation.components.elements import Element


class TopologyError(ValueError):
    pass


@dataclass
class Node:
    id: str
    name: str
    elevation: float  # m, relative to MSL, positive up


@dataclass
class SeriesTopology:
    nodes: dict[str, Node]
    #: Elements ordered from reservoir to boundary.
    path: list[Element]
    reservoir_node: str
    boundary_node: str

    @property
    def node_order(self) -> list[str]:
        return [self.path[0].from_node] + [e.to_node for e in self.path]

    def element(self, element_id: str) -> Element:
        for e in self.path:
            if e.id == element_id:
                return e
        raise KeyError(element_id)

    @classmethod
    def build(cls, nodes: list[Node], elements: list[Element], reservoir_node: str, boundary_node: str) -> "SeriesTopology":
        node_map: dict[str, Node] = {}
        for n in nodes:
            if n.id in node_map:
                raise TopologyError(f"duplicate node id {n.id!r}")
            node_map[n.id] = n
        ids = [e.id for e in elements]
        if len(set(ids)) != len(ids):
            raise TopologyError("duplicate element ids")
        for e in elements:
            for nid in (e.from_node, e.to_node):
                if nid not in node_map:
                    raise TopologyError(f"element {e.id!r} references unknown node {nid!r}")
            if e.from_node == e.to_node:
                raise TopologyError(f"element {e.id!r} connects a node to itself")
        for nid in (reservoir_node, boundary_node):
            if nid not in node_map:
                raise TopologyError(f"unknown node {nid!r}")

        outgoing: dict[str, Element] = {}
        incoming: dict[str, Element] = {}
        for e in elements:
            if e.from_node in outgoing:
                raise TopologyError(f"node {e.from_node!r} has more than one outgoing element (branching not supported in Release 1)")
            if e.to_node in incoming:
                raise TopologyError(f"node {e.to_node!r} has more than one incoming element (merging not supported in Release 1)")
            outgoing[e.from_node] = e
            incoming[e.to_node] = e

        path: list[Element] = []
        current = reservoir_node
        visited = {current}
        while current != boundary_node:
            if current not in outgoing:
                raise TopologyError(f"flow path is broken at node {current!r}: no element continues toward the boundary")
            e = outgoing[current]
            path.append(e)
            current = e.to_node
            if current in visited:
                raise TopologyError("flow path contains a loop")
            visited.add(current)
        if len(path) != len(elements):
            unused = sorted(set(ids) - {e.id for e in path})
            raise TopologyError(f"elements not on the reservoir-to-boundary path: {unused}")
        if path[0].kind != "inflow":
            raise TopologyError("the first element must be the reservoir inflow (IPR)")
        if sum(1 for e in path if e.kind == "inflow") != 1:
            raise TopologyError("exactly one inflow element is required")
        unused_nodes = set(node_map) - visited
        if unused_nodes:
            raise TopologyError(f"nodes not on the flow path: {sorted(unused_nodes)}")
        return cls(nodes=node_map, path=path, reservoir_node=reservoir_node, boundary_node=boundary_node)
