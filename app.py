"""Research interface; original analysis and upload calculations stay separate."""
from pathlib import Path
import hashlib
import json
from html import escape
import pandas as pd
import streamlit as st

from oxygen_workflow import (PREDICTORS, METHODS, read_csv, suggested_minutes, prepare,
                             evaluate, eligibility, export_fills, to_csv_bytes)
from app_ui import style, hero, facts, section, table, audit_gap_view, choice_gap_view, comparison_plot, preview_plot, source_audit, method_label

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'input'/'Water quality & dissolved carbon in LA salt marsh.csv'
CASE='Case Study Overview'
PROCESS='Process New Data'
st.set_page_config(page_title='Louisiana Oxygen Readings',layout='wide',initial_sidebar_state='expanded')
style()
# Preserve explicit widget values while their stage is not rendered.
for key in list(st.session_state):
    if key.startswith(('control_', 'units_', 'quality_', 'interval_', 'predictor_confirmation_', 'method_', 'gaps_', 'duration_')):
        st.session_state[key] = st.session_state[key]
with st.sidebar:
    st.markdown('<div class="brand">Louisiana<br>Oxygen Readings</div>',unsafe_allow_html=True)
    page=st.radio('Pages',[CASE,PROCESS],label_visibility='collapsed',captions=[
        'Read the Wilkinson Bayou study','Upload and evaluate a monitoring CSV'])


def control(kind, label, *args, **kwargs):
    key=kwargs.setdefault('key', 'control_'+label)
    # Session-state values are kept when a widget is temporarily hidden on a
    # later stage. Avoid also passing its original default on reruns.
    if key in st.session_state:
        kwargs.pop('index',None)
        kwargs.pop('value',None)
    kwargs.setdefault('on_change', invalidate)
    return getattr(kwargs.pop('target',st), kind)(label, *args, **kwargs)


def move(stage):
    st.session_state['oxygen_stage']=stage
    st.rerun()


def invalidate():
    for key in list(st.session_state):
        if key in ('oxygen_evaluation','oxygen_prepared','oxygen_output','oxygen_choice') or key.startswith(('method_','gaps_','gap_picker_')):
            del st.session_state[key]


def reset_source_review(confirmation_key):
    invalidate()
    st.session_state[confirmation_key]=False


def case_study():
    hero('', 'What happens when oxygen readings go missing?',
         'A case study of missing hourly measurements in Wilkinson Bayou, Louisiana, using public USGS observations.')
    audit=json.loads((ROOT/'audit.json').read_text())
    results=pd.read_csv(ROOT/'summary.csv')
    st.write('Continuous oxygen sensors record conditions between field visits, but outages leave parts of a day unknown. '
             'A missing interval may cover the lowest oxygen readings or hours spent below a threshold. '
             'Filling those hours can make a record easier to analyze, but the estimates can also change what a daily summary tells us.')
    a,b=st.columns([1.3,1],gap='large')
    with a:
        st.markdown('### The research question')
        st.write('How well do common ways of handling missing readings preserve the daily average, the daily minimum, '
                 'and approximate time below 2 mg/L? To measure the difference, this study hid readings that were already known, '
                 'estimated them, and compared the resulting summaries with the complete day.')
    with b:
        st.markdown('### The public source')
        st.write('The public record contains fixed mid-depth measurements from Wilkinson Bayou, June 16, 2022–October 24, 2023. '
                 'USGS describes processing for sensor fouling, drift, and quality checks. These are the reference observations for the experiment.')
        st.markdown('[USGS data release ↗](https://doi.org/10.5066/P13GBADQ)')
    facts([(f"{audit['source_rows']:,}",'Timestamped source rows'),(f"{audit['observed_do_rows']:,}",'Recorded oxygen values'),
           (f"{audit['complete_test_days']:,}",'Complete test days')])
    section('01 / Data coverage','Gaps and missing values in the source')
    st.write(f"The source has **{audit['source_rows']-audit['observed_do_rows']:,} rows with blank oxygen readings**. "
             'That count does not include hours with no row in the file. The experiment used complete days with known readings for its tests.')
    if SOURCE.exists():
        try:
            raw=read_csv(SOURCE.read_bytes())
            if hashlib.sha256(SOURCE.read_bytes()).hexdigest()!=audit['source_sha256']:
                st.warning('The local source differs from the saved audit. The original results below have not been recomputed.')
            runs,jumps=source_audit(raw)
            st.write(f"**{int(runs['Blank rows'].max()):,} blank readings occur together in one stretch.** "
                     'Because the tests cover only 1-, 3-, and 6-hour gaps, they cannot establish how that long stretch should be filled.')
            with st.expander('Source gaps and timing details'):
                st.write(f'{len(runs)} stretches of blank rows and {len(jumps)} departures from hourly timestamp spacing were recorded. Some spacing changes reflect missing rows; others reflect a change in recording time. No timestamps were moved.')
                table(runs);table(jumps)
        except ValueError as exc:
            st.warning(f'Local source audit unavailable: {exc}')
    else:
        st.info('Download the original source into input/ to inspect its blank runs. Saved case-study results remain available below.')
    with st.expander('Oxygen conditions across the recorded period'):
        st.write('Daily averages and recorded ranges show how oxygen varied over time. Breaks indicate periods without usable readings.')
        st.image(str(ROOT/'data_context.png'),width='stretch')
    section('02 / Controlled validation','What was tested')
    st.write('The study compared leaving a gap missing, median, linear interpolation, and random forest. '
             'Methods learned from observations before July 1, 2023, then were tested on 113 complete days after that date. '
             'The study temporarily removed **1, 3, or 6 consecutive hours** of known readings, repeating each duration 20 times per day.')
    with st.expander('How the four methods work'):
        st.table(pd.DataFrame([
            ['Leave missing','Summarize the readings that remain; make no estimate.'],
            ['Median','Use the middle value of earlier oxygen readings.'],
            ['Linear interpolation','Connect the known oxygen readings on both sides of a gap.'],
            ['Random forest','Use temperature, salinity, pH, turbidity, and time to estimate oxygen.'],
        ],columns=['Method','Information used']),hide_index=True)
    section('03 / Saved experiment results','Compare results by gap length')
    st.write('Mean absolute error (MAE) is the average size of the difference from the recorded value. Lower is closer. The table compares daily summaries; the chart below shows how one error changes as gaps get longer.')
    duration=st.radio('Simulated gap length',[1,3,6],index=2,horizontal=True,format_func=lambda n:f'{n}-hour gap')
    shown=results.loc[results.gap_hours.eq(duration)].copy()
    count=int(shown.trials.iloc[0])
    view=shown[['method','trials','daily_mean_mae','daily_minimum_mae','low_hours_mae']].rename(columns={
        'method':'Method','trials':'Repeated tests','daily_mean_mae':'Daily mean MAE (mg/L)',
        'daily_minimum_mae':'Daily minimum MAE (mg/L)','low_hours_mae':'Low-hours MAE (h/day)'})
    view['Method']=view.Method.map(method_label)
    st.subheader(f'Daily-summary errors after {duration}-hour gaps')
    table(view,{c:'%.3f' for c in view if 'MAE' in c})
    st.caption(f'{count:,} repeated tests per method at this gap length, drawn from 113 days. Some tests overlap; these are not separate field outages or confidence intervals.')
    def lowest(column):
        names=shown.loc[shown[column].eq(shown[column].min()),'method'].map(method_label).str.lower()
        return escape(', '.join(names)) + (' (tie)' if len(names)>1 else '')
    st.write(f'Lowest errors at {duration} hours: daily mean — {lowest("daily_mean_mae")}; '
             f'daily minimum — {lowest("daily_minimum_mae")}; low-oxygen time — {lowest("low_hours_mae")}.' )
    st.subheader('How error changes as gaps get longer')
    st.write('In these tests, errors rose as the hidden gap grew from one to six hours. How much they rose depended on the method and the daily summary.')
    metric=st.selectbox('Chart measure',['Daily mean error','Daily minimum error','Low-oxygen time error'])
    key,label={'Daily mean error':('daily_mean_mae','Daily mean MAE (mg/L)'),
               'Daily minimum error':('daily_minimum_mae','Daily minimum MAE (mg/L)'),
               'Low-oxygen time error':('low_hours_mae','Low-hours MAE (hours/day)')}[metric]
    comparison_plot(results,key,label)
    st.caption('Each point represents 2,260 repeated tests per method at that gap length; tests come from the same 113 days.')
    with st.expander('All saved metrics and low-day counts'):
        table(results.assign(method=results.method.map(method_label)))
        st.caption('Negative low-hours bias means undercounting. Low-day counts repeat the same days across masks; '
                   'the 1,800 low-day trials represent 90 days repeated 20 times. Unfilled point MAE is undefined.')
        labeled_results=results.assign(method=results.method.map(method_label))
        st.download_button('Download results CSV',labeled_results.to_csv(index=False).encode(),'case_study_summary.csv','text/csv')
    section('04 / Implications for monitoring','What a monitoring team could take from this')
    st.write('The method with the smallest error depends on which daily summary matters. A monitoring team can use the same kind of test on its own record before deciding how to handle missing readings.')
    st.write('For a team such as the Lake Maurepas Monitoring Project, this provides a way to test gap-handling choices against its own known observations before reconstructing missing data. The observations here are from Wilkinson Bayou, not Lake Maurepas; local sampling, seasons, and sensor availability would need their own evaluation.')
    st.subheader('Limits of this study')
    st.write('These errors come from temporarily removing known readings on complete days in one test period. They may differ during real outages. Multi-day outages, boundary gaps, and simultaneous sensor failures were not tested.')
    st.write('The exploratory **2 mg/L** threshold counts hourly readings, not continuous exposure. It is not a site-specific '
             'regulatory standard or evidence of biological harm. Source observations are reference values, not independently verified truth.')
    st.caption('The original experiment did not fill genuine gaps.')
    st.download_button('Download original research brief',(ROOT/'Louisiana_Oxygen_Gap_Case_Study.pdf').read_bytes(),
                       'Louisiana_Oxygen_Gap_Case_Study.pdf','application/pdf')


STAGES=['Upload a file','Check the record','Test the methods','Choose gaps','Review and download']


def workflow():
    hero('Monitoring data','Process New Data',
         'Upload a dissolved-oxygen CSV to check its timestamps and missing readings. This page tests filling methods against known readings in your file, shows their errors, and lets you choose which eligible gaps to fill. You can then preview the changes and download a separate CSV that labels every estimate.')
    stage=st.session_state.get('oxygen_stage',1)
    st.markdown('<nav class="steps" aria-label="Processing stages">'+
        '<span class="arrow">→</span>'.join(f'<span class="{"current" if i==stage else "complete" if i<stage else "upcoming"}" '+
        ('aria-current="step"' if i==stage else '')+f'>{escape(name)}</span>' for i,name in enumerate(STAGES,1))+'</nav>',unsafe_allow_html=True)
    if stage>1:
        if st.button('← Back to '+STAGES[stage-2].lower()):
            move(stage-1)
    if stage==1:
        section('Stage 1 of 5','Upload a file and identify its columns')
        input_stage()
        return
    p=st.session_state.get('oxygen_prepared')
    if p is None:
        move(1)
    if stage==2:
        audit_stage(p)
    elif stage==3:
        evaluation_stage(p)
    else:
        ev=st.session_state.get('oxygen_evaluation')
        if ev is None or ev.fingerprint!=p.fingerprint:
            move(3)
        if stage==4:
            choose_stage(p,ev)
        else:
            review_stage(p,ev)


def input_stage():
    upload=st.file_uploader('Dissolved oxygen CSV',type=['csv'],help='UTF-8 CSV, unique column names, maximum 10 MB.')
    if upload is not None:
        st.session_state['uploaded_bytes']=upload.getvalue()
    data=st.session_state.get('uploaded_bytes')
    if upload is None and data is not None:
        st.caption('Using the file already uploaded in this session. Upload another CSV to replace it.')
    with st.expander('Try an example dataset'):
        st.caption('Download this synthetic monitoring record, then upload the CSV above. It contains invented readings and several kinds of gaps.')
        st.download_button('Download synthetic CSV',
                           (ROOT/'examples'/'compatible.csv').read_bytes(),
                           'oxygen_synthetic_example.csv','text/csv')
        st.caption('[Open the same example in Google Sheets](https://docs.google.com/spreadsheets/d/1FjAOMsvJLyI15ajZxg2zrHWyXPIqfyMgsrKPijchWAA/edit?gid=1921450387#gid=1921450387).')
    with st.expander('Input format and limits'):
        st.markdown('''- **mg/L only**, one series, 1–360 minute sampling interval, up to 100,000 grid rows. Use unambiguous ISO dates in one timezone or fixed local time.
- No timestamp shifts, rounding, or automatic duplicate removal. Blank, `NA`, `NaN`, `null`, and `N/A` readings mean missing.
- Invalid, nonfinite, negative, above-bound, or quality-rejected readings remain excluded. Their original cells are retained.
- Only interior gaps of **at most six samples and six hours** can qualify, and only after testing their exact duration. This limit does not establish scientific validity.
- Combine multiple source quality flags into one acceptance flag before upload. Independent predictor measurements are required for a forest.''')
    if data is None:
        return
    input_key=hashlib.sha256(data).hexdigest()
    if input_key!=st.session_state.get('input_key'):
        invalidate()
        for key in list(st.session_state):
            if key.startswith('control_'):
                del st.session_state[key]
        st.session_state['input_key']=input_key
    try:
        raw=read_csv(data)
    except ValueError as exc:
        st.error(str(exc));return
    st.caption(f'{len(raw):,} original rows · {len(raw.columns)} columns · Original values retained in the export')
    with st.expander('Preview source rows'):
        table(raw.head(8))
    columns=raw.columns.tolist()
    default_time='Timestamp_UTCminus6' if 'Timestamp_UTCminus6' in columns else columns[0]
    default_do='DO' if 'DO' in columns else columns[min(1,len(columns)-1)]
    with st.container(border=True):
        st.subheader('Identify the measurements')
        a,b=st.columns(2,gap='medium')
        review_key='quality_'+input_key
        time_col=control('selectbox','Timestamp column',columns,target=a,index=columns.index(default_time),
                         on_change=reset_source_review,args=(review_key,))
        do_col=control('selectbox','Dissolved oxygen column',columns,target=b,index=columns.index(default_do),
                       on_change=reset_source_review,args=(review_key,))
        try:
            proposed=suggested_minutes(raw,time_col)
        except ValueError as exc:
            st.error(str(exc));return
        st.markdown('### Before continuing: complete both required steps')
        st.caption('* Required')
        st.markdown('**1. Confirm the measurement units and sampling interval**')
        a,b=st.columns(2,gap='medium')
        units=control('selectbox','Dissolved oxygen units *',['Confirm units…','mg/L','Other / unknown'],target=a,key='units_'+input_key)
        minutes=control('number_input','Sampling interval (minutes) *',target=b,min_value=1.0,max_value=360.0,
                               value=float(min(360,max(1,proposed))),key=f'interval_{input_key[:12]}_{time_col}',
                               on_change=reset_source_review,args=(review_key,),
                               help=f'Suggested from timestamps: {proposed:g} minutes. Confirm against source information; missing rows can make this estimate misleading.')
        with st.expander('Quality flags and screening limits',expanded=True):
            a,b=st.columns(2,gap='medium')
            flag=control('selectbox','Row quality flag',['No flag column']+columns,target=a,
                         on_change=reset_source_review,args=(review_key,))
            upper=control('number_input','Upper oxygen screening bound (mg/L)',target=b,min_value=2.1,max_value=100.0,value=25.0,
                                  on_change=reset_source_review,args=(review_key,),
                                  help='A configurable exclusion screen, not a universal scientific limit. Values outside 0 to this bound remain unfilled.')
            accepted=[]
            if flag!='No flag column':
                accepted=control('multiselect','Accepted flag values',raw[flag].unique().tolist(),
                                 on_change=reset_source_review,args=(review_key,),
                                 help='Exact matches. Rejected flags exclude oxygen and predictors on that row.')
        st.markdown('**2. Review source checks**')
        st.caption('Verify the sampling interval against source information; review quality flags (or confirm there are none) and the oxygen screening limit above.')
        quality=control('checkbox','I reviewed these source checks. *',key=review_key)
    with st.expander('Optional: enable random forest comparison'):
        st.caption('Four independent sensor measurements are required. No predictor imputation and no shared trained model.')
        rf_enabled=control('checkbox','Include random forest if supported')
        mapping={};confirmed=False
        if rf_enabled:
            cols=st.columns(2)
            for i,name in enumerate(PREDICTORS):
                options=['Not available']+[c for c in columns if c not in (time_col,do_col,flag)]
                col=control('selectbox',f'Predictor: {name}',options,target=cols[i%2],index=options.index(name) if name in options else 0)
                if col!='Not available':mapping[name]=col
            st.caption('Supported predictor ranges: −5–50 °C · 0–50 psu · pH 0–14 · 0–10,000 FNU. '
                       'Out-of-range or missing predictors make affected forest tests or real gaps unavailable.')
            confirmed=control('checkbox','Predictors are independent measurements in the stated units, not derived from oxygen; their quality flags have been applied.',
                                   key='predictor_confirmation_'+input_key)
    signature=repr((input_key,time_col,do_col,units,minutes,flag,upper,accepted,quality,mapping,confirmed))
    if signature!=st.session_state.get('oxygen_settings'):
        invalidate()
        st.session_state['oxygen_settings']=signature
    ready=units=='mg/L' and quality
    if not ready:
        missing=[]
        if units!='mg/L':
            missing.append('select **mg/L** for oxygen units')
        if not quality:
            missing.append('complete **Review source checks**')
        st.info('To continue, '+ ' and '.join(missing)+'.')
        st.button('Check the record →',type='primary',disabled=True,
                  help='Complete both required steps above to review the gap audit.')
        return
    try:
        p=prepare(raw,time_col,do_col,minutes,units=units,upper_do=upper,
                  flag_col=None if flag=='No flag column' else flag,accepted_flags=accepted,
                  predictor_map=mapping,rf_confirmed=confirmed)
    except ValueError as exc:
        st.error(str(exc))
        st.caption('Nothing was filled. Correct the source or upload a compatible regular segment; timestamps are never moved.')
        return
    if st.button('Check the record →',type='primary',help='Open the gap audit for this uploaded file.'):
        st.session_state['oxygen_prepared']=p
        move(2)


def audit_stage(p):
    section('Stage 2 of 5','Gaps found in your file',
            'This review uses the CSV you uploaded and the columns and quality checks you confirmed.')
    excluded=p.status.str.startswith('excluded')
    facts([(int(p.y.notna().sum()),'Usable oxygen readings'),(len(p.gaps),'Gaps found')])
    blank_count=int((p.status=='missing_blank').sum())
    absent_count=int((p.status=='missing_timestamp').sum())
    coverage=[]
    if blank_count:
        coverage.append(f'{blank_count} blank readings (timestamped rows with no oxygen value)')
    if absent_count:
        coverage.append(f'{absent_count} absent timestamp rows (expected times with no row in the file)')
    if excluded.any():
        coverage.append(f'{int(excluded.sum())} excluded readings (kept in the export, but not used for testing or filling)')
    if coverage:
        st.write('Record details: '+ '; '.join(coverage)+'.')
    if excluded.any():
        with st.expander('Excluded rows and reasons'):
            detail=p.raw.loc[excluded].copy();detail['Exclusion reason']=p.status.loc[excluded];table(detail)
    if p.gaps.empty:
        st.info('No gaps were found. You can still test methods on known readings, but there are no missing values to fill.')
    else:
        ready=int(p.gaps.reason.eq('').sum())
        blocked=len(p.gaps)-ready
        st.write(f'**{ready}** can proceed to method testing; **{blocked}** cannot be filled by this tool. '
                 'Testing does not fill a gap: you will compare methods and choose what to apply later.')
        table(audit_gap_view(p.gaps))
    if st.button('Test the methods →',type='primary'):
        move(3)


def evaluation_stage(p):
    section('Stage 3 of 5','Test the methods',
            'Compare estimates with readings already in your file before deciding whether to fill any gaps.')
    if st.button('Run method tests',type='primary'):
        for key in list(st.session_state):
            if key in ('oxygen_output','oxygen_choice') or key.startswith(('method_','gaps_')):
                del st.session_state[key]
        with st.spinner('Testing shared hidden blocks…'):
            st.session_state['oxygen_evaluation']=evaluate(p)
    ev=st.session_state.get('oxygen_evaluation')
    if ev is None or ev.fingerprint!=p.fingerprint:
        st.write('Run the tests to see which methods could be evaluated and how close their estimates came to the recorded values.')
        return
    st.subheader('Errors for the tested gap lengths')
    st.write('Mean absolute error (MAE) is the average size of the difference between an estimate and the recorded oxygen value. Smaller errors mean closer estimates.')
    scored=ev.results.loc[ev.results.status.eq('evaluated')].copy()
    if not scored.empty:
        scored['Gap length']=scored.apply(lambda r:f"{r.samples*p.step.total_seconds()/3600:g} h ({r.samples} reading{'' if r.samples==1 else 's'})",axis=1)
        view=scored[['Gap length','method','test_blocks','test_points','point_mae_mg_L']].rename(columns={
            'method':'Method','test_blocks':'Tests','test_points':'Known readings tested','point_mae_mg_L':'MAE (mg/L)'})
        view['Method']=view['Method'].map(method_label)
        table(view,{'MAE (mg/L)':'%.3f'})
    else:
        st.info('There were not enough suitable known readings to measure an error for this file.')
    forest=ev.results.loc[ev.results.method.eq('Random forest') & ev.results.status.eq('unavailable')]
    if not forest.empty:
        if forest.reason.str.contains('four independently measured predictors|four valid predictors',case=False).all():
            st.write('Random forest was not tested because four independent sensor measurements were not confirmed for this file.')
        else:
            st.write('Random forest could not be tested for every gap length. The data requirements are listed under test details below.')
    if p.gaps.empty or not p.gaps.reason.eq('').any():
        st.write('These tests describe the recorded readings; no gap in this file qualifies for filling.')
    st.caption('These tests temporarily hide recorded readings. Errors during real sensor outages may differ. Nothing is filled or selected at this stage.')
    with st.expander('How the tests were run'):
        st.write('The first 60% of the record supplied training data; the remaining 40% supplied test readings. '
                 'The test needs at least 48 clean training readings and five separate test gaps of each length. '
                 'Up to 40 gaps per length are selected with a fixed seed. If no real gap qualifies, tests of 1, 3, and 6 readings demonstrate performance without permitting a fill.')
        st.write('The methods were tested on the same recorded readings. Interpolation used observations on both sides; '
                 'median and forest fitting used only earlier observations. Forest testing also required four usable sensor measurements.')
        st.caption(f'Training ended before {p.y.index[ev.cutoff].isoformat()} · {ev.training_points} clean training readings · {ev.rf_training_points} with complete forest predictors. Test gaps of different lengths may overlap; results are descriptive, with no confidence intervals.')
    with st.expander('Other measures and test details'):
        st.write('Low-oxygen time counts readings below the exploratory 2 mg/L threshold within each test gap. Negative bias means a method counted too little low-oxygen time.')
        table(ev.results.assign(method=ev.results.method.map(method_label)))
        table(pd.DataFrame([{'Samples':n,'Start':p.y.index[a],'End':p.y.index[b-1],'Test points':b-a}
                            for n,blocks in ev.blocks.items() for a,b in blocks]))
        st.download_button('Download evaluation table',ev.results.assign(method=ev.results.method.map(method_label)).to_csv(index=False).encode(),'oxygen_evaluation.csv','text/csv')
    if st.button('Choose gaps →',type='primary'):
        move(4)


def choose_stage(p,ev):
    section('Stage 4 of 5','Choose a method for your gaps')
    choices={method:eligibility(p,ev,method) for method in METHODS}
    available=[method for method,gaps in choices.items() if not gaps.empty and gaps.eligible.any()]
    with st.container(border=True):
        st.write('You have seen the measured errors. Choose the method you want to consider for this file; nothing is filled yet.')
        method=st.selectbox('Method to apply',['Choose a method…']+available,
                            key='method_'+p.fingerprint,format_func=method_label,disabled=not available)
    if not available:
        st.info('No gaps in this file can be filled by the tested methods. The missing readings stay missing.')
        return
    unavailable=[name for name in METHODS if name not in available]
    if unavailable:
        notes=[]
        for name in unavailable:
            gaps=choices[name]
            if name=='Random forest' and p.rf_reason:
                detail='this file was not confirmed to have the four other sensor measurements it needs'
            elif name=='Random forest' and gaps.reason.str.startswith('Required predictors').any():
                detail='required sensor readings are missing during the gaps'
            else:
                detail='no gap in this file passed its test and data requirements'
            notes.append(f'{method_label(name)} is unavailable because {detail}')
        st.caption('. '.join(notes)+'.')
    if method=='Choose a method…':
        return
    gap_picker_key='gap_picker_'+p.fingerprint
    if st.session_state.get('last_method')!=method:
        for key in list(st.session_state):
            if key.startswith('gaps_'):
                del st.session_state[key]
        st.session_state.pop(gap_picker_key,None)
        st.session_state.pop('oxygen_output',None)
        st.session_state.pop('oxygen_choice',None)
        st.session_state['last_method']=method
    eligible=choices[method]
    rejected=eligible.loc[~eligible.eligible]
    ids=eligible.loc[eligible.eligible,'gap_id'].tolist()
    st.write(f'**{len(ids)} gaps can be selected; {len(rejected)} will stay missing** with {method_label(method).lower()}.')
    if not rejected.empty:
        st.subheader('Gaps that will stay missing')
        table(choice_gap_view(rejected))
    with st.expander('Detailed gap audit for this method'):
        table(choice_gap_view(eligible,detailed=True))
    if st.session_state.get(gap_picker_key)!=method:
        if st.button('Choose gaps →',type='primary'):
            st.session_state[gap_picker_key]=method
            st.rerun()
        return
    st.subheader('Select gaps to reconstruct')
    st.write('The selector below lists only gaps supported by the tests. Choose at least one to preview; your original file stays unchanged.')
    labels={g.gap_id:f"Gap {g.gap_id}: {g.start:%Y-%m-%d %H:%M} · {g.samples} reading{'' if g.samples==1 else 's'} / {g.hours:g} h" for g in eligible.itertuples()}
    selected=st.multiselect('Gaps to fill',ids,format_func=lambda x:labels[x],key='gaps_'+p.fingerprint+method)
    if not selected:
        return
    if st.button('Review selected gaps →',type='primary'):
        with st.spinner('Preparing the selected reconstructions…'):
            st.session_state['oxygen_output']=export_fills(p,ev,method,selected)
        st.session_state['oxygen_choice']=(method,selected)
        move(5)


def review_stage(p,ev):
    method,selected=st.session_state['oxygen_choice']
    output=st.session_state['oxygen_output']
    eligible=eligibility(p,ev,method)
    labels={g.gap_id:f"Gap {g.gap_id}: {g.start:%Y-%m-%d %H:%M} · {g.samples} reading{'' if g.samples==1 else 's'} / {g.hours:g} h" for g in eligible.itertuples()}
    section('Stage 5 of 5','Review and download',f'{method_label(method)} · {len(selected)} selected gaps. Inspect each gap before downloading the separate result.')
    filled=output.oxy_is_reconstructed
    facts([(int(filled.sum()),'values to reconstruct'),(int(output.oxy_processed_DO_mg_L.isna().sum()),'left missing / excluded'),
           (int(p.y.notna().sum()),'observations unchanged')])
    preview_id=st.selectbox('Gap to preview',selected,format_func=lambda x:labels[x],key='preview_'+p.fingerprint+method)
    gap=eligible.loc[eligible.gap_id.eq(preview_id)].iloc[0]
    st.subheader('Measurements and proposed estimates')
    st.caption('Green points are measured oxygen. Orange crosses are reconstructed values within the shaded gap.')
    preview_plot(p,output,gap)
    st.subheader('Before and after: selected gap')
    st.caption('The table includes neighboring measurements as context. Only rows marked Reconstructed contain estimates.')
    positions=list(range(max(0,int(gap.start_pos)-2),min(len(output),int(gap.stop_pos)+2)))
    rows=output.iloc[positions][['oxy_timestamp','oxy_original_DO','oxy_processed_DO_mg_L','oxy_original_status','oxy_is_reconstructed','oxy_method']].copy()
    rows['oxy_original_status']=rows.oxy_original_status.replace({'observed':'Measured','missing_blank':'Blank reading','missing_timestamp':'Absent timestamp','excluded_invalid_DO':'Excluded value','excluded_quality_flag':'Excluded by quality flag'})
    view=rows.head(20).rename(columns={'oxy_timestamp':'Timestamp','oxy_original_DO':'Original DO',
          'oxy_processed_DO_mg_L':'Processed DO (mg/L)','oxy_original_status':'Original status',
          'oxy_is_reconstructed':'Reconstructed','oxy_method':'Method'})
    view['Method']=view['Method'].map(method_label)
    table(view.style.apply(lambda row: ['background-color: #fff0da; color: #613d1f' if row.Reconstructed else '' for _ in row],axis=1),{'Processed DO (mg/L)':'%.4f'})
    st.caption('The download contains the entire record and all selected gaps. Original readings and reconstructed estimates are labeled separately.')
    with st.expander('Gaps remaining missing and their reasons'):
        remaining=output.loc[output.oxy_unfilled_reason.ne(''),['oxy_timestamp','oxy_gap_id','oxy_unfilled_reason']]
        if remaining.empty:
            st.write('No gaps remain missing in this reviewed record.')
        else:
            table(remaining.rename(columns={'oxy_timestamp':'Timestamp','oxy_gap_id':'Gap','oxy_unfilled_reason':'Reason left missing'}))
    if method!='Linear interpolation':
        st.caption('Application fitting uses all eligible observations from this upload. The forest is fitted fresh; '
                   'evaluation used only the earlier training period. This remains retrospective reconstruction.')
    st.subheader('Download the reviewed record')
    st.write('Original columns and values stay intact. Added fields identify the original row status, chosen method, '
             'reconstructed values, and reasons for gaps left missing.')
    labeled_output=output.copy()
    labeled_output['oxy_method']=labeled_output.oxy_method.map(method_label)
    st.download_button('Download separate processed CSV',to_csv_bytes(labeled_output),'oxygen_processed.csv','text/csv',type='primary')
    with st.expander('Export fields and provenance'):
        st.write('`oxy_original_DO` preserves the original cell; `oxy_processed_DO_mg_L` holds the eligible observation '
                 'or estimate. `oxy_is_reconstructed` is true only for fills, with the method in `oxy_method`. '
                 '`oxy_original_status` distinguishes observed, blank, absent, and excluded rows. '
                 '`oxy_unfilled_reason` explains remaining gaps.')
        st.caption('Added timestamp rows have no source row number. Output is timestamp-sorted; input files are never overwritten. '
                   'No upload is pooled with another or used to update a shared model.')


if page==CASE:
    case_study()
else:
    workflow()
