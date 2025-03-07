################################################################################
# © Copyright 2022-2023 Zapata Computing Inc.
################################################################################
import os
import sys

MAIN_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(MAIN_DIR))
from examples.data.get_icm import get_icm  # noqa: E402
from examples.ex_1_from_qasm import main as from_qasm_main  # noqa: E402


def test_from_qasm_example():
    file_path = os.path.join("examples", "data", "example_circuit.qasm")
    from_qasm_main(file_path)
