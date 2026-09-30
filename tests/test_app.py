from pathlib import Path
from io import BytesIO
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

ROOT=Path(__file__).resolve().parents[1]


def find(elements,label):
    return next(x for x in elements if x.label==label)


def synthetic():
    at=AppTest.from_file(str(ROOT/'app.py')).run(timeout=30)
    at.session_state['uploaded_bytes']=(ROOT/'examples'/'compatible.csv').read_bytes()
    find(at.radio,'Pages').set_value('Process New Data').run()
    find(at.selectbox,'Dissolved oxygen units *').set_value('mg/L').run()
    find(at.checkbox,'I reviewed these source checks. *').check().run()
    return at


def evaluate_ui(at):
    find(at.button,'Check the record →').click().run()
    assert not any(x.label=='Run method tests' for x in at.button)
    find(at.button,'Test the methods →').click().run()
    find(at.button,'Run method tests').click().run(timeout=30)
    assert not any(x.label=='Method to apply' for x in at.selectbox)
    find(at.button,'Choose gaps →').click().run()


def back_to_input(at):
    while at.session_state['oxygen_stage']>1:
        next(x for x in at.button if x.label.startswith('← Back')).click().run()


def choose_method(at, method):
    find(at.selectbox,'Method to apply').set_value(method).run(timeout=30)
    find(at.button,'Choose gaps →').click().run(timeout=30)


class AppTests(unittest.TestCase):
    def test_stage_one_required_steps_are_separate_and_gate_the_gap_audit(self):
        at=AppTest.from_file(str(ROOT/'app.py')).run(timeout=30)
        at.session_state['uploaded_bytes']=(ROOT/'examples'/'compatible.csv').read_bytes()
        find(at.radio,'Pages').set_value('Process New Data').run()
        self.assertTrue(any('complete both required steps' in x.value.lower() for x in at.markdown))
        self.assertTrue(find(at.button,'Check the record →').disabled)
        self.assertTrue(any('Review source checks' in x.value for x in at.markdown))

        find(at.selectbox,'Dissolved oxygen units *').set_value('mg/L').run()
        self.assertTrue(find(at.button,'Check the record →').disabled)
        review=find(at.checkbox,'I reviewed these source checks. *')
        review.check().run()
        self.assertFalse(find(at.button,'Check the record →').disabled)
        find(at.number_input,'Upper oxygen screening bound (mg/L)').set_value(24.0).run()
        self.assertFalse(find(at.checkbox,'I reviewed these source checks. *').value)
        self.assertTrue(find(at.button,'Check the record →').disabled)
        find(at.checkbox,'I reviewed these source checks. *').check().run()
        self.assertFalse(find(at.button,'Check the record →').disabled)
        find(at.button,'Check the record →').click().run()
        self.assertEqual(at.session_state['oxygen_stage'],2)
        self.assertFalse(at.exception)

    def test_upload_ingress_and_problematic_file(self):
        # AppTest does not drive a native file picker. Supply its returned byte stream,
        # then exercise the real upload branch, validation, evaluation, and export UI.
        for filename in ['compatible.csv','problematic.csv']:
            with self.subTest(filename=filename), patch('streamlit.file_uploader',return_value=BytesIO((ROOT/'examples'/filename).read_bytes())):
                at=AppTest.from_file(str(ROOT/'app.py')).run(timeout=30)
                find(at.radio,'Pages').set_value('Process New Data').run()
                self.assertFalse(any(x.label=='Input' for x in at.selectbox))
                self.assertTrue(any(x.label=='Try an example dataset' for x in at.expander))
                self.assertFalse(any('Next: map your columns' in x.value for x in at.markdown))
                find(at.selectbox,'Dissolved oxygen units *').set_value('mg/L').run()
                find(at.checkbox,'I reviewed these source checks. *').check().run()
                if filename=='problematic.csv':
                    self.assertTrue(any('Irregular timestamps' in e.value for e in at.error))
                    self.assertFalse(any(x.label=='Run method tests' for x in at.button))
                else:
                    evaluate_ui(at)
                    choose_method(at,'Linear interpolation')
                    find(at.multiselect,'Gaps to fill').set_value([2]).run()
                    find(at.button,'Review selected gaps →').click().run(timeout=30)
                    self.assertTrue(any(x.proto.label=='Download separate processed CSV' for x in at.get('download_button')))
                self.assertFalse(at.exception)

    def test_ui_selection_preview_download_and_stale_results(self):
        at=synthetic()
        find(at.selectbox,'Row quality flag').set_value('quality').run()
        at.multiselect[0].set_value(['good']).run()
        find(at.checkbox,'I reviewed these source checks. *').check().run()
        find(at.checkbox,'Include random forest if supported').check().run()
        find(at.checkbox,'Predictors are independent measurements in the stated units, not derived from oxygen; their quality flags have been applied.').check().run()
        evaluate_ui(at)
        self.assertFalse(at.exception)
        method=find(at.selectbox,'Method to apply')
        self.assertEqual(method.value,'Choose a method…')
        self.assertIn('Random forest',method.options)
        choose_method(at,'Random forest')
        gaps=find(at.multiselect,'Gaps to fill')
        self.assertEqual(gaps.value,[])
        gaps.set_value([2]).run(timeout=30)
        find(at.button,'Review selected gaps →').click().run(timeout=30)
        self.assertFalse(at.exception)
        self.assertTrue(any('<strong>1</strong> values to reconstruct' in x.value for x in at.markdown))
        download=next(x for x in at.get('download_button') if x.proto.label=='Download separate processed CSV')
        self.assertTrue(download.proto.url)
        # Any validation setting change invalidates prior evaluation and removes export.
        next(x for x in at.button if x.label.startswith('← Back')).click().run()
        self.assertEqual(find(at.selectbox,'Method to apply').value,'Random forest')
        self.assertEqual(find(at.multiselect,'Gaps to fill').value,[2])
        back_to_input(at)
        self.assertEqual(find(at.selectbox,'Dissolved oxygen units *').value,'mg/L')
        find(at.number_input,'Upper oxygen screening bound (mg/L)').set_value(24.0).run()
        self.assertFalse(any(x.label=='Method to apply' for x in at.selectbox))
        self.assertFalse(any(x.proto.label=='Download separate processed CSV' for x in at.get('download_button')))
        self.assertNotIn('oxygen_evaluation',at.session_state)
        self.assertNotIn('oxygen_output',at.session_state)
        self.assertFalse(at.exception)

    def test_ui_without_predictors_and_new_input_reset(self):
        at=synthetic()
        evaluate_ui(at)
        method=find(at.selectbox,'Method to apply')
        self.assertNotIn('Random forest',method.options)
        choose_method(at,'Linear interpolation')
        find(at.multiselect,'Gaps to fill').set_value([2,3,4,6]).run()
        find(at.button,'Review selected gaps →').click().run(timeout=30)
        self.assertTrue(any('<strong>8</strong> values to reconstruct' in x.value for x in at.markdown))
        self.assertTrue(any('<strong>12</strong> left missing / excluded' in x.value for x in at.markdown))
        back_to_input(at)
        with patch('streamlit.file_uploader',return_value=BytesIO((ROOT/'examples'/'problematic.csv').read_bytes())):
            at.run()
        self.assertNotIn('oxygen_evaluation',at.session_state)
        self.assertFalse(any(x.proto.label=='Download separate processed CSV' for x in at.get('download_button')))
        self.assertFalse(at.exception)

    def test_example_gap_audit_is_plain_and_matches_prepared_record(self):
        at=synthetic()
        find(at.button,'Check the record →').click().run()
        prepared=at.session_state['oxygen_prepared']
        self.assertEqual(len(prepared.gaps),6)
        self.assertEqual(int(prepared.gaps.reason.eq('').sum()),4)
        self.assertTrue(any('**4** can proceed to method testing; **2** cannot be filled' in x.value for x in at.markdown))
        gap_view=at.dataframe[0].value
        self.assertEqual(gap_view.shape,(6,4))
        self.assertEqual((gap_view['What happens next']=='Can proceed to testing').sum(),4)
        self.assertTrue(any('start of the record' in value for value in gap_view['What happens next']))
        self.assertTrue(any('10 hours exceeds the six-hour limit' in value for value in gap_view['What happens next']))
        self.assertFalse(any('missing or excluded runs' in x.value for x in at.markdown))
        self.assertFalse(at.exception)

    def test_method_comparison_shows_errors_and_counts_once(self):
        at=synthetic()
        find(at.button,'Check the record →').click().run()
        find(at.button,'Test the methods →').click().run()
        find(at.button,'Run method tests').click().run(timeout=30)
        scored=at.session_state['oxygen_evaluation'].results
        scored=scored.loc[scored.status.eq('evaluated')]
        comparison=at.dataframe[0].value
        self.assertEqual(len(comparison),len(scored))
        self.assertEqual(int(comparison['Known readings tested'].sum()),int(scored.test_points.sum()))
        self.assertEqual(int(comparison['Tests'].sum()),int(scored.test_blocks.sum()))
        for row in scored.itertuples():
            shown=comparison.loc[(comparison.Method==('Median' if row.method=='Training median' else row.method)) &
                                 comparison['Gap length'].str.startswith(f'{row.samples} h')]
            self.assertEqual(len(shown),1)
            np.testing.assert_allclose(float(shown['MAE (mg/L)'].iloc[0]),row.point_mae_mg_L)
        self.assertTrue(any('Random forest was not tested' in x.value for x in at.markdown))
        self.assertFalse(at.exception)

    def test_method_choice_focus_and_gap_counts(self):
        at=synthetic()
        evaluate_ui(at)
        self.assertEqual(find(at.selectbox,'Method to apply').value,'Choose a method…')
        self.assertFalse(any(x.label=='Gaps to fill' for x in at.multiselect))
        choose_method(at,'Linear interpolation')
        p=at.session_state['oxygen_prepared']
        ev=at.session_state['oxygen_evaluation']
        from oxygen_workflow import eligibility
        gaps=eligibility(p,ev,'Linear interpolation')
        self.assertTrue(any(f'**{int(gaps.eligible.sum())} gaps can be selected; {int((~gaps.eligible).sum())} will stay missing**' in x.value for x in at.markdown))
        self.assertEqual(len(at.dataframe[0].value),int((~gaps.eligible).sum()))
        self.assertEqual(find(at.multiselect,'Gaps to fill').value,[])
        self.assertEqual(len(find(at.multiselect,'Gaps to fill').options),int(gaps.eligible.sum()))
        self.assertTrue(any('Random forest is unavailable because' in x.value for x in at.get('caption')))
        self.assertFalse(at.exception)

    @unittest.skipUnless((ROOT/'input'/'Water quality & dissolved carbon in LA salt marsh.csv').exists(),'Public input is optional')
    def test_public_segment_ui(self):
        source=pd.read_csv(ROOT/'input'/'Water quality & dissolved carbon in LA salt marsh.csv')
        dates=pd.to_datetime(source.Timestamp_UTCminus6,format='mixed')
        segment=source.loc[dates>=pd.Timestamp('2023-07-01')].to_csv(index=False).encode()
        at=AppTest.from_file(str(ROOT/'app.py')).run(timeout=30)
        at.session_state['uploaded_bytes']=segment
        find(at.radio,'Pages').set_value('Process New Data').run()
        find(at.selectbox,'Dissolved oxygen units *').set_value('mg/L').run()
        find(at.checkbox,'I reviewed these source checks. *').check().run()
        evaluate_ui(at)
        self.assertFalse(at.exception)
        self.assertFalse(at.error)
        choose_method(at,'Linear interpolation')
        find(at.multiselect,'Gaps to fill').set_value([1,2]).run()
        find(at.button,'Review selected gaps →').click().run(timeout=30)
        self.assertTrue(any('<strong>4</strong> values to reconstruct' in x.value for x in at.markdown))
        find(at.selectbox,'Gap to preview').set_value(2).run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state['oxygen_choice'][0],'Linear interpolation')
        self.assertTrue(any(x.proto.label=='Download separate processed CSV' for x in at.get('download_button')))

    @unittest.skipUnless((ROOT/'input'/'Water quality & dissolved carbon in LA salt marsh.csv').exists(),'Public input is optional')
    def test_original_csv_rejected_without_shifting_or_filling(self):
        original=(ROOT/'input'/'Water quality & dissolved carbon in LA salt marsh.csv').read_bytes()
        with patch('streamlit.file_uploader',return_value=BytesIO(original)):
            at=AppTest.from_file(str(ROOT/'app.py')).run(timeout=30)
            find(at.radio,'Pages').set_value('Process New Data').run()
            find(at.selectbox,'Dissolved oxygen units *').set_value('mg/L').run()
            find(at.checkbox,'I reviewed these source checks. *').check().run()
            self.assertTrue(any('Irregular timestamps' in e.value for e in at.error))
            self.assertFalse(any(x.label=='Method to apply' for x in at.selectbox))
            self.assertFalse(any(x.proto.label=='Download separate processed CSV' for x in at.get('download_button')))
            self.assertFalse(at.exception)

    def test_back_navigation_page_switch_and_method_change(self):
        at=synthetic()
        evaluate_ui(at)
        choose_method(at,'Linear interpolation')
        find(at.multiselect,'Gaps to fill').set_value([2]).run()
        find(at.button,'Review selected gaps →').click().run(timeout=30)
        find(at.radio,'Pages').set_value('Case Study Overview').run()
        find(at.radio,'Pages').set_value('Process New Data').run()
        self.assertEqual(at.session_state['oxygen_stage'],5)
        self.assertTrue(any(x.proto.label=='Download separate processed CSV' for x in at.get('download_button')))
        find(at.button,'← Back to choose gaps').click().run()
        self.assertEqual(find(at.multiselect,'Gaps to fill').value,[2])
        find(at.selectbox,'Method to apply').set_value('Training median').run()
        self.assertFalse(any(x.label=='Gaps to fill' for x in at.multiselect))
        self.assertTrue(any(x.label=='Choose gaps →' for x in at.button))
        self.assertFalse(any(x.label=='Review selected gaps →' for x in at.button))
        self.assertFalse(at.exception)

    def test_case_study_duration_counts_and_ties(self):
        at=AppTest.from_file(str(ROOT/'app.py')).run(timeout=30)
        self.assertFalse(at.exception)
        result_table=next(x.value for x in at.dataframe if 'Repeated tests' in x.value)
        self.assertTrue(result_table['Repeated tests'].eq(2260).all())
        saved=pd.read_csv(ROOT/'summary.csv').query('gap_hours == 6')
        for row in saved.itertuples():
            label={'Training median':'Median','Unfilled':'Leave missing'}.get(row.method,row.method)
            shown=result_table.loc[result_table.Method.eq(label)]
            self.assertEqual(len(shown),1)
            np.testing.assert_allclose(float(shown['Daily mean MAE (mg/L)'].iloc[0]),row.daily_mean_mae)
        find(at.radio,'Simulated gap length').set_value(1).run()
        result_table=next(x.value for x in at.dataframe if 'Repeated tests' in x.value)
        self.assertTrue(result_table['Repeated tests'].eq(2260).all())
        self.assertTrue(any('(tie)' in x.value for x in at.markdown))
        self.assertFalse(at.exception)


if __name__=='__main__':
    unittest.main()
