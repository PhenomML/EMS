"""Unit tests for EMS.manager pure utility functions.

No cluster, database, or cloud credentials are required.
"""

import numpy as np
import pandas as pd
import pytest

from EMS.manager import (
    dedup_experiment,
    remove_stop_list,
    unroll_parameters_gpt,
    EvalOnCluster,
)


# ---------------------------------------------------------------------------
# unroll_parameters_gpt
# ---------------------------------------------------------------------------

class TestUnrollParametersGpt:
    def test_empty_dict_returns_empty_list(self):
        assert unroll_parameters_gpt({}) == []

    def test_single_param_single_value(self):
        result = unroll_parameters_gpt({'a': [1]})
        assert result == [{'a': 1}]

    def test_single_param_multiple_values(self):
        result = unroll_parameters_gpt({'a': [1, 2, 3]})
        assert result == [{'a': 1}, {'a': 2}, {'a': 3}]

    def test_two_params_cartesian_product(self):
        result = unroll_parameters_gpt({'a': [1, 2], 'b': [10, 20]})
        assert len(result) == 4
        assert {'a': 1, 'b': 10} in result
        assert {'a': 1, 'b': 20} in result
        assert {'a': 2, 'b': 10} in result
        assert {'a': 2, 'b': 20} in result

    def test_three_params_count(self):
        result = unroll_parameters_gpt({'a': [1, 2], 'b': [10, 20], 'c': [100, 200, 300]})
        assert len(result) == 2 * 2 * 3

    def test_numpy_array_values(self):
        result = unroll_parameters_gpt({'x': np.array([0.1, 0.2]), 'y': [1, 2]})
        assert len(result) == 4
        xs = {r['x'] for r in result}
        assert abs(min(xs) - 0.1) < 1e-9
        assert abs(max(xs) - 0.2) < 1e-9


# ---------------------------------------------------------------------------
# remove_stop_list
# ---------------------------------------------------------------------------

class TestRemoveStopList:
    def test_empty_stop_list_returns_all(self):
        params = [{'a': 1, 'b': 2}, {'a': 3, 'b': 4}]
        assert remove_stop_list(params, []) == params

    def test_exact_match_removed(self):
        params = [{'a': 1, 'b': 2}, {'a': 3, 'b': 4}]
        stop = [{'a': 1, 'b': 2}]
        result = remove_stop_list(params, stop)
        assert result == [{'a': 3, 'b': 4}]

    def test_partial_match_not_removed(self):
        # Only one key matches — should NOT be removed.
        params = [{'a': 1, 'b': 2}]
        stop = [{'a': 1, 'b': 99}]
        assert remove_stop_list(params, stop) == params

    def test_no_match_returns_all(self):
        params = [{'a': 1}, {'a': 2}]
        stop = [{'a': 99}]
        assert remove_stop_list(params, stop) == params

    def test_mismatched_key_lengths_not_removed(self):
        params = [{'a': 1, 'b': 2, 'c': 3}]
        stop = [{'a': 1, 'b': 2}]
        assert remove_stop_list(params, stop) == params

    def test_all_removed(self):
        params = [{'a': 1}, {'a': 2}]
        stop = [{'a': 1}, {'a': 2}]
        assert remove_stop_list(params, stop) == []

    def test_stop_list_entry_consumed_once(self):
        # Each stop entry should only block one params entry.
        params = [{'a': 1}, {'a': 1}]
        stop = [{'a': 1}]
        result = remove_stop_list(params, stop)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# dedup_experiment
# ---------------------------------------------------------------------------

class TestDedupExperiment:
    def test_empty_params_returns_empty(self):
        df = pd.DataFrame({'a': [1], 'b': [2]})
        assert dedup_experiment(df, []) == []

    def test_all_new_params_returned(self):
        df = pd.DataFrame({'a': [1], 'b': [2]})
        params = [{'a': 3, 'b': 4}, {'a': 5, 'b': 6}]
        result = dedup_experiment(df, params)
        assert result == params

    def test_all_duplicates_filtered(self):
        df = pd.DataFrame({'a': [1, 3], 'b': [2, 4]})
        params = [{'a': 1, 'b': 2}, {'a': 3, 'b': 4}]
        assert dedup_experiment(df, params) == []

    def test_partial_overlap(self):
        df = pd.DataFrame({'a': [1], 'b': [2]})
        params = [{'a': 1, 'b': 2}, {'a': 3, 'b': 4}]
        result = dedup_experiment(df, params)
        assert result == [{'a': 3, 'b': 4}]

    def test_duplicate_within_params_deduplicated(self):
        df = pd.DataFrame({'a': [], 'b': []})
        params = [{'a': 1, 'b': 2}, {'a': 1, 'b': 2}]
        result = dedup_experiment(df, params)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# EvalOnCluster.key_from_params validation
# ---------------------------------------------------------------------------

class TestKeyFromParams:
    """Tests for EvalOnCluster.key_from_params without a real Dask client."""

    def _make_eval(self):
        # Construct without a real client — we only test key_from_params.
        obj = object.__new__(EvalOnCluster)
        obj.keys = None
        return obj

    def test_first_call_sets_keys(self):
        ev = self._make_eval()
        key = ev.key_from_params({'b': 2, 'a': 1})
        assert ev.keys == ['a', 'b']
        assert key == (1, 2)

    def test_consistent_keys_pass(self):
        ev = self._make_eval()
        ev.key_from_params({'a': 1, 'b': 2})
        # Same keys, different values — should succeed.
        key = ev.key_from_params({'a': 10, 'b': 20})
        assert key == (10, 20)

    def test_mismatched_keys_raise_value_error(self):
        ev = self._make_eval()
        ev.key_from_params({'a': 1, 'b': 2})
        with pytest.raises(ValueError, match='parameter keys changed'):
            ev.key_from_params({'a': 1, 'c': 3})

    def test_extra_key_raises_value_error(self):
        ev = self._make_eval()
        ev.key_from_params({'a': 1})
        with pytest.raises(ValueError):
            ev.key_from_params({'a': 1, 'b': 2})
