################################################################################
# © Copyright 2021-2022 Zapata Computing Inc.
################################################################################

import os
from collections import Counter
from math import sqrt

import numpy as np
import pytest
from sympy import I, Matrix, Symbol, cos, exp, sin

from orquestra.quantum.backends import SymbolicSimulator
from orquestra.quantum.circuits._builtin_gates import RX, RY, U3, H, X
from orquestra.quantum.circuits._circuit import Circuit
from orquestra.quantum.testing import create_random_wavefunction
from orquestra.quantum.utils import RNDSEED, bitstring_to_tuple
from orquestra.quantum.wavefunction import (
    Wavefunction,
    load_wavefunction,
    sample_from_wavefunction,
    save_wavefunction,
)


def remove_file_if_exists(filename):
    try:
        os.remove(filename)
    except OSError:
        pass


class TestInitSystemInZeroState:
    def test_init_system_returns_numpy_array(self):
        wf = Wavefunction.zero_state(2)
        assert isinstance(wf._amplitude_vector, np.ndarray)

    def test_constructor_returns_numpy_array_for_no_symbols(self):
        wf = Wavefunction([1.0, 0, 0, 0])
        assert isinstance(wf._amplitude_vector, np.ndarray)

    def test_constructor_returns_sympy_matrix_for_free_symbols(self):
        wf = Wavefunction([0.25, 0, Symbol("alpha"), 0])
        assert isinstance(wf._amplitude_vector, Matrix)

    @pytest.mark.parametrize(
        "input_list", [[], np.zeros(17), create_random_wavefunction(3)[:-1]]
    )
    def test_init_fails_when_len_of_passed_list_is_not_power_of_two(self, input_list):
        with pytest.raises(ValueError):
            Wavefunction(input_list)

    @pytest.mark.parametrize("input_list", [np.ones(8), np.zeros(4)])
    def test_init_fails_when_passed_list_has_no_free_symbols_and_no_unity(
        self, input_list
    ):
        with pytest.raises(ValueError):
            Wavefunction(input_list)

    @pytest.mark.parametrize(
        "input_list",
        [
            [Symbol("alpha"), 2.0],
            [
                Symbol("alpha"),
                Symbol("beta"),
                sqrt(3) / 2,
                sqrt(3) / 2,
            ],
        ],
    )
    def test_init_fails_when_passed_list_has_free_symbols_and_exceeds_unity(
        self, input_list
    ):
        with pytest.raises(ValueError):
            Wavefunction(input_list)

    @pytest.mark.parametrize("n_qubits", [1, 2, 3, 4, 5])
    def test_init_system_returns_expected_wavefunction_size(self, n_qubits):
        wavefunction = Wavefunction.zero_state(n_qubits=n_qubits)

        # Check length
        assert len(wavefunction) == 2**n_qubits

        # Check internal property
        assert wavefunction.n_qubits == n_qubits

        # Check amplitude of zero state
        assert wavefunction[0] == 1.0

        # Check amplitude of the rest of the states
        assert not np.any(wavefunction[1:])

    def test_init_system_raises_warning_for_non_ints(self):
        with pytest.warns(UserWarning):
            Wavefunction.zero_state(1.234)

    @pytest.mark.parametrize("n_qubits", [0, -1, -2])
    def test_init_system_fails_on_invalid_params(self, n_qubits):
        with pytest.raises(ValueError):
            Wavefunction.zero_state(n_qubits=n_qubits)


class TestInitSystemInDickeState:
    @pytest.mark.parametrize("num_qubits", [-1, 0])
    def test_function_fails_for_invalid_number_of_qubits(self, num_qubits):
        with pytest.raises(ValueError):
            Wavefunction.dicke_state(num_qubits, 2)

    @pytest.mark.parametrize("hamming_weight", [-1, 3, 3.36])
    def test_function_fails_for_invalid_hamming_weight(self, hamming_weight):
        with pytest.raises(ValueError):
            Wavefunction.dicke_state(2, hamming_weight)

    @pytest.mark.parametrize(
        "expected_set_states,expected_amplitude,hamming_weight",
        [
            ([0], 1.0, 0),
            ([1, 2, 4, 8], 1 / np.sqrt(4), 1),
            ([3, 5, 6, 9, 10, 12], 1 / np.sqrt(6), 2),
            ([7, 11, 13, 14], 1 / np.sqrt(4), 3),
            ([int("1111", base=2)], 1.0, 4),
        ],
    )
    def test_function_returns_expected_wf_for_given_hamming_weight(
        self, expected_set_states, expected_amplitude, hamming_weight
    ):
        wf = Wavefunction.dicke_state(4, hamming_weight=hamming_weight)

        unique = np.unique(wf)
        unique = np.delete(unique, np.where(unique == 0.0))
        assert len(unique) == 1
        assert unique.item() == expected_amplitude

        indices = np.where(wf.amplitudes == unique.item())[0]
        np.testing.assert_array_equal(np.array(expected_set_states), indices)


class TestFunctions:
    @pytest.fixture
    def symbolic_wf(self) -> Wavefunction:
        return Wavefunction([Symbol("alpha"), 0.5, Symbol("beta"), 0.5])

    @pytest.fixture
    def numeric_wf(self) -> Wavefunction:
        return Wavefunction([0.5, 0.5, 0.5, 0.5])

    @pytest.mark.parametrize("new_val", [1.0, -1.0])
    def test_set_item_raises_error_for_invalid_sets(self, symbolic_wf, new_val):
        with pytest.raises(ValueError):
            symbolic_wf[0] = new_val

    @pytest.mark.parametrize("new_value", [0.5, Symbol("gamma")])
    def test_set_item_passes_if_still_below_unity(self, symbolic_wf, new_value):
        symbolic_wf[0] = new_value

        assert symbolic_wf[0] == new_value

    def test_iterator(self, symbolic_wf):
        for i, elem in enumerate(symbolic_wf):
            assert elem == symbolic_wf[i]

    @pytest.mark.parametrize(
        "symbol_map", [{"alpha": 1.0}, {"alpha": 0.5, "beta": 0.6}]
    )
    def test_bindings_fail_like_setitem(self, symbolic_wf, symbol_map):
        with pytest.raises(ValueError):
            symbolic_wf.bind(symbol_map)

    def test_bind_returns_new_object_for_symbolic_wf(self, symbolic_wf):
        assert symbolic_wf is not symbolic_wf.bind({})

    def test_bind_does_not_return_new_object_for_numeric_wf(self, numeric_wf):
        assert numeric_wf is numeric_wf.bind({})

    def test_binding_all_symbols_returns_numpy_array(self, symbolic_wf: Wavefunction):
        assert isinstance(
            symbolic_wf.bind({"alpha": 0.5, "beta": 0.5})._amplitude_vector, np.ndarray
        )

    @pytest.mark.parametrize("other_obj", [[], np.zeros(8)])
    def test_eq_returns_false_for_non_wavefunction_objects(
        self, symbolic_wf, numeric_wf, other_obj
    ):
        assert not (symbolic_wf == other_obj)
        assert not (numeric_wf == other_obj)

    def test_eq_returns_true_for_objects_with_equal_wavefunctions(
        self, symbolic_wf: Wavefunction, numeric_wf: Wavefunction
    ):
        test_wf = Wavefunction(symbolic_wf._amplitude_vector)
        assert symbolic_wf == test_wf

        test_wf = Wavefunction(numeric_wf._amplitude_vector)
        assert numeric_wf == test_wf


class TestRepresentations:
    def test_string_output_of_symbolic_wavefunction(self):
        wf = Wavefunction([Symbol("alpha"), 0])

        wf_str = wf.__str__()

        assert "alpha" in wf_str
        assert wf_str.endswith("])")
        assert wf_str.startswith("Wavefunction([")

    def test_string_output_of_numeric_wavefunction(self):
        wf = Wavefunction([1j, 0])

        wf_str = wf.__str__()

        assert "j" in wf_str
        assert wf_str.endswith("])")
        assert wf_str.startswith("Wavefunction([")

    @pytest.mark.parametrize(
        "wf", [Wavefunction.zero_state(2), Wavefunction([Symbol("alpha"), 0.0])]
    )
    def test_amplitudes_and_probs_output_type(self, wf: Wavefunction):
        if len(wf.free_symbols) > 0:
            assert wf.amplitudes.dtype == object
            assert wf.get_probabilities().dtype == object
        else:
            assert wf.amplitudes.dtype == np.complex128
            assert wf.get_probabilities().dtype == np.float64

    @pytest.mark.parametrize(
        "wf_vec",
        [
            [1.0, 0.0],
            [0.5, 0.5, 0.5, 0.5],
            [1 / sqrt(2), 0, 0, 0, 0, 0, 0, 1 / sqrt(2)],
        ],
    )
    def test_get_outcome_probs(self, wf_vec):
        wf = Wavefunction(wf_vec)
        probs_dict = wf.get_outcome_probs()

        assert all([len(key) == wf.n_qubits for key in probs_dict.keys()])

        for key in probs_dict.keys():
            assert len(key) == wf.n_qubits

            assert wf.get_probabilities()[int(key, 2)] == probs_dict[key]


class TestGates:
    @pytest.fixture
    def simulator(self) -> SymbolicSimulator:
        return SymbolicSimulator()

    @pytest.mark.parametrize(
        "circuit, expected_wavefunction",
        [
            (
                Circuit([RX(Symbol("theta"))(0)]),
                Wavefunction(
                    [1.0 * cos(Symbol("theta") / 2), -1j * sin(Symbol("theta") / 2)]
                ),
            ),
            (
                Circuit([X(0), RY(Symbol("theta"))(0)]),
                Wavefunction(
                    [
                        -1.0 * sin(Symbol("theta") / 2),
                        1.0 * cos(Symbol("theta") / 2),
                    ]
                ),
            ),
            (
                Circuit(
                    [H(0), U3(Symbol("theta"), Symbol("phi"), Symbol("lambda"))(0)]
                ),
                Wavefunction(
                    [
                        cos(Symbol("theta") / 2) / sqrt(2)
                        + -exp(I * Symbol("lambda"))
                        * sin(Symbol("theta") / 2)
                        / sqrt(2),
                        exp(I * Symbol("phi")) * sin(Symbol("theta") / 2) / sqrt(2)
                        + exp(I * (Symbol("lambda") + Symbol("phi")))
                        * cos(Symbol("theta") / 2)
                        / sqrt(2),
                    ]
                ),
            ),
        ],
    )
    def test_wavefunction_works_as_expected_with_symbolic_circuits(
        self,
        simulator: SymbolicSimulator,
        circuit: Circuit,
        expected_wavefunction: Wavefunction,
    ):
        returned_wavefunction = simulator.get_wavefunction(circuit)

        assert returned_wavefunction == expected_wavefunction


def test_real_wavefunction_io():
    wf = Wavefunction([0, 1, 0, 0, 0, 0, 0, 0])
    save_wavefunction(wf, "wavefunction.json")
    loaded_wf = load_wavefunction("wavefunction.json")
    assert np.allclose(wf.amplitudes, loaded_wf.amplitudes)
    remove_file_if_exists("wavefunction.json")


def test_imag_wavefunction_io():
    wf = Wavefunction([0, 1j, 0, 0, 0, 0, 0, 0])
    save_wavefunction(wf, "wavefunction.json")
    loaded_wf = load_wavefunction("wavefunction.json")
    assert np.allclose(wf.amplitudes, loaded_wf.amplitudes)
    remove_file_if_exists("wavefunction.json")


def test_sample_from_wavefunction():
    wavefunction = create_random_wavefunction(4, seed=RNDSEED)
    num_samples = 100000

    samples = sample_from_wavefunction(wavefunction, num_samples, seed=RNDSEED)
    sampled_dict = Counter(samples)

    sampled_probabilities = []
    for num in range(len(wavefunction)):
        bitstring = format(num, "b")
        while len(bitstring) < wavefunction.n_qubits:
            bitstring = "0" + bitstring
        measurement = bitstring_to_tuple(bitstring)[::-1]
        sampled_probabilities.append(sampled_dict[measurement] / num_samples)

    probabilities = wavefunction.get_probabilities()
    for sampled_prob, exact_prob in zip(sampled_probabilities, probabilities):
        assert np.allclose(sampled_prob, exact_prob, atol=0.01)


def test_sample_from_wavefunction_column_vector():
    n_qubits = 4
    expected_bitstring = (0, 0, 0, 1)
    amplitudes = np.array([0] * (2**n_qubits)).reshape(2**n_qubits, 1)
    amplitudes[1] = 1  # |0001> will be measured in all cases.
    wavefunction = Wavefunction(amplitudes)
    sample = set(sample_from_wavefunction(wavefunction, 500))
    assert len(sample) == 1
    assert sample.pop() == expected_bitstring


def test_sample_from_wavefunction_row_vector():
    n_qubits = 4
    expected_bitstring = (0, 0, 0, 1)
    amplitudes = np.array([0] * (2**n_qubits))
    amplitudes[1] = 1  # |0001> will be measured in all cases.
    wavefunction = Wavefunction(amplitudes)
    sample = set(sample_from_wavefunction(wavefunction, 500))
    assert len(sample) == 1
    assert sample.pop() == expected_bitstring


def test_sample_from_wavefunction_list():
    n_qubits = 4
    expected_bitstring = (0, 0, 0, 1)
    amplitudes = [0] * (2**n_qubits)
    amplitudes[1] = 1  # |0001> will be measured in all cases.
    wavefunction = Wavefunction(amplitudes)
    sample = set(sample_from_wavefunction(wavefunction, 500))
    assert len(sample) == 1
    assert sample.pop() == expected_bitstring


@pytest.mark.parametrize("n_samples", [-1, 0])
def test_sample_from_wavefunction_fails_for_invalid_n_samples(n_samples):
    n_qubits = 4
    amplitudes = [0] * (2**n_qubits)
    amplitudes[1] = 1
    wavefunction = Wavefunction(amplitudes)
    with pytest.raises(ValueError):
        sample_from_wavefunction(wavefunction, n_samples)
