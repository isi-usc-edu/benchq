################################################################################
# © Copyright 2022-2023 Zapata Computing Inc.
################################################################################
import os
import pathlib

import networkx as nx
import numpy as np
import pytest
import stim
from numba import njit
from orquestra.integrations.qiskit.conversions import import_from_qiskit
from orquestra.quantum.circuits import CNOT, CZ, Circuit, Dagger, H, S, T, X
from qiskit import QuantumCircuit

from benchq.compilation.circuits import compile_to_native_gates
from benchq.compilation.graph_states import jl
from benchq.problem_embeddings.quantum_program import QuantumProgram

SKIP_SLOW = pytest.mark.skipif(
    os.getenv("SLOW_BENCHMARKS") is None,
    reason="Slow benchmarks can only run if SLOW_BENCHMARKS env variable is defined",
)


@pytest.mark.parametrize(
    "circuit",
    [
        Circuit([X(0)]),
        Circuit([H(0)]),
        Circuit([S(0)]),
        Circuit([H(0), S(0), H(0)]),
        Circuit([H(0), S(0)]),
        Circuit([S(0), H(0)]),
        Circuit([S.dagger(0)]),
        Circuit([H(2)]),
        Circuit([H(0), CNOT(0, 1)]),
        Circuit([CZ(0, 1), H(2)]),
        Circuit([H(0), S(0), CNOT(0, 1), H(2)]),
        Circuit([CNOT(0, 1), CNOT(1, 2)]),
        Circuit(
            [
                H(0),
                S(0),
                H(1),
                CZ(0, 1),
                H(2),
                CZ(1, 2),
            ]
        ),
        Circuit(
            [
                H(0),
                H(1),
                H(3),
                CZ(0, 3),
                CZ(1, 4),
                H(3),
                H(4),
                CZ(3, 4),
            ]
        ),
    ],
)
def test_stabilizer_states_are_the_same_for_simple_circuits(circuit):
    target_tableau = get_target_tableau(circuit)

    hyperparams = jl.RbSHyperparams(
        jl.UInt16(999), jl.UInt8(4), jl.UInt8(6), jl.UInt32(1e5), jl.UInt8(0)
    )

    asg, pauli_tracker, _ = jl.get_rbs_graph_state_data(
        circuit,
        verbose=False,
        takes_graph_input=False,
        gives_graph_output=False,
        optimization="Time",
        hyperparams=hyperparams,
    )
    num_logical_qubits = jl.get_num_logical_qubits(pauli_tracker.layering, asg, "Time")

    asg = jl.python_asg(asg)
    pauli_tracker = jl.python_pauli_tracker(pauli_tracker)

    vertices = list(zip(asg["sqs"], asg["edge_data"]))
    graph_tableau = get_stabilizer_tableau_from_vertices(vertices)

    assert len(pauli_tracker["layering"]) == 1
    assert num_logical_qubits == circuit.n_qubits
    assert_tableaus_correspond_to_the_same_stabilizer_state(
        graph_tableau, target_tableau
    )


@pytest.mark.parametrize(
    "circuit, target_non_clifford_layers, target_qubits, optimization, max_num_qubits",
    [
        (Circuit([H(0)] + [CNOT(0, i) for i in range(4)]), 1, 4, "Time", -1),
        (Circuit([H(0)] + [CNOT(0, i) for i in range(4)]), 3, 2, "Space", -1),
        (Circuit([H(0)] + [CNOT(0, i) for i in range(4)]), 3, 2, "Variable", 2),
        (Circuit([H(0), T(0)] * 3), 3, 3, "Time", -1),
        (Circuit([H(0), T(0)] * 3), 3, 2, "Space", -1),
        (Circuit([H(0), T(0)] * 3), 3, 2, "Variable", 2),
    ],
)
def test_tocks_layers_and_qubits_are_correct(
    circuit,
    target_non_clifford_layers,
    target_qubits,
    optimization,
    max_num_qubits,
):
    hyperparams = jl.RbSHyperparams(
        jl.UInt16(999), jl.UInt8(4), jl.UInt8(6), jl.UInt32(1e5), jl.UInt8(0)
    )
    asg, pauli_tracker, _ = jl.get_rbs_graph_state_data(
        circuit,
        verbose=False,
        takes_graph_input=False,
        gives_graph_output=False,
        optimization=optimization,
        hyperparams=hyperparams,
        max_num_qubits=max_num_qubits,
    )
    num_logical_qubits = jl.get_num_logical_qubits(
        pauli_tracker.layering, asg, optimization
    )

    asg = jl.python_asg(asg)
    pauli_tracker = jl.python_pauli_tracker(pauli_tracker)

    assert len(pauli_tracker["layering"]) == target_non_clifford_layers
    assert num_logical_qubits == target_qubits


@pytest.mark.parametrize(
    "filename",
    [
        "example_circuit.qasm",
    ],
)
def test_stabilizer_states_are_the_same_for_circuits(filename):
    try:
        qiskit_circuit = import_from_qiskit(QuantumCircuit.from_qasm_file(filename))
    except FileNotFoundError:
        qiskit_circuit = import_from_qiskit(
            QuantumCircuit.from_qasm_file(os.path.join("examples", "data", filename))
        )

    circuit = compile_to_native_gates(qiskit_circuit)
    test_circuit = get_icm(circuit)

    target_tableau = get_target_tableau(test_circuit)

    hyperparams = jl.RbSHyperparams(
        jl.UInt16(999), jl.UInt8(4), jl.UInt8(6), jl.UInt32(1e5), jl.UInt8(0)
    )
    asg, pauli_tracker, _ = jl.get_rbs_graph_state_data(
        circuit,
        verbose=False,
        takes_graph_input=False,
        gives_graph_output=False,
        optimization="Time",
        hyperparams=hyperparams,
    )
    asg = jl.python_asg(asg)

    vertices = list(zip(asg["sqs"], asg["edge_data"]))
    graph_tableau = get_stabilizer_tableau_from_vertices(vertices)

    assert_tableaus_correspond_to_the_same_stabilizer_state(
        graph_tableau, target_tableau
    )


@pytest.mark.parametrize(
    "circuit, teleportation_threshold, teleportation_distance, num_teleportations",
    [
        # tests that a circuit with no teleportations does not teleport
        (Circuit([H(0), *[CNOT(0, i) for i in range(1, 5)]]), 4, 4, 0),
        # tests changing threshold
        (Circuit([H(0), *[CNOT(0, i) for i in range(1, 5)]]), 3, 4, 1),
        # test that teleportation_distance is respected
        (Circuit([H(0), *[CNOT(0, i) for i in range(1, 6)]]), 4, 6, 1),
        # creates a node of degree 4 which will be teleported. Requires 5 CNOTS
        # 4 to make the node of degree 4 and 1 to activate the teleport
        (Circuit([H(0), *[CNOT(0, i) for i in range(1, 6)]]), 4, 4, 1),
        (Circuit([H(0), *[CNOT(0, i) for i in range(1, 8)]]), 4, 4, 1),
        # test multiple teleportations:
        (Circuit([H(0), *[CNOT(0, i) for i in range(1, 9)]]), 4, 4, 2),
        (Circuit([H(0), *[CNOT(0, i) for i in range(1, 11)]]), 4, 4, 2),
        (Circuit([H(0), *[CNOT(0, i) for i in range(1, 12)]]), 4, 4, 3),
        (Circuit([H(0), *[CNOT(0, i) for i in range(1, 14)]]), 4, 4, 3),
        (Circuit([H(0), *[CNOT(0, i) for i in range(1, 15)]]), 4, 4, 4),
        # test gates that must be decomposed
        (Circuit([H(0), *[T(0) for _ in range(1, 5)]]), 4, 4, 0),
        # commenting out these test for now as they are only relevant for
        # decomposition strategy 1.
        # # test single teleporatation
        # (Circuit([H(0), *[T(0) for _ in range(1, 6)]]), 4, 4, 1),
        # (Circuit([H(0), *[T(0) for _ in range(1, 8)]]), 4, 4, 1),
        # # test multiple teleportations with gates that must be decomposed
        # (Circuit([H(0), *[T(0) for _ in range(1, 9)]]), 4, 4, 2),
        # (Circuit([H(0), *[T(0) for _ in range(1, 11)]]), 4, 4, 2),
        # (Circuit([H(0), *[T(0) for _ in range(1, 12)]]), 4, 4, 3),
        # (Circuit([H(0), *[T(0) for _ in range(1, 14)]]), 4, 4, 3),
        # (Circuit([H(0), *[T(0) for _ in range(1, 15)]]), 4, 4, 4),
    ],
)
def test_teleportation_produces_correct_number_of_nodes_for_small_circuits(
    circuit, teleportation_threshold, teleportation_distance, num_teleportations
):
    quantum_program = QuantumProgram.from_circuit(circuit)
    n_t_gates = quantum_program.n_t_gates
    n_rotations = quantum_program.n_rotation_gates

    hyperparams = jl.RbSHyperparams(
        jl.UInt16(teleportation_threshold),
        jl.UInt8(teleportation_distance),
        jl.UInt8(6),
        jl.UInt32(1e5),
        jl.UInt8(0),
    )
    asg, pauli_tracker, _ = jl.get_rbs_graph_state_data(
        circuit,
        verbose=False,
        takes_graph_input=False,
        gives_graph_output=False,
        optimization="Time",
        hyperparams=hyperparams,
    )
    asg = jl.python_asg(asg)

    n_nodes = len(asg["sqp"])

    assert (
        n_nodes
        == circuit.n_qubits
        + (n_t_gates + n_rotations)
        + teleportation_distance * num_teleportations
    )


# @pytest.mark.skip(reason="This test requires hyperparameter tuning.")
@pytest.mark.parametrize(
    "circuit, rbs_iteration_time, expected_prop_range, logical_architecture_name",
    [
        (Circuit([H(0), CNOT(0, 1)]), 1.0, [0.9, 1.0], "two_row_bus"),
        (Circuit([H(0), CNOT(0, 1)]), 1.0, [0.9, 1.0], "all_to_all"),
        (
            Circuit(
                [H(0), *[CNOT(j, i) for i in range(1, 300) for j in range(2, 300)]]
            ),
            0.1,
            [0.0, 0.5],
            "two_row_bus",
        ),
        (
            Circuit(
                [H(0), *[CNOT(j, i) for i in range(1, 300) for j in range(2, 300)]]
            ),
            0.1,
            [0.0, 0.5],
            "all_to_all",
        ),
    ],
)
def test_rbs_gives_reasonable_prop(
    circuit, rbs_iteration_time, expected_prop_range, logical_architecture_name
):
    # when
    _, prop = jl.run_ruby_slippers(
        circuit,
        takes_graph_input=False,
        gives_graph_output=False,
        logical_architecture_name=logical_architecture_name,
        optimization="Time",
        verbose=True,
        max_graph_size=9999,
        teleportation_threshold=40,
        teleportation_distance=9,
        max_time=rbs_iteration_time,
    )

    # then
    assert prop >= expected_prop_range[0] and prop <= expected_prop_range[1]


def test_rbs_with_all_to_all_gives_fewer_graph_creation_cycles_than_two_row():

    # given
    circuit = Circuit(
        [
            H(0),
            T(0),
            *[CNOT(j, i) for i in range(1, 300) for j in range(2, 300)],
        ]
    )
    optimization = "Time"

    compiled_data_two_row, _ = jl.run_ruby_slippers(
        circuit,
        verbose=False,
        logical_architecture_name="two_row_bus",
        optimization=optimization,
    )

    compiled_data_all_to_all, _ = jl.run_ruby_slippers(
        circuit,
        verbose=False,
        logical_architecture_name="all_to_all",
        optimization=optimization,
    )

    # then
    assert sum(compiled_data_all_to_all["graph_creation_tocks_per_layer"]) < sum(
        compiled_data_two_row["graph_creation_tocks_per_layer"]
    )


def test_all_to_all_has_fewer_tocks_than_two_row():

    # given
    toffoli_circuit = Circuit(
        [
            T(0),
            T(1),
            H(2),
            CNOT(0, 1),
            T(2),
            CNOT(1, 2),
            T.dagger(1),
            T(2),
            CNOT(0, 1),
            CNOT(1, 2),
            CNOT(0, 1),
            T.dagger(2),
            CNOT(1, 2),
            CNOT(0, 1),
            T.dagger(2),
            CNOT(1, 2),
            H(2),
        ]
    )
    optimization = "Time"

    compiled_data_two_row, _ = jl.run_ruby_slippers(
        toffoli_circuit,
        verbose=True,
        logical_architecture_name="two_row_bus",
        optimization=optimization,
    )

    compiled_data_all_to_all, _ = jl.run_ruby_slippers(
        toffoli_circuit,
        verbose=False,
        logical_architecture_name="all_to_all",
        optimization=optimization,
    )

    # then
    assert sum(compiled_data_all_to_all["graph_creation_tocks_per_layer"]) < sum(
        compiled_data_two_row["graph_creation_tocks_per_layer"]
    )


def test_number_of_t_measurements_equals_number_of_t_gates():
    toffoli_circuit = Circuit(
        [
            T(0),
            T(1),
            H(2),
            CNOT(0, 1),
            T(2),
            CNOT(1, 2),
            T.dagger(1),
            T(2),
            CNOT(0, 1),
            CNOT(1, 2),
            CNOT(0, 1),
            T.dagger(2),
            CNOT(1, 2),
            CNOT(0, 1),
            T.dagger(2),
            CNOT(1, 2),
            H(2),
        ]
    )
    optimization = "Time"
    number_of_t_gates = sum(
        [1 for op in toffoli_circuit.operations if op.gate.name in ["T", "T_Dagger"]]
    )

    compiled_data_two_row, _ = jl.run_ruby_slippers(
        toffoli_circuit,
        verbose=True,
        logical_architecture_name="two_row_bus",
        optimization=optimization,
    )

    compiled_data_all_to_all, _ = jl.run_ruby_slippers(
        toffoli_circuit,
        verbose=False,
        logical_architecture_name="all_to_all",
        optimization=optimization,
    )
    assert sum(compiled_data_all_to_all["t_states_per_layer"]) == number_of_t_gates
    assert sum(compiled_data_two_row["t_states_per_layer"]) == number_of_t_gates


########################################################################################
# Everything below here is testing utils
########################################################################################


def get_icm(circuit: Circuit, gates_to_decompose=["T", "T_Dagger", "RZ"]) -> Circuit:
    """Convert a circuit to the ICM form.

    Args:
        circuit (Circuit): the circuit to convert to ICM form
        gates_to_decompose (list, optional): list of gates to decompose into CNOT
        and adding ancilla qubits. Defaults to ["T", "T_Dagger"].

    Returns:
        Circuit: the circuit in ICM form
    """
    compiled_qubit_index = {i: i for i in range(circuit.n_qubits)}
    icm_circuit = []
    icm_circuit_n_qubits = circuit.n_qubits - 1
    for op in circuit.operations:
        compiled_qubits = [
            compiled_qubit_index.get(qubit, qubit) for qubit in op.qubit_indices
        ]

        if op.gate.name in gates_to_decompose:
            for original_qubit, compiled_qubit in zip(
                op.qubit_indices, compiled_qubits
            ):
                icm_circuit_n_qubits += 1
                compiled_qubit_index[original_qubit] = icm_circuit_n_qubits
                icm_circuit += [CNOT(compiled_qubit, icm_circuit_n_qubits)]
        elif op.gate.name == "RESET":
            for original_qubit, compiled_qubit in zip(
                op.qubit_indices, compiled_qubits
            ):
                icm_circuit_n_qubits += 1
                compiled_qubit_index[original_qubit] = icm_circuit_n_qubits
        else:
            icm_circuit += [
                op.gate(*[compiled_qubit_index[i] for i in op.qubit_indices])
            ]

    return Circuit(icm_circuit)


def get_target_tableau(circuit):
    sim = stim.TableauSimulator()
    for op in circuit.operations:
        if op.gate.name == "I":
            continue
        if op.gate.name == "X":
            sim.x(*op.qubit_indices)
        elif op.gate.name == "Y":
            sim.y(*op.qubit_indices)
        elif op.gate.name == "Z":
            sim.z(*op.qubit_indices)
        elif op.gate.name == "CNOT":
            sim.cx(*op.qubit_indices)
        elif op.gate.name == "S_Dagger":
            sim.s_dag(*op.qubit_indices)
        elif op.gate.name == "S":
            sim.s(*op.qubit_indices)
        elif op.gate.name == "SX":
            sim.sqrt_x(*op.qubit_indices)
        elif op.gate.name == "SX_Dagger":
            sim.sqrt_x_dag(*op.qubit_indices)
        elif op.gate.name == "H":
            sim.h(*op.qubit_indices)
        elif op.gate.name == "CZ":
            sim.cz(*op.qubit_indices)
        else:
            raise ValueError(f"Gate {op.gate.name} not supported.")
    return get_tableau_from_stim_simulator(sim)


def get_stabilizer_tableau_from_vertices(vertices):
    n_qubits = len(vertices)

    all_xs = np.identity(n_qubits, dtype=bool)
    all_zs = np.zeros((n_qubits, n_qubits), dtype=bool)

    for vertex_id, vertex in enumerate(vertices):
        for neighbor in vertex[1]:
            all_zs[neighbor, vertex_id] = True
            all_zs[vertex_id, neighbor] = True

    paulis = []
    for xs, zs in zip(all_xs, all_zs):
        paulis = paulis + [stim.PauliString.from_numpy(xs=xs, zs=zs)]

    sim = stim.TableauSimulator()
    tableau = stim.Tableau.from_stabilizers(paulis)  # performance bottleneck is here
    sim.set_inverse_tableau(tableau.inverse())

    cliffords = []
    for vertex in vertices:
        # get vertex operations for each node in the tableau
        pauli_perm_class = vertex[0] - 1
        if pauli_perm_class == 0:
            cliffords += [[]]
        if pauli_perm_class == 1:
            cliffords += [["s"]]
        if pauli_perm_class == 2:
            cliffords += [["h"]]
        if pauli_perm_class == 3:
            cliffords += [["h", "s", "h"]]
        if pauli_perm_class == 4:
            cliffords += [["s", "h"]]
        if pauli_perm_class == 5:
            cliffords += [["h", "s"]]

    # perform the vertices operations on the tableau
    for i in range(n_qubits):
        for clifford in cliffords[i]:
            if clifford == "s":
                sim.s(i)
            elif clifford == "h":
                sim.h(i)

    return get_tableau_from_stim_simulator(sim)


def get_tableau_from_stim_simulator(sim):
    return np.column_stack(sim.current_inverse_tableau().inverse().to_numpy()[2:4])


def assert_tableaus_correspond_to_the_same_stabilizer_state(tableau_1, tableau_2):
    assert tableau_1.shape == tableau_2.shape

    n_qubits = len(tableau_2)

    # ensure that the graph tableau and the target tableau are composed
    # of paulis belonging to the same stabilizer group
    assert check_tableau_entries_commute

    # ensure that the stabilizers in the tableaus are linearly independent
    assert np.linalg.matrix_rank(tableau_1) == n_qubits
    assert np.linalg.matrix_rank(tableau_2) == n_qubits


@njit
def check_tableau_entries_commute(tableau_1, tableau_2):
    """Checks that the entries of two tableaus commute with each other.

    Args:
        tableau (np.array): tableau to check

    Returns:
        bool: true if the entries commute, false otherwise.
    """
    n_qubits = len(tableau_1) // 2

    for i in range(n_qubits):
        for j in range(i, n_qubits):
            if not commutes(tableau_1[i], tableau_2[j]):
                return False
    return True


@njit
def commutes(stab_1, stab_2):
    """Returns true if self commutes with other, otherwise false.

    Args:
        other (SymplecticPauli): SymplecticPauli for commutation

    Returns:
        bool: true if self and other commute, false otherwise.
    """
    n_qubits = len(stab_1) // 2
    comm1 = _bool_dot(stab_1[:n_qubits], stab_2[n_qubits:])
    comm2 = _bool_dot(stab_1[n_qubits:], stab_2[:n_qubits])
    return not (comm1 ^ comm2)


# numpy doesn't use the boolean binary ring when performing dot products
# https://github.com/numpy/numpy/issues/1456.
# So we define our own dot product which uses "xor" instead of "or" for addition.
@njit
def _bool_dot(x, y):
    array_and = np.logical_and(x, y)
    ans = array_and[0]
    for i in array_and[1:]:
        ans = np.logical_xor(ans, i)
    return ans


def adjacency_list_to_graph(adjacency_list):
    """Converts an adjacency list to an adjacency matrix.

    Args:
      adjacency_list: The adjacency list to convert.

    Returns:
      The adjacency matrix.
    """

    # Create the adjacency matrix.
    adjacency_matrix = [
        [0 for _ in range(len(adjacency_list))] for _ in range(len(adjacency_list))
    ]

    # Iterate over the adjacency list and fill in the adjacency matrix.
    for node, neighbors in enumerate(adjacency_list):
        for neighbor in neighbors:
            adjacency_matrix[node][neighbor] = 1

    return nx.from_numpy_matrix(np.array(adjacency_matrix))


# Take this code to plot a graph
# import matplotlib.pyplot as plt
# nx.draw(adjacency_list_to_graph(adj))
# plt.show()
