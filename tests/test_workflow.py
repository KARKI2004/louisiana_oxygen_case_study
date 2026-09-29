import copy
from io import BytesIO
from pathlib import Path
import unittest
import numpy as np
import pandas as pd

from oxygen_workflow import (PREDICTORS, METHODS, read_csv, prepare, evaluate, predict_blocks,
                             eligibility, export_fills, to_csv_bytes, make_forest)

ROOT=Path(__file__).resolve().parents[1]


def fixture(rf=True):
    raw=read_csv((ROOT/'examples/compatible.csv').read_bytes())
    return raw, prepare(raw,'timestamp','DO',60,flag_col='quality',accepted_flags=['good'],
                        predictor_map={c:c for c in PREDICTORS},rf_confirmed=rf)


class WorkflowTests(unittest.TestCase):
    def test_export_preserves_observed_decimal_precision(self):
        raw,_=fixture()
        literals=['3.1234567890123456789', ' 2.000000000000000001 ', '1.234567890123456789e-2']
        raw.loc[20:22,'DO']=literals
        p=prepare(raw,'timestamp','DO',60)
        ev=evaluate(p)
        gaps=eligibility(p,ev,'Linear interpolation')
        output=export_fills(p,ev,'Linear interpolation',gaps.loc[gaps.eligible,'gap_id'])
        before=output.copy(deep=True)
        exported=pd.read_csv(BytesIO(to_csv_bytes(output)),dtype=str,keep_default_na=False)
        self.assertEqual(exported.loc[20:22,'oxy_original_DO'].tolist(),literals)
        self.assertEqual(exported.loc[20:22,'oxy_processed_DO_mg_L'].tolist(),[s.strip() for s in literals])
        pd.testing.assert_frame_equal(output,before)

    def test_csv_rejects_ragged_records_and_preserves_cell_text(self):
        for content in [b't,DO\na,2,unexpected\nb,3,extra\nc,4,extra',
                        b't,DO\na,2\n\nb,3\nc,4', b't,t\na,2\nb,3\nc,4']:
            with self.assertRaises(ValueError):
                read_csv(content)
        text=b't,DO,note\na,2,"two\nlines"\nb,3,"a,b"\nc,4,NA'
        raw=read_csv(text)
        self.assertEqual(raw.loc[0,'note'],'two\nlines')
        self.assertEqual(raw.loc[1,'note'],'a,b')
        self.assertEqual(raw.loc[2,'note'],'NA')
        raw,_=fixture()
        raw.loc[20,'DO']='1,2'
        p=prepare(raw,'timestamp','DO',60)
        self.assertEqual(p.status.iloc[20],'excluded_invalid_DO')

    def test_end_to_end_each_method_and_csv_provenance(self):
        raw,p=fixture()
        ev=evaluate(p)
        self.assertTrue((ev.results.status=='evaluated').all())
        self.assertEqual(set(p.gaps.samples),{1,2,3,10})
        for method in METHODS:
            gaps=eligibility(p,ev,method)
            selected=gaps.loc[gaps.eligible,'gap_id'].tolist()
            output=export_fills(p,ev,method,selected)
            exported=pd.read_csv(BytesIO(to_csv_bytes(output)),dtype=str,keep_default_na=False)
            existing=exported.oxy_source_row.ne('')
            source_rows=exported.loc[existing,'oxy_source_row'].astype(float).astype(int).to_numpy()-1
            pd.testing.assert_frame_equal(exported.loc[existing,raw.columns].reset_index(drop=True),raw.iloc[source_rows].reset_index(drop=True))
            observed=p.y.notna().to_numpy()
            np.testing.assert_array_equal(output.loc[observed,'oxy_processed_DO_mg_L'],p.y.loc[p.y.notna()])
            filled=output.oxy_is_reconstructed
            self.assertTrue(output.loc[filled,'oxy_method'].eq(method).all())
            self.assertTrue(output.loc[~filled,'oxy_method'].eq('').all())
            self.assertTrue(output.loc[filled,'oxy_original_status'].isin(['missing_blank','missing_timestamp']).all())
            self.assertEqual(filled.sum(),gaps.loc[gaps.eligible,'samples'].sum())
            self.assertEqual(output.loc[output.oxy_processed_DO_mg_L.isna(),'oxy_unfilled_reason'].eq('').sum(),0)
            # Boundary and long gap remain missing regardless of method.
            self.assertTrue(output.iloc[:2].oxy_processed_DO_mg_L.isna().all())
            self.assertTrue(output.iloc[250:260].oxy_processed_DO_mg_L.isna().all())
            if method=='Random forest':
                self.assertFalse(gaps.loc[gaps.absent_rows.gt(0),'eligible'].any())

    def test_masked_truth_changes_cannot_change_predictions_or_training(self):
        _,p=fixture()
        ev=evaluate(p)
        for size,blocks in ev.blocks.items():
            q=copy.deepcopy(p)
            for a,b in blocks:
                q.y.iloc[a:b]=999999.0
            for method in METHODS:
                before=predict_blocks(p,method,blocks,ev.cutoff)
                after=predict_blocks(q,method,blocks,ev.cutoff)
                np.testing.assert_array_equal(np.concatenate(before),np.concatenate(after))
        class Spy:
            def fit(self,x,y):
                self.assertions(x,y)
                return self
            def assertions(self,x,y):
                assert (x.index < p.y.index[ev.cutoff]).all()
                assert y.max()<999999
                assert 'DO' not in x.columns
            def predict(self,x):
                return np.zeros(len(x))
        evaluate(p,forest_factory=Spy)

    def test_disjoint_shared_masks_and_counts(self):
        _,p=fixture()
        ev=evaluate(p)
        for size,blocks in ev.blocks.items():
            occupied=set()
            for a,b in blocks:
                window=set(range(a-1,b+1))
                self.assertFalse(occupied & window)
                occupied.update(window)
                self.assertGreater(a,ev.cutoff)
                self.assertTrue(p.y.iloc[a-1:b+1].notna().all())
            rows=ev.results[ev.results.samples==size]
            self.assertTrue(rows.test_blocks.eq(len(blocks)).all())
            self.assertTrue(rows.test_points.eq(len(blocks)*size).all())

    def test_problematic_irregular_duplicate_and_invalid_time(self):
        bad=read_csv((ROOT/'examples/problematic.csv').read_bytes())
        with self.assertRaisesRegex(ValueError,'Irregular'):
            prepare(bad,'timestamp','DO',60)
        raw,_=fixture()
        for value in [raw.loc[1,'timestamp'],'not a date','']:
            altered=raw.copy();altered.loc[2,'timestamp']=value
            with self.assertRaises(ValueError):
                prepare(altered,'timestamp','DO',60)
        with self.assertRaisesRegex(ValueError,'mg/L'):
            prepare(raw,'timestamp','DO',60,units='percent')

    def test_invalid_values_and_flags_are_not_fill_candidates(self):
        raw,_=fixture()
        raw.loc[30,'DO']='broken';raw.loc[31,'DO']='-2';raw.loc[32,'quality']='reject'
        raw.loc[33,'DO']='inf';raw.loc[34,'DO']='1000'
        p=prepare(raw,'timestamp','DO',60,flag_col='quality',accepted_flags=['good'])
        ev=evaluate(p)
        for method in METHODS[:2]:
            gaps=eligibility(p,ev,method)
            output=export_fills(p,ev,method,gaps.loc[gaps.eligible,'gap_id'])
            self.assertTrue(output.iloc[30:35].oxy_original_status.str.startswith('excluded').all())
            self.assertFalse(output.iloc[30:35].oxy_is_reconstructed.any())
            self.assertTrue(output.iloc[30:35].oxy_processed_DO_mg_L.isna().all())
            self.assertTrue(output.iloc[30:35].oxy_unfilled_reason.str.contains('invalid or quality').all())

    def test_unavailable_and_inadequate_tests_never_authorize_fills(self):
        raw,p=fixture(rf=False)
        ev=evaluate(p)
        self.assertTrue(ev.results.loc[ev.results.method=='Random forest','status'].eq('unavailable').all())
        q=prepare(raw.iloc[:60],'timestamp','DO',60)
        small=evaluate(q)
        self.assertTrue(small.results.status.eq('unavailable').all())
        self.assertTrue(small.results.point_mae_mg_L.isna().all())
        for method in METHODS:
            self.assertFalse(eligibility(q,small,method).eligible.any())
        # Plenty of training but fewer than five complete test windows.
        altered=raw.copy();altered.loc[365:,'DO']=''
        q=prepare(altered,'timestamp','DO',60)
        tiny=evaluate(q)
        self.assertTrue(tiny.results.status.eq('unavailable').all())
        with self.assertRaisesRegex(ValueError,'unsupported'):
            export_fills(p,ev,'Linear interpolation',[999])
        with self.assertRaisesRegex(ValueError,'does not belong'):
            export_fills(q,ev,'Linear interpolation',[])

    def test_missing_test_predictors_disable_forest_on_common_blocks(self):
        raw,p=fixture()
        ev=evaluate(p)
        start=next(iter(ev.blocks.values()))[0][0]
        # Work in the prepared feature table so a known shared test point is invalid.
        p.features.iloc[start,0]=np.nan
        result=evaluate(p)
        size=next(iter(ev.blocks))
        row=result.results[(result.results.method=='Random forest')&(result.results.samples==size)].iloc[0]
        self.assertEqual(row.status,'unavailable')
        self.assertIn('shared test blocks',row.reason)

    def test_fresh_application_forest_trains_only_on_this_upload_observations(self):
        _,p=fixture()
        ev=evaluate(p)
        gaps=eligibility(p,ev,'Random forest')
        ids=gaps.loc[gaps.eligible,'gap_id'].tolist()
        fits=[]
        class Spy:
            def fit(self,x,y):
                fits.append((self,x.copy(),y.copy()))
                return self
            def predict(self,x):
                return np.full(len(x),3.)
        export_fills(p,ev,'Random forest',ids,forest_factory=Spy)
        export_fills(p,ev,'Random forest',ids,forest_factory=Spy)
        self.assertEqual(len(fits),2)
        self.assertIsNot(fits[0][0],fits[1][0])
        expected=p.y.notna() & np.isfinite(p.features).all(axis=1)
        pd.testing.assert_series_equal(fits[0][2],p.y.loc[expected])
        self.assertGreater(fits[0][2].index.max(),p.y.index[ev.cutoff])

    def test_long_run_619_is_never_eligible_even_with_long_record(self):
        raw,_=fixture()
        base=raw.iloc[:1].copy()
        long=pd.concat([base]*1400,ignore_index=True)
        long['timestamp']=pd.date_range('2025-01-01',periods=1400,freq='h').astype(str)
        long['DO']='3.0';long.loc[100:718,'DO']=''
        p=prepare(long,'timestamp','DO',60)
        ev=evaluate(p)
        self.assertEqual(p.gaps.iloc[0].samples,619)
        for method in METHODS:
            g=eligibility(p,ev,method)
            self.assertFalse(g.eligible.any())
            self.assertIn('Exceeds',g.iloc[0].reason)
            with self.assertRaises(ValueError):
                export_fills(p,ev,method,[1])

    def test_six_hour_limit_at_coarse_sampling_and_absent_rows(self):
        raw,_=fixture()
        raw=raw.iloc[:200].copy()
        raw['timestamp']=pd.date_range('2025-01-01',periods=len(raw),freq='2h').astype(str)
        raw['DO']='3';raw.loc[50:53,'DO']=''
        p=prepare(raw,'timestamp','DO',120)
        self.assertEqual(p.max_steps,3)
        self.assertIn('Exceeds',p.gaps.iloc[0].reason)


if __name__=='__main__':
    unittest.main()
