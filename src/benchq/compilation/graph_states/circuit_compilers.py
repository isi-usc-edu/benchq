################################################################################
# © Copyright 2022-2023 Zapata Computing Inc.
################################################################################
from datetime import datetime

import networkx as nx
from orquestra.quantum.circuits import Circuit

from .compiled_data_structures import GSCInfo
from .initialize_julia import jl


def get_nx_graph_from_rbs_adj_list(adj: list) -> nx.Graph:
    graph = nx.empty_graph(len(adj))
    for vertex_id, neighbors in enumerate(adj):
        for neighbor in neighbors:
            graph.add_edge(vertex_id, neighbor)

    return graph


def default_ruby_slippers_circuit_compiler(
    circuit: Circuit,
    logical_architecture_name: str,
    optimization: str,
    verbose: bool,
) -> GSCInfo:
    compiled_graph_data, _ = jl.run_ruby_slippers(
        circuit,
        verbose=verbose,
        logical_architecture_name=logical_architecture_name,
        optimization=optimization,
    )
    return GSCInfo.from_dict(compiled_graph_data)


def get_ruby_slippers_circuit_compiler(
    takes_graph_input: bool = True,
    gives_graph_output: bool = True,
    max_num_qubits: int = 1,
    optimal_dag_density: int = 1,
    use_fully_optimized_dag: bool = False,
    teleportation_threshold: int = 40,
    teleportation_distance: int = 4,
    min_neighbor_degree: int = 6,
    max_num_neighbors_to_search: int = int(1e5),
    decomposition_strategy: int = 0,
    max_graph_size: int = int(1e7),
):
    def rbs_circuit_compiler(
        circuit: Circuit,
        logical_architecture_name: str,
        optimization: str,
        verbose: bool,
    ) -> GSCInfo:
        (compiled_graph_data, _,) = jl.run_ruby_slippers(
            circuit,
            verbose=verbose,
            takes_graph_input=takes_graph_input,
            gives_graph_output=gives_graph_output,
            logical_architecture_name=logical_architecture_name,
            optimization=optimization,
            max_num_qubits=max_num_qubits,
            optimal_dag_density=optimal_dag_density,
            use_fully_optimized_dag=use_fully_optimized_dag,
            teleportation_threshold=teleportation_threshold,
            teleportation_distance=teleportation_distance,
            min_neighbor_degree=min_neighbor_degree,
            max_num_neighbors_to_search=max_num_neighbors_to_search,
            decomposition_strategy=decomposition_strategy,
            max_graph_size=max_graph_size,
        )

        return GSCInfo.from_dict(compiled_graph_data)

    return rbs_circuit_compiler


def get_jabalizer_circuit_compiler(
    space_optimal_timeout: int = 60,
):
    def jabalizer_circuit_compiler(
        circuit: Circuit,
        logical_architecture_name: str = "two_row_bus",
        optimization: str = "Space",
        verbose: bool = False,
    ) -> GSCInfo:
        if logical_architecture_name == "Time":
            print("deepest")
            breakpoint()
        compiled_graph_data = jl.run_jabalizer(
            circuit,
            logical_architecture_name,
            optimization,
            verbose,
            space_optimal_timeout,
        )

        return GSCInfo.from_dict(compiled_graph_data)

    return jabalizer_circuit_compiler


def get_algorithmic_graph_and_icm_output(circuit):
    svec, op_seq, icm_output, data_qubits_map = jl.run_jabalizer(circuit)
    return create_graph_from_stabilizers(svec), op_seq, icm_output, data_qubits_map


def create_graph_from_stabilizers(svec) -> nx.Graph:
    G = nx.Graph()
    siz = len(svec)
    for i in range(siz):
        z = svec[i].Z
        for j in range(i + 1, siz):
            if z[j]:
                G.add_edge(i, j)
    return G
