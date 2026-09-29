from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from app_ui import comparison_plot


class ChartTests(unittest.TestCase):
    def test_identical_method_errors_share_one_visible_legend_entry(self):
        results = pd.read_csv(Path(__file__).resolve().parents[1] / 'summary.csv')
        cases = [
            ('daily_mean_mae', 4, False, 'Leave missing'),
            ('low_hours_mae', 3, True, 'Leave missing = Median'),
            ('daily_minimum_mae', 2, True,
             'Leave missing = Median = Linear interpolation'),
        ]
        for metric, expected_lines, expected_tie, shared_label in cases:
            with self.subTest(metric=metric), patch('app_ui.st.pyplot') as pyplot:
                tied = comparison_plot(results, metric, 'Error')
                figure = pyplot.call_args.args[0]
                axis = figure.axes[0]
                labels = [text.get_text() for text in axis.get_legend().get_texts()]
                self.assertEqual(tied, expected_tie)
                self.assertEqual(len(axis.lines), expected_lines)
                self.assertIn(shared_label, labels)
                shared = next(line for line in axis.lines if line.get_label() == shared_label)
                expected = results.loc[results.method.eq('Unfilled')].sort_values('gap_hours')[metric]
                np.testing.assert_array_equal(shared.get_ydata(), expected.to_numpy())


if __name__ == '__main__':
    unittest.main()
