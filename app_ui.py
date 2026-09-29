"""Presentation helpers only. Analysis and eligibility live in oxygen_workflow."""
from html import escape
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
import streamlit as st

COLORS = {'Linear interpolation':'#17766e','Training median':'#aa742b',
          'Random forest':'#7161a7','Unfilled':'#89939a'}


def method_label(name):
    return {'Training median':'Median','Unfilled':'Leave missing'}.get(name,name)


def style():
    st.markdown('''<style>
    .stApp {background:#fbfcfa; color:#223a3d}
    [data-testid="stMainBlockContainer"] {max-width:1180px; padding:2.7rem 3.1rem 5rem}
    [data-testid="stSidebar"] {background:#eef3ef; border-right:1px solid #dce5df}
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {gap:1rem}
    h1 {font-family:Georgia,serif !important; font-weight:400 !important; letter-spacing:-.04em !important; font-size:2.7rem !important; line-height:1.12 !important; color:#183f40}
    h2 {font-size:1.45rem !important; letter-spacing:-.025em; padding-top:.4rem !important}
    h3 {font-size:1.13rem !important; letter-spacing:-.01em}
    p,li {line-height:1.6}
    [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p, [data-testid="stCaptionContainer"] [data-testid="stMarkdownContainer"] p {color:#526966 !important; opacity:1 !important} [data-testid="stSidebar"] [data-testid="stWidgetLabelHelp"] p {color:#526966 !important; opacity:1 !important}
    [data-testid="stTable"] td {white-space:normal; line-height:1.5; padding:.8rem !important}
    [data-testid="stDataFrame"] {border:1px solid #dce5df; border-radius:8px}
    [data-testid="stExpander"] {background:#fff; border-color:#dce5df}
    [data-testid="stMetricValue"] {font-size:1.85rem; color:#185f59}
    .eyebrow {color:#37766e; font-size:.73rem; font-weight:700; letter-spacing:.15em; text-transform:uppercase; margin-bottom:1rem}
    .brand {font-family:Georgia,serif; font-size:1.65rem; line-height:1.25; color:#184f4a; padding:.4rem 0}
    .deck {font-size:1.08rem; color:#52686a; max-width:780px; margin-bottom:1.3rem}
    .facts {display:grid; grid-template-columns:repeat(auto-fit,minmax(145px,1fr)); flex-wrap:wrap; gap:.5rem 1.4rem; border-top:1px solid #dce5df; border-bottom:1px solid #dce5df; padding:1rem 0; margin:.7rem 0 1rem; font-size:.91rem; color:#4b6665}
    .facts span {display:flex; flex-direction:column; background:#f0f5f1; border:1px solid #dce5df; border-radius:7px; padding:1.1rem; line-height:1.45} .facts strong {color:#254c4b; font-family:Georgia,serif; font-size:1.9rem; font-weight:400; margin-bottom:.3rem}
    .finding {border-left:3px solid #17766e; padding:.6rem 1rem; margin:.5rem 0 1rem; background:#eef5f0; font-size:1rem; line-height:1.65}
    .steps {display:flex; flex-wrap:wrap; gap:.7rem 1.25rem; padding:.9rem 0 1.3rem; border-bottom:1px solid #dce5df; color:#526d6b; font-size:.84rem}
    .steps .current {color:#145c55; font-weight:700; border-bottom:3px solid #17766e; padding-bottom:.65rem} .steps .complete {color:#386c63} .steps .upcoming {color:#758581} .steps .arrow {color:#a3b3ac} .steps {align-items:baseline; gap:.55rem; font-size:.78rem; margin-bottom:1rem} [data-testid=stSidebar] [role=radiogroup] label {padding:.8rem .4rem; border-bottom:1px solid #dce5df}
    .section-label {font-size:.7rem; font-weight:700; letter-spacing:.12em; text-transform:uppercase; color:#528079; margin-top:1.4rem}
    .pending {padding:1rem 0; color:#526d6b; font-size:.95rem}
    [data-testid="stSidebar"] [role="radiogroup"] {gap:.65rem}
    @media(max-width:800px) {[data-testid="stMainBlockContainer"]{padding:2rem 1.2rem} h1{font-size:2.1rem !important}}
    </style>''', unsafe_allow_html=True)


def hero(kicker,title,description):
    st.markdown(f'<div class="eyebrow">{escape(kicker)}</div>',unsafe_allow_html=True)
    st.title(title)
    st.markdown(f'<div class="deck">{escape(description)}</div>',unsafe_allow_html=True)


def facts(items):
    st.markdown('<div class="facts">'+''.join(f'<span><strong>{escape(str(a))}</strong> {escape(b)}</span>' for a,b in items)+'</div>',unsafe_allow_html=True)


def section(number,title,description=None):
    st.markdown(f'<div class="section-label">{escape(str(number))}</div>',unsafe_allow_html=True)
    st.header(title)
    if description:
        st.write(description)


def table(frame, formats=None):
    st.dataframe(frame,hide_index=True,width='stretch',
                 column_config={c:st.column_config.NumberColumn(c,format=f) for c,f in (formats or {}).items()})


def choice_gap_reason(gap):
    reason=gap.reason
    if reason.startswith('Boundary'):
        return 'No earlier reading before the gap' if gap.start_pos==0 else 'No later reading after the gap'
    if reason.startswith('Exceeds'):
        return (f'A {gap.hours:g}-hour gap exceeds the 6-hour limit' if gap.hours>6
                else f'{gap.samples} readings exceed the 6-reading limit')
    if reason.startswith('Contains'):
        return 'Includes a reading excluded by the quality checks'
    if reason.startswith('This method'):
        return f'Not enough successful tests for a {gap.hours:g}-hour gap'
    if reason.startswith('Required predictors'):
        return 'Other sensor readings needed by random forest are missing here'
    return reason or 'Can be selected'


def choice_gap_view(gaps, detailed=False):
    rows=[]
    for gap in gaps.itertuples():
        row={'Gap':gap.gap_id,'Starts':gap.start,
             'Length':f"{gap.hours:g} h · {gap.samples} reading{'' if gap.samples==1 else 's'}"}
        if detailed:
            row.update({'Ends':gap.end,'Blank readings':gap.blank_rows,
                        'Absent timestamps':gap.absent_rows,'Excluded readings':gap.excluded_rows,
                        'Status':'Can be selected' if gap.eligible else 'Stays missing'})
        else:
            row['Reason']=choice_gap_reason(gap)
        rows.append(row)
    return pd.DataFrame(rows)


def audit_gap_view(gaps):
    """Plain-language Stage 2 view of the unchanged gap audit."""
    rows=[]
    for gap in gaps.itertuples():
        missing=[]
        for count, name in ((gap.blank_rows,'blank reading'),
                            (gap.absent_rows,'absent timestamp'),
                            (gap.excluded_rows,'excluded reading')):
            if count:
                missing.append(f"{count} {name}{'' if count==1 else 's'}")
        if not gap.reason:
            next_step='Can proceed to testing'
        elif gap.reason.startswith('Boundary'):
            side='start' if gap.start_pos==0 else 'end'
            next_step=f'Cannot fill: at the {side} of the record'
        elif gap.reason.startswith('Exceeds'):
            limit='six-hour' if gap.hours>6 else 'six-reading'
            next_step=f'Cannot fill: {gap.hours:g} hours exceeds the {limit} limit' if gap.hours>6 else f'Cannot fill: {gap.samples} readings exceeds the {limit} limit'
        elif gap.reason.startswith('Contains'):
            next_step='Cannot fill: contains excluded readings'
        else:
            next_step=f'Cannot fill: {gap.reason}'
        rows.append({'When gap starts':gap.start,'Length':f"{gap.hours:g} h · {gap.samples} reading{'' if gap.samples==1 else 's'}",
                     'What is missing':', '.join(missing),'What happens next':next_step})
    return pd.DataFrame(rows,columns=['When gap starts','Length','What is missing','What happens next'])


def axes_style(ax):
    ax.set_facecolor('#fbfcfa')
    ax.spines[['top','right','left']].set_visible(False)
    ax.spines['bottom'].set_color('#cbd7d0')
    ax.grid(axis='y',color='#dfe7e1',linewidth=.65)
    ax.set_axisbelow(True)
    ax.tick_params(axis='both',length=0,labelsize=10,pad=8,colors='#405c5d')
    ax.yaxis.label.set_color('#405c5d')
    ax.xaxis.label.set_color('#405c5d')


def comparison_plot(results, metric, ylabel, x='gap_hours'):
    fig,ax=plt.subplots(figsize=(10,3.5),layout='constrained')
    fig.patch.set_facecolor('#fbfcfa')
    plotted=[]
    has_ties=False
    for name in ['Unfilled','Training median','Linear interpolation','Random forest']:
        rows=results[results.method.eq(name)].sort_values(x)
        if rows.empty or rows[metric].notna().sum()==0:
            continue
        coordinates=(rows[x].to_numpy(),rows[metric].to_numpy())
        match=next((line for line in plotted
                    if np.array_equal(line['x'],coordinates[0])
                    and np.array_equal(line['y'],coordinates[1],equal_nan=True)),None)
        if match is not None:
            match['names'].append(method_label(name))
            has_ties=True
        else:
            plotted.append({'x':coordinates[0],'y':coordinates[1],
                            'names':[method_label(name)],
                            'color':COLORS[name]})
    for line in plotted:
        ax.plot(line['x'],line['y'],marker='o',markersize=6,linewidth=2,
                label=' = '.join(line['names']),color=line['color'])
    ax.set(xticks=sorted(results[x].unique()),xlabel='Hidden gap duration (hours)',ylabel=ylabel)
    ax.set_ylim(bottom=0)
    axes_style(ax)
    ax.legend(loc='upper left',bbox_to_anchor=(0,1.2),ncol=4,frameon=False,fontsize=9)
    st.pyplot(fig);plt.close(fig)
    return has_ties


def preview_plot(p, output, gap):
    left=max(0,int(gap.start_pos)-12);right=min(len(p.y),int(gap.stop_pos)+12)
    idx=p.y.index[left:right]
    fig,ax=plt.subplots(figsize=(10,3.7),layout='constrained')
    fig.patch.set_facecolor('#fbfcfa')
    ax.axvspan(p.y.index[int(gap.start_pos)]-p.step/2,
               p.y.index[int(gap.stop_pos)-1]+p.step/2,color='#f2e9d6',alpha=.75,label='Selected gap')
    ax.plot(idx,p.y.iloc[left:right],'.-',label='Observed oxygen',color='#17766e',linewidth=1.6,markersize=6)
    shown=output.iloc[left:right]
    filled=shown.oxy_is_reconstructed.to_numpy()
    ax.scatter(idx[filled],shown.oxy_processed_DO_mg_L.to_numpy()[filled],marker='X',s=65,
               color='#b4612d',zorder=4,label='Reconstructed estimate')
    locator=mdates.AutoDateLocator(minticks=4,maxticks=7)
    ax.xaxis.set_major_locator(locator);ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
    ax.set_ylabel('Dissolved oxygen (mg/L)');axes_style(ax)
    ax.legend(loc='upper left',bbox_to_anchor=(0,1.18),ncol=3,frameon=False,fontsize=9)
    st.pyplot(fig);plt.close(fig)


def source_audit(raw):
    """Describe recorded blanks and timing jumps without regularizing the source."""
    times=pd.to_datetime(raw.Timestamp_UTCminus6,format='mixed')
    d=raw.assign(time=times).sort_values('time').reset_index(drop=True)
    missing=d.DO.str.strip().str.lower().isin(['','na','nan','null','n/a'])
    groups=missing.ne(missing.shift()).cumsum()
    runs=[]
    for _,g in d.loc[missing].groupby(groups[missing]):
        runs.append({'First blank timestamp':g.time.iloc[0],'Last blank timestamp':g.time.iloc[-1],
                     'Blank rows':len(g),'Interpretation':'Not validated for filling' if len(g)>6 else 'Recorded blank run; not a test result'})
    delta=d.time.diff()
    jumps=[]
    for i in np.flatnonzero((delta.notna() & delta.ne(pd.Timedelta(hours=1))).to_numpy()):
        elapsed=delta.iloc[i]
        aligned=elapsed.value % pd.Timedelta(hours=1).value==0
        jumps.append({'Previous timestamp':d.time.iloc[i-1],'Next timestamp':d.time.iloc[i],
                      'Elapsed time':str(elapsed),'Interpretation':'Absent hourly rows' if aligned else 'Sampling offset change; do not snap to an hourly grid'})
    return pd.DataFrame(runs),pd.DataFrame(jumps)
